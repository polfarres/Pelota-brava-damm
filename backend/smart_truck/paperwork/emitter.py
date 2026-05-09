"""Smart Hoja Carga + Smart Hoja Ruta PDF emitters (FR-010, FR-011).

These render PDFs that visually echo the source DDIDGP paperwork but
add the value our optimiser produces:

- **Smart Hoja Carga** — same four sections (``Carga lleno``,
  ``Carga lleno sin ubicación``, ``Carga retorno lleno``,
  ``Carga envases``) and same column shape, but the ``Descarga``
  column is populated with the truck slot each line should go into.
  Colour-coding by destination customer cluster.

- **Smart Hoja Ruta** — same row shape but stops are reordered to the
  optimised sequence. Each row gains an ``ETA`` column and a CONTADO
  badge; rows whose time window will be missed are highlighted.

We use ReportLab's Platypus tables (pure Python, no system-library
dependency, runs on any deploy target). The output is intentionally
*recognisable* rather than pixel-perfect: same letterhead, same
section structure, same column order.

Both functions accept a parsed source object plus a :class:`Plan`. If
``plan`` is ``None``, the renderer behaves like a pass-through: same
source content, ``Descarga`` left blank, baseline-equivalent ordering.
This keeps the emitter testable in isolation while Track A's optimiser
is still in flight.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..models import Plan, SlotAssignment, StopPlan
from .parser import HojaCarga, HojaCargaLine, HojaRuta, HojaRutaStop

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

_DAMM_RED = colors.HexColor("#E30613")
_HEADER_BG = colors.HexColor("#F2F2F2")
_CONTADO_BG = colors.HexColor("#FFF6D8")
_ENVASE_BG = colors.HexColor("#EEF7FB")
_RETORNO_BG = colors.HexColor("#FBEEEE")

_styles = getSampleStyleSheet()
_title_style = ParagraphStyle(
    "title",
    parent=_styles["Heading2"],
    textColor=_DAMM_RED,
    spaceAfter=4,
)
_section_style = ParagraphStyle(
    "section",
    parent=_styles["Heading4"],
    textColor=_DAMM_RED,
    spaceBefore=10,
    spaceAfter=2,
)
_meta_style = ParagraphStyle(
    "meta", parent=_styles["BodyText"], fontSize=8, leading=10
)
_footer_style = ParagraphStyle(
    "footer", parent=_styles["BodyText"], fontSize=8, alignment=2
)


# ---------------------------------------------------------------------------
# Smart Hoja Carga
# ---------------------------------------------------------------------------

_CARGA_SECTION_LABELS = {
    "lleno": "Carga lleno",
    "lleno_sin_ubic": "Carga lleno sin ubicación",
    "retorno": "Carga retorno lleno",
    "envases": "Carga envases",
}


def _build_descarga_lookup(plan: Plan | None) -> dict[str, str]:
    """``sku → slot_id`` mapping for outbound (non-envase) plan slots."""
    if plan is None:
        return {}
    lookup: dict[str, str] = {}
    for slot in plan.slot_assignments:
        if slot.is_envase_zone:
            continue
        for line in slot.contents:
            lookup.setdefault(line.sku, slot.slot_id)
    return lookup


def _envase_slot_id(plan: Plan | None) -> str | None:
    if plan is None:
        return None
    for slot in plan.slot_assignments:
        if slot.is_envase_zone:
            return slot.slot_id
    return None


def _customer_cluster_color(stop_sequence: int | None) -> colors.Color | None:
    """Stable pastel colour per stop sequence, used to colour-code rows
    that belong to the same customer cluster in the load.
    """
    if stop_sequence is None:
        return None
    palette = [
        colors.HexColor("#FFE9B0"),
        colors.HexColor("#D6F0FF"),
        colors.HexColor("#E5FFD6"),
        colors.HexColor("#FFD6E0"),
        colors.HexColor("#E8D6FF"),
        colors.HexColor("#FFEFD6"),
        colors.HexColor("#D6FFEC"),
        colors.HexColor("#F2D6FF"),
    ]
    return palette[(stop_sequence - 1) % len(palette)]


def _slot_to_stop_sequence(plan: Plan | None) -> dict[str, int]:
    if plan is None:
        return {}
    out: dict[str, int] = {}
    for slot in plan.slot_assignments:
        if slot.stop_sequences:
            out[slot.slot_id] = slot.stop_sequences[0]
    return out


def emit_smart_hoja_carga(
    source: HojaCarga,
    plan: Plan | None,
    output_path: Path,
) -> Path:
    """Render a Smart Hoja Carga PDF and return its path."""
    descarga_lookup = _build_descarga_lookup(plan)
    envase_slot = _envase_slot_id(plan)
    slot_to_seq = _slot_to_stop_sequence(plan)

    elements: list = []
    elements.extend(_carga_header(source))

    sections_with_lines = _group_lines_by_section(source.lines)
    for section in ("lleno", "lleno_sin_ubic", "retorno", "envases"):
        section_lines = sections_with_lines.get(section, [])
        if not section_lines:
            continue
        elements.append(Paragraph(_CARGA_SECTION_LABELS[section], _section_style))
        elements.append(
            _carga_section_table(
                section_lines,
                section=section,
                descarga_lookup=descarga_lookup,
                envase_slot=envase_slot,
                slot_to_seq=slot_to_seq,
            )
        )

    elements.append(Spacer(0, 4 * mm))
    elements.append(_carga_totals_table(source))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Smart Hoja Carga {source.nº_carga}",
    )
    doc.build(elements)
    return output_path


def _group_lines_by_section(
    lines: Iterable[HojaCargaLine],
) -> dict[str, list[HojaCargaLine]]:
    out: dict[str, list[HojaCargaLine]] = {}
    for ln in lines:
        out.setdefault(ln.section, []).append(ln)
    return out


def _carga_header(source: HojaCarga) -> list:
    title = Paragraph("Smart Hoja Carga", _title_style)
    meta = Paragraph(
        (
            f"<b>Nº Carga:</b> {source.nº_carga}/{source.nº_precarga} &nbsp;&nbsp; "
            f"<b>Vehículo:</b> {source.vehiculo} &nbsp;&nbsp; "
            f"<b>Repartidor:</b> {source.repartidor_id} {source.repartidor_name} &nbsp;&nbsp; "
            f"<b>Nº Viaje:</b> {source.nº_viaje} &nbsp;&nbsp; "
            f"<b>Fecha:</b> {source.fecha.strftime('%d.%m.%Y')} &nbsp;&nbsp; "
            f"<b>Ruta:</b> {source.ruta}"
        ),
        _meta_style,
    )
    return [title, meta, Spacer(0, 4 * mm)]


def _carga_section_table(
    lines: list[HojaCargaLine],
    *,
    section: str,
    descarga_lookup: dict[str, str],
    envase_slot: str | None,
    slot_to_seq: dict[str, int],
) -> Table:
    headers = ["Ubicación", "Nº Prod.", "Descripción", "Cantidad", "Unidad", "Lote", "Descarga"]
    if section == "retorno":
        headers = ["Ubicación", "Nº Prod.", "Descripción", "Estado", "Cantidad", "Unidad", "Descarga"]
    if section == "envases":
        headers = ["Ubicación", "Nº Prod.", "Descripción", "Cantidad", "Unidad", "Descarga"]

    rows: list[list] = [headers]
    row_colours: list[tuple[int, colors.Color]] = []

    for i, ln in enumerate(lines, start=1):
        descarga = ""
        if section == "envases":
            descarga = envase_slot or ""
        elif section in ("lleno", "lleno_sin_ubic"):
            descarga = descarga_lookup.get(ln.sku, "")
        # Retorno is supplier-side; leave Descarga blank.

        if section == "retorno":
            rows.append([
                ln.ubicacion or "",
                ln.sku,
                ln.description,
                ln.estado or "",
                f"{ln.quantity:g}",
                ln.unit,
                descarga,
            ])
        elif section == "envases":
            rows.append([
                ln.ubicacion or "",
                ln.sku,
                ln.description,
                f"{ln.quantity:g}",
                ln.unit,
                descarga,
            ])
        else:
            rows.append([
                ln.ubicacion or "",
                ln.sku,
                ln.description,
                f"{ln.quantity:g}",
                ln.unit,
                ln.lote or "",
                descarga,
            ])

        # Cluster colour by destination stop.
        if section in ("lleno", "lleno_sin_ubic") and descarga:
            seq = slot_to_seq.get(descarga)
            colour = _customer_cluster_color(seq)
            if colour:
                row_colours.append((i, colour))

    rows.append([
        "Total Cantidad:",
        "",
        "",
        f"{int(sum(ln.quantity for ln in lines))}",
        "",
        "",
    ] + ([""] if len(headers) == 7 else []))

    # Column widths roughly mirror the source layout proportions.
    if len(headers) == 7:
        col_widths = [22 * mm, 22 * mm, 60 * mm, 18 * mm, 18 * mm, 18 * mm, 25 * mm]
    else:
        col_widths = [22 * mm, 22 * mm, 70 * mm, 18 * mm, 22 * mm, 30 * mm]

    style = TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (-2, 1), (-1, -1), "CENTER"),  # Cantidad/unit/Descarga centered
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), _HEADER_BG),
    ])

    if section == "envases":
        style.add("BACKGROUND", (0, 1), (-1, -2), _ENVASE_BG)
    elif section == "retorno":
        style.add("BACKGROUND", (0, 1), (-1, -2), _RETORNO_BG)

    # Apply per-row cluster colours (overrides the section background where set).
    for row_idx, colour in row_colours:
        style.add("BACKGROUND", (-1, row_idx), (-1, row_idx), colour)

    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(style)
    return table


def _carga_totals_table(source: HojaCarga) -> Table:
    headers = ["", "Cantidad", "Volumen", "Peso (kg)"]
    rows = [
        headers,
        [
            "Entrega",
            str(source.totals_entrega.cantidad or "-"),
            f"{source.totals_entrega.volumen or '-'}",
            f"{source.totals_entrega.peso_kg or '-'}",
        ],
        [
            "Devolución",
            str(source.totals_devolucion.cantidad or "-"),
            f"{source.totals_devolucion.volumen or '-'}",
            f"{source.totals_devolucion.peso_kg or '-'}",
        ],
    ]
    table = Table(rows, colWidths=[35 * mm, 30 * mm, 30 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]))
    return table


# ---------------------------------------------------------------------------
# Smart Hoja Ruta
# ---------------------------------------------------------------------------


def emit_smart_hoja_ruta(
    source: HojaRuta,
    plan: Plan | None,
    output_path: Path,
) -> Path:
    """Render a Smart Hoja Ruta PDF and return its path.

    If ``plan`` is provided, the rows are reordered to ``plan.stops``
    sequence (matched on ``customer_id``) and an ETA column is added.
    Otherwise the source order is preserved.
    """
    elements: list = []
    elements.extend(_ruta_header(source))

    if plan is not None:
        ordered = _order_ruta_stops_by_plan(source.stops, plan.stops)
        eta_lookup = {s.customer_id: s.eta for s in plan.stops if s.eta}
    else:
        ordered = list(source.stops)
        eta_lookup = {}

    elements.append(_ruta_table(ordered, eta_lookup=eta_lookup))
    elements.append(Spacer(0, 4 * mm))
    elements.append(_ruta_totals_paragraph(source))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Smart Hoja Ruta {source.nº_carga}",
    )
    doc.build(elements)
    return output_path


def _ruta_header(source: HojaRuta) -> list:
    title = Paragraph("Smart Hoja Ruta", _title_style)
    meta = Paragraph(
        (
            f"<b>Nº Carga:</b> {source.nº_carga} &nbsp;&nbsp; "
            f"<b>Fecha:</b> {source.fecha.strftime('%d.%m.%Y')} &nbsp;&nbsp; "
            f"<b>Vehículo:</b> {source.vehiculo} &nbsp;&nbsp; "
            f"<b>Repartidor:</b> {source.repartidor_id} {source.repartidor_name} &nbsp;&nbsp; "
            f"<b>Nº viaje:</b> {source.nº_viaje}"
        ),
        _meta_style,
    )
    return [title, meta, Spacer(0, 4 * mm)]


def _order_ruta_stops_by_plan(
    source_stops: list[HojaRutaStop],
    plan_stops: list[StopPlan],
) -> list[HojaRutaStop]:
    """Reorder source rows to the plan's stop sequence by matching on
    ``customer_id``. Rows whose customer doesn't appear in the plan
    (e.g. abonos for absent clients) keep their relative order at the
    end."""
    by_customer: dict[int, list[HojaRutaStop]] = {}
    for s in source_stops:
        by_customer.setdefault(s.customer_id, []).append(s)

    seen: set[int] = set()
    ordered: list[HojaRutaStop] = []
    for ps in plan_stops:
        if ps.customer_id in by_customer and ps.customer_id not in seen:
            ordered.extend(by_customer[ps.customer_id])
            seen.add(ps.customer_id)

    for s in source_stops:
        if s.customer_id not in seen:
            ordered.append(s)
            seen.add(s.customer_id)
    return ordered


def _format_eta(eta: time | None) -> str:
    if eta is None:
        return ""
    return eta.strftime("%H:%M")


def _ruta_table(
    stops: list[HojaRutaStop],
    *,
    eta_lookup: dict[int, time | None],
) -> Table:
    headers = [
        "#", "SSTT", "Pago", "ETA", "Nº Doc.",
        "Nº Cliente", "Nombre", "Dirección",
        "Total Proforma", "Total Cobro",
    ]
    rows: list[list] = [headers]
    contado_indices: list[int] = []

    for i, s in enumerate(stops, start=1):
        eta = _format_eta(eta_lookup.get(s.customer_id))
        rows.append([
            str(i),
            s.sstt,
            s.payment_condition,
            eta,
            str(s.albaran_id),
            str(s.customer_id),
            s.customer_name,
            s.address,
            _format_money(s.proforma_total),
            _format_money(s.cash_total),
        ])
        if s.payment_condition == "CONTADO":
            contado_indices.append(i)

    style = TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (0, 1), (4, -1), "CENTER"),
        ("ALIGN", (-2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])
    for i in contado_indices:
        style.add("BACKGROUND", (0, i), (-1, i), _CONTADO_BG)

    col_widths = [
        8 * mm, 9 * mm, 13 * mm, 12 * mm, 18 * mm,
        18 * mm, 28 * mm, 50 * mm, 18 * mm, 16 * mm,
    ]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(style)
    return table


def _format_money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ruta_totals_paragraph(source: HojaRuta) -> Paragraph:
    n = len(source.stops)
    total_carga = source.total_carga if source.total_carga is not None else Decimal(0)
    total_cobro = source.total_cobro if source.total_cobro is not None else Decimal(0)
    text = (
        f"<b>Nº de pedidos:</b> {n} &nbsp;&nbsp; "
        f"<b>T. Carga:</b> {_format_money(total_carga)} &nbsp;&nbsp; "
        f"<b>T. Cobro:</b> {_format_money(total_cobro)}"
    )
    return Paragraph(text, _footer_style)
