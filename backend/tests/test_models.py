"""Smoke tests for the shared dataclass contract.

These mostly assert that the schema fields are spelled the way the rest
of the codebase expects, so a future rename surfaces here loudly.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from smart_truck.models import (
    BaselinePlan,
    DeliveredLine,
    Explanation,
    KpiDelta,
    Plan,
    SlotAssignment,
    StopPlan,
)


def _sample_line() -> DeliveredLine:
    return DeliveredLine(
        sku="ED13",
        description="ESTRELLA DAMM 1/3 RET. PP",
        quantity=24,
        unit="Caja",
        ce=24.0,
        weight_kg=12.6,
        source_ubicacion="AA09A1",
    )


def _sample_stop() -> StopPlan:
    return StopPlan(
        sequence=1,
        customer_id=9100627695,
        customer_name="BAR PAVELLO ST JULIA VILATORTA",
        address="AVENIDA SANT LLORENÇ S/N, 08504 SANT JULIÀ DE VILATORTA",
        lat=41.918,
        lon=2.299,
        eta=time(9, 30),
        time_window=(time(8, 0), time(14, 0)),
        payment_condition="CONTADO",
        proforma_total=Decimal("314.92"),
        delivered_lines=[_sample_line()],
        returns_estimated_ce=10.0,
        in_truck_zones_touched=1,
    )


def test_delivered_line_is_immutable() -> None:
    line = _sample_line()
    with pytest.raises(Exception):
        line.quantity = 99  # type: ignore[misc]


def test_plan_construction_smoke() -> None:
    stop = _sample_stop()
    slot = SlotAssignment(
        slot_id="P1",
        is_envase_zone=False,
        stop_sequences=[1],
        contents=[_sample_line()],
        ce_used=24.0,
        ce_capacity=60.0,
    )
    plan = Plan(
        ruta="DR0027",
        fecha=date(2026, 5, 8),
        vehicle_profile="truck_6p_sidecurtain",
        stops=[stop],
        slot_assignments=[slot],
        explanations=[
            Explanation(target="stop", target_id="1", reason="closest to depot")
        ],
    )
    assert plan.ruta == "DR0027"
    assert plan.stops[0].customer_id == 9100627695
    assert plan.slot_assignments[0].ce_used == 24.0


def test_baseline_and_plan_share_stop_shape() -> None:
    stop = _sample_stop()
    slot = SlotAssignment(slot_id="P1", is_envase_zone=False, stop_sequences=[1])
    base = BaselinePlan(
        ruta="DR0027",
        fecha=date(2026, 5, 8),
        vehicle_profile="truck_6p_sidecurtain",
        stops=[stop],
        slot_assignments=[slot],
    )
    plan = Plan(
        ruta="DR0027",
        fecha=date(2026, 5, 8),
        vehicle_profile="truck_6p_sidecurtain",
        stops=[stop],
        slot_assignments=[slot],
    )
    # Same stop dataclass on both sides; KPI engine relies on this.
    assert base.stops[0] is plan.stops[0]


def test_kpi_delta_signs_and_pct() -> None:
    d = KpiDelta(metric="total_km", baseline=100.0, proposed=80.0)
    assert d.delta == -20.0
    assert d.delta_pct == pytest.approx(-20.0)
    assert d.is_improvement is True


def test_kpi_delta_zero_baseline_safe() -> None:
    d = KpiDelta(metric="in_truck_searches", baseline=0.0, proposed=0.0)
    assert d.delta_pct == 0.0


def test_space_utilisation_improves_when_higher() -> None:
    # Improvement direction is reversed for utilisation.
    d = KpiDelta(metric="space_utilisation_pct", baseline=0.6, proposed=0.8)
    assert d.is_improvement is True
    d2 = KpiDelta(metric="space_utilisation_pct", baseline=0.8, proposed=0.6)
    assert d2.is_improvement is False
