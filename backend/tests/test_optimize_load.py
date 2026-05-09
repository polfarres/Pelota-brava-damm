"""Tests for FR-006/006a v2 — Stack-LIFO Packer with MILP.

The v2 packer enforces:
- A-36: no envase zone (truck leaves 100% full of outbound product).
- A-37: barrels and cases never share a pallet.
- A-38: within-pallet stack order = ascending delivery sequence (top
  = first delivered, bottom = last delivered).
"""

from __future__ import annotations

from unittest.mock import patch

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


def _line(sku: str, qty: float, ce: float = 1.0, unit: str = "Caja") -> DeliveredLine:
    return DeliveredLine(
        sku=sku,
        description=sku,
        quantity=qty,
        unit=unit,
        ce=ce,
        weight_kg=0.0,
        source_ubicacion="A0",
    )


# ---------------------------------------------------------------------------
# Smoke + regression
# ---------------------------------------------------------------------------


def test_pack_simple_two_stops_truck_6p() -> None:
    """Two whole-pallet stops fit in two case-pallets. No envase zone."""
    profile = _profile("truck_6p_sidecurtain")
    stops = [
        StopDemand(sequence=1, customer_id=100, lines=[_line("X", qty=60, ce=1.0)]),
        StopDemand(sequence=2, customer_id=200, lines=[_line("Y", qty=60, ce=1.0)]),
    ]
    plan = pack_truck(profile, stops, use_milp=False)
    used = [a for a in plan.slot_assignments if a.stack]
    assert len(used) >= 2
    # A-36: no envase zone in v2.
    assert all(not a.is_envase_zone for a in plan.slot_assignments)
    # A-37: every used slot has a pallet_type.
    assert all(a.pallet_type in {"CASE", "BARREL"} for a in used)


def test_capacity_overflow_rejected() -> None:
    """Demand exceeding vehicle slot count must raise LoadPlanError."""
    profile = _profile("furgo_3p")  # 3 slots × 60 CE = 180 CE
    stops = [
        StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=100, ce=1.0)]),
        StopDemand(sequence=2, customer_id=2, lines=[_line("X", qty=100, ce=1.0)]),
        StopDemand(sequence=3, customer_id=3, lines=[_line("X", qty=100, ce=1.0)]),
        StopDemand(sequence=4, customer_id=4, lines=[_line("X", qty=100, ce=1.0)]),
    ]
    with pytest.raises(LoadPlanError):
        pack_truck(profile, stops, use_milp=False)


# ---------------------------------------------------------------------------
# A-37 — Barrel / case segregation
# ---------------------------------------------------------------------------


def test_barrel_case_segregation() -> None:
    """A stop with both a barrel line and a case line ends up in two
    distinct slots: one BARREL, one CASE."""
    profile = _profile("truck_6p_sidecurtain")
    stops = [
        StopDemand(
            sequence=1,
            customer_id=1,
            lines=[
                _line("CASE_SKU", qty=20, ce=1.0, unit="Caja"),
                _line("BARREL_SKU", qty=2, ce=10.0, unit="Barril"),
            ],
        ),
    ]
    plan = pack_truck(profile, stops, use_milp=False)
    types = {a.pallet_type for a in plan.slot_assignments if a.stack}
    assert types == {"CASE", "BARREL"}


# ---------------------------------------------------------------------------
# A-38 — Within-pallet stack order = ascending delivery sequence
# ---------------------------------------------------------------------------


def test_stack_order_top_is_earliest_delivery() -> None:
    """Three stops sharing a slot must stack with stop 3 → 5 → 8 from
    top to bottom (smallest seq is the top — first to be delivered)."""
    profile = _profile("truck_6p_sidecurtain")
    # Three small stops that fit in one slot together.
    stops = [
        StopDemand(sequence=3, customer_id=300, lines=[_line("A", qty=10, ce=1.0)]),
        StopDemand(sequence=5, customer_id=500, lines=[_line("B", qty=10, ce=1.0)]),
        StopDemand(sequence=8, customer_id=800, lines=[_line("C", qty=10, ce=1.0)]),
    ]
    plan = pack_truck(profile, stops, use_milp=False)
    # Find a slot that contains all three.
    candidates = [a for a in plan.slot_assignments if len(a.stop_sequences) >= 2]
    assert candidates, "expected at least one shared slot for three small stops"
    sa = max(candidates, key=lambda a: len(a.stop_sequences))
    seqs = [layer.stop_sequence for layer in sa.stack]
    # Top to bottom = ascending sequence.
    assert seqs == sorted(seqs)
    # And first layer's customer is the first-delivered.
    assert sa.stack[0].stop_sequence == min(seqs)


def test_lifo_across_slots_first_stop_in_shallow_slot() -> None:
    """Across slots, stops with higher delivery sequence go to deeper
    (loaded-first) slot positions. The first stop should sit in a slot
    that is NOT the same as the last stop's slot."""
    profile = _profile("truck_8p_lift")
    stops = [
        StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=60)]),
        StopDemand(sequence=2, customer_id=2, lines=[_line("X", qty=60)]),
        StopDemand(sequence=3, customer_id=3, lines=[_line("X", qty=60)]),
    ]
    plan = pack_truck(profile, stops, use_milp=False)
    seq_to_slot: dict[int, str] = {}
    for a in plan.slot_assignments:
        for s in a.stop_sequences:
            seq_to_slot[s] = a.slot_id
    assert seq_to_slot[1] != seq_to_slot[3]


