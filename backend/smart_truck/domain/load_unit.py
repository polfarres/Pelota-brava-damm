"""LoadUnit taxonomy (DR-009).

Aligned with DAMM's four official product categories from slide 3 of
``INTERHACK Barcelona 2026.pptx``: barriles, retornables, latas, cajas.
Capacity is volumetric in caixes estadístiques (CE) per A-31 — weight
is informational only (A-30).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LoadCategory(str, Enum):
    """DAMM's four picking categories — drives rotation by volume."""

    BARRIL = "BARRIL"
    RETORNABLE = "RETORNABLE"
    LATA = "LATA"
    CAJA = "CAJA"


class LoadUnitClass(str, Enum):
    """Physical placement granularity used by the packer."""

    EUR_PALLET = "EUR_PALLET"
    INDUSTRIAL_PALLET = "INDUSTRIAL_PALLET"
    CASE = "CASE"
    BRL = "BRL"
    KEG_FULL = "KEG_FULL"
    KEG_EMPTY = "KEG_EMPTY"
    BARREL_EMPTY = "BARREL_EMPTY"
    TUBE = "TUBE"


@dataclass(frozen=True)
class LoadUnit:
    cls: LoadUnitClass
    category: LoadCategory
    sku: str | None
    ce_per_unit: float
    weight_kg: float
    is_envase: bool = False

    @property
    def ce_load(self) -> float:
        return self.ce_per_unit
