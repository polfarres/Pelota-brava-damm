# Pelota Brava — DAMM Smart Truck (Interhack BCN 2026)

Joint route + truck-load optimisation for the DDI Mollet warehouse.
Decision-support tool that takes a real route's orders and produces:

- An optimised stop sequence (VRP-TW with OR-Tools + OSRM real-road matrix).
- A Stack-LIFO + MILP truck load (PuLP/CBC) honouring case/barrel
  segregation and within-pallet rotation order (A-37 / A-38).
- A **Smart Hoja Carga** PDF that mirrors today's DDIDGP layout but populates
  the (currently blank) `Descarga` column with truck pallet targets.
- A **Smart Hoja Ruta** PDF reordered to the optimised sequence.
- A 3D truck twin animation, a 3D warehouse load-by-Ubicació view,
  a driver mobile mockup, and a KPI panel comparing against the as-is
  paperwork.

## Repository layout

```
Hackaton/                     # raw materials provided by DAMM and the hackathon
  DAMM/
    PLAN/                     # team docs — start here
    PRESENTATION/             # pitch deck (Marp), block diagrams (Mermaid)
    RECURSOS/                 # real DDIDGP paperwork samples
    Hackaton.xlsx, ZM040.XLSX, Horarios Entrega.XLSX, Layout Mollet.xlsx
backend/                      # FastAPI + OR-Tools + PuLP/CBC + ReportLab
frontend/                     # Next.js 14 + Tailwind + Leaflet + react-three-fiber
```

## Prerequisites

- **Python 3.11+** (the backend uses `from __future__ import annotations`,
  dataclass / `Literal` features available from 3.11).
- **Node.js 18+** with `npm` (Next.js 14 requirement).
- **Git** with the repo cloned locally.

Optional:

- An OSRM endpoint reachable at `http://router.project-osrm.org` (the
  backend falls back to haversine and a 1.4 detour factor if offline).

## First-time setup

### 1 · Backend

```bash
cd backend

# Create virtualenv
python -m venv .venv

# Activate it
# Windows (PowerShell / cmd):
.venv\Scripts\activate
# Windows (Git Bash) / macOS / Linux:
source .venv/Scripts/activate    # Git Bash
source .venv/bin/activate        # Unix

# Install dependencies (~2 min — pulls ortools + pulp/CBC binaries)
pip install -r requirements.txt
```

Then run the one-time data pipelines:

```bash
# ETL: reads Hackaton/DAMM/{Hackaton.xlsx, ZM040.XLSX, …} → 5 parquet files
python -m smart_truck.data.load

# Geocode: warm the demo route's lat/lon (Photon + Nominatim, file-cached)
python -m smart_truck.data.geocode --route DR0027
```

Both outputs are committed to the repo (`backend/data/processed/*.parquet`
and `backend/data/geo_cache.json`), so on a fresh clone the cache hits
instantly.

### 2 · Frontend

```bash
cd frontend
npm install        # ~1 min
```

The frontend reads `NEXT_PUBLIC_API_URL` (defaults to
`http://localhost:8000`). To override, create `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Running the application

You need **two terminals**: one for the backend API, one for the
frontend dev server.

### Terminal 1 · Backend API

```bash
cd backend
source .venv/Scripts/activate          # or .venv\Scripts\activate on Windows
uvicorn smart_truck.api:app --port 8000 --reload
```

- `http://localhost:8000/health` — liveness probe.
- `http://localhost:8000/docs` — Swagger UI (interactive).

### Terminal 2 · Frontend

```bash
cd frontend
npm run dev
```

- `http://localhost:3000/` — main dashboard (map + KPIs + stop list).
- `http://localhost:3000/truck` — 3D truck twin, animates the load.
- `http://localhost:3000/loading` — 3D warehouse load-by-Ubicació.
- `http://localhost:3000/pick-list` — Smart Hoja Carga viewer (Original ↔ Smart toggle).
- `http://localhost:3000/driver` — driver mobile mockup.

## One-shot demo (no UI needed)

After backend setup, produce every pitch artefact in one command:

```bash
cd backend
python -m smart_truck.demo
```

Outputs (in `backend/data/demo_output/`):

- `smart_hoja_carga_DR0027_2026-05-08.pdf` — populated `Descarga` column.
- `smart_hoja_ruta_DR0027_2026-05-08.pdf` — re-sequenced route sheet.
- Console: 5/5 KPI improvements vs the parsed baseline (km, total min,
  unload min, in-truck searches, space utilisation).

Flags:

- `--no-pdfs` — skip the emit step (~5 s smoke run).
- `--prefer-osrm` — use OSRM instead of haversine (real km, needs network).
- `--route` / `--fecha` — override demo target.

## API endpoints

- `GET /health` — liveness probe.
- `GET /baseline?ruta=&fecha=` — as-is plan reconstructed from the source paperwork.
- `GET /customers/{id}` — single customer with lat/lon.
- `POST /plan` — run the optimiser (body: `{ruta, fecha, force?}`).
- `GET /plan/{run_id}` — cached optimised plan + KPI deltas (`run_id = {ruta}-{fecha}`).
- `GET /plan/{run_id}/hoja-carga.pdf` — Smart Hoja Carga (Descarga column populated).
- `GET /plan/{run_id}/hoja-ruta.pdf` — Smart Hoja Ruta (re-sequenced).

## Demo target

Carga `11764300`, route `DR0027`, vehicle `7524KXX`, driver Fran Romero
(`850004`), 2026-05-08. 18 stops in Sant Julià de Vilatorta → Calldetenes →
Folgueroles. The actual `Hoja Carga` and `Hoja Ruta` PDFs for that day are in
`Hackaton/DAMM/RECURSOS/` — they are our as-is baseline.

## Tests

```bash
cd backend
pytest                       # full suite
pytest tests/test_kpi.py     # one module
```

## Branches

- `main` — pitch-day artefacts. In sync with `develop`.
- `develop` — integration branch. Daily work lands here.

## Troubleshooting

- **Port already in use** — kill the prior `uvicorn` (Windows: `taskkill
  /F /PID <pid>` after `netstat -ano | grep :8000`) or pass `--port 8001`.
- **`ModuleNotFoundError: smart_truck`** — your virtualenv isn't active.
  Re-activate from the `backend/` folder.
- **PDF endpoints return empty Descarga column** — the API serves a
  cached optimised plan; if you've never hit `POST /plan` or
  `GET /plan/{run_id}`, the cache is empty. Hit the GET endpoint once
  to populate it (or just re-run `python -m smart_truck.demo`).
- **OSRM 503 / network errors** — the distance backend auto-falls back
  to haversine; the demo runs offline by default.
