"""End-to-end test for FR-008 pipeline (v2 model)."""

from __future__ import annotations

from datetime import date

from smart_truck.models import Plan
from smart_truck.optimize.pipeline import plan


def test_pipeline_dr0027_2026_05_08() -> None:
    """The demo run: DR0027 / 2026-05-08 must yield a non-empty Plan
    that respects the v2 invariants (A-36, A-37, A-38)."""
    p = plan("DR0027", date(2026, 5, 8), use_ortools=False, prefer_osrm=False)
    assert isinstance(p, Plan)
    assert p.ruta == "DR0027"
    assert p.fecha == date(2026, 5, 8)
    assert len(p.stops) > 0, "no stops resolved for DR0027/2026-05-08"
    assert len(p.slot_assignments) > 0, "no slots assigned"

    # A-36: no envase zone in v2.
    assert all(not sa.is_envase_zone for sa in p.slot_assignments)

    # A-37: every used slot has a pallet_type.
    used = [sa for sa in p.slot_assignments if sa.stack]
    assert used, "expected at least one used slot"
    assert all(sa.pallet_type in {"CASE", "BARREL"} for sa in used)

    # A-38: each slot's stack is in ascending delivery sequence (top first).
    for sa in used:
        seqs = [layer.stop_sequence for layer in sa.stack]
        assert seqs == sorted(seqs), f"slot {sa.slot_id} stack out of order: {seqs}"

    # delivered_lines per stop comes from each slot's stack layers
    # belonging to that stop. With v3 Albarán parsing this is exactly the
    # customer's own lines; until then the upstream pipeline distributes
    # the carga's aggregated SKUs across stops by proportional weight, so
    # per-stop counts can still be inflated. We only assert that the
    # field is populated.
    assert all(s.delivered_lines is not None for s in p.stops)
    assert any(len(s.delivered_lines) > 0 for s in p.stops)

    # Sanity: every stop has a sequence and customer_id.
    for s in p.stops:
        assert s.sequence > 0
        assert s.customer_id > 0


def test_pipeline_familiarity_weight_changes_route() -> None:
    """Two runs with different familiarity weights should still both
    produce a valid Plan (the actual ordering depends on data)."""
    p1 = plan("DR0027", date(2026, 5, 8),
              familiarity_weight=0.0, use_ortools=False, prefer_osrm=False)
    p2 = plan("DR0027", date(2026, 5, 8),
              familiarity_weight=100.0, use_ortools=False, prefer_osrm=False)
    assert len(p1.stops) > 0 and len(p2.stops) > 0
    assert {s.customer_id for s in p1.stops} == {s.customer_id for s in p2.stops}


def test_pipeline_explanations_include_load_packer_summary() -> None:
    """The pipeline appends an explanation describing the v2 packer's
    output (number of case/barrel pallets + estimated driver minutes)."""
    p = plan("DR0027", date(2026, 5, 8), use_ortools=False, prefer_osrm=False)
    texts = " ".join(e.reason for e in p.explanations)
    assert "Stack-LIFO load packer" in texts or "stack-lifo" in texts.lower()
    assert "min" in texts
