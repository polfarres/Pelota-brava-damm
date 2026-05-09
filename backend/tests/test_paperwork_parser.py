"""Integration tests for the Hoja Carga / Hoja Ruta parsers (FR-004).

These tests run against the real sample PDFs in ``Hackaton/DAMM/RECURSOS/``
because we have no synthetic fixtures with the same layout.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from smart_truck.paperwork.parser import parse_hoja_carga, parse_hoja_ruta

REPO_ROOT = Path(__file__).resolve().parents[2]
RECURSOS = REPO_ROOT / "Hackaton" / "DAMM" / "RECURSOS"
PDF_CARGA = RECURSOS / "Hoja Carga.pdf"
PDF_RUTA = RECURSOS / "Hoja Ruta.pdf"


pytestmark = pytest.mark.skipif(
    not (PDF_CARGA.exists() and PDF_RUTA.exists()),
    reason="Sample PDFs not present (Hackaton/DAMM/RECURSOS/).",
)


# ---------------------------------------------------------------------------
# Hoja Carga
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def hc():
    return parse_hoja_carga(PDF_CARGA)


def test_carga_header(hc) -> None:
    assert hc.nº_carga == 11_764_300
    assert hc.nº_precarga == "D131999991"
    assert hc.vehiculo == "V235045"
    assert hc.repartidor_id == 850_004
    assert "FRAN" in hc.repartidor_name and "ROMERO" in hc.repartidor_name
    assert hc.nº_viaje == 1
    assert hc.fecha == date(2026, 5, 8)
    assert hc.ruta == "DR0027"


def test_carga_all_four_sections_present(hc) -> None:
    sections = {ln.section for ln in hc.lines}
    assert sections == {"lleno", "lleno_sin_ubic", "retorno", "envases"}


def test_carga_section_subtotals_match_source(hc) -> None:
    """Subtotals printed on the source PDF: 815 / 22 / 1 / 258."""
    by_section: dict[str, int] = {}
    for ln in hc.lines:
        by_section[ln.section] = by_section.get(ln.section, 0) + int(ln.quantity)
    assert by_section["lleno"] == 815
    assert by_section["lleno_sin_ubic"] == 22
    assert by_section["retorno"] == 1
    assert by_section["envases"] == 258


def test_carga_grand_totals_match_source(hc) -> None:
    """Final document-level totals printed on the last page."""
    assert hc.totals_entrega.cantidad == 837
    assert hc.totals_devolucion.cantidad == 259
    assert hc.totals_entrega.peso_kg == pytest.approx(4719.12)
    assert hc.totals_devolucion.peso_kg == pytest.approx(2094.276)


def test_carga_descarga_column_is_blank_in_source(hc) -> None:
    """A-21: source PDFs always have an empty Descarga column. We
    parse it through unchanged."""
    assert all(ln.descarga is None for ln in hc.lines)


def test_carga_lote_column_is_blank_in_source(hc) -> None:
    """A-21: same for Lote — pass through unchanged."""
    assert all(ln.lote is None for ln in hc.lines)


def test_carga_envases_recognised_by_sku(hc) -> None:
    """Envases SKUs follow the 3ENV…/CJ…/BRL…V/TB8V pattern (DR-006)."""
    envases = [ln for ln in hc.lines if ln.section == "envases"]
    assert envases
    for ln in envases:
        sku = ln.sku
        assert sku.startswith("3ENV") or sku.startswith("CJ") or (
            sku.startswith("BRL") and sku.endswith("V")
        ) or sku == "TB8V", f"unexpected envase SKU: {sku!r}"


# ---------------------------------------------------------------------------
# Hoja Ruta
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def hr():
    return parse_hoja_ruta(PDF_RUTA)


def test_ruta_header(hr) -> None:
    assert hr.nº_carga == 11_764_300
    assert hr.fecha == date(2026, 5, 8)
    assert hr.vehiculo == "7524KXX"
    assert hr.repartidor_id == 850_004
    assert "FRAN" in hr.repartidor_name and "ROMERO" in hr.repartidor_name
    assert hr.nº_viaje == 1


def test_ruta_eighteen_stops(hr) -> None:
    assert len(hr.stops) == 18


def test_ruta_payment_conditions(hr) -> None:
    """Source PDF: 7 CONTADO + 11 CREDITO."""
    contado = sum(1 for s in hr.stops if s.payment_condition == "CONTADO")
    credito = sum(1 for s in hr.stops if s.payment_condition == "CREDITO")
    assert contado == 7
    assert credito == 11


def test_ruta_negative_abonos_preserved(hr) -> None:
    """Three credit-note (abono) lines on the source PDF carry negative
    proforma totals: -15.91, -48.34, -8.36."""
    negatives = [s.proforma_total for s in hr.stops if s.proforma_total < 0]
    assert len(negatives) == 3
    total = sum(negatives)
    assert total == pytest.approx(Decimal("-72.61"))


def test_ruta_total_carga_matches_sum(hr) -> None:
    """Sum of proforma totals on the parsed stops should equal the
    printed footer ``T. Carga`` value."""
    line_sum = sum(s.proforma_total for s in hr.stops)
    assert line_sum == pytest.approx(Decimal("7832.38"))
    assert hr.total_carga == pytest.approx(Decimal("7832.38"))


def test_ruta_cash_total_matches_contado_sum(hr) -> None:
    """Total Cobro on the footer = sum of cash_total over all stops."""
    cash_sum = sum(s.cash_total for s in hr.stops)
    assert cash_sum == pytest.approx(Decimal("2891.08"))
    assert hr.total_cobro == pytest.approx(Decimal("2891.08"))


def test_ruta_credito_rows_have_zero_cash(hr) -> None:
    for s in hr.stops:
        if s.payment_condition == "CREDITO":
            assert s.cash_total == 0


# ---------------------------------------------------------------------------
# Cross-document sanity
# ---------------------------------------------------------------------------


def test_carga_and_ruta_share_carga_id(hc, hr) -> None:
    assert hc.nº_carga == hr.nº_carga
    assert hc.fecha == hr.fecha
    assert hc.repartidor_id == hr.repartidor_id