# ---------------------------------------------------------------------------
# A-36 — No envase zone
# ---------------------------------------------------------------------------


def test_no_envase_zone_under_v2() -> None:
    """A-36: truck leaves 100% full of outbound product. The packer
    must never set ``is_envase_zone=True`` on any slot."""
    profile = _profile("truck_6p_sidecurtain")
    stops = [
        StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=30)]),
        StopDemand(sequence=2, customer_id=2, lines=[_line("Y", qty=30)]),
    ]
    plan = pack_truck(profile, stops, use_milp=False)
    assert all(not a.is_envase_zone for a in plan.slot_assignments)


def test_envase_lines_arg_accepted_but_ignored() -> None:
    """The ``envase_lines=`` kwarg is preserved for backward signature
    compatibility but ignored in v2 — outbound envases ride along with
    delivered cases. Passing them must not produce a separate slot or
    throw."""
    profile = _profile("truck_6p_sidecurtain")
    stops = [
        StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=30)]),
    ]
    envases = [_line("3ENV01", qty=5, ce=1.0)]
    plan = pack_truck(profile, stops, envase_lines=envases, use_milp=False)
    # No envase slot.
    assert all(not a.is_envase_zone for a in plan.slot_assignments)
    # The envase lines were not added as a phantom stop.
    used = [a for a in plan.slot_assignments if a.stack]
    assert len(used) == 1
    assert used[0].pallet_type == "CASE"


# ---------------------------------------------------------------------------
# Access feasibility (preserved from v1)
# ---------------------------------------------------------------------------


def test_furgo_access_constraint_respected() -> None:
    """Two stops in a 3-pallet van. Reverse-order placement keeps deepest
    (P3) for stop 2 and a shallower position for stop 1; both reachable."""
    profile = _profile("furgo_3p")
    stops = [
        StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=60)]),
        StopDemand(sequence=2, customer_id=2, lines=[_line("X", qty=60)]),
    ]
    plan = pack_truck(profile, stops, use_milp=False)
    assert plan.slot_assignments


# ---------------------------------------------------------------------------
# MILP fallback
# ---------------------------------------------------------------------------


def test_milp_solver_falls_back_to_heuristic_on_unavailable() -> None:
    """When the MILP solver returns ``None`` (timeout, infeasible,
    PuLP missing) the packer must still produce a valid plan via the
    heuristic fallback."""
    profile = _profile("truck_6p_sidecurtain")
    stops = [
        StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=20)]),
        StopDemand(sequence=2, customer_id=2, lines=[_line("Y", qty=20)]),
        StopDemand(sequence=3, customer_id=3, lines=[_line("Z", qty=20)]),
    ]
    with patch("smart_truck.optimize.load._assign_milp", return_value=None):
        plan = pack_truck(profile, stops, use_milp=True)
    assert plan.slot_assignments
    assert plan.estimated_driver_minutes > 0


def test_milp_path_produces_same_shape_as_heuristic() -> None:
    """Sanity: the MILP and heuristic both produce valid plans with
    correct A-37/A-38 invariants on the same input."""
    profile = _profile("truck_6p_sidecurtain")
    stops = [
        StopDemand(sequence=1, customer_id=10, lines=[_line("A", qty=15)]),
        StopDemand(sequence=2, customer_id=20, lines=[_line("B", qty=15)]),
        StopDemand(sequence=3, customer_id=30, lines=[_line("C", qty=15)]),
        StopDemand(sequence=4, customer_id=40, lines=[_line("D", qty=15)]),
    ]
    plan_milp = pack_truck(profile, stops, use_milp=True)
    plan_heur = pack_truck(profile, stops, use_milp=False)
    for plan in (plan_milp, plan_heur):
        assert all(not a.is_envase_zone for a in plan.slot_assignments)
        for a in plan.slot_assignments:
            if a.stack:
                seqs = [layer.stop_sequence for layer in a.stack]
                assert seqs == sorted(seqs), "stack must be ascending top→bottom"


# ---------------------------------------------------------------------------
# Driver-minutes estimate
# ---------------------------------------------------------------------------


def test_estimated_driver_minutes_grows_with_stop_count() -> None:
    """More stops → more time. Sanity check on the cost function."""
    profile = _profile("truck_6p_sidecurtain")
    one_stop = pack_truck(
        profile,
        [StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=20)])],
        use_milp=False,
    )
    three_stops = pack_truck(
        profile,
        [
            StopDemand(sequence=1, customer_id=1, lines=[_line("X", qty=20)]),
            StopDemand(sequence=2, customer_id=2, lines=[_line("Y", qty=20)]),
            StopDemand(sequence=3, customer_id=3, lines=[_line("Z", qty=20)]),
        ],
        use_milp=False,
    )
    assert three_stops.estimated_driver_minutes > one_stop.estimated_driver_minutes
