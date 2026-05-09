"""KPI engine (FR-009).

Compares a :class:`BaselinePlan` with an optimised :class:`Plan` on the
five metrics in the spec (volume KPI dropped per A-11):

- ``total_km``                 — distance along the chosen sequence
                                 including the legs from / to the depot.
- ``total_minutes``            — travel time + per-stop service time.
- ``unload_minutes_estimated`` — service-time-per-stop summed, where
                                 ``service_time = 10 + 2 × zones_touched``
                                 minutes (A-06). The Smart packer
                                 reduces zones_touched to ~1, so this is
                                 where the operational saving shows up.
- ``in_truck_searches``        — sum of ``in_truck_zones_touched`` per
                                 stop. The total number of times the
                                 driver has to find an item inside the
                                 truck.
- ``space_utilisation_pct``    — ``Σ ce_used / Σ ce_capacity`` across
                                 the slot assignments. Higher is better.

Each delta is wrapped in a :class:`KpiDelta` whose ``is_improvement``
property knows the right direction.

Distance/time defaults to OSRM (real road routing); pass
``prefer_osrm=False`` in tests to use the haversine fallback and avoid
network calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .data.distance import DistanceMatrix, build_matrix
from .models import BaselinePlan, KpiDelta, Plan, SlotAssignment

# Mollet depot lat/lon — geocoded from the warehouse address (A-08).
MOLLET_DEPOT: tuple[float, float] = (41.5444, 2.2143)

DEFAULT_SPEED_KMH = 25.0  # urban + interurban blend
SERVICE_TIME_BASE_MIN = 10.0
SERVICE_TIME_PER_ZONE_MIN = 2.0


@dataclass
class KpiSummary:
    """The full set of KPI deltas plus the underlying per-plan numbers."""

    deltas: list[KpiDelta]
    baseline_metrics: dict[str, float] = field(default_factory=dict)
    proposed_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def by_metric(self) -> dict[str, KpiDelta]:
        return {d.metric: d for d in self.deltas}

    @property
    def improvement_count(self) -> int:
        return sum(1 for d in self.deltas if d.is_improvement)


def compute_kpis(
    baseline: BaselinePlan,
    plan: Plan,
    *,
    depot: tuple[float, float] = MOLLET_DEPOT,
    prefer_osrm: bool = True,
) -> KpiSummary:
    """Compute the five KPI deltas between baseline and the proposed plan."""
    base_metrics = measure(baseline, depot=depot, prefer_osrm=prefer_osrm)
    proposed_metrics = measure(plan, depot=depot, prefer_osrm=prefer_osrm)

    metrics = (
        "total_km",
        "total_minutes",
        "unload_minutes_estimated",
        "in_truck_searches",
        "space_utilisation_pct",
    )
    deltas = [
        KpiDelta(
            metric=m,  # type: ignore[arg-type]
            baseline=base_metrics[m],
            proposed=proposed_metrics[m],
        )
        for m in metrics
    ]
    return KpiSummary(
        deltas=deltas,
        baseline_metrics=base_metrics,
        proposed_metrics=proposed_metrics,
    )


def measure(
    plan: BaselinePlan | Plan,
    *,
    depot: tuple[float, float] = MOLLET_DEPOT,
    prefer_osrm: bool = True,
) -> dict[str, float]:
    """Compute the five metric values for one plan in isolation."""
    travel_km, travel_min = _route_travel(plan, depot=depot, prefer_osrm=prefer_osrm)
    unload_min = sum(
        SERVICE_TIME_BASE_MIN
        + SERVICE_TIME_PER_ZONE_MIN * stop.in_truck_zones_touched
        for stop in plan.stops
    )
    searches = float(sum(stop.in_truck_zones_touched for stop in plan.stops))
    space_util = _space_utilisation_pct(plan.slot_assignments)

    return {
        "total_km": travel_km,
        "total_minutes": travel_min + unload_min,
        "unload_minutes_estimated": unload_min,
        "in_truck_searches": searches,
        "space_utilisation_pct": space_util,
    }


def _route_travel(
    plan: BaselinePlan | Plan,
    *,
    depot: tuple[float, float],
    prefer_osrm: bool,
) -> tuple[float, float]:
    """Compute ``(km, minutes)`` along ``depot → stop_1 → … → stop_N → depot``.

    Stops without lat/lon are dropped from the route; the caller can see
    this as a low km if many stops are missing coords. Returns ``(0, 0)``
    when fewer than two points (depot + at least one stop) are usable.
    """
    coords: list[tuple[float, float]] = [depot]
    coords.extend(
        (stop.lat, stop.lon)
        for stop in plan.stops
        if stop.lat is not None and stop.lon is not None
    )
    coords.append(depot)

    # Need at least depot → 1 stop → depot to have any travel.
    if len(coords) < 3:
        return 0.0, 0.0

    matrix: DistanceMatrix = build_matrix(coords, prefer_osrm=prefer_osrm)
    total_km = sum(matrix.km[i][i + 1] for i in range(matrix.n - 1))
    total_min = sum(matrix.minutes[i][i + 1] for i in range(matrix.n - 1))
    return total_km, total_min


def _space_utilisation_pct(slots: list[SlotAssignment]) -> float:
    """``Σ ce_used / Σ ce_capacity`` × 100. ``0`` if no slots."""
    if not slots:
        return 0.0
    cap = sum(s.ce_capacity for s in slots)
    if cap == 0:
        return 0.0
    used = sum(s.ce_used for s in slots)
    return used / cap * 100.0
