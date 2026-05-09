"""FR-006/006a: hybrid load packer with vehicle access constraints.

Heuristic packer (no ILP). The flow is:

1. For each stop, compute the demanded :class:`DeliveredLine` items and
   the resulting CE total. Stops with CE ≥ a "whole-pallet" threshold
   (default 50 CE) are *whole-pallet stops*; the rest are *partial*.
2. Iterate the route in **reverse delivery order** and place whole-pallet
   stops onto truck slots, deepest-first (LIFO) — that is, the *last*
   stop's pallet goes into the slot that is hardest to reach. We pick
   slot order using each profile's ``lifo_order_per_face`` if present;
   otherwise we fall back to the order the slots appear in the YAML
   (which the YAML files already lay out front-to-back).
3. Reserve trailing slot(s) flagged ``envase_zone_slot_ids`` for envases
   (mark ``is_envase_zone=True``).
4. Pack partial stops onto remaining slots (consolidator pallets). Each
   consolidator carries a contiguous group of partials in route order;
   inside, lines are grouped by SKU.
5. Verify access feasibility: at every stop's turn, the slots assigned
   to it must be reachable through at least one of their declared
   ``reachable_from`` faces, given that no upstream-not-yet-delivered
   slot blocks the view (per ``blocked_by_per_face``).

The packer is deliberately simple. If a placement violates capacity or
access, we raise :class:`LoadPlanError` and let the caller (the
pipeline) widen its options (e.g. fall back to a smaller vehicle, or
retry the route with a different ordering).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from smart_truck.domain.vehicle import (
    Slot,
    VehicleProfile,
)
from smart_truck.models import DeliveredLine, SlotAssignment


CE_PER_PALLET = 60.0  # A-31
WHOLE_PALLET_CE_THRESHOLD = 50.0  # Anything ≥ this is treated as whole-pallet


class LoadPlanError(Exception):
    """Raised when the carga is infeasible for the chosen vehicle."""


@dataclass
class StopDemand:
    """Per-stop demand input to the packer."""

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

    @property
    def utilisation_pct(self) -> float:
        if self.total_capacity_ce <= 0:
            return 0.0
        used = sum(sa.ce_used for sa in self.slot_assignments)
        return used / self.total_capacity_ce * 100.0


# ---------------------------------------------------------------------------
# Slot ordering helpers
# ---------------------------------------------------------------------------


def _slot_order(profile: VehicleProfile) -> list[Slot]:
    """Return slots in the order the packer should consume them.

    Heuristic: prefer the LIFO order of the profile's primary access
    face (REAR if present, otherwise the first face that appears in any
    slot's ``reachable_from``). If no LIFO order is declared, fall back
    to the order slots appear in the YAML (front-to-back).
    """
    if profile.lifo_order_per_face:
        # Pick the longest declared LIFO list; that's typically the one
        # the planner cares most about (e.g. REAR for the lift truck).
        face, sequence = max(
            profile.lifo_order_per_face.items(),
            key=lambda kv: len(kv[1]),
        )
        by_id = {s.id: s for s in profile.slots}
        ordered = [by_id[sid] for sid in sequence if sid in by_id]
        # Append any remaining slots not in the lifo list.
        seen = {s.id for s in ordered}
        ordered.extend(s for s in profile.slots if s.id not in seen)
        return ordered
    return list(profile.slots)


def _envase_slots(profile: VehicleProfile) -> list[Slot]:
    """Slots earmarked as envase zone (FR-006: reserved for empties)."""
    by_id = {s.id: s for s in profile.slots}
    return [by_id[sid] for sid in profile.envase_zone_slot_ids if sid in by_id]


# ---------------------------------------------------------------------------
# Access feasibility
# ---------------------------------------------------------------------------


def _stop_first_assigned_to(
    slot_id: str, slot_to_first_stop: dict[str, int]
) -> int | None:
    return slot_to_first_stop.get(slot_id)


def verify_access(
    profile: VehicleProfile,
    assignments: Sequence[SlotAssignment],
) -> None:
    """Check that each slot used by stop *N* is reachable when its turn
    comes — i.e. through at least one face whose ``blocked_by_per_face``
    blockers have all already been delivered (their last stop_sequence
    ≤ the current slot's first stop_sequence).

    Raises :class:`LoadPlanError` on the first violation.
    """
    by_id = {s.id: s for s in profile.slots}
    # When does each slot first need to be touched?
    slot_first_stop: dict[str, int] = {}
    slot_last_stop: dict[str, int] = {}
    for sa in assignments:
        if not sa.stop_sequences:
            continue
        slot_first_stop[sa.slot_id] = min(sa.stop_sequences)
        slot_last_stop[sa.slot_id] = max(sa.stop_sequences)

    for sa in assignments:
        if not sa.stop_sequences:
            continue
        slot = by_id.get(sa.slot_id)
        if slot is None:
            raise LoadPlanError(f"slot_id {sa.slot_id!r} not in profile")
        first_touch = slot_first_stop[sa.slot_id]

        # At least one reachable face must be unblocked by first_touch.
        ok = False
        for face in slot.reachable_from:
            blockers = slot.blocked_by_per_face.get(face, [])
            face_ok = True
            for b in blockers:
                blast = slot_last_stop.get(b)
                # Blocker is empty (unused) OR fully delivered before our turn.
                if blast is not None and blast >= first_touch:
                    face_ok = False
                    break
            if face_ok:
                ok = True
                break
        if not ok:
            raise LoadPlanError(
                f"Slot {slot.id} is unreachable at stop {first_touch}: "
                f"all faces blocked by un-emptied neighbours."
            )


# ---------------------------------------------------------------------------
# Packer
# ---------------------------------------------------------------------------


def _pack_lines_into_slot(lines: list[DeliveredLine]) -> tuple[list[DeliveredLine], float]:
    """Group lines by SKU (sum quantities) and return the consolidated list
    plus total CE."""
    by_sku: dict[str, DeliveredLine] = {}
    total_ce = 0.0
    for ln in lines:
        total_ce += ln.ce * ln.quantity
        existing = by_sku.get(ln.sku)
        if existing is None:
            by_sku[ln.sku] = ln
        else:
            # Merge: same SKU, sum quantities; keep first description/unit.
            by_sku[ln.sku] = DeliveredLine(
                sku=existing.sku,
                description=existing.description,
                quantity=existing.quantity + ln.quantity,
                unit=existing.unit,
                ce=existing.ce,
                weight_kg=existing.weight_kg + ln.weight_kg * (ln.quantity / max(ln.quantity, 1)),
                source_ubicacion=existing.source_ubicacion,
            )
    return list(by_sku.values()), total_ce


def pack_truck(
    profile: VehicleProfile,
    stops: Sequence[StopDemand],
    *,
    envase_lines: Sequence[DeliveredLine] = (),
    whole_pallet_threshold_ce: float = WHOLE_PALLET_CE_THRESHOLD,
) -> LoadPlan:
    """Pack one truck. Returns a :class:`LoadPlan` with slot assignments.

    The route order is the order of ``stops`` (sequence ascending).
    """
    # Validate capacity first.
    total_demand_ce = sum(s.ce_total for s in stops) + sum(
        l.ce * l.quantity for l in envase_lines
    )
    if total_demand_ce > profile.total_capacity_ce + 1e-6:
        raise LoadPlanError(
            f"Carga {total_demand_ce:.1f} CE exceeds {profile.profile_id} "
            f"capacity {profile.total_capacity_ce:.1f} CE."
        )

    slot_order = _slot_order(profile)
    envase_ids = set(profile.envase_zone_slot_ids)

    # Reserve envase slots (peeled off the slot pool from the back).
    available_slots = [s for s in slot_order if s.id not in envase_ids]
    reserved_envase_slots = [s for s in slot_order if s.id in envase_ids]

    # Split into whole-pallet vs partial stops.
    whole = [s for s in stops if s.ce_total >= whole_pallet_threshold_ce]
    partial = [s for s in stops if s.ce_total < whole_pallet_threshold_ce]

    assignments: list[SlotAssignment] = []
    used_slot_ids: set[str] = set()

    # 1. Whole-pallet stops in REVERSE delivery order — last stop in first
    #    (so it ends up in the deepest, hardest-to-reach slot).
    deep_slots = list(available_slots)  # iterate from index 0 = deepest
    for stop in sorted(whole, key=lambda s: -s.sequence):
        if not deep_slots:
            raise LoadPlanError(
                f"No remaining slot for whole-pallet stop {stop.sequence}."
            )
        # Find first slot(s) that haven't been used and which can host the pallet.
        remaining_ce = stop.ce_total
        # We may need multiple slots for stops above 60 CE.
        slots_for_stop: list[Slot] = []
        while remaining_ce > 0 and deep_slots:
            slot = deep_slots.pop(0)
            slots_for_stop.append(slot)
            remaining_ce -= slot.capacity_ce
        if remaining_ce > 1e-6:
            raise LoadPlanError(
                f"Stop {stop.sequence} demands {stop.ce_total:.1f} CE; not "
                f"enough slot capacity remaining."
            )

        # Distribute lines proportionally across the slots for this stop
        # (simple split: pack full slots first, leftover into the last).
        consolidated, total_ce = _pack_lines_into_slot(list(stop.lines))
        # Trivial split: keep all lines in the first slot, pad others if
        # the stop spans > 1 slot. The actual line→slot allocation only
        # matters for visualisation — the access-feasibility check uses
        # stop_sequences, not contents.
        first = True
        for slot in slots_for_stop:
            assignments.append(
                SlotAssignment(
                    slot_id=slot.id,
                    is_envase_zone=False,
                    stop_sequences=[stop.sequence],
                    contents=consolidated if first else [],
                    ce_used=min(slot.capacity_ce, stop.ce_total) if first else max(
                        0.0, stop.ce_total - sum(a.ce_used for a in assignments[-len(slots_for_stop):-1] if a.slot_id != slot.id)
                    ),
                    ce_capacity=slot.capacity_ce,
                )
            )
            used_slot_ids.add(slot.id)
            first = False

    # 2. Pack partial stops onto consolidator pallets — group contiguous
    #    runs in route order. We size each group so that, even if the
    #    aggregate slightly exceeds 60 CE, partial stops are physically
    #    cases stacked onto a 'consolidator pallet' (mentor: dispatchers
    #    routinely overload consolidators by ~10%). When we run out of
    #    delivery slots, we fall back to merging the remainder into the
    #    last consolidator (it'll be over-pack but at least feasible).
    if partial:
        partial.sort(key=lambda s: s.sequence)

        # Compute target number of consolidator slots based on remaining
        # capacity. We have len(deep_slots) slots available.
        n_slots = max(1, len(deep_slots))
        total_partial_ce = sum(s.ce_total for s in partial)
        target_per_slot = max(CE_PER_PALLET, total_partial_ce / n_slots * 1.05)

        consolidators: list[list[StopDemand]] = []
        cur_group: list[StopDemand] = []
        cur_ce = 0.0
        for stop in partial:
            if (
                cur_ce + stop.ce_total > target_per_slot
                and cur_group
                and len(consolidators) < n_slots - 1
            ):
                consolidators.append(cur_group)
                cur_group = []
                cur_ce = 0.0
            cur_group.append(stop)
            cur_ce += stop.ce_total
        if cur_group:
            consolidators.append(cur_group)

        # Place consolidators in reverse delivery order (the consolidator
        # whose last stop has the highest sequence goes deepest).
        consolidators.sort(
            key=lambda group: -max(s.sequence for s in group)
        )
        for group in consolidators:
            if not deep_slots:
                # Should be unreachable with the n_slots cap above, but
                # if it happens, fall back to merging into the last
                # consolidator placement.
                if not assignments:
                    raise LoadPlanError(
                        f"No remaining slot for consolidator pallet covering "
                        f"stops {[s.sequence for s in group]}."
                    )
                # Merge into the most-recently-added partial assignment.
                last = assignments[-1]
                all_lines = list(last.contents)
                for stop in group:
                    all_lines.extend(stop.lines)
                consolidated, total_ce = _pack_lines_into_slot(all_lines)
                last.contents = consolidated
                last.ce_used = total_ce
                last.stop_sequences = sorted(
                    set(last.stop_sequences) | {s.sequence for s in group}
                )
                continue
            slot = deep_slots.pop(0)
            all_lines = []
            for stop in group:
                all_lines.extend(stop.lines)
            consolidated, total_ce = _pack_lines_into_slot(all_lines)
            assignments.append(
                SlotAssignment(
                    slot_id=slot.id,
                    is_envase_zone=False,
                    stop_sequences=sorted(s.sequence for s in group),
                    contents=consolidated,
                    ce_used=total_ce,
                    ce_capacity=slot.capacity_ce,
                )
            )
            used_slot_ids.add(slot.id)

    # 3. Envase slot — always include at least one envase assignment so
    #    the returns tracker has somewhere to dump empties.
    if reserved_envase_slots:
        envase_slot = reserved_envase_slots[-1]
        envase_consolidated, envase_ce = _pack_lines_into_slot(list(envase_lines))
        assignments.append(
            SlotAssignment(
                slot_id=envase_slot.id,
                is_envase_zone=True,
                stop_sequences=[],  # envase is empty at start; fills as route progresses
                contents=envase_consolidated,
                ce_used=envase_ce,
                ce_capacity=envase_slot.capacity_ce,
            )
        )
        used_slot_ids.add(envase_slot.id)

    # 4. Verify access feasibility (skip envase slot — empty at start).
    deliverable = [a for a in assignments if not a.is_envase_zone]
    verify_access(profile, deliverable)

    # Sort assignments by slot id (stable, for output consistency).
    assignments.sort(key=lambda a: a.slot_id)

    pallet_equivalents = sum(s.ce_total for s in stops) / CE_PER_PALLET
    return LoadPlan(
        slot_assignments=assignments,
        pallet_equivalents_used=pallet_equivalents,
        total_capacity_ce=profile.total_capacity_ce,
    )
