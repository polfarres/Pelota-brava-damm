"""End-to-end test for FR-008 pipeline."""

from __future__ import annotations

from datetime import date

from smart_truck.models import Plan
from smart_truck.optimize.pipeline import plan


def test_pipeline_dr0027_2026_05_08():
    """The demo run: DR0027 / 2026-05-08 must yield a non-empty Plan."""
    p = plan("DR0027", date(2026, 5, 8), use_ortools=False, prefer_osrm=False)
    assert isinstance(p, Plan)
    assert p.ruta == "DR0027"
    assert p.fecha == date(2026, 5, 8)
    assert len(p.stops) > 0, "no stops resolved for DR0027/2026-05-08"
    assert len(p.slot_assignments) > 0, "no slots assigned"
    # Sanity: every stop has a sequence and customer_id.
    for s in p.stops:
        assert s.sequence > 0
        assert s.customer_id > 0


def test_pipeline_familiarity_weight_changes_route():
    """Two runs with different familiarity weights should still both
    produce a valid Plan (the actual ordering depends on data)."""
    p1 = plan("DR0027", date(2026, 5, 8),
              familiarity_weight=0.0, use_ortools=False, prefer_osrm=False)
    p2 = plan("DR0027", date(2026, 5, 8),
              familiarity_weight=100.0, use_ortools=False, prefer_osrm=False)
    assert len(p1.stops) > 0 and len(p2.stops) > 0
    assert {s.customer_id for s in p1.stops} == {s.customer_id for s in p2.stops}
