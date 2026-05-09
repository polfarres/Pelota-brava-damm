"""Tests for the Smart Hoja Carga / Smart Hoja Ruta emitters (FR-010, FR-011)."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from pathlib import Path

import pdfplumber
import pytest

from smart_truck.models import (
    DeliveredLine,
    Plan,
    SlotAssignment,
    StopPlan,
)
from smart_truck.paperwork.emitter import (
    emit_smart_hoja_carga,
    emit_smart_hoja_ruta,
)
from smart_truck.paperwork.parser import parse_hoja_carga, parse_hoja_ruta

REPO_ROOT = Path(__file__).resolve().parents[2]
RECURSOS = REPO_ROOT / "Hackaton" / "DAMM" / "RECURSOS"
PDF_CARGA = RECURSOS / "Hoja Carga.pdf"
PDF_RUTA = RECURSOS / "Hoja Ruta.pdf"


pytestmark = pytest.mark.skipif(
    not (PDF_CARGA.exists() and PDF_RUTA.exists()),
    reason="Sample source PDFs not present.",
)


@pytest.fixture(scope="module")
def parsed_carga():
    return parse_hoja_carga(PDF_CARGA)


@pytest.fixture(scope="module")
def parsed_ruta():
    return parse_hoja_ruta(PDF_RUTA)


def _read_pdf_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


# ---------------------------------------------------------------------------
# Pass-through (no plan) — should render but Descarga blank.
# ---------------------------------------------------------------------------


def test_carga_passthrough_renders(tmp_path: Path, parsed_carga) -> None:
    out = tmp_path / "carga.pdf"
    emit_smart_hoja_carga(parsed_carga, plan=None, output_path=out)
    assert out.exists() and out.stat().st_size > 1000
    head = out.read_bytes()[:5]
    assert head.startswith(b"%PDF-")


def test_carga_passthrough_contains_source_skus(tmp_path: Path, parsed_carga) -> None:
    out = tmp_path / "carga.pdf"
    emit_smart_hoja_carga(parsed_carga, plan=None, output_path=out)
    text = _read_pdf_text(out)
    # A handful of representative SKUs from the source.
    for sku in ("ED13", "TU13", "CJ13", "BRL30V"):
        assert sku in text, f"expected {sku} in emitted PDF"


def test_carga_includes_all_section_titles(tmp_path: Path, parsed_carga) -> None:
    out = tmp_path / "carga.pdf"
    emit_smart_hoja_carga(parsed_carga, plan=None, output_path=out)
    text = _read_pdf_text(out)
    assert "Carga lleno" in text
    assert "envases" in text.lower()


def test_ruta_passthrough_renders(tmp_path: Path, parsed_ruta) -> None:
    out = tmp_path / "ruta.pdf"
    emit_smart_hoja_ruta(parsed_ruta, plan=None, output_path=out)
    assert out.exists() and out.stat().st_size > 500
    text = _read_pdf_text(out)
    assert "DR0027" in text or "Smart Hoja Ruta" in text
    assert "FRAN" in text  # driver name


def test_ruta_passthrough_lists_18_albaranes(tmp_path: Path, parsed_ruta) -> None:
    out = tmp_path / "ruta.pdf"
    emit_smart_hoja_ruta(parsed_ruta, plan=None, output_path=out)
    text = _read_pdf_text(out)
    # Each albarán id appears in the table.
    for s in parsed_ruta.stops:
        assert str(s.albaran_id) in text


# ---------------------------------------------------------------------------
# With a hand-built Plan — Descarga + reordering kick in.
# ---------------------------------------------------------------------------


def _toy_plan(parsed_carga, parsed_ruta) -> Plan:
    """Build a Plan that round-robins carga lines into 6 truck slots and
    reverses the stop order. Just enough fixture to exercise the
    Descarga lookup and the row-reordering code path. Honors A-31:
    each slot is capped at 60 CE (lines beyond the cap are dropped from
    the toy plan — the test only needs *some* coverage per slot)."""
    slots: list[SlotAssignment] = []
    by_id: dict[str, SlotAssignment] = {}
    outbound = [ln for ln in parsed_carga.lines if ln.section in ("lleno", "lleno_sin_ubic")]
    for j, ln in enumerate(outbound):
        slot_num = (j % 6) + 1
        sid = f"P{slot_num}"
        slot = by_id.get(sid)
        if slot is None:
            slot = SlotAssignment(slot_id=sid, is_envase_zone=False)
            slots.append(slot)
            by_id[sid] = slot
        if sum(c.ce for c in slot.contents) + 1.0 > 60.0:
            continue
        slot.contents.append(
            DeliveredLine(
                sku=ln.sku,
                description=ln.description,
                quantity=ln.quantity,
                unit=ln.unit,
                ce=1.0,
                weight_kg=0.0,
                source_ubicacion=ln.ubicacion,
            )
        )
        slot.stop_sequences = [slot_num]
    slots.append(SlotAssignment(slot_id="E1", is_envase_zone=True))

    return Plan(
        ruta="DR0027",
        fecha=date(2026, 5, 8),
        vehicle_profile="truck_6p_sidecurtain",
        stops=[
            StopPlan(
                sequence=i,
                customer_id=s.customer_id,
                customer_name=s.customer_name,
                address=s.address,
                lat=None,
                lon=None,
                eta=time(9, (i * 5) % 60),
                time_window=None,
                payment_condition=s.payment_condition,
                proforma_total=s.proforma_total,
            )
            for i, s in enumerate(reversed(parsed_ruta.stops), start=1)
        ],
        slot_assignments=slots,
    )


def test_carga_with_plan_populates_descarga(
    tmp_path: Path, parsed_carga, parsed_ruta
) -> None:
    """Smart Hoja Carga populates the Descarga column with slot ids
    from every used pallet — not just one. Guards against the v1 bug
    where ``setdefault(sku, slot_id)`` kept only the first slot per SKU
    and made every row look like it went to P1."""
    plan = _toy_plan(parsed_carga, parsed_ruta)
    out = tmp_path / "carga_smart.pdf"
    emit_smart_hoja_carga(parsed_carga, plan=plan, output_path=out)
    text = _read_pdf_text(out)
    # All six toy slots must appear in the rendered Descarga column.
    for sid in ("P1", "P2", "P3", "P4", "P5", "P6"):
        assert sid in text, f"slot {sid} missing from rendered Smart Hoja Carga"
    assert "E1" in text  # envase slot id


def test_descarga_split_when_sku_spans_slots(tmp_path: Path) -> None:
    """A source row whose SKU lives in two plan slots is rendered as
    *two* rows in the PDF — same Ubicación / SKU / Description / Unit,
    one per slot, with the source quantity distributed proportionally.
    """
    from smart_truck.paperwork.parser import (
        HojaCarga,
        HojaCargaLine,
        HojaCargaTotals,
    )
    line = HojaCargaLine(
        section="lleno",
        ubicacion="AA09A1",
        sku="SPLITME",
        description="A SKU SPANNING TWO SLOTS",
        quantity=100,
        unit="Caja",
        lote=None,
        estado=None,
        descarga=None,
    )
    source = HojaCarga(
        nº_carga=1, nº_precarga="X", vehiculo="V", repartidor_id=1,
        repartidor_name="X", nº_viaje=1, fecha=date(2026, 5, 8), ruta="DR0001",
        lines=[line],
        totals_entrega=HojaCargaTotals(cantidad=100, volumen=None, peso_kg=None),
        totals_devolucion=HojaCargaTotals(cantidad=0, volumen=None, peso_kg=None),
    )

    plan = Plan(
        ruta="DR0001",
        fecha=date(2026, 5, 8),
        vehicle_profile="truck_6p_sidecurtain",
        stops=[],
        slot_assignments=[
            SlotAssignment(
                slot_id="P1", is_envase_zone=False, pallet_type="CASE",
                stop_sequences=[1],
                contents=[DeliveredLine(
                    sku="SPLITME", description="A SKU SPANNING TWO SLOTS",
                    quantity=30, unit="Caja", ce=1.0, weight_kg=0.0,
                    source_ubicacion="AA09A1",
                )],
                ce_used=30.0, ce_capacity=60.0,
            ),
            SlotAssignment(
                slot_id="P3", is_envase_zone=False, pallet_type="CASE",
                stop_sequences=[2],
                contents=[DeliveredLine(
                    sku="SPLITME", description="A SKU SPANNING TWO SLOTS",
                    quantity=70, unit="Caja", ce=1.0, weight_kg=0.0,
                    source_ubicacion="AA09A1",
                )],
                ce_used=70.0, ce_capacity=60.0,
            ),
        ],
    )

    out = tmp_path / "split.pdf"
    emit_smart_hoja_carga(source, plan=plan, output_path=out)
    text = _read_pdf_text(out)

    # Both slot ids must appear next to the SKU.
    assert "P1" in text and "P3" in text

    # The source qty 100 should split into 30 (P1) + 70 (P3) — both
    # appear as standalone tokens in the rendered table.
    import re
    qtys = [int(m.group(1)) for m in re.finditer(r"\bSPLITME\b.*?\b(\d+)\s+Caja", text)]
    assert sorted(qtys) == [30, 70], f"expected [30, 70], got {qtys}"


def test_per_slot_ce_never_exceeds_capacity_in_pdf(
    tmp_path: Path, parsed_carga, parsed_ruta
) -> None:
    """The per-slot footer line must report a CE figure ≤ 60 for every
    listed slot (A-31 invariant — visible in the printed sheet)."""
    plan = _toy_plan(parsed_carga, parsed_ruta)
    out = tmp_path / "footer.pdf"
    emit_smart_hoja_carga(parsed_carga, plan=plan, output_path=out)
    text = _read_pdf_text(out)
    assert "Per slot" in text
    import re
    # Match patterns like "P1 59 / 60 CE" — capture the used number.
    pairs = re.findall(r"\bP\d+\s+(\d+(?:\.\d+)?)\s*/\s*60\s*CE", text)
    assert pairs, f"no per-slot CE figures parsed; PDF text was:\n{text[-400:]}"
    for used in pairs:
        assert float(used) <= 60.0 + 1e-6, f"slot reported {used} CE > 60 cap"


def test_ruta_with_plan_reorders_to_plan_sequence(
    tmp_path: Path, parsed_carga, parsed_ruta
) -> None:
    plan = _toy_plan(parsed_carga, parsed_ruta)
    out = tmp_path / "ruta_smart.pdf"
    emit_smart_hoja_ruta(parsed_ruta, plan=plan, output_path=out)
    text = _read_pdf_text(out)
    # The plan reverses the stops; the LAST source stop's albarán should
    # appear before the FIRST source stop's albarán in the text stream.
    last_id = str(parsed_ruta.stops[-1].albaran_id)
    first_id = str(parsed_ruta.stops[0].albaran_id)
    assert text.find(last_id) < text.find(first_id)


def test_emit_returns_the_output_path(tmp_path: Path, parsed_carga) -> None:
    out = tmp_path / "ret.pdf"
    result = emit_smart_hoja_carga(parsed_carga, plan=None, output_path=out)
    assert result == out
