"""Load YAML vehicle profiles into typed dataclasses (DR-008).

Profiles live in ``backend/smart_truck/data/vehicles/*.yaml``. The loader
also runs structural validation: unique slot IDs, ``blocked_by_per_face``
references resolve, ``total_capacity_ce`` matches the slot sum, and every
``lifo_order_per_face`` slot declares the matching face in
``reachable_from``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from smart_truck.domain.load_unit import LoadUnitClass
from smart_truck.domain.vehicle import (
    AccessFace,
    AccessMechanism,
    CurtainAccess,
    Slot,
    SlotType,
    VehicleProfile,
)

VEHICLES_DIR = Path(__file__).resolve().parents[1] / "data" / "vehicles"


def _slot_from_dict(d: dict) -> Slot:
    return Slot(
        id=d["id"],
        type=SlotType(d["type"]),
        pos_cm=tuple(d.get("pos_cm", (0, 0, 0))),
        size_cm=tuple(d.get("size_cm", (0, 0, 0))),
        accepts=[LoadUnitClass(c) for c in d.get("accepts", [])],
        capacity_ce=float(d["capacity_ce"]),
        max_weight_kg=float(d.get("max_weight_kg", 0.0)),
        reachable_from=[AccessFace(f) for f in d["reachable_from"]],
        blocked_by_per_face={
            AccessFace(face): list(slots)
            for face, slots in (d.get("blocked_by_per_face") or {}).items()
        },
        can_host_returns_of=[
            LoadUnitClass(c) for c in d.get("can_host_returns_of", [])
        ],
        notes=d.get("notes", ""),
    )


def _profile_from_dict(d: dict) -> VehicleProfile:
    access_d = d["access"]
    access = AccessMechanism(
        rear_doors=bool(access_d["rear_doors"]),
        rear_lift=bool(access_d.get("rear_lift", False)),
        curtain=CurtainAccess(access_d["curtain"]),
        partition=bool(access_d.get("partition", False)),
    )
    slots = [_slot_from_dict(s) for s in d["slots"]]
    return VehicleProfile(
        profile_id=d["profile_id"],
        display_name=d["display_name"],
        fleet_count=int(d["fleet_count"]),
        external_dim_cm=tuple(d.get("external_dim_cm", (0, 0, 0))),
        internal_dim_cm=tuple(d.get("internal_dim_cm", (0, 0, 0))),
        access=access,
        slots=slots,
        total_capacity_ce=float(d["total_capacity_ce"]),
        nominal_payload_kg=float(d.get("nominal_payload_kg", 0.0)),
        envase_zone_slot_ids=list(d.get("envase_zone_slot_ids", [])),
        lifo_order_per_face={
            AccessFace(face): list(seq)
            for face, seq in (d.get("lifo_order_per_face") or {}).items()
        },
        schema_version=d.get("schema_version", "1.1"),
    )


def validate(profile: VehicleProfile) -> None:
    ids = [s.id for s in profile.slots]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{profile.profile_id}: duplicate slot IDs in {ids}")

    by_id = {s.id: s for s in profile.slots}
    for s in profile.slots:
        for face, blockers in s.blocked_by_per_face.items():
            if face not in s.reachable_from:
                raise ValueError(
                    f"{profile.profile_id}/{s.id}: blocked_by face {face} "
                    f"not in reachable_from {s.reachable_from}"
                )
            for ref in blockers:
                if ref not in by_id:
                    raise ValueError(
                        f"{profile.profile_id}/{s.id}: blocked_by references "
                        f"missing slot {ref!r}"
                    )

    declared = round(profile.total_capacity_ce, 6)
    actual = round(sum(s.capacity_ce for s in profile.slots), 6)
    if declared != actual:
        raise ValueError(
            f"{profile.profile_id}: total_capacity_ce={declared} but "
            f"sum(slots)={actual}"
        )

    for face, seq in profile.lifo_order_per_face.items():
        for sid in seq:
            if sid not in by_id:
                raise ValueError(
                    f"{profile.profile_id}: lifo_order_per_face[{face}] "
                    f"references missing slot {sid!r}"
                )
            if face not in by_id[sid].reachable_from:
                raise ValueError(
                    f"{profile.profile_id}: lifo_order_per_face[{face}] "
                    f"includes {sid} but that slot is not reachable from {face}"
                )

    for sid in profile.envase_zone_slot_ids:
        if sid not in by_id:
            raise ValueError(
                f"{profile.profile_id}: envase_zone_slot_ids references "
                f"missing slot {sid!r}"
            )


def load_profile(path: Path) -> VehicleProfile:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    profile = _profile_from_dict(data)
    validate(profile)
    return profile


def load_all(directory: Path | None = None) -> dict[str, VehicleProfile]:
    directory = directory or VEHICLES_DIR
    profiles: dict[str, VehicleProfile] = {}
    for path in sorted(directory.glob("*.yaml")):
        profile = load_profile(path)
        profiles[profile.profile_id] = profile
    return profiles
