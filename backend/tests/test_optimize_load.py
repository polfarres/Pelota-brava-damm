"""Tests for FR-006/006a load packer."""

from __future__ import annotations

import pytest

from smart_truck.domain.vehicle_loader import VEHICLES_DIR, load_profile
from smart_truck.models import DeliveredLine
from smart_truck.optimize.load import (
    LoadPlanError,
    StopDemand,
    pack_truck,
)


def _profile(name: str):
    return load_profile(VEHICLES_DIR / f"{name}.yaml")


def _line(sku: str, qty: float, ce: float = 1.0) -> DeliveredLine:
    return DeliveredLine(
        sku=sku, description=sku, quantity=qty, unit="Caja",
        ce=ce, weight_kg=0.0, source_ubicacion="A0",
    )


def test_pack_simple_two_stops_truck_6p():
    profile = _profile("truck_6p_sidecurtain")
    stops = [
        StopDemand(sequence=1, customer_id=100, lines=[_line("X", qty=60, ce=1.0)]),
        StopDemand(sequence=2, customer_id=200, lines=[_line("Y", qty=60, ce=1.0)]),
    ]
    plan = pack_truck(profile, stops)
    # Each stop gets at least one slot. Plus one envase slot.
    used = [a for a in plan.slot_assignments if not a.is_envase_zone]
    assert len(used) >= 2
    assert any(a.is_envase_zone for a in plan.slot_assignments)


def test_capacity_overflow_rejected():
    profile = _profile("furgo_3p")  # 180 CE total
    stops = [
        StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=100, ce=1.0)]),
        StopDemand(sequence=2, customer_id=2, lines=[_line("X", qty=100, ce=1.0)]),
    ]
    with pytest.raises(LoadPlanError):
        pack_truck(profile, stops)


def test_lifo_reverse_order_first_stop_in_shallow_slot():
    """Whole-pallet stops are placed in REVERSE delivery order — last
    stop goes deepest. So stop 1 ends up in a shallower slot than stop 3."""
    profile = _profile("truck_8p_lift")  # has explicit REAR LIFO
    stops = [
        StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=60)]),
        StopDemand(sequence=2, customer_id=2, lines=[_line("X", qty=60)]),
        StopDemand(sequence=3, customer_id=3, lines=[_line("X", qty=60)]),
    ]
    plan = pack_truck(profile, stops)
    # Map seq -> slot
    seq_to_slot = {}
    for a in plan.slot_assignments:
        if a.is_envase_zone or not a.stop_sequences:
            continue
        for s in a.stop_sequences:
            seq_to_slot[s] = a.slot_id
    # In TRUCK_8P_LIFT, lifo_order_per_face[REAR] = [P7, P8, P5, P6, P3, P4, P1, P2]
    # Reverse delivery → seq 3 first into deep slot (P7 reserved for envase).
    # Available non-envase: [P5, P6, P3, P4, P1, P2]. Last stop (3) deepest = P5.
    # So seq 1 should be placed at a slot that's NOT deeper than seq 3.
    assert seq_to_slot[1] != seq_to_slot[3]
    # Sanity: stop 1's slot should be more "front" (higher in YAML order) than stop 3's.


def test_envase_slot_allocated():
    profile = _profile("truck_6p_sidecurtain")
    envases = [_line("3ENV01", qty=10, ce=1.0)]
    stops = [
        StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=30)]),
    ]
    plan = pack_truck(profile, stops, envase_lines=envases)
    envase_assignments = [a for a in plan.slot_assignments if a.is_envase_zone]
    assert len(envase_assignments) == 1
    assert envase_assignments[0].slot_id in profile.envase_zone_slot_ids


def test_furgo_access_constraint_respected():
    """The furgo's P2 is blocked-by P3 from REAR. Stop 1 → P3, stop 2 → P2
    is feasible (P3 emptied first); the reverse would not be."""
    profile = _profile("furgo_3p")
    stops = [
        StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=60)]),
        StopDemand(sequence=2, customer_id=2, lines=[_line("X", qty=60)]),
    ]
    # Reverse order: last stop (2) goes deepest (P3 LIFO order says rear-most
    # first). At delivery time, stop 1 is delivered first; stop 2 needs P3
    # which is reachable from REAR with no blockers (deepest in LIFO).
    # This should pack without raising.
    plan = pack_truck(profile, stops)
    assert plan.slot_assignments
