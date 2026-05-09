# Smart Truck — Backend

FastAPI + OR-Tools + ReportLab implementation of the Smart Truck plan.
See `../Hackaton/DAMM/PLAN/Specifications.md` for functional requirements
and `../Hackaton/DAMM/PLAN/Pitch.md` for the speaker outline.

## Setup

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt
```

## Pipelines (run once after setup)

```bash
# 1. ETL — reads Hackaton/DAMM/{Hackaton.xlsx, Horarios Entrega.XLSX,
#    ZM040.XLSX, Caixes_Estadístiques.xlsx} into 5 parquet files +
#    a CE coverage report.
python -m smart_truck.data.load

# 2. Geocode customer addresses — Photon primary, Nominatim fallback,
#    1 req/sec, results cached to data/geo_cache.json (committed).
python -m smart_truck.data.geocode --route DR0027   # demo route only
python -m smart_truck.data.geocode --all            # full catalogue (~20 min)
```

## End-to-end demo runner

One command to produce every pitch artefact:

```bash
python -m smart_truck.demo
# → parses the source paperwork
# → reconstructs the BaselinePlan
# → optionally runs the optimiser (Track A) and computes KPI deltas
# → emits Smart Hoja Carga + Smart Hoja Ruta PDFs to data/demo_output/
```

Flags:
- `--no-pdfs` — skip the emit step (fast smoke run, ~5 s).
- `--prefer-osrm` — use OSRM road routing instead of haversine (real km, needs network).
- `--route` / `--fecha` — override demo target.

The script self-degrades when Track A's optimiser isn't yet on the
branch: it prints baseline-only metrics and emits pass-through PDFs.

## Run the API

```bash
uvicorn smart_truck.api:app --reload
# → http://localhost:8000/health
# → http://localhost:8000/docs (Swagger UI)
```

Endpoints:

| Method + path | Purpose |
|---|---|
| `GET /health` | Liveness |
| `GET /baseline?ruta=&fecha=` | Full BaselinePlan JSON (today gated to `DR0027 / 2026-05-08`) |
| `GET /customers/{id}` | Single customer + lat/lon if geocoded |
| `POST /plan` | Run optimiser (501 until Track A wires the pipeline) |
| `GET /plan/{run_id}/hoja-carga.pdf` | Smart Hoja Carga (run_id format `{ruta}-{fecha}`) |
| `GET /plan/{run_id}/hoja-ruta.pdf` | Smart Hoja Ruta |

## Tests

```bash
pytest                     # 93 passing as of develop
pytest tests/test_kpi.py   # one module
```

## Layout

```
smart_truck/
  api.py                 # FastAPI app (FR-012) — implemented
  baseline.py            # BaselinePlan reconstruction (FR-004) — implemented
  kpi.py                 # KPI engine (FR-009) — implemented
  models.py              # frozen dataclass contract (Plan, BaselinePlan, …)
  demo.py                # one-command end-to-end runner
  data/
    load.py              # ETL: xlsx → parquet (FR-001) — implemented
    geocode.py           # Photon + Nominatim cached geocoding (FR-002) — implemented
    distance.py          # OSRM + haversine fallback (FR-003) — implemented
    vehicles/*.yaml      # 4 vehicle profiles (DR-008)
    ce_overrides.yaml    # CE-per-unit overrides (DR-010)
  domain/                # LoadUnit, Vehicle, vehicle_loader (DR-008/9)
  paperwork/
    parser.py            # Hoja Carga + Hoja Ruta PDF parsers (FR-004) — implemented
    emitter.py           # Smart Hoja Carga + Hoja Ruta emit (FR-010/011) — implemented
  optimize/              # FR-005..FR-008 — Track A in flight on its own branch
data/
  processed/             # parquet output of the ETL (committed)
  geo_cache.json         # geocode cache (committed)
  demo_output/           # demo runner artefacts (gitignored)
```
