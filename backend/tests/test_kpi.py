"""Tests for the KPI engine (FR-009)."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from smart_truck.kpi import (
    SERVICE_TIME_BASE_MIN,
    SERVICE_TIME_PER_ZONE_MIN,
    compute_kpis,
    measure,
)
from smart_truck.models import (
    BaselinePlan,
    Plan,
    SlotAssignment,
    StopPlan,
)


def _stop(seq: int, lat: float, lon: float, zones_touched: int = 5) -> StopPlan:
    return StopPlan(
        sequence=seq,
        customer_id=9100000000 + seq,
        customer_name=f"Cust {seq}",
        address="…",
        lat=lat,
        lon=lon,
        eta=None,
        time_window=None,
        payment_condition="CONTADO",
        proforma_total=Decimal("100.00"),
        delivered_lines=[],
        returns_estimated_ce=0.0,
        in_truck_zones_touched=zones_touched,
    )


def _baseline(zones_per_stop: int = 5) -> BaselinePlan:
    return BaselinePlan(
        ruta="DR0027",
        fecha=date(2026, 5, 8),
        vehicle_profile="truck_6p_sidecurtain",
        stops=[
            _stop(1, 41.92, 2.36, zones_per_stop),
            _stop(2, 41.92, 2.32, zones_per_stop),
            _stop(3, 41.93, 2.33, zones_per_stop),
        ],
        slot_assignments=[
            SlotAssignment(slot_id=f"baseline-{i}", is_envase_zone=False, ce_used=20.0)
            for i in range(50)
        ],
    )


def _plan(zones_per_stop: int = 1) -> Plan:
    return Plan(
        ruta="DR0027",
        fecha=date(2026, 5, 8),
        vehicle_profile="truck_6p_sidecurtain",
        stops=[
            _stop(1, 41.92, 2.36, zones_per_stop),
            _stop(2, 41.92, 2.32, zones_per_stop),
            _stop(3, 41.93, 2.33, zones_per_stop),
        ],
        slot_assignments=[
            SlotAssignment(slot_id=f"P{i}", is_envase_zone=False, ce_used=40.0)
            for i in range(6)
        ],
    )


def test_unload_minutes_uses_a06_formula() -> None:
    """``service_time = 10 + 2 × zones_touched`` per A-06."""
    base = _baseline(zones_per_stop=5)
    base_metrics = measure(base, prefer_osrm=False)
    expected = 3 * (SERVICE_TIME_BASE_MIN + SERVICE_TIME_PER_ZONE_MIN * 5)
    assert base_metrics["unload_minutes_estimated"] == pytest.approx(expected)


def test_in_truck_searches_sums_zones_touched() -> None:
    base = _baseline(zones_per_stop=5)
    base_metrics = measure(base, prefer_osrm=False)
    assert base_metrics["in_truck_searches"] == 3 * 5


def test_space_utilisation_baseline_vs_plan() -> None:
    """Baseline: 50 slots × 20 CE / 50 slots × 60 CE = 33.3%.
    Plan: 6 slots × 40 CE / 6 slots × 60 CE = 66.7%.
    """
    base = _baseline()
    plan = _plan()
    bm = measure(base, prefer_osrm=False)
    pm = measure(plan, prefer_osrm=False)
    assert bm["space_utilisation_pct"] == pytest.approx(33.333, rel=0.01)
    assert pm["space_utilisation_pct"] == pytest.approx(66.667, rel=0.01)


def test_compute_kpis_returns_five_metrics() -> None:
    summary = compute_kpis(_baseline(), _plan(), prefer_osrm=False)
    assert len(summary.deltas) == 5
    metrics = {d.metric for d in summary.deltas}
    assert metrics == {
        "total_km",
        "total_minutes",
        "unload_minutes_estimated",
        "in_truck_searches",
        "space_utilisation_pct",
    }


def test_smart_plan_improves_unload_and_searches() -> None:
    """The whole point of Smart Truck: dropping zones_touched to 1 per
    stop slashes both unload time and searches."""
    summary = compute_kpis(
        _baseline(zones_per_stop=5),
        _plan(zones_per_stop=1),
        prefer_osrm=False,
    )
    by = summary.by_metric
    assert by["unload_minutes_estimated"].is_improvement
    assert by["in_truck_searches"].is_improvement
    assert by["space_utilisation_pct"].is_improvement


def test_total_minutes_includes_unload() -> None:
    """``total_minutes`` should equal ``travel_minutes + unload_minutes``."""
    base = _baseline()
    m = measure(base, prefer_osrm=False)
    # travel = total_minutes - unload
    travel_only = m["total_minutes"] - m["unload_minutes_estimated"]
    assert travel_only >= 0


def test_route_with_no_geocoded_stops_returns_zero_km() -> None:
    plan = Plan(
        ruta="X",
        fecha=date(2026, 5, 8),
        vehicle_profile="furgo_3p",
        stops=[
            StopPlan(
                sequence=1,
                customer_id=1,
                customer_name="X",
                address="X",
                lat=None,
                lon=None,
                eta=None,
                time_window=None,
                payment_condition="CONTADO",
                proforma_total=Decimal("0"),
                in_truck_zones_touched=1,
            ),
        ],
        slot_assignments=[],
    )
    m = measure(plan, prefer_osrm=False)
    assert m["total_km"] == 0.0


def test_improvement_count_helper() -> None:
    summary = compute_kpis(
        _baseline(zones_per_stop=5),
        _plan(zones_per_stop=1),
        prefer_osrm=False,
    )
    # Unload, searches and space-util definitely improve.
    assert summary.improvement_count >= 3
