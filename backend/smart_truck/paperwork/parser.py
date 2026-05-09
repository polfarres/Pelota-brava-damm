"""Parse DDIDGP-format ``Hoja Carga`` and ``Hoja Ruta`` PDFs (FR-004).

The PDFs are text-based (not scanned). pdfplumber's auto-table extraction
collapses everything into one column, so we work directly with word-level
positions: extract every word with its bounding box, group words by
y-coordinate (same row), and assign each word to a column based on its
x-coordinate. Column boundaries are detected from the column-header line.

DDIDGP text occasionally encodes accented characters in a way pdfplumber
returns as ``�`` (e.g. ``Ubicaci�n`` for ``Ubicación``). We
detect headers by their unaccented prefix to avoid coupling to the encoding.

Schemas come from ``Specifications.md`` § DR-006 and DR-007.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Literal

import pdfplumber

# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

Section = Literal["lleno", "lleno_sin_ubic", "retorno", "envases"]


@dataclass
class HojaCargaLine:
    section: Section
    ubicacion: str | None
    sku: str
    description: str
    quantity: float
    unit: str
    lote: str | None
    estado: str | None
    descarga: str | None  # always None when read from source paperwork


@dataclass
class HojaCargaTotals:
    cantidad: int | None
    volumen: float | None
    peso_kg: float | None


@dataclass
class HojaCarga:
    nº_carga: int
    nº_precarga: str
    vehiculo: str
    repartidor_id: int
    repartidor_name: str
    nº_viaje: int
    fecha: date
    ruta: str
    lines: list[HojaCargaLine]
    totals_entrega: HojaCargaTotals = field(default_factory=lambda: HojaCargaTotals(None, None, None))
    totals_devolucion: HojaCargaTotals = field(default_factory=lambda: HojaCargaTotals(None, None, None))


PaymentCondition = Literal["CONTADO", "CREDITO"]


@dataclass
class HojaRutaStop:
    sequence: int
    sstt: str
    payment_condition: PaymentCondition
    albaran_id: int
    customer_id: int
    customer_name: str
    address: str
    proforma_total: Decimal  # negative on credit notes (abonos)
    cash_total: Decimal


@dataclass
class HojaRuta:
    nº_carga: int
    fecha: date
    vehiculo: str  # licence plate, e.g. "7524KXX"
    repartidor_id: int
    repartidor_name: str
    preparador: str | None
    nº_viaje: int
    stops: list[HojaRutaStop]
    total_carga: Decimal | None
    total_cobro: Decimal | None


# ---------------------------------------------------------------------------
# Word + line plumbing
# ---------------------------------------------------------------------------


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float


def _ascii_fold(s: str) -> str:
    """Strip diacritics and the Unicode replacement char so we can match
    section / column headers regardless of how pdfplumber decoded them."""
    s = s.replace("�", "")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _extract_words(page) -> list[Word]:
    raw = page.extract_words(x_tolerance=2, y_tolerance=2, keep_blank_chars=False)
    return [
        Word(text=w["text"], x0=float(w["x0"]), x1=float(w["x1"]),
             top=float(w["top"]), bottom=float(w["bottom"]))
        for w in raw
    ]


def _group_lines(words: list[Word], y_tol: float = 2.5) -> list[list[Word]]:
    """Group words into visual lines using their top y coordinate."""
    out: list[list[Word]] = []
    current: list[Word] = []
    current_top: float | None = None
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        if current_top is None or abs(w.top - current_top) <= y_tol:
            current.append(w)
            current_top = w.top if current_top is None else current_top
        else:
            out.append(sorted(current, key=lambda w: w.x0))
            current = [w]
            current_top = w.top
    if current:
        out.append(sorted(current, key=lambda w: w.x0))
    return out


def _line_text(line: list[Word]) -> str:
    return " ".join(w.text for w in line)


# ---------------------------------------------------------------------------
# Hoja Carga
# ---------------------------------------------------------------------------

# Column boundaries (left edges) for the Carga body. We snap each word to the
# closest header below.
_CARGA_HEADERS = ["ubicacion", "n prod", "descripcion", "cantidad", "unidad", "lote", "descarga"]


def _find_carga_columns(line: list[Word]) -> dict[str, tuple[float, float]] | None:
    """Locate column boundaries from a column-header line; returns None if
    this line isn't the header.

    Three section variants exist, with different column sets:

    - ``Carga lleno`` / ``Carga lleno sin ubicación``:
      ``Ubicación | Nº Prod. | Descripción | Cantidad | Unidad | Lote | Descarga``
    - ``Carga retorno lleno``: same but ``Estado`` replaces ``Lote``.
    - ``Carga envases``: no ``Lote``, no ``Estado``.

    The required columns are ``Ubicación``, ``Nº Prod.``, ``Descripción``,
    ``Cantidad``, ``Unidad``, ``Descarga``; ``Lote`` and ``Estado`` are
    optional.
    """
    text = _ascii_fold(_line_text(line))
    if "ubicacion" not in text or "descarga" not in text:
        return None
    starts: dict[str, float] = {}
    for w in line:
        folded = _ascii_fold(w.text)
        # pdfplumber sometimes splits "Cantidad" → "Cantida" + "d"
        # so we accept any word starting with "cantida".
        if folded.startswith("ubicac"):
            starts["ubicacion"] = w.x0
        elif folded.startswith("prod"):
            starts.setdefault("sku", w.x0 - 12)
        elif folded.startswith("descrip"):
            starts["description"] = w.x0
        elif folded.startswith("cantida"):
            starts["cantidad"] = w.x0
        elif folded == "unidad":
            starts["unidad"] = w.x0
        elif folded == "lote":
            starts["lote"] = w.x0
        elif folded == "estado":
            starts["estado"] = w.x0
        elif folded == "descarga":
            starts["descarga"] = w.x0
    required = {"ubicacion", "sku", "description", "cantidad", "unidad", "descarga"}
    if not required.issubset(starts):
        return None
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    bounds: dict[str, tuple[float, float]] = {}
    for i, (name, x0) in enumerate(ordered):
        x1 = ordered[i + 1][1] if i + 1 < len(ordered) else 1e9
        bounds[name] = (x0 - 1, x1 - 1)
    return bounds


def _bucket_words_by_column(line: list[Word], bounds: dict[str, tuple[float, float]]) -> dict[str, str]:
    cols: dict[str, list[Word]] = {k: [] for k in bounds}
    for w in line:
        cx = (w.x0 + w.x1) / 2
        for name, (lo, hi) in bounds.items():
            if lo <= cx < hi:
                cols[name].append(w)
                break
    return {name: " ".join(x.text for x in sorted(ws, key=lambda w: w.x0)) for name, ws in cols.items()}


_SECTION_PATTERNS: list[tuple[re.Pattern[str], Section]] = [
    (re.compile(r"^carga\s*lleno\s*sin\s*ubic", re.I), "lleno_sin_ubic"),
    (re.compile(r"^carga\s*retorno", re.I), "retorno"),
    (re.compile(r"^carga\s*envases", re.I), "envases"),
    (re.compile(r"^carga\s*lleno\b", re.I), "lleno"),
]


def _detect_section(line: list[Word]) -> Section | None:
    text = _ascii_fold(_line_text(line))
    for pat, sec in _SECTION_PATTERNS:
        if pat.match(text):
            return sec
    return None


def _is_total_line(line: list[Word]) -> bool:
    return _ascii_fold(_line_text(line)).startswith("total cantidad")


def _parse_int(s: str) -> int | None:
    s = s.strip().replace(".", "").replace(",", "")
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_float(s: str) -> float | None:
    s = s.strip().replace(".", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date_dotted(s: str) -> date:
    """Parse ``DD.MM.YYYY``."""
    d, m, y = s.split(".")
    return date(int(y), int(m), int(d))


# Header parsing — runs on the first page only.

def _parse_carga_header(lines: Iterable[list[Word]]) -> dict[str, str]:
    """Find the first header table (two lines: labels + values) and return
    a dict of values keyed by short labels."""
    fields = {}
    label_line: list[Word] | None = None
    for line in lines:
        text = _ascii_fold(_line_text(line))
        if "carga" in text and "precarga" in text and "ruta" in text:
            label_line = line
            continue
        if label_line is not None:
            # First non-header line after the label line: the values.
            tokens = [w.text for w in sorted(line, key=lambda w: w.x0)]
            # Expected order: nº_carga/nº_precarga, vehiculo, repartidor_blob, viaje, fecha, ruta
            # The repartidor blob may contain spaces (e.g. "850004/30432 FRAN ROMERO").
            # We anchor on the first slash-prefixed Nº Carga and the dotted date and DR ruta.
            joined = " ".join(tokens)
            m_carga = re.search(r"(\d+)\s*/\s*(\S+)", joined)
            m_date = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", joined)
            m_ruta = re.search(r"\b(D[RA]\d{4})\b", joined)
            m_viaje = re.search(r"\b0[1-9]\b", joined)
            m_vehic = re.search(r"\bV\d{6}\b", joined)
            m_rep = re.search(r"(\d{6})\s*/\s*(\d+)\s+([A-ZÁÉÍÓÚÑ ]+?)(?:\s+0[1-9]\b)", joined)
            if m_carga:
                fields["nº_carga"] = m_carga.group(1)
                fields["nº_precarga"] = m_carga.group(2)
            if m_date:
                fields["fecha"] = m_date.group(1)
            if m_ruta:
                fields["ruta"] = m_ruta.group(1)
            if m_viaje:
                fields["nº_viaje"] = m_viaje.group(0)
            if m_vehic:
                fields["vehiculo"] = m_vehic.group(0)
            if m_rep:
                fields["repartidor_id"] = m_rep.group(1)
                fields["repartidor_name"] = m_rep.group(3).strip()
            return fields
    return fields


def _parse_carga_totals(line: list[Word]) -> tuple[HojaCargaTotals, HojaCargaTotals] | None:
    """Parse the final ``Total Cantidad / Volumen / Peso`` block.

    The PDF prints it as a 3×4 grid; we detect it by the ``Total Cantidad
    Entrega`` label and read the next 5 numeric tokens on the same logical
    line cluster.
    """
    text = _ascii_fold(_line_text(line))
    if "total cantidad entrega" not in text:
        return None
    # Numbers after the labels — pdfplumber keeps them as separate words.
    nums = [w.text for w in line if re.fullmatch(r"[\d.,]+", w.text)]
    if len(nums) < 2:
        return None
    return None  # totals come on a separate line cluster — handled outside


# Main parse function.

def _all_lines(path: Path) -> list[list[Word]]:
    """Group words into lines, one page at a time, then concatenate the
    per-page line lists. We can't pool words across pages because each
    page's coordinate system starts fresh at the top — pooling makes
    words from different pages cluster onto the same logical line.
    """
    out: list[list[Word]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = _extract_words(page)
            out.extend(_group_lines(words))
    return out


_SKU_PATTERN = re.compile(r"^[A-Z0-9]{2,12}$")
_PAGE_HEADER_LABEL = re.compile(r"\bcarga\b.*\bprecarga\b.*\bvehiculo\b", re.I)
_PAGE_HEADER_VALUE = re.compile(r"\d{8}/D\d+")  # e.g. "11764300/D131999991"


def _is_page_header(text_folded: str, raw_text: str) -> bool:
    """Detect a page-break repeat of the carga header (label or value
    line). When this lands in the middle of a section we want to
    reset bounds, not parse it as a body row.
    """
    if _PAGE_HEADER_LABEL.search(text_folded):
        return True
    if _PAGE_HEADER_VALUE.search(raw_text):
        return True
    return False


def parse_hoja_carga(path: Path) -> HojaCarga:
    """Parse a ``Hoja Carga`` PDF into a :class:`HojaCarga` object."""
    lines = _all_lines(path)

    header = _parse_carga_header(lines)
    if not header.get("nº_carga"):
        raise ValueError(f"Could not parse Hoja Carga header in {path}")

    bounds: dict[str, tuple[float, float]] | None = None
    section: Section | None = None
    parsed_lines: list[HojaCargaLine] = []
    totals_entrega = HojaCargaTotals(None, None, None)
    totals_devolucion = HojaCargaTotals(None, None, None)
    pending_totals_block: list[list[Word]] = []
    in_totals = False

    for idx, line in enumerate(lines):
        raw = _line_text(line)
        text = _ascii_fold(raw)

        # Page-break header repeats (carga label or value line). Reset
        # bounds so the next column header re-establishes them.
        if _is_page_header(text, raw):
            bounds = None
            continue

        # Section header.
        sec = _detect_section(line)
        if sec is not None:
            section = sec
            bounds = None  # will be re-established by the next column header.
            continue

        # Column header inside a section.
        new_bounds = _find_carga_columns(line)
        if new_bounds is not None:
            bounds = new_bounds
            continue

        # Final document-level totals block — must be checked before the
        # subtotal-skip below, otherwise "Total Cantidad Entrega: …" gets
        # eaten as a subtotal.
        if "total cantidad entrega" in text or "total volumen entrega" in text or "total peso entrega" in text:
            in_totals = True
        if in_totals:
            pending_totals_block.append(line)
            continue

        # Per-section subtotals like "Total Cantidad: 815".
        if _is_total_line(line):
            continue

        if section is None or bounds is None:
            continue

        # Bucket the row into cells.
        cells = _bucket_words_by_column(line, bounds)
        sku = cells.get("sku", "").strip()

        # Filter out page-header repeats that show up between sections.
        # Real SKUs are alphanumeric, no spaces. Page-header values like
        # "11764300/D131999991" or "precarga Vehículo" don't match.
        if not _SKU_PATTERN.match(sku):
            continue

        # Quantity sometimes wraps to the next visual line (e.g. ED13
        # showing "ESTRELLA DAMM 1/3 RET. PP" on one line and "114" on
        # the next). When the quantity cell is empty, peek ahead.
        quantity = _parse_float(cells.get("cantidad", ""))
        if quantity in (None, 0.0):
            for j in range(idx + 1, min(idx + 3, len(lines))):
                next_line = lines[j]
                next_text = _line_text(next_line).strip()
                if re.fullmatch(r"\d+(?:[.,]\d+)?", next_text):
                    quantity = _parse_float(next_text)
                    break
                if any(_SKU_PATTERN.match(w.text) for w in next_line):
                    break  # next real row; stop looking
        quantity = quantity or 0.0

        ubic = cells.get("ubicacion", "").strip() or None
        description = cells.get("description", "").strip()
        unit = cells.get("unidad", "").strip()
        lote_raw = cells.get("lote", "").strip()
        estado_raw = cells.get("estado", "").strip()

        estado: str | None = estado_raw or None
        lote: str | None = lote_raw or None
        # In the retorno layout there is no Lote column; if Estado isn't
        # picked up directly (older variant where Estado is rendered into
        # what we treat as Lote), fall back to the Lote text.
        if section == "retorno" and estado is None and lote_raw and lote_raw.isupper() and not lote_raw.isdigit():
            estado = lote_raw
            lote = None

        parsed_lines.append(
            HojaCargaLine(
                section=section,
                ubicacion=ubic,
                sku=sku,
                description=description,
                quantity=quantity,
                unit=unit,
                lote=lote,
                estado=estado,
                descarga=cells.get("descarga", "").strip() or None,
            )
        )

    if pending_totals_block:
        totals_entrega, totals_devolucion = _parse_totals_block(pending_totals_block)

    return HojaCarga(
        nº_carga=int(header["nº_carga"]),
        nº_precarga=header["nº_precarga"],
        vehiculo=header.get("vehiculo", ""),
        repartidor_id=int(header.get("repartidor_id", "0")),
        repartidor_name=header.get("repartidor_name", ""),
        nº_viaje=int(header.get("nº_viaje", "1")),
        fecha=_parse_date_dotted(header["fecha"]),
        ruta=header["ruta"],
        lines=parsed_lines,
        totals_entrega=totals_entrega,
        totals_devolucion=totals_devolucion,
    )


def _parse_totals_block(lines: list[list[Word]]) -> tuple[HojaCargaTotals, HojaCargaTotals]:
    entrega = HojaCargaTotals(None, None, None)
    devolucion = HojaCargaTotals(None, None, None)
    for line in lines:
        text = " ".join(w.text for w in line)
        folded = _ascii_fold(text)
        nums = [tok for tok in re.findall(r"[\d][\d.,]*", text) if any(c.isdigit() for c in tok)]
        if not nums:
            continue
        if "cantidad entrega" in folded and "devolucion" in folded:
            if len(nums) >= 2:
                entrega.cantidad = _parse_int(nums[0])
                devolucion.cantidad = _parse_int(nums[1])
        elif "volumen entrega" in folded and "devolucion" in folded:
            if len(nums) >= 2:
                entrega.volumen = _parse_float(nums[0])
                devolucion.volumen = _parse_float(nums[1])
        elif "peso entrega" in folded and "devolucion" in folded:
            if len(nums) >= 2:
                entrega.peso_kg = _parse_float(nums[0])
                devolucion.peso_kg = _parse_float(nums[1])
    return entrega, devolucion


# ---------------------------------------------------------------------------
# Hoja Ruta
# ---------------------------------------------------------------------------


def _parse_decimal_eu(s: str) -> Decimal:
    """Parse European-formatted decimal: ``1.839,26`` → ``1839.26``.
    Trailing ``-`` indicates negative."""
    s = s.strip()
    neg = False
    if s.endswith("-"):
        neg = True
        s = s[:-1]
    s = s.replace(".", "").replace(",", ".")
    try:
        v = Decimal(s)
    except Exception:  # noqa: BLE001
        return Decimal(0)
    return -v if neg else v


_RUTA_HEADERS = {
    "sstt": "sstt",
    "condicion": "payment_condition",
    "doc": "albaran_id",
    "cliente": "customer_id",
    "nombre": "customer_name",
    "direccion": "address",
    "proforma": "proforma_total",
    "cobro": "cash_total",
}


def _find_ruta_columns(line: list[Word]) -> dict[str, tuple[float, float]] | None:
    text = _ascii_fold(_line_text(line))
    if "sstt" not in text or "doc" not in text or "proforma" not in text:
        return None
    starts: dict[str, float] = {}
    for w in line:
        f = _ascii_fold(w.text)
        # pdfplumber sometimes joins adjacent words (e.g. "Nº Doc." → "NºDoc.")
        # so we accept the relevant token anywhere within the word.
        if f == "sstt":
            starts["sstt"] = w.x0
        elif "condic" in f:
            starts["payment_condition"] = w.x0
        elif "doc" in f:
            starts["albaran_id"] = w.x0
        elif "cliente" in f:
            starts["customer_id"] = w.x0
        elif "nombre" in f and "nombre" not in starts.get("nombre", ""):
            starts["customer_name"] = w.x0
        elif "direcci" in f:
            starts["address"] = w.x0
        elif "proforma" in f:
            starts["proforma_total"] = w.x0
        elif "cobro" in f:
            starts["cash_total"] = w.x0
    expected = set(_RUTA_HEADERS.values())
    if not expected.issubset(starts):
        return None
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    bounds = {}
    for i, (name, x0) in enumerate(ordered):
        x1 = ordered[i + 1][1] if i + 1 < len(ordered) else 1e9
        bounds[name] = (x0 - 1, x1 - 1)
    return bounds


def _parse_ruta_header(lines: Iterable[list[Word]]) -> dict[str, str]:
    """Header has ``Nº Carga | Fecha de entrega | Vehículo | Repartidor / Nombre | Preparador | Nº viaje``.

    pdfplumber sometimes joins adjacent words (``de entrega`` →
    ``deentrega``, ``Repartidor /`` → ``Repartidor/``), so we match
    loosely on the label line and rely on regexes against the value
    line to extract structured fields.
    """
    fields: dict[str, str] = {}
    found_label = False
    for line in lines:
        text = _ascii_fold(_line_text(line))
        if not found_label and "carga" in text and "vehiculo" in text and ("entrega" in text or "fecha" in text):
            found_label = True
            continue
        if found_label:
            joined = " ".join(w.text for w in sorted(line, key=lambda w: w.x0))
            m_carga = re.search(r"\b(\d{8})\b", joined)
            m_date = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", joined)
            m_plate = re.search(r"\b\d{4}[A-Z]{3}\b", joined)
            # Driver: 6-digit id, then name (UPPERCASE letters, possibly
            # joined into one token like "FRANROMERO"), then viaje "01".
            m_rep = re.search(r"(\d{6})\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]*?)\s+0[1-9]\b", joined)
            # Viaje is the LAST `0N` token on the line (the date contains
            # `08` so a leftmost match would pick that up instead).
            viajes = re.findall(r"\b(0[1-9])\b", joined)
            m_viaje = viajes[-1] if viajes else None
            if m_carga:
                fields["nº_carga"] = m_carga.group(1)
            if m_date:
                fields["fecha"] = m_date.group(1)
            if m_plate:
                fields["vehiculo"] = m_plate.group(0)
            if m_rep:
                fields["repartidor_id"] = m_rep.group(1)
                fields["repartidor_name"] = m_rep.group(2).strip()
            if m_viaje:
                fields["nº_viaje"] = m_viaje
            return fields
    return fields


def parse_hoja_ruta(path: Path) -> HojaRuta:
    lines = _all_lines(path)
    header = _parse_ruta_header(lines)
    if not header.get("nº_carga"):
        raise ValueError(f"Could not parse Hoja Ruta header in {path}")

    bounds: dict[str, tuple[float, float]] | None = None
    stops: list[HojaRutaStop] = []
    seq = 0
    total_carga: Decimal | None = None
    total_cobro: Decimal | None = None

    for line in lines:
        text = _ascii_fold(_line_text(line))

        nb = _find_ruta_columns(line)
        if nb is not None:
            bounds = nb
            continue

        if "de pedidos" in text:
            # Last line of the customer table: "Nº de pedidos N T. Carga X Y"
            raw = _line_text(line)
            decs = re.findall(r"[\d.]+,\d{2}-?", raw)
            if len(decs) >= 2:
                total_carga = _parse_decimal_eu(decs[0])
                total_cobro = _parse_decimal_eu(decs[1])
            continue

        if bounds is None:
            continue

        cells = _bucket_words_by_column(line, bounds)
        # A real customer row starts with "NO" or "SI" in the SSTT column,
        # has a payment condition (CONTADO/CREDITO) and a numeric albarán id.
        sstt = cells.get("sstt", "").strip()
        cond = cells.get("payment_condition", "").strip().upper()
        if sstt not in ("NO", "SI") or cond not in ("CONTADO", "CREDITO"):
            continue

        albaran_raw = cells.get("albaran_id", "").strip()
        m = re.search(r"\b(\d{8,})\b", albaran_raw)
        if not m:
            continue
        albaran_id = int(m.group(1))

        customer_raw = cells.get("customer_id", "").strip()
        m_cust = re.search(r"\b(\d{10,})\b", customer_raw)
        customer_id = int(m_cust.group(1)) if m_cust else 0

        proforma = _parse_decimal_eu(cells.get("proforma_total", "0"))
        cash = _parse_decimal_eu(cells.get("cash_total", "0"))

        seq += 1
        stops.append(
            HojaRutaStop(
                sequence=seq,
                sstt=sstt,
                payment_condition=cond,  # type: ignore[arg-type]
                albaran_id=albaran_id,
                customer_id=customer_id,
                customer_name=cells.get("customer_name", "").strip(),
                address=cells.get("address", "").strip(),
                proforma_total=proforma,
                cash_total=cash,
            )
        )

    return HojaRuta(
        nº_carga=int(header["nº_carga"]),
        fecha=_parse_date_dotted(header["fecha"]),
        vehiculo=header.get("vehiculo", ""),
        repartidor_id=int(header.get("repartidor_id", "0")),
        repartidor_name=header.get("repartidor_name", ""),
        preparador=None,
        nº_viaje=int(header.get("nº_viaje", "1")),
        stops=stops,
        total_carga=total_carga,
        total_cobro=total_cobro,
    )
