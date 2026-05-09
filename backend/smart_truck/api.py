"""FastAPI app — Smart Truck (FR-012).

Endpoints (planned):

- ``POST /plan`` body ``{ruta, fecha}`` → optimised plan JSON.
- ``GET  /plan/{run_id}/hoja-carga.pdf`` → Smart Hoja Carga.
- ``GET  /plan/{run_id}/hoja-ruta.pdf``  → Smart Hoja Ruta.
- ``GET  /baseline?ruta=…&fecha=…``     → as-is reconstruction.
- ``GET  /customers/{id}``               → customer detail.

Run::

    uvicorn smart_truck.api:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Smart Truck", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "Smart Truck API", "version": "0.1.0"}
