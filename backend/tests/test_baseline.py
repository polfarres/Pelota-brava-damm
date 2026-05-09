"""Integration tests for the BaselinePlan reconstruction (FR-004)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from smart_truck.baseline import (
    RECURSOS_DIR,
    BaselineInputs,
    reconstruct_baseline,
)
from smart_truck.models import BaselinePlan

PDF_CARGA = RECURSOS_DIR / "Hoja Carga.pdf"
PDF_RUTA = RECURSOS_DIR / "Hoja Ruta.pdf"


pytestmark = pytest.mark.skipif(
    not (PDF_CARGA.exists() and PDF_RUTA.exists()),
    reason="Sample PDFs not present (Hackaton/DAMM/RECURSOS/).",
)


@pytest.fixture(scope="module")
def baseline() -> BaselinePlan:
    return reconstruct_baseline(PDF_CARGA, PDF_RUTA)


def test_baseline_metadata(baseline: BaselinePlan) -> None:
    assert baseline.ruta == "DR0027"
    assert baseline.fecha == date(2026, 5, 8)
    assert baseline.vehicle_profile == "truck_6p_sidecurtain"


def test_baseline_has_eighteen_stops_in_print_order(baseline: BaselinePlan) -> None:
    """A-04: drivers follow the printed Hoja Ruta order."""
    assert len(baseline.stops) == 18
    sequences = [s.sequence for s in baseline.stops]
    assert sequences == sorted(sequences)
    assert sequences[0] == 1
    assert sequences[-1] == 18


def test_baseline_preserves_payment_split(baseline: BaselinePlan) -> None:
    contado = sum(1 for s in baseline.stops if s.payment_condition == "CONTADO")
    credito = sum(1 for s in baseline.stops if s.payment_condition == "CREDITO")
    assert contado == 7
    assert credito == 11


def test_baseline_proforma_sum_matches_source(baseline: BaselinePlan) -> None:
    """Sum of stop proforma totals should equal the printed footer."""
    total = sum(s.proforma_total for s in baseline.stops)
    assert total == pytest.approx(Decimal("7832.38"))


def test_baseline_negative_abonos_preserved(baseline: BaselinePlan) -> None:
    negatives = [s.proforma_total for s in baseline.stops if s.proforma_total < 0]
    assert len(negatives) == 3
    assert sum(negatives) == pytest.approx(Decimal("-72.61"))


def test_baseline_geocoded_majority(baseline: BaselinePlan) -> None:
    """At least 90% of stops should be geocoded (Photon hit rate on the
    cached cohort)."""
    geocoded = sum(1 for s in baseline.stops if s.lat is not None)
    assert geocoded >= 16


def test_baseline_zones_touched_estimate_present(baseline: BaselinePlan) -> None:
    """Each stop must carry a non-zero zones-touched estimate so the
    KPI engine can compute baseline service time."""
    for s in baseline.stops:
        assert s.in_truck_zones_touched >= 1


def test_baseline_zones_touched_consistent(baseline: BaselinePlan) -> None:
    """v1 uses the same average across all stops; the value is
    ``ceil(num_outbound_lines / num_stops)``. For DR0027/2026-05-08
    that's ``ceil(82/18) = 5``."""
    values = {s.in_truck_zones_touched for s in baseline.stops}
    assert len(values) == 1, f"expected uniform estimate, got {values}"
    only = next(iter(values))
    assert only == 5


def test_baseline_slots_include_envase_zone(baseline: BaselinePlan) -> None:
    """The DR0027 carga ships envases, so we must allocate an envase
    slot in the baseline truck-load model."""
    envase_slots = [s for s in baseline.slot_assignments if s.is_envase_zone]
    assert len(envase_slots) == 1


def test_baseline_slots_sorted_lex(baseline: BaselinePlan) -> None:
    """Outbound slots are lex-sorted by Ubicación (mirrors picker walk)."""
    outbound = [s.slot_id for s in baseline.slot_assignments if not s.is_envase_zone]
    assert outbound == sorted(outbound)
    # First few should match the alphabetic warehouse layout.
    assert outbound[0].startswith("baseline-")


def test_baseline_inputs_loadable() -> None:
    """The data layer is reachable from the baseline module."""
    inputs = BaselineInputs.load()
    assert len(inputs.customers) > 1000
    assert len(inputs.products) > 1000
    assert len(inputs.time_windows) > 0
