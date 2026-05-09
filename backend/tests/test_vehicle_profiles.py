"""Vehicle profile round-trip + structural validation (DR-008)."""

from __future__ import annotations

from smart_truck.domain.load_unit import LoadUnitClass
from smart_truck.domain.vehicle import AccessFace, CurtainAccess
from smart_truck.domain.vehicle_loader import load_all


def test_all_four_profiles_load() -> None:
    profiles = load_all()
    assert set(profiles) == {"FURGO_3P", "TRUCK_6P_SC", "TRUCK_8P_SC", "TRUCK_8P_LIFT"}


def test_fleet_counts_match_mentor_session() -> None:
    profiles = load_all()
    assert profiles["FURGO_3P"].fleet_count == 1
    assert profiles["TRUCK_6P_SC"].fleet_count == 11
    assert profiles["TRUCK_8P_SC"].fleet_count == 4
    assert profiles["TRUCK_8P_LIFT"].fleet_count == 4


def test_total_capacity_ce_matches_slot_sum() -> None:
    for profile in load_all().values():
        actual = sum(s.capacity_ce for s in profile.slots)
        assert profile.total_capacity_ce == actual, profile.profile_id


def test_furgo_topology_a32() -> None:
    p = load_all()["FURGO_3P"]
    p1, p2, p3 = p.slot("P1"), p.slot("P2"), p.slot("P3")
    assert p1.reachable_from == [AccessFace.LEFT]
    assert p2.reachable_from == [AccessFace.REAR]
    assert p3.reachable_from == [AccessFace.REAR]
    assert p2.blocked_by_per_face[AccessFace.REAR] == ["P3"]
    assert p3.blocked_by_per_face[AccessFace.REAR] == []
    assert p.lifo_order_per_face[AccessFace.REAR] == ["P3", "P2"]


def test_6p_partitioned_a33() -> None:
    p = load_all()["TRUCK_6P_SC"]
    assert p.access.curtain == CurtainAccess.BOTH_SIDES_PARTITIONED
    assert p.access.partition is True
    assert p.access.rear_doors is False
    left = {"P1", "P3", "P5"}
    right = {"P2", "P4", "P6"}
    for sid in left:
        assert p.slot(sid).reachable_from == [AccessFace.LEFT]
    for sid in right:
        assert p.slot(sid).reachable_from == [AccessFace.RIGHT]


def test_8p_lift_rear_blocking_a34() -> None:
    p = load_all()["TRUCK_8P_LIFT"]
    assert p.access.rear_lift is True
    p1 = p.slot("P1")
    assert AccessFace.REAR in p1.reachable_from
    assert p1.blocked_by_per_face[AccessFace.REAR] == ["P3", "P5", "P7"]
    p7 = p.slot("P7")
    assert p7.blocked_by_per_face[AccessFace.REAR] == []
    assert p.lifo_order_per_face[AccessFace.REAR] == [
        "P7", "P8", "P5", "P6", "P3", "P4", "P1", "P2",
    ]


def test_pallet_floor_capacity_is_60_ce_a31() -> None:
    for profile in load_all().values():
        for slot in profile.slots:
            assert slot.capacity_ce == 60.0, (profile.profile_id, slot.id)


def test_envase_zone_resolves() -> None:
    for profile in load_all().values():
        for sid in profile.envase_zone_slot_ids:
            profile.slot(sid)


def test_pallet_slots_accept_eur_pallet() -> None:
    for profile in load_all().values():
        for slot in profile.slots:
            assert LoadUnitClass.EUR_PALLET in slot.accepts, (
                profile.profile_id, slot.id,
            )
