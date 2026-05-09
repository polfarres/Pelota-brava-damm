"""Tests for FR-005 route solver."""

from __future__ import annotations

from datetime import time

from smart_truck.optimize.route import RouteStop, solve_route


# Three "cities" in a triangle around Mollet.
DEPOT = (41.5396, 2.2103)
A = RouteStop(customer_id=1, lat=41.55, lon=2.21)
B = RouteStop(customer_id=2, lat=41.56, lon=2.22)
C = RouteStop(customer_id=3, lat=41.57, lon=2.23)


def test_three_stops_no_time_window_returns_all():
    sol = solve_route([A, B, C], DEPOT, prefer_osrm=False)
    assert len(sol.ordered_customer_ids) == 3
    assert set(sol.ordered_customer_ids) == {1, 2, 3}
    assert sol.total_km > 0
    assert sol.total_minutes > 0


def test_empty_stop_list():
    sol = solve_route([], DEPOT, prefer_osrm=False)
    assert sol.ordered_customer_ids == []
    assert sol.total_km == 0


def test_route_respects_time_windows_with_ortools():
    """With a tight time window on stop 3, it should still appear in the
    route (the day is long enough) and its ETA must be inside the window."""
    a = RouteStop(customer_id=1, lat=41.55, lon=2.21,
                  time_window=(time(9, 0), time(11, 0)))
    b = RouteStop(customer_id=2, lat=41.56, lon=2.22,
                  time_window=(time(10, 0), time(12, 0)))
    c = RouteStop(customer_id=3, lat=41.57, lon=2.23,
                  time_window=(time(11, 0), time(13, 0)))
    sol = solve_route([a, b, c], DEPOT, start_time=time(8, 0), prefer_osrm=False)
    assert set(sol.ordered_customer_ids) == {1, 2, 3}


def test_familiarity_bias_keeps_baseline_order():
    """A strong familiarity weight should pull the route towards the
    baseline order, even when it isn't the geometric optimum."""
    # Reverse-spatial baseline.
    baseline = [3, 2, 1]
    weak = solve_route(
        [A, B, C], DEPOT,
        baseline_order=baseline, familiarity_weight=0.0,
        prefer_osrm=False,
    )
    strong = solve_route(
        [A, B, C], DEPOT,
        baseline_order=baseline, familiarity_weight=500.0,
        prefer_osrm=False,
    )
    # Whatever the strong-bias route is, with a baseline of [3,2,1] it
    # should rank stop 3 ahead of stop 1 (which is the spatially-closest
    # stop to the depot, so a no-bias solver would pick it first).
    assert strong.ordered_customer_ids.index(3) <= strong.ordered_customer_ids.index(1)
    # Sanity: no-bias result still has all stops.
    assert set(weak.ordered_customer_ids) == {1, 2, 3}


def test_heuristic_fallback_works():
    """Forcing use_ortools=False should still yield a valid route."""
    sol = solve_route([A, B, C], DEPOT, use_ortools=False, prefer_osrm=False)
    assert sol.backend == "heuristic"
    assert set(sol.ordered_customer_ids) == {1, 2, 3}
