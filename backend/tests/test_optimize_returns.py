"""Tests for FR-007/007a returns / free-space tracker."""

from __future__ import annotations

import pytest

from smart_truck.models import SlotAssignment
from smart_truck.optimize.returns import (
    ReturnsInfeasibleError,
    estimate_returnable_ce_per_stop,
    simulate_returns,
)
from smart_truck.models import DeliveredLine


def _line(sku, qty=1.0, ce=1.0):
    return DeliveredLine(
        sku=sku, description=sku, quantity=qty, unit="Caja",
        ce=ce, weight_kg=0.0, source_ubicacion=None,
    )


def test_simulate_returns_feasible():
    """Two stops, each delivers 60 CE returnable; envase has 60 CE free.
    After stop 1, slot freed (60 CE); 60 CE returns × 0.6 = 36 CE → fits."""
    sa = [
        SlotAssignment(slot_id="P1", is_envase_zone=False,
                       stop_sequences=[1], ce_used=60.0, ce_capacity=60.0),
        SlotAssignment(slot_id="P2", is_envase_zone=False,
                       stop_sequences=[2], ce_used=60.0, ce_capacity=60.0),
        SlotAssignment(slot_id="P3", is_envase_zone=True,
                       stop_sequences=[], ce_used=0.0, ce_capacity=60.0),
    ]
    delivered = {1: 60.0, 2: 60.0}
    traces = simulate_returns(sa, delivered)
    assert len(traces) == 2
    assert traces[0].cumulative_returns_ce == 36.0


def test_simulate_returns_infeasible_overflow():
    """Big returns at stop 1 with no freed space yet should raise."""
    sa = [
        SlotAssignment(slot_id="P1", is_envase_zone=False,
                       stop_sequences=[2], ce_used=60.0, ce_capacity=60.0),
        SlotAssignment(slot_id="P2", is_envase_zone=False,
                       stop_sequences=[2], ce_used=60.0, ce_capacity=60.0),
        SlotAssignment(slot_id="P3", is_envase_zone=True,
                       stop_sequences=[], ce_used=0.0, ce_capacity=10.0),
    ]
    # Stop 1 returns are huge, but no slot freed at stop 1 (both freed at 2).
    # Envase only 10 CE free. 100 CE × 0.6 = 60 > 10. Infeasible.
    delivered = {1: 100.0, 2: 0.0}
    with pytest.raises(ReturnsInfeasibleError):
        simulate_returns(sa, delivered)


def test_estimate_returnable_ce_per_stop_with_filter():
    lines_by_stop = {
        1: [_line("RET", qty=2, ce=1.0), _line("ENV", qty=1, ce=1.0)],
        2: [_line("RET", qty=3, ce=1.0)],
    }
    is_returnable = {"RET": True, "ENV": False}
    out = estimate_returnable_ce_per_stop(lines_by_stop, is_returnable)
    assert out[1] == 2.0
    assert out[2] == 3.0


def test_simulate_returns_empty():
    assert simulate_returns([], {}) == []
