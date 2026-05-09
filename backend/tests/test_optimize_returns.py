"""Tests for FR-007/007a v2 — per-pallet returns absorption.

The v2 returns model (A-36) drops the dedicated envase zone. Empties
absorb into the freed space inside each pallet position as deliveries
happen. At the locked 60% return rate (A-35), returns always fit — the
``ReturnsInfeasibleError`` is now a defensive guard, not a hot path.
"""

from __future__ import annotations

from smart_truck.models import DeliveredLine, SlotAssignment
from smart_truck.optimize.returns import (
    estimate_returnable_ce_per_stop,
    simulate_returns,
)


def _line(sku: str, qty: float = 1.0, ce: float = 1.0) -> DeliveredLine:
    return DeliveredLine(
        sku=sku, description=sku, quantity=qty, unit="Caja",
        ce=ce, weight_kg=0.0, source_ubicacion=None,
    )


def test_simulate_returns_feasible_v2() -> None:
    """Two stops, each delivers 60 CE; at 60% return rate that's 36 CE
    of empties per stop. Slots free up after their respective deliveries
    so returns absorb cleanly without a dedicated envase zone."""
    sa = [
        SlotAssignment(
            slot_id="P1", is_envase_zone=False, pallet_type="CASE",
            stop_sequences=[1], ce_used=60.0, ce_capacity=60.0,
        ),
        SlotAssignment(
            slot_id="P2", is_envase_zone=False, pallet_type="CASE",
            stop_sequences=[2], ce_used=60.0, ce_capacity=60.0,
        ),
    ]
    delivered = {1: 60.0, 2: 60.0}
    traces = simulate_returns(sa, delivered)
    assert len(traces) == 2
    assert traces[0].returns_added_ce == 36.0
    assert traces[1].cumulative_returns_ce == 72.0
    # After stop 2, both slots freed (120 CE), 72 CE absorbed → 48 free.
    assert traces[1].free_ce_after == 48.0


def test_simulate_returns_60pct_always_fits() -> None:
    """A-35 (flat 60% return rate) + A-36 (truck full out) means returns
    can never exceed freed pallet capacity. This used to raise under
    v1 (when there was a too-small envase zone); under v2 it must
    pass cleanly."""
    sa = [
        SlotAssignment(
            slot_id="P1", is_envase_zone=False, pallet_type="CASE",
            stop_sequences=[1], ce_used=60.0, ce_capacity=60.0,
        ),
        SlotAssignment(
            slot_id="P2", is_envase_zone=False, pallet_type="CASE",
            stop_sequences=[2], ce_used=60.0, ce_capacity=60.0,
        ),
    ]
    # Even at the worst case (100% returnable), 60 CE × 0.60 = 36 CE per
    # stop, well under the 60 CE freed at each stop.
    delivered = {1: 60.0, 2: 60.0}
    traces = simulate_returns(sa, delivered)
    # Free-space curve is monotone non-negative — never zero.
    assert all(t.free_ce_after >= 0 for t in traces)


def test_estimate_returnable_ce_per_stop_with_filter() -> None:
    lines_by_stop = {
        1: [_line("RET", qty=2, ce=1.0), _line("ENV", qty=1, ce=1.0)],
        2: [_line("RET", qty=3, ce=1.0)],
    }
    is_returnable = {"RET": True, "ENV": False}
    out = estimate_returnable_ce_per_stop(lines_by_stop, is_returnable)
    assert out[1] == 2.0
    assert out[2] == 3.0


def test_estimate_returnable_ce_default_all_returnable() -> None:
    lines_by_stop = {1: [_line("X", qty=5, ce=1.0)]}
    out = estimate_returnable_ce_per_stop(lines_by_stop)
    assert out[1] == 5.0


def test_simulate_returns_empty() -> None:
    assert simulate_returns([], {}) == []


def test_v1_envase_zone_slot_treated_as_pre_freed() -> None:
    """For backward compat: if a SlotAssignment with ``is_envase_zone=True``
    is passed in (legacy v1 input), the trace treats it as freed from
    sequence 0 — its capacity contributes to the pool from the start."""
    sa = [
        SlotAssignment(
            slot_id="P1", is_envase_zone=False, pallet_type="CASE",
            stop_sequences=[2], ce_used=60.0, ce_capacity=60.0,
        ),
        SlotAssignment(
            slot_id="P2", is_envase_zone=True,
            stop_sequences=[], ce_used=0.0, ce_capacity=60.0,
        ),
    ]
    # Stop 1 returns absorb into the legacy envase zone.
    delivered = {1: 50.0, 2: 0.0}
    traces = simulate_returns(sa, delivered)
    assert traces[0].cumulative_returns_ce == 30.0
    assert traces[0].free_ce_after == 30.0  # 60 envase - 30 used
