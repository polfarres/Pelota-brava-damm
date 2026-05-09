"""FR-005: route optimisation (VRP with time windows).

We solve a single-vehicle TSP/VRP-TW that starts and ends at the depot.

Solver strategy:

1. Try ``ortools`` ``RoutingModel`` (cap wall-time at 30 s). Honour
   per-stop time windows when provided and apply an additive distance
   penalty proportional to the deviation from a baseline order — this
   is the soft *driver familiarity bias* (A-12).
2. If ``ortools`` isn't importable (e.g. on Python 3.14 where wheels
   may lag), fall back to a pure-Python nearest-neighbour from the
   depot followed by a single 2-opt improvement pass.

Distance / time matrix uses :func:`smart_truck.data.distance.build_matrix`
which already has OSRM with a haversine fallback. Times are in minutes.

Inputs and outputs are kept simple intentionally — the orchestrator in
:mod:`smart_truck.optimize.pipeline` is responsible for marshalling them
into / out of :class:`smart_truck.models.StopPlan`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Sequence

from smart_truck.data.distance import build_matrix, DistanceMatrix

try:  # pragma: no cover - import test
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    _HAS_ORTOOLS = True
except Exception:  # pragma: no cover - fallback path
    _HAS_ORTOOLS = False


Coord = tuple[float, float]


@dataclass
class RouteStop:
    """Input to the route solver — one delivery candidate."""

    customer_id: int
    lat: float
    lon: float
    ce_demand: float = 0.0
    time_window: tuple[time, time] | None = None
    service_time_min: float = 10.0


@dataclass
class RouteSolution:
    """Output of :func:`solve_route`."""

    ordered_customer_ids: list[int]
    etas: list[time | None]  # one per stop in route order
    total_km: float
    total_minutes: float
    backend: str  # "ortools" | "heuristic"
    matrix: DistanceMatrix | None = field(default=None)


# ---------------------------------------------------------------------------
# Familiarity penalty
# ---------------------------------------------------------------------------


def _familiarity_penalty_matrix(
    n: int,
    baseline_index: dict[int, int],
    n_stops: int,
    weight: float,
    depot_index: int = 0,
) -> list[list[float]]:
    """Build an additive penalty matrix that discourages deviating from a
    baseline ordering.

    The penalty has two components:

    - **Going-backwards penalty:** an arc ``i → j`` where
      ``rank[j] < rank[i]`` (visiting an earlier-baseline stop after a
      later one) is penalised by ``weight × (rank[i] - rank[j])``.
    - **Skipping penalty:** an arc ``i → j`` with ``rank[j] > rank[i] +
      1`` (skipping ahead) is penalised by
      ``weight × (rank[j] - rank[i] - 1)``.

    Arcs that match the baseline (rank[j] == rank[i] + 1) carry no
    penalty. The depot is treated as rank -1 so the first arc out of
    the depot is steered to the lowest-rank stop.
    """
    pen = [[0.0] * n for _ in range(n)]
    if not baseline_index or weight <= 0 or n_stops <= 1:
        return pen

    rank: dict[int, int] = dict(baseline_index)
    rank[depot_index] = -1  # depot anchors at the start
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            ri = rank.get(i)
            rj = rank.get(j)
            if ri is None or rj is None:
                continue
            if rj < ri:
                # Going backwards relative to baseline.
                pen[i][j] = weight * (ri - rj)
            elif rj > ri + 1:
                # Skipping forward.
                pen[i][j] = weight * (rj - ri - 1)
    return pen


def _add_matrices(
    a: list[list[float]], b: list[list[float]]
) -> list[list[float]]:
    n = len(a)
    return [[a[i][j] + b[i][j] for j in range(n)] for i in range(n)]


# ---------------------------------------------------------------------------
# Heuristic solver (NN + 2-opt) — used when OR-Tools is unavailable or as a
# robust fallback for tiny problems.
# ---------------------------------------------------------------------------


def _nn_order(cost: list[list[float]], start: int, customers: list[int]) -> list[int]:
    """Greedy nearest-neighbour from ``start`` over the indices in
    ``customers``. Returns the visit order (customers only, no depot)."""
    remaining = set(customers)
    order: list[int] = []
    cur = start
    while remaining:
        nxt = min(remaining, key=lambda j: cost[cur][j])
        order.append(nxt)
        remaining.discard(nxt)
        cur = nxt
    return order


def _route_cost(cost: list[list[float]], depot: int, order: list[int]) -> float:
    if not order:
        return 0.0
    total = cost[depot][order[0]]
    for a, b in zip(order, order[1:]):
        total += cost[a][b]
    total += cost[order[-1]][depot]
    return total


def _two_opt(cost: list[list[float]], depot: int, order: list[int]) -> list[int]:
    if len(order) < 4:
        return order
    improved = True
    best = list(order)
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for k in range(i + 1, len(best)):
                # Reverse the segment best[i:k+1]
                new = best[:i] + list(reversed(best[i:k + 1])) + best[k + 1:]
                if _route_cost(cost, depot, new) + 1e-9 < _route_cost(cost, depot, best):
                    best = new
                    improved = True
                    break
            if improved:
                break
    return best


def _heuristic_solve(
    cost: list[list[float]],
    depot_index: int,
    stop_indices: list[int],
) -> list[int]:
    """Returns route as a list of indices (excluding depot bookends)."""
    if not stop_indices:
        return []
    order = _nn_order(cost, depot_index, stop_indices)
    order = _two_opt(cost, depot_index, order)
    return order


# ---------------------------------------------------------------------------
# OR-Tools solver
# ---------------------------------------------------------------------------


def _ortools_solve(
    cost: list[list[float]],
    minutes: list[list[float]],
    depot_index: int,
    stops: list[RouteStop],
    capacity_ce: float | None,
    start_time: time,
    time_limit_s: int = 30,
) -> list[int] | None:
    """Run OR-Tools VRP-TW. Returns a route (list of matrix indices in
    visit order, excluding depot) or ``None`` if no solution found."""
    n = len(cost)
    manager = pywrapcp.RoutingIndexManager(n, 1, depot_index)
    routing = pywrapcp.RoutingModel(manager)

    # Cost (distance + familiarity penalty already baked into `cost`)
    SCALE = 1000

    def distance_cb(from_idx, to_idx):
        i = manager.IndexToNode(from_idx)
        j = manager.IndexToNode(to_idx)
        return int(round(cost[i][j] * SCALE))

    transit_cb = routing.RegisterTransitCallback(distance_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    # Time dimension — minutes since start_time.
    start_min = start_time.hour * 60 + start_time.minute

    def time_cb(from_idx, to_idx):
        i = manager.IndexToNode(from_idx)
        j = manager.IndexToNode(to_idx)
        travel = minutes[i][j]
        # Service time at the from-node (skip depot service time).
        if i == depot_index:
            service = 0.0
        else:
            stop = stops[i - 1] if i > depot_index else stops[i]
            # Map matrix index back to RouteStop:
            # depot is at depot_index=0 here; stops are 1..n-1
            service = stop.service_time_min if i != depot_index else 0.0
        return int(round(travel + service))

    time_cb_idx = routing.RegisterTransitCallback(time_cb)
    horizon = 24 * 60
    routing.AddDimension(
        time_cb_idx,
        horizon,  # max waiting
        horizon * 2,  # max time per vehicle
        False,  # don't force start cumul to zero
        "Time",
    )
    time_dim = routing.GetDimensionOrDie("Time")
    # Set vehicle start at start_min.
    index = routing.Start(0)
    time_dim.CumulVar(index).SetRange(start_min, start_min)

    # Apply per-stop time windows.
    for i, stop in enumerate(stops):
        if stop.time_window is None:
            continue
        node = i + 1 if depot_index == 0 else (i if i < depot_index else i + 1)
        idx = manager.NodeToIndex(node)
        s, e = stop.time_window
        s_min = s.hour * 60 + s.minute
        e_min = e.hour * 60 + e.minute
        if e_min < s_min:  # closed window — skip (don't enforce)
            continue
        time_dim.CumulVar(idx).SetRange(s_min, e_min)

    # Optional capacity dimension (single-vehicle, so this is mostly a
    # sanity guard; the load packer is the real arbiter of capacity).
    if capacity_ce is not None and capacity_ce > 0:
        SCALE_CE = 100

        def demand_cb(from_idx):
            i = manager.IndexToNode(from_idx)
            if i == depot_index:
                return 0
            stop = stops[i - 1] if i > depot_index else stops[i]
            return int(round(stop.ce_demand * SCALE_CE))

        demand_cb_idx = routing.RegisterUnaryTransitCallback(demand_cb)
        routing.AddDimensionWithVehicleCapacity(
            demand_cb_idx,
            0,
            [int(round(capacity_ce * SCALE_CE))],
            True,
            "Capacity",
        )

    # Search params.
    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_params.time_limit.seconds = time_limit_s

    solution = routing.SolveWithParameters(search_params)
    if solution is None:
        return None

    # Extract the route.
    index = routing.Start(0)
    route_nodes: list[int] = []
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if node != depot_index:
            route_nodes.append(node)
        index = solution.Value(routing.NextVar(index))
    return route_nodes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def solve_route(
    stops: Sequence[RouteStop],
    depot: Coord,
    *,
    capacity_ce: float | None = None,
    baseline_order: Sequence[int] | None = None,
    familiarity_weight: float = 0.0,
    start_time: time = time(8, 0),
    use_ortools: bool = True,
    time_limit_s: int = 30,
    prefer_osrm: bool = False,
) -> RouteSolution:
    """Solve a single-vehicle VRP with optional time windows.

    Args:
        stops: list of :class:`RouteStop`. The depot is **not** in this list.
        depot: ``(lat, lon)`` of the depot.
        capacity_ce: optional CE capacity for a soft VRP-capacity check.
            The packer (:mod:`load`) is the authoritative capacity arbiter.
        baseline_order: optional list of customer IDs in the as-is order
            for soft driver-familiarity bias (A-12).
        familiarity_weight: weight applied to deviations from
            ``baseline_order``. Same units as the distance cost (km).
            ``0`` disables the bias, large values pull strongly towards
            the baseline.
        start_time: wall-clock start of the day at the depot.
        use_ortools: ``False`` forces the heuristic fallback.
        time_limit_s: OR-Tools wall-time budget (default 30 s per FR-005).
        prefer_osrm: pass-through to :func:`build_matrix`. Default ``False``
            for fast unit tests.
    """
    if not stops:
        return RouteSolution(
            ordered_customer_ids=[],
            etas=[],
            total_km=0.0,
            total_minutes=0.0,
            backend="empty",
            matrix=None,
        )

    coords: list[Coord] = [depot] + [(s.lat, s.lon) for s in stops]
    matrix = build_matrix(coords, prefer_osrm=prefer_osrm)
    cost = [row[:] for row in matrix.km]

    # Apply familiarity penalty as an additive cost.
    n = len(coords)
    if baseline_order and familiarity_weight > 0:
        # Map customer_id -> baseline rank.
        rank = {cid: r for r, cid in enumerate(baseline_order)}
        baseline_index = {}
        for i, s in enumerate(stops):
            if s.customer_id in rank:
                baseline_index[i + 1] = rank[s.customer_id]
        pen = _familiarity_penalty_matrix(
            n, baseline_index, n_stops=len(stops),
            weight=familiarity_weight, depot_index=0,
        )
        cost = _add_matrices(cost, pen)

    depot_index = 0
    stop_indices = list(range(1, n))

    route_nodes: list[int] | None = None
    backend = "heuristic"
    if use_ortools and _HAS_ORTOOLS:
        try:
            route_nodes = _ortools_solve(
                cost,
                matrix.minutes,
                depot_index,
                list(stops),
                capacity_ce,
                start_time,
                time_limit_s=time_limit_s,
            )
            if route_nodes is not None:
                backend = "ortools"
        except Exception:  # pragma: no cover - safety net
            route_nodes = None

    if route_nodes is None:
        route_nodes = _heuristic_solve(cost, depot_index, stop_indices)
        backend = "heuristic"

    # Convert matrix indices → customer IDs and compute ETAs.
    ordered_ids = [stops[i - 1].customer_id for i in route_nodes]

    etas = _compute_etas(
        matrix, route_nodes, depot_index, list(stops), start_time
    )
    total_km = _route_cost(matrix.km, depot_index, route_nodes)
    total_minutes = _route_total_minutes(matrix.minutes, route_nodes, depot_index, list(stops))

    return RouteSolution(
        ordered_customer_ids=ordered_ids,
        etas=etas,
        total_km=total_km,
        total_minutes=total_minutes,
        backend=backend,
        matrix=matrix,
    )


def _compute_etas(
    matrix: DistanceMatrix,
    route_nodes: list[int],
    depot_index: int,
    stops: list[RouteStop],
    start_time: time,
) -> list[time | None]:
    """Forward-propagate arrival times along the route. Honour each stop's
    earliest-window-start by waiting at the curb."""
    etas: list[time | None] = []
    cur_minutes = start_time.hour * 60 + start_time.minute
    prev = depot_index
    for node in route_nodes:
        cur_minutes += matrix.minutes[prev][node]
        stop = stops[node - 1]
        if stop.time_window is not None:
            s, e = stop.time_window
            window_start = s.hour * 60 + s.minute
            if cur_minutes < window_start:
                cur_minutes = window_start
        # Snap to a valid time-of-day; if we go past 24h, clamp.
        h = int(cur_minutes // 60) % 24
        m = int(cur_minutes % 60)
        try:
            etas.append(time(h, m))
        except ValueError:
            etas.append(None)
        cur_minutes += stop.service_time_min
        prev = node
    return etas


def _route_total_minutes(
    minutes: list[list[float]],
    route_nodes: list[int],
    depot_index: int,
    stops: list[RouteStop],
) -> float:
    if not route_nodes:
        return 0.0
    total = minutes[depot_index][route_nodes[0]]
    for a, b in zip(route_nodes, route_nodes[1:]):
        total += minutes[a][b]
    total += minutes[route_nodes[-1]][depot_index]
    # add service times
    for n in route_nodes:
        total += stops[n - 1].service_time_min
    return total
