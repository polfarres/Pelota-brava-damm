"""Shared dataclass contracts for the Smart Truck pipeline.

These types are the boundary between the parallel work tracks:

- ``smart_truck.optimize`` (Track A) — produces :class:`Plan`.
- ``smart_truck.baseline`` (Track B) — produces :class:`BaselinePlan`.
- ``smart_truck.kpi`` (Track B) — consumes both, emits :class:`KpiDelta`.
- ``smart_truck.api`` (Track B) — serialises everything to JSON for the
  frontend.
- ``frontend/lib/api.ts`` (Track C) — the TypeScript mirror of these
  types.

**Schema is frozen for the build day.** Additive changes (new optional
fields with sensible defaults) are fine; renames or required-field
additions must be coordinated in team chat first.

Anchors in the spec:

- :class:`SlotAssignment` capacity defaults to 60 CE (A-31).
- :class:`StopPlan.in_truck_zones_touched` drives the
  ``service_time_min = 10 + 2 × zones_touched`` model (A-06).
- :class:`Plan.vehicle_profile` references the YAML profile name in
  ``smart_truck/data/vehicles/`` (DR-008): ``furgo_3p``,
  ``truck_6p_sidecurtain``, ``truck_8p_sidecurtain``, ``truck_8p_lift``.
- :class:`KpiDelta.metric` covers the five KPIs in FR-009 (volume KPI
  dropped per A-11; weight + count + time + zones-touched).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from typing import Literal

PaymentCondition = Literal["CONTADO", "CREDITO"]

KpiMetric = Literal[
    "total_km",
    "total_minutes",
    "unload_minutes_estimated",
    "in_truck_searches",
    "space_utilisation_pct",
]

VehicleProfileName = Literal[
    "furgo_3p",
    "truck_6p_sidecurtain",
    "truck_8p_sidecurtain",
    "truck_8p_lift",
]


@dataclass(frozen=True)
class DeliveredLine:
    """One product line delivered at a stop.

    Mirrors a Hoja Carga line that pertains to one customer's albarán.
    """

    sku: str
    description: str
    quantity: float
    unit: str  # "Caja" | "Barril" | "Tubo" | "Unidad" | "Pack" | "Botella"
    ce: float  # caixes estadístiques units (DR-010)
    weight_kg: float
    source_ubicacion: str | None  # warehouse location code, lex sortable


@dataclass
class StopPlan:
    """A scheduled visit to one customer."""

    sequence: int  # 1-indexed position in the route
    customer_id: int
    customer_name: str
    address: str
    lat: float | None  # None if geocoding failed
    lon: float | None
    eta: time | None
    time_window: tuple[time, time] | None
    payment_condition: PaymentCondition
    proforma_total: Decimal  # negative for abonos (credit notes)
    delivered_lines: list[DeliveredLine] = field(default_factory=list)
    returns_estimated_ce: float = 0.0  # expected returnable volume in CE
    in_truck_zones_touched: int = 0  # drives unload-time KPI


@dataclass
class SlotAssignment:
    """One pallet position / zone in the truck and what is loaded in it."""

    slot_id: str  # references the Vehicle YAML's slots[].id
    is_envase_zone: bool
    stop_sequences: list[int] = field(default_factory=list)
    contents: list[DeliveredLine] = field(default_factory=list)
    ce_used: float = 0.0
    ce_capacity: float = 60.0  # A-31: 60 CE per pallet position


@dataclass
class Explanation:
    """Per-stop or per-slot justification surfaced as an explanation card."""

    target: Literal["stop", "slot"]
    target_id: str  # ``str(sequence)`` or ``slot_id``
    reason: str


@dataclass
class Plan:
    """Output of the joint route + load optimisation pipeline (FR-008)."""

    ruta: str
    fecha: date
    vehicle_profile: VehicleProfileName
    stops: list[StopPlan]
    slot_assignments: list[SlotAssignment]
    explanations: list[Explanation] = field(default_factory=list)


@dataclass
class BaselinePlan:
    """Reconstruction of as-is operation (FR-004) from the source paperwork.

    Same shape as :class:`Plan` but produced by reading the actual
    ``Hoja Carga`` and ``Hoja Ruta`` PDFs rather than by optimisation.
    """

    ruta: str
    fecha: date
    vehicle_profile: VehicleProfileName
    stops: list[StopPlan]
    slot_assignments: list[SlotAssignment]


@dataclass
class KpiDelta:
    """One metric's comparison between :class:`BaselinePlan` and :class:`Plan`."""

    metric: KpiMetric
    baseline: float
    proposed: float

    @property
    def delta(self) -> float:
        return self.proposed - self.baseline

    @property
    def delta_pct(self) -> float:
        """Percent change versus baseline. ``0.0`` if baseline is zero."""
        if self.baseline == 0:
            return 0.0
        return (self.proposed - self.baseline) / self.baseline * 100.0

    @property
    def is_improvement(self) -> bool:
        """All five KPIs improve when they go *down* (less km, less time,
        fewer searches, lower space-util headroom is better when ratio
        decreases? — actually space_utilisation increasing is better as
        we use the truck more efficiently). Treat metrics consistently:
        improvement = delta < 0 except for ``space_utilisation_pct``.
        """
        if self.metric == "space_utilisation_pct":
            return self.delta > 0
        return self.delta < 0
