"""FR-006/006a v2: Stack-LIFO Packer with MILP customer-to-pallet assignment.

The truck is modelled as a row of pallet positions (slots). Each slot is
typed as ``CASE`` or ``BARREL`` for the duration of the route (A-37) and
holds a vertical stack of customer cargo, with ≤60 caixes estadístiques
(CE) per pallet (A-31). The stack is ordered **top-to-bottom = first
delivered → last delivered** (A-38), so when the driver arrives at the
next stop, that stop's items sit at the top of the relevant pallet —
zero rotation in the typical case.

The truck **leaves Mollet 100% full of outbound product** (A-36); there
is no dedicated envase zone. Returns absorb opportunistically into the
freed space inside each pallet position as deliveries happen, and at
the locked 60% return rate (A-35) returns always fit (60% < 100% of
delivered volume).

## Pipeline

```
Phase 1  Categorise lines per stop into CASE vs BARREL (UoM-based, A-37)
Phase 2  Pallet-count budget — ceil(Σ CE / 60) per type
Phase 3  Assign physical slots to types (heuristic: barrels closer to
         access face; respect each slot's `accepts` list and the YAML's
         `lifo_order_per_face` if declared)
Phase 4  Customer→pallet assignment via MILP (PuLP/CBC, 10s timeout)
         — minimise total in-slot delivery-sequence spread
         — fall back to a reverse-sequential greedy heuristic on time-out
Phase 5  Within-pallet stack order = ascending delivery sequence
         (top = first delivered)
Phase 6  Verify access feasibility (re-uses v1 verify_access)
Phase 7  Estimate driver-minutes per stop:
         t = T_BASE + T_OPEN·pallets + T_ROT·rotations + T_PER_LINE·lines
```

Public surface preserved from v1:

- :func:`pack_truck`, :func:`verify_access`
- :class:`StopDemand`, :class:`LoadPlan`, :class:`LoadPlanError`
- ``CE_PER_PALLET`` constant

The ``envase_lines`` keyword arg of :func:`pack_truck` is now ignored
(A-36); kept for backward signature compat.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field, replace
from typing import Sequence

from smart_truck.domain.vehicle import Slot, VehicleProfile
from smart_truck.models import DeliveredLine, PalletType, SlotAssignment, StackEntry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CE_PER_PALLET = 60.0  # A-31
MILP_SOLVE_TIME_S = 10  # cap solver wall-time, fall back to heuristic

# UoM → pallet-type mapping (A-37). Hoja Carga units we've seen:
# "Caja", "Pack", "Botella", "Unidad", "Lat" → CASE
# "Barril", "Tubo" → BARREL
CASE_UNITS = frozenset({"Caja", "Pack", "Botella", "Unidad", "Lat"})
BARREL_UNITS = frozenset({"Barril", "Tubo"})

# Tier-1 staple SKUs: the "Estrella 1/3 cycle" — the full bottle going
# out and the empty crate coming back. Cross-route analysis of the
# Mar 2026 deliveries dataset shows these two SKUs alone hit 60-72%
# of stops on every analysed route every analysed day. Reserving a
# dedicated column lets the picker bring them as one warehouse wave
# and the driver pluck cases without rotating the rest of the pallet.
# (Discussed with team 2026-05-10; see /backend tools/staples_analysis.)
STAPLE_TIER1_SKUS = frozenset({"CJ13", "ED13"})

# Slots whose post-MILP ``ce_used`` falls below this threshold get
# fused into another partial of the same type during the warehouse-
# load-time rebalance. Once the truck leaves Mollet the layout is
# frozen — A-35 returns flow back into the same physical positions.
PARTIAL_PALLET_THRESHOLD_CE = 30.0


# ---------------------------------------------------------------------------
# Public dataclasses + errors
# ---------------------------------------------------------------------------


class LoadPlanError(Exception):
    """Raised when the carga is infeasible for the chosen vehicle."""


# Alias kept for callers that already use the more descriptive name.
LoadInfeasibleError = LoadPlanError


@dataclass
class StopDemand:
    """Per-stop demand input to :func:`pack_truck`."""

    sequence: int
    customer_id: int
    lines: list[DeliveredLine]

    @property
    def ce_total(self) -> float:
        return sum(l.ce * l.quantity for l in self.lines)


@dataclass
class LoadPlan:
    """Output of :func:`pack_truck`."""

    slot_assignments: list[SlotAssignment]
    pallet_equivalents_used: float
    total_capacity_ce: float
    estimated_driver_minutes: float = 0.0

    @property
    def utilisation_pct(self) -> float:
        if self.total_capacity_ce <= 0:
            return 0.0
        used = sum(sa.ce_used for sa in self.slot_assignments)
        return used / self.total_capacity_ce * 100.0


# ---------------------------------------------------------------------------
# Phase 1 — Type categorisation (A-37)
# ---------------------------------------------------------------------------


def _categorise_unit(unit: str) -> PalletType:
    """Map a Hoja Carga unit token to ``CASE`` or ``BARREL`` (A-37)."""
    if unit in BARREL_UNITS:
        return "BARREL"
    return "CASE"  # default for Caja/Pack/Botella/Unidad/Lat and unknowns


def _split_lines_by_type(
    lines: list[DeliveredLine],
) -> tuple[list[DeliveredLine], list[DeliveredLine]]:
    case_lines: list[DeliveredLine] = []
    barrel_lines: list[DeliveredLine] = []
    for ln in lines:
        if _categorise_unit(ln.unit) == "BARREL":
            barrel_lines.append(ln)
        else:
            case_lines.append(ln)
    return case_lines, barrel_lines


def _ce_total(lines: list[DeliveredLine]) -> float:
    return sum(l.ce * l.quantity for l in lines)


# ---------------------------------------------------------------------------
# Phase 2 + Phase 3 — Pallet budget and slot-type assignment
# ---------------------------------------------------------------------------


def _slot_order(profile: VehicleProfile) -> list[Slot]:
    """Slots in the order the packer should consume them.

    Prefer the longest-declared ``lifo_order_per_face`` (deepest-first);
    fall back to YAML order (front-to-back).
    """
    if profile.lifo_order_per_face:
        face, sequence = max(
            profile.lifo_order_per_face.items(),
            key=lambda kv: len(kv[1]),
        )
        by_id = {s.id: s for s in profile.slots}
        ordered = [by_id[sid] for sid in sequence if sid in by_id]
        seen = {s.id for s in ordered}
        ordered.extend(s for s in profile.slots if s.id not in seen)
        return ordered
    return list(profile.slots)


def _slot_accepts(slot: Slot, pallet_type: PalletType) -> bool:
    """Does this slot accept this pallet type?

    Slot.accepts lists ``LoadUnitClass`` enum members. We pull their
    ``.value`` if present (enum) or assume str. CASE compatibility is
    granted by ``EUR_PALLET / INDUSTRIAL_PALLET / CASE``; BARREL by
    ``BRL / KEG_FULL / KEG_EMPTY / TUBE``.
    """
    accepts = {a.value if hasattr(a, "value") else str(a) for a in slot.accepts}
    case_tags = {"EUR_PALLET", "INDUSTRIAL_PALLET", "CASE"}
    barrel_tags = {"BRL", "KEG_FULL", "KEG_EMPTY", "TUBE"}
    if pallet_type == "BARREL":
        return bool(accepts & barrel_tags)
    return bool(accepts & case_tags)


def _budget_and_assign_types(
    profile: VehicleProfile,
    stops: Sequence[StopDemand],
) -> tuple[dict[str, PalletType], float, float]:
    """Compute per-type CE totals, decide pallet counts, assign slot types.

    Returns ``(slot_type_map, total_case_ce, total_barrel_ce)`` where
    ``slot_type_map`` is keyed by ``Slot.id`` and only contains slots that
    are actually used in this route.

    Raises :class:`LoadPlanError` when the carga needs more pallets than
    the vehicle has, or when no compatible slots exist for the required
    pallet types.
    """
    total_case_ce = 0.0
    total_barrel_ce = 0.0
    for s in stops:
        for ln in s.lines:
            ce = ln.ce * ln.quantity
            if _categorise_unit(ln.unit) == "BARREL":
                total_barrel_ce += ce
            else:
                total_case_ce += ce

    n_case = math.ceil(total_case_ce / CE_PER_PALLET) if total_case_ce > 0 else 0
    n_barrel = math.ceil(total_barrel_ce / CE_PER_PALLET) if total_barrel_ce > 0 else 0
    n_total = n_case + n_barrel

    if n_total > len(profile.slots):
        raise LoadPlanError(
            f"Carga needs {n_total} pallets ({n_case} case + {n_barrel} barrel) "
            f"but {profile.profile_id} has only {len(profile.slots)}."
        )

    # Slot-type heuristic: place barrels in slots accessible from the
    # SHALLOW end (closer to the access face — barrels are heavy, the
    # driver lifts them out by hand). For the standard side-curtain
    # trucks this means we walk the lifo_order_per_face list IN REVERSE
    # (deepest-first list, so reversed = shallowest first) and pick the
    # first n_barrel slots that accept BARREL.
    slots_in_order = _slot_order(profile)
    barrel_candidates = [s for s in reversed(slots_in_order) if _slot_accepts(s, "BARREL")]
    chosen_barrel = barrel_candidates[:n_barrel]
    chosen_barrel_ids = {s.id for s in chosen_barrel}

    case_candidates = [
        s for s in slots_in_order
        if s.id not in chosen_barrel_ids and _slot_accepts(s, "CASE")
    ]
    chosen_case = case_candidates[:n_case]

    if len(chosen_barrel) < n_barrel:
        raise LoadPlanError(
            f"Need {n_barrel} barrel-accepting slots in {profile.profile_id}, "
            f"only {len(chosen_barrel)} found."
        )
    if len(chosen_case) < n_case:
        raise LoadPlanError(
            f"Need {n_case} case-accepting slots in {profile.profile_id}, "
            f"only {len(chosen_case)} found."
        )

    type_map: dict[str, PalletType] = {}
    for s in chosen_barrel:
        type_map[s.id] = "BARREL"
    for s in chosen_case:
        type_map[s.id] = "CASE"
    return type_map, total_case_ce, total_barrel_ce


# ---------------------------------------------------------------------------
# Phase 4 — Customer-to-pallet assignment (MILP + heuristic fallback)
# ---------------------------------------------------------------------------


@dataclass
class _VirtualCustomer:
    """A customer or a slice of a >60-CE customer.

    The MILP and heuristic operate on virtual customers so that every
    item fits in one pallet. Multiple virtual customers from the same
    real customer share their ``seq`` and ``customer_id`` and end up
    adjacent in the stack (same stop_sequence groups stack together).
    """

    seq: int
    customer_id: int
    pallet_type: PalletType
    ce: float
    lines: list[DeliveredLine] = field(default_factory=list)


def _split_large_customers(
    stops: Sequence[StopDemand],
    pallet_capacity: float = CE_PER_PALLET,
) -> list[_VirtualCustomer]:
    """Split each stop into per-type virtual customers, slicing if >60 CE."""
    out: list[_VirtualCustomer] = []
    for stop in stops:
        case_lines, barrel_lines = _split_lines_by_type(stop.lines)
        for ptype, lines in (("CASE", case_lines), ("BARREL", barrel_lines)):
            if not lines:
                continue
            ce = _ce_total(lines)
            if ce <= pallet_capacity + 1e-6:
                out.append(_VirtualCustomer(
                    seq=stop.sequence,
                    customer_id=stop.customer_id,
                    pallet_type=ptype,  # type: ignore[arg-type]
                    ce=ce,
                    lines=lines,
                ))
                continue

            # Need to slice. Walk lines, pack greedily up to pallet_capacity.
            running: list[DeliveredLine] = []
            running_ce = 0.0
            for ln in lines:
                line_ce = ln.ce * ln.quantity
                if running_ce + line_ce > pallet_capacity and running:
                    out.append(_VirtualCustomer(
                        seq=stop.sequence,
                        customer_id=stop.customer_id,
                        pallet_type=ptype,  # type: ignore[arg-type]
                        ce=running_ce,
                        lines=running,
                    ))
                    running, running_ce = [], 0.0
                running.append(ln)
                running_ce += line_ce
            if running:
                out.append(_VirtualCustomer(
                    seq=stop.sequence,
                    customer_id=stop.customer_id,
                    pallet_type=ptype,  # type: ignore[arg-type]
                    ce=running_ce,
                    lines=running,
                ))
    return out


def _assign_milp(
    customers: list[_VirtualCustomer],
    slot_types: dict[str, PalletType],
    pallet_capacity: float = CE_PER_PALLET,
    time_limit_s: int = MILP_SOLVE_TIME_S,
) -> dict[int, str] | None:
    """Solve customer→slot assignment as a MILP via PuLP/CBC.

    Variables:
        x[c, s] ∈ {0, 1}              c assigned to s  (only valid type pairs)
        seq_min[s], seq_max[s] ∈ ℝ≥0  in-slot sequence range
        pal[s] ∈ {0, 1}               slot used at all

    Constraints:
        Σ_s x[c, s] = 1                                ∀ c
        Σ_c ce[c]·x[c, s] ≤ 60                         ∀ s
        x[c, s] ≤ pal[s]                               ∀ c, s
        seq_max[s] ≥ seq(c)·x[c, s]                    ∀ c, s
        seq_min[s] ≤ seq(c) + M·(1 - x[c, s])          ∀ c, s

    Objective:
        minimise Σ_s (seq_max[s] - seq_min[s]) + 0.01·Σ_s pal[s]

    Returns ``{customer_index: slot_id}`` on success, or ``None`` if the
    solver is unavailable, infeasible, or didn't reach optimality within
    the time limit.
    """
    try:
        import pulp
    except ImportError:
        log.info("pulp unavailable; skipping MILP, will fall back to heuristic.")
        return None

    if not customers:
        return {}

    BIG_M = 10_000

    prob = pulp.LpProblem("stack_lifo_assignment", pulp.LpMinimize)

    x: dict[tuple[int, str], "pulp.LpVariable"] = {}
    for ci, cust in enumerate(customers):
        for sid, sptype in slot_types.items():
            if sptype != cust.pallet_type:
                continue
            x[(ci, sid)] = pulp.LpVariable(f"x_{ci}_{sid}", cat="Binary")

    pal = {sid: pulp.LpVariable(f"pal_{sid}", cat="Binary") for sid in slot_types}
    seq_min = {sid: pulp.LpVariable(f"smin_{sid}", lowBound=0) for sid in slot_types}
    seq_max = {sid: pulp.LpVariable(f"smax_{sid}", lowBound=0) for sid in slot_types}

    # 1. Each customer assigned to exactly one slot.
    for ci, cust in enumerate(customers):
        valid = [x[(ci, sid)] for sid in slot_types if (ci, sid) in x]
        if not valid:
            log.warning(
                "Customer %d (seq %d, %s) has no compatible slot; MILP infeasible.",
                ci, cust.seq, cust.pallet_type,
            )
            return None
        prob += pulp.lpSum(valid) == 1, f"assign_c{ci}"

    # 2. Capacity per slot.
    for sid in slot_types:
        prob += (
            pulp.lpSum(
                cust.ce * x[(ci, sid)]
                for ci, cust in enumerate(customers)
                if (ci, sid) in x
            )
            <= pallet_capacity,
            f"cap_{sid}",
        )

    # 3. Pal indicator.
    for (ci, sid), var in x.items():
        prob += var <= pal[sid], f"pal_{ci}_{sid}"

    # 4. seq_max linearisation.
    for (ci, sid), var in x.items():
        prob += seq_max[sid] >= customers[ci].seq * var, f"smax_{ci}_{sid}"

    # 5. seq_min linearisation.
    for (ci, sid), var in x.items():
        prob += (
            seq_min[sid] <= customers[ci].seq + BIG_M * (1 - var),
            f"smin_{ci}_{sid}",
        )

    # Force unused slots to spread = 0.
    for sid in slot_types:
        prob += seq_max[sid] <= BIG_M * pal[sid], f"smax_zero_{sid}"
        prob += seq_min[sid] <= BIG_M * pal[sid], f"smin_zero_{sid}"

    # Objective: spread minimisation + tiny penalty per pallet to break ties
    # in favour of using fewer pallets.
    prob += (
        pulp.lpSum(seq_max[sid] - seq_min[sid] for sid in slot_types)
        + 0.01 * pulp.lpSum(pal[sid] for sid in slot_types)
    )

    try:
        solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit_s)
        status = prob.solve(solver)
    except Exception as e:  # pragma: no cover  # noqa: BLE001
        log.warning("MILP solver crashed: %s", e)
        return None

    if status != pulp.LpStatusOptimal:
        log.info("MILP returned status %s; falling back.", pulp.LpStatus.get(status, status))
        return None

    assignment: dict[int, str] = {}
    for ci in range(len(customers)):
        chosen = None
        for sid in slot_types:
            v = x.get((ci, sid))
            if v is None:
                continue
            val = v.value()
            if val is not None and val > 0.5:
                chosen = sid
                break
        if chosen is None:
            log.warning("MILP solution missing customer %d; falling back.", ci)
            return None
        assignment[ci] = chosen
    return assignment


def _assign_heuristic(
    customers: list[_VirtualCustomer],
    slot_types: dict[str, PalletType],
    pallet_capacity: float = CE_PER_PALLET,
) -> dict[int, str]:
    """Reverse-sequential greedy: highest-seq customer placed first into
    the slot of matching type whose existing customers are closest in
    sequence (= tightest cluster). Open a new slot only when necessary.
    """
    indexed = sorted(enumerate(customers), key=lambda kv: -kv[1].seq)

    slot_load: dict[str, float] = {sid: 0.0 for sid in slot_types}
    slot_seqs: dict[str, list[int]] = {sid: [] for sid in slot_types}
    assignment: dict[int, str] = {}

    slots_of_type: dict[PalletType, list[str]] = {"CASE": [], "BARREL": []}
    for sid, ptype in slot_types.items():
        slots_of_type[ptype].append(sid)

    for ci, cust in indexed:
        candidates = []
        for sid in slots_of_type[cust.pallet_type]:
            if slot_load[sid] + cust.ce > pallet_capacity + 1e-6:
                continue
            existing = slot_seqs[sid]
            gap = min((abs(cust.seq - s) for s in existing), default=10**9)
            candidates.append((gap, sid))
        if not candidates:
            raise LoadPlanError(
                f"Heuristic: customer {cust.customer_id} (seq {cust.seq}, "
                f"{cust.ce:.1f} CE, {cust.pallet_type}) doesn't fit any slot."
            )
        # Prefer slots with existing customers (smaller gap); fall back to
        # opening an empty slot only when no partial slot has room.
        candidates.sort()
        sid = candidates[0][1]
        assignment[ci] = sid
        slot_load[sid] += cust.ce
        slot_seqs[sid].append(cust.seq)
    return assignment


def _assign_customers(
    customers: list[_VirtualCustomer],
    slot_types: dict[str, PalletType],
    pallet_capacity: float = CE_PER_PALLET,
    use_milp: bool = True,
    milp_time_limit_s: int = MILP_SOLVE_TIME_S,
) -> tuple[dict[int, str], str]:
    """Try MILP first, fall back to heuristic. Returns ``(assignment, backend)``."""
    if use_milp:
        result = _assign_milp(customers, slot_types, pallet_capacity, milp_time_limit_s)
        if result is not None:
            return result, "milp"
    return _assign_heuristic(customers, slot_types, pallet_capacity), "heuristic"


# ---------------------------------------------------------------------------
# Phase 5 + 6 — Materialise SlotAssignments with stack order
# ---------------------------------------------------------------------------


def _build_slot_assignments(
    customers: list[_VirtualCustomer],
    assignment: dict[int, str],
    slot_types: dict[str, PalletType],
    profile: VehicleProfile,
) -> list[SlotAssignment]:
    """Materialise SlotAssignments. Stack ordered TOP→BOTTOM by ascending
    delivery sequence (top = first delivered)."""
    by_id = {s.id: s for s in profile.slots}
    by_slot: dict[str, list[_VirtualCustomer]] = {}
    for ci, sid in assignment.items():
        by_slot.setdefault(sid, []).append(customers[ci])

    out: list[SlotAssignment] = []
    for sid, ptype in slot_types.items():
        slot = by_id[sid]
        custs = by_slot.get(sid, [])

        # Group virtual customers by stop_sequence (sliced large customers
        # share the same seq and stack as one logical layer).
        by_seq: dict[int, list[_VirtualCustomer]] = {}
        for c in custs:
            by_seq.setdefault(c.seq, []).append(c)
        seqs_sorted = sorted(by_seq.keys())  # ascending = top-first

        stack: list[StackEntry] = []
        flat_lines: list[DeliveredLine] = []
        ce_used = 0.0
        for seq in seqs_sorted:
            layer_lines: list[DeliveredLine] = []
            layer_ce = 0.0
            cust_id: int | None = None
            for vc in by_seq[seq]:
                cust_id = vc.customer_id
                layer_lines.extend(vc.lines)
                layer_ce += vc.ce
            assert cust_id is not None
            stack.append(StackEntry(
                stop_sequence=seq,
                customer_id=cust_id,
                ce=layer_ce,
                lines=layer_lines,
            ))
            flat_lines.extend(layer_lines)
            ce_used += layer_ce

        out.append(SlotAssignment(
            slot_id=sid,
            is_envase_zone=False,
            pallet_type=ptype,
            stack=stack,
            stop_sequences=seqs_sorted,
            contents=flat_lines,
            ce_used=ce_used,
            ce_capacity=slot.capacity_ce,
        ))
    return out


# ---------------------------------------------------------------------------
# Phase 6 — Access feasibility (re-used from v1, semantics unchanged)
# ---------------------------------------------------------------------------


def verify_access(
    profile: VehicleProfile,
    assignments: Sequence[SlotAssignment],
) -> None:
    """At every slot's first stop, at least one ``reachable_from`` face
    must have all its blockers already delivered. Raises
    :class:`LoadPlanError` on the first violation."""
    by_id = {s.id: s for s in profile.slots}
    slot_first: dict[str, int] = {}
    slot_last: dict[str, int] = {}
    for sa in assignments:
        if not sa.stop_sequences:
            continue
        slot_first[sa.slot_id] = min(sa.stop_sequences)
        slot_last[sa.slot_id] = max(sa.stop_sequences)

    for sa in assignments:
        if not sa.stop_sequences:
            continue
        slot = by_id.get(sa.slot_id)
        if slot is None:
            raise LoadPlanError(f"slot_id {sa.slot_id!r} not in profile")
        first = slot_first[sa.slot_id]
        ok = False
        for face in slot.reachable_from:
            blockers = slot.blocked_by_per_face.get(face, [])
            face_ok = True
            for b in blockers:
                blast = slot_last.get(b)
                if blast is not None and blast >= first:
                    face_ok = False
                    break
            if face_ok:
                ok = True
                break
        if not ok:
            raise LoadPlanError(
                f"Slot {slot.id} unreachable at stop {first}: all faces blocked."
            )


# ---------------------------------------------------------------------------
# Phase 7 — Driver-time estimate
# ---------------------------------------------------------------------------

# Constants are mentor-tunable; locked at A-06 baseline values for now.
T_BASE_MIN = 5.0
T_OPEN_MIN = 1.0           # per pallet curtain opened at this stop
T_ROT_MIN = 0.05           # per box-equivalent rotated aside
T_PER_LINE_MIN = 0.4       # per albarán line item


def _estimate_driver_minutes(
    stops: Sequence[StopDemand],
    slots: list[SlotAssignment],
) -> float:
    """t(stop) = T_BASE + T_OPEN·#pallets + T_ROT·rotations + T_PER_LINE·#lines.

    *Rotations* is the cumulative box-equivalent of empties from earlier-
    delivered customers sitting above this stop's items in shared
    pallets. Approximated as ``0.6 × CE`` of those earlier customers
    (60% return rate per A-35).
    """
    stop_to_slots: dict[int, list[str]] = {}
    for sa in slots:
        for seq in sa.stop_sequences:
            stop_to_slots.setdefault(seq, []).append(sa.slot_id)
    slot_by_id = {s.slot_id: s for s in slots}

    total = 0.0
    for stop in stops:
        slot_ids = stop_to_slots.get(stop.sequence, [])
        n_pallets = max(1, len(slot_ids))
        rotations = 0.0
        for sid in slot_ids:
            sa = slot_by_id[sid]
            for i, layer in enumerate(sa.stack):
                if layer.stop_sequence == stop.sequence:
                    for above in sa.stack[:i]:
                        if above.stop_sequence < stop.sequence:
                            rotations += above.ce * 0.6
                    break
        n_lines = len(stop.lines)
        total += (
            T_BASE_MIN
            + T_OPEN_MIN * n_pallets
            + T_ROT_MIN * rotations
            + T_PER_LINE_MIN * n_lines
        )
    return round(total, 2)


# ---------------------------------------------------------------------------
# Phase 0 — Staple extraction (Tier-1 SKUs reserve a dedicated column)
# ---------------------------------------------------------------------------


def _split_staples_from_stops(
    stops: Sequence[StopDemand],
) -> tuple[list[StopDemand], dict[int, tuple[int, list[DeliveredLine]]]]:
    """Pull Tier-1 staples out of each stop's lines.

    Returns ``(residual_stops, staples_per_stop)``:
    - ``residual_stops``: same stops, lines filtered to drop staples.
    - ``staples_per_stop``: ``stop_seq → (customer_id, staple_lines)``
      for stops that had staple SKUs (else not present).
    """
    residual: list[StopDemand] = []
    staples: dict[int, tuple[int, list[DeliveredLine]]] = {}
    for s in stops:
        keep: list[DeliveredLine] = []
        take: list[DeliveredLine] = []
        for ln in s.lines:
            (take if ln.sku in STAPLE_TIER1_SKUS else keep).append(ln)
        residual.append(StopDemand(sequence=s.sequence, customer_id=s.customer_id, lines=keep))
        if take:
            staples[s.sequence] = (s.customer_id, take)
    return residual, staples


def _build_staple_pallet(
    profile: VehicleProfile,
    staples_per_stop: dict[int, tuple[int, list[DeliveredLine]]],
    excluded_slot_ids: set[str],
) -> SlotAssignment | None:
    """Build the dedicated staple SlotAssignment.

    Picks the first CASE-compatible slot in the vehicle's curtain-
    accessible order that isn't already in ``excluded_slot_ids``, then
    stacks the staple lines per stop in delivery sequence order
    (top = first delivered, A-38 invariant).

    Returns ``None`` if there are no staple lines, the total CE exceeds
    one pallet (caller falls back to vanilla packing), or no eligible
    slot is available.
    """
    if not staples_per_stop:
        return None

    total_ce = sum(
        sum(l.ce * l.quantity for l in lines)
        for _, lines in staples_per_stop.values()
    )
    if total_ce <= 0 or total_ce > CE_PER_PALLET + 1e-6:
        return None

    candidate: Slot | None = None
    for slot in _slot_order(profile):
        if slot.id in excluded_slot_ids:
            continue
        if not _slot_accepts(slot, "CASE"):
            continue
        candidate = slot
        break
    if candidate is None:
        return None

    seqs = sorted(staples_per_stop.keys())
    stack: list[StackEntry] = []
    contents: list[DeliveredLine] = []
    ce_used = 0.0
    for seq in seqs:
        cid, lines = staples_per_stop[seq]
        layer_ce = sum(l.ce * l.quantity for l in lines)
        stack.append(StackEntry(
            stop_sequence=seq,
            customer_id=cid,
            ce=layer_ce,
            lines=list(lines),
        ))
        contents.extend(lines)
        ce_used += layer_ce

    return SlotAssignment(
        slot_id=candidate.id,
        is_envase_zone=False,
        pallet_type="CASE",
        stack=stack,
        stop_sequences=seqs,
        contents=contents,
        ce_used=ce_used,
        ce_capacity=candidate.capacity_ce,
    )


# ---------------------------------------------------------------------------
# Phase 6.5 — Warehouse-load-time rebalance of partial pallets
# ---------------------------------------------------------------------------


def _rebalance_partial_pallets(
    slots: list[SlotAssignment],
    threshold_ce: float = PARTIAL_PALLET_THRESHOLD_CE,
) -> list[SlotAssignment]:
    """Fuse near-empty pallets into others of the same type.

    Runs ONCE at warehouse load time. Once the truck is out, the layout
    is frozen (A-35 returns flow into freed top-of-stack space at the
    same physical position).

    Repeats until no partial pallet (``ce_used < threshold_ce``) can be
    merged into another non-empty pallet of matching type without
    breaking the 60-CE cap.
    """
    while True:
        merged_this_pass = False
        # Snapshot the partials list each pass since slots mutate.
        partials = [sa for sa in slots if sa.stack and sa.ce_used < threshold_ce]
        if len(partials) < 2 and not any(
            sa.stack and sa.ce_used < threshold_ce for sa in slots
        ):
            return slots

        for src in partials:
            if not src.stack:
                continue
            best_dst: SlotAssignment | None = None
            best_headroom = -1.0
            for dst in slots:
                if dst is src or not dst.stack:
                    continue
                if dst.pallet_type != src.pallet_type:
                    continue
                headroom = dst.ce_capacity - dst.ce_used
                if src.ce_used > headroom + 1e-6:
                    continue
                # Prefer the dst whose existing stops are closest in
                # sequence to src's — keeps tight LIFO clusters tight.
                if headroom > best_headroom:
                    best_headroom = headroom
                    best_dst = dst
            if best_dst is None:
                continue
            # Merge: append src layers, re-sort by stop_sequence ascending.
            merged_stack = sorted(
                best_dst.stack + src.stack,
                key=lambda e: e.stop_sequence,
            )
            best_dst.stack = merged_stack
            best_dst.contents = [ln for entry in merged_stack for ln in entry.lines]
            best_dst.stop_sequences = [e.stop_sequence for e in merged_stack]
            best_dst.ce_used = best_dst.ce_used + src.ce_used
            # Empty src.
            src.stack = []
            src.contents = []
            src.stop_sequences = []
            src.ce_used = 0.0
            merged_this_pass = True
            break

        if not merged_this_pass:
            return slots


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def pack_truck(
    profile: VehicleProfile,
    stops: Sequence[StopDemand],
    *,
    envase_lines: Sequence[DeliveredLine] = (),
    use_milp: bool = True,
    milp_time_limit_s: int = MILP_SOLVE_TIME_S,
    whole_pallet_threshold_ce: float = CE_PER_PALLET,
    use_staple_column: bool = True,
) -> LoadPlan:
    """Pack one truck end-to-end. The route order is the order of ``stops``
    (sequence ascending).

    ``envase_lines`` and ``whole_pallet_threshold_ce`` are accepted for
    backward signature compatibility with the v1 packer but are ignored
    under the v2 model (A-36): outbound envases ride along with the
    case-pallets they belong to, and there is no whole-pallet/partial
    distinction beyond the CE budget itself.

    When ``use_staple_column`` is true (default) the packer tries to
    extract :data:`STAPLE_TIER1_SKUS` into a dedicated curtain-side
    column before running the MILP on the remainder. If extraction
    isn't feasible (no slot, or staples > 60 CE) the packer falls
    back to packing everything together.
    """
    _ = envase_lines
    _ = whole_pallet_threshold_ce

    if not profile.slots:
        raise LoadPlanError(f"Vehicle {profile.profile_id} has no slots.")

    # Phase 0: try the staple-aware path first.
    staple_slot: SlotAssignment | None = None
    working_stops: Sequence[StopDemand] = stops
    if use_staple_column:
        residual_stops, staples_per_stop = _split_staples_from_stops(stops)
        if staples_per_stop:
            # Pre-select the staple slot and verify residual fits in the
            # remaining slots before committing to the split.
            ss = _build_staple_pallet(
                profile,
                staples_per_stop,
                excluded_slot_ids=set(),
            )
            if ss is not None:
                try:
                    _budget_and_assign_types(
                        _profile_excluding(profile, {ss.slot_id}),
                        residual_stops,
                    )
                except LoadPlanError:
                    # Residual won't fit if we steal a slot for staples;
                    # silently fall back to packing everything together.
                    log.info(
                        "Staple-aware split skipped: residual demand "
                        "doesn't fit in profile minus the staple slot."
                    )
                else:
                    # Residual fits — commit to the split.
                    staple_slot = ss
                    working_stops = residual_stops

    excluded = {staple_slot.slot_id} if staple_slot else set()
    working_profile = _profile_excluding(profile, excluded)
    type_map, total_case_ce, total_barrel_ce = _budget_and_assign_types(
        working_profile, working_stops
    )

    customers = _split_large_customers(working_stops, CE_PER_PALLET)
    if not customers and staple_slot is None:
        return LoadPlan(
            slot_assignments=[],
            pallet_equivalents_used=0.0,
            total_capacity_ce=profile.total_capacity_ce,
            estimated_driver_minutes=0.0,
        )

    if customers:
        assignment, backend = _assign_customers(
            customers,
            type_map,
            pallet_capacity=CE_PER_PALLET,
            use_milp=use_milp,
            milp_time_limit_s=milp_time_limit_s,
        )
        slots_out = _build_slot_assignments(customers, assignment, type_map, profile)
    else:
        backend = "skipped"
        slots_out = []

    # Phase 6.5: rebalance partial pallets ONCE before the truck leaves.
    slots_out = _rebalance_partial_pallets(slots_out)

    if staple_slot is not None:
        slots_out.insert(0, staple_slot)

    verify_access(profile, slots_out)
    driver_min = _estimate_driver_minutes(stops, slots_out)

    pallets_used = float(sum(1 for sa in slots_out if sa.stack))
    log.info(
        "pack_truck OK [%s] %s: %d pallets used (%d case + %d barrel%s), "
        "%.0f case-CE + %.0f barrel-CE, ~%.0f min driver time.",
        backend, profile.profile_id, int(pallets_used),
        sum(1 for ptype in type_map.values() if ptype == "CASE"),
        sum(1 for ptype in type_map.values() if ptype == "BARREL"),
        " + 1 staple column" if staple_slot else "",
        total_case_ce, total_barrel_ce, driver_min,
    )

    return LoadPlan(
        slot_assignments=slots_out,
        pallet_equivalents_used=pallets_used,
        total_capacity_ce=profile.total_capacity_ce,
        estimated_driver_minutes=driver_min,
    )


def _profile_excluding(profile: VehicleProfile, exclude: set[str]) -> VehicleProfile:
    """Return a shallow copy of ``profile`` with the named slots removed.

    Used to hide the reserved staple slot from the budget / MILP / type
    assignment so the residual demand only competes for the remaining
    physical positions.
    """
    if not exclude:
        return profile
    return replace(
        profile,
        slots=[s for s in profile.slots if s.id not in exclude],
        lifo_order_per_face={
            face: [sid for sid in order if sid not in exclude]
            for face, order in profile.lifo_order_per_face.items()
        },
    )
