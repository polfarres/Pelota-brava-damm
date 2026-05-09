"""Vehicle profile schema (DR-008).

Slot-graph model. Each profile describes a real fleet vehicle with its
access mechanism, slot disposition, and lateral-blocking adjacency.
Capacity is volumetric (CE per A-31); weight is informational only (A-30).

Fleet (per slide 3 of ``INTERHACK Barcelona 2026.pptx`` + mentor session
2026-05-09): 1 furgoneta + 11 ×6P side-curtain + 4 ×8P side-curtain +
4 ×8P with rear tail-lift = 20 vehicles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from smart_truck.domain.load_unit import LoadUnitClass


class SlotType(str, Enum):
    PALLET_FLOOR = "PALLET_FLOOR"
    SHELF = "SHELF"
    FLOOR_KEG = "FLOOR_KEG"
    OVERFLOW = "OVERFLOW"


class AccessFace(str, Enum):
    REAR = "REAR"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"


class CurtainAccess(str, Enum):
    NONE = "NONE"
    SINGLE_SIDE = "SINGLE_SIDE"
    BOTH_SIDES_PARTITIONED = "BOTH_SIDES_PARTITIONED"
    BOTH_SIDES_OPEN = "BOTH_SIDES_OPEN"


@dataclass
class AccessMechanism:
    rear_doors: bool
    rear_lift: bool
    curtain: CurtainAccess
    partition: bool


@dataclass
class Slot:
    id: str
    type: SlotType
    pos_cm: tuple[float, float, float]
    size_cm: tuple[float, float, float]
    accepts: list[LoadUnitClass]
    capacity_ce: float
    max_weight_kg: float
    reachable_from: list[AccessFace]
    blocked_by_per_face: dict[AccessFace, list[str]] = field(default_factory=dict)
    can_host_returns_of: list[LoadUnitClass] = field(default_factory=list)
    notes: str = ""


@dataclass
class VehicleProfile:
    profile_id: str
    display_name: str
    fleet_count: int
    external_dim_cm: tuple[float, float, float]
    internal_dim_cm: tuple[float, float, float]
    access: AccessMechanism
    slots: list[Slot]
    total_capacity_ce: float
    nominal_payload_kg: float
    envase_zone_slot_ids: list[str]
    lifo_order_per_face: dict[AccessFace, list[str]] = field(default_factory=dict)
    schema_version: str = "1.1"

    def slot(self, slot_id: str) -> Slot:
        for s in self.slots:
            if s.id == slot_id:
                return s
        raise KeyError(f"slot {slot_id!r} not in profile {self.profile_id}")
