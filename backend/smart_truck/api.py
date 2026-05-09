"""FastAPI app — Smart Truck (FR-012).

Endpoints:

- ``GET  /health``                       — liveness.
- ``GET  /baseline?ruta=&fecha=``        — as-is reconstruction
                                           from the source paperwork.
- ``GET  /customers/{id}``               — single customer detail.
- ``POST /plan``                         — run the joint route + load
                                           optimiser. Stub today; wired
                                           when Track A's pipeline lands.
- ``GET  /plan/{run_id}/hoja-carga.pdf`` — Smart Hoja Carga (Track B).
- ``GET  /plan/{run_id}/hoja-ruta.pdf``  — Smart Hoja Ruta (Track B).

Run::

    uvicorn smart_truck.api:app --reload
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .baseline import RECURSOS_DIR, BaselineInputs, reconstruct_baseline

app = FastAPI(title="Smart Truck", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------


def _jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses, dates, Decimals, etc. to JSON-safe
    primitives. Used because we hand FastAPI plain dataclasses rather
    than pydantic models — keeps the contract one-sided."""
    if is_dataclass(obj):
        return _jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Smart Truck API", "version": "0.1.0"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/baseline")
def get_baseline(ruta: str, fecha: str) -> dict[str, Any]:
    """As-is reconstruction (FR-004) for a given ``(ruta, fecha)``.

    Today only ``DR0027 / 2026-05-08`` is wired — that's the only carga
    we have source PDFs for. Future versions will discover PDFs by ruta
    and fecha automatically.
    """
    if (ruta, fecha) != ("DR0027", "2026-05-08"):
        raise HTTPException(
            status_code=404,
            detail=(
                "Only DR0027 / 2026-05-08 has source PDFs for now. "
                "Add a Hoja Carga + Hoja Ruta PDF pair under "
                "Hackaton/DAMM/RECURSOS/ to extend coverage."
            ),
        )
    bp = reconstruct_baseline(
        RECURSOS_DIR / "Hoja Carga.pdf",
        RECURSOS_DIR / "Hoja Ruta.pdf",
    )
    return _jsonable(bp)


@app.get("/customers/{customer_id}")
def get_customer(customer_id: int) -> dict[str, Any]:
    """Single customer record + lat/lon if geocoded."""
    df = BaselineInputs.load().customers
    matches = df[df["customer_id"] == customer_id]
    if matches.empty:
        raise HTTPException(status_code=404, detail=f"customer {customer_id} not found")
    row = matches.iloc[0]
    return {
        "customer_id": int(row["customer_id"]),
        "name": str(row["name"]),
        "street": str(row["street"]),
        "postcode": str(row["postcode"]),
        "city": str(row["city"]),
        "lat": float(row["lat"]) if pd.notna(row.get("lat")) else None,
        "lon": float(row["lon"]) if pd.notna(row.get("lon")) else None,
    }


class PlanRequest(BaseModel):
    ruta: str
    fecha: str  # ISO YYYY-MM-DD


@app.post("/plan")
def post_plan(_req: PlanRequest) -> dict[str, Any]:
    """Run the joint optimiser and return a Plan + KPI summary.

    Stub today: returns 501 until Track A's optimiser pipeline is in.
    Frontend (Track C) can mock this with a hand-built Plan that matches
    ``smart_truck.models.Plan``.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "Joint route + load optimisation not yet wired. "
            "Track A: implement smart_truck.optimize.pipeline.plan(...) "
            "and route this endpoint to it."
        ),
    )


@app.get("/plan/{run_id}/hoja-carga.pdf")
def get_smart_hoja_carga(run_id: str) -> Response:  # noqa: ARG001 - placeholder
    """Smart Hoja Carga PDF (FR-010). Stub until the emitter ships."""
    raise HTTPException(status_code=501, detail="Smart Hoja Carga emitter pending (FR-010).")


@app.get("/plan/{run_id}/hoja-ruta.pdf")
def get_smart_hoja_ruta(run_id: str) -> Response:  # noqa: ARG001 - placeholder
    """Smart Hoja Ruta PDF (FR-011). Stub until the emitter ships."""
    raise HTTPException(status_code=501, detail="Smart Hoja Ruta emitter pending (FR-011).")
