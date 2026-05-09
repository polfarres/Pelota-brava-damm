# Smart Truck — Backend

FastAPI + OR-Tools + ReportLab implementation of the Smart Truck plan.
See `../Hackaton/DAMM/PLAN/Specifications.md` for functional requirements.

## Setup

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt
```

## Run the ETL

Reads `Hackaton/DAMM/{Hackaton.xlsx, Horarios Entrega.XLSX, ZM040.XLSX}` and
writes parquet files into `backend/data/processed/`.

```bash
python -m smart_truck.data.load
```

## Run the API

```bash
uvicorn smart_truck.api:app --reload
# → http://localhost:8000/health
# → http://localhost:8000/docs (Swagger UI)
```

## Tests

```bash
pytest
```

## Layout

```
smart_truck/
  api.py                 # FastAPI app (FR-012)
  data/
    load.py              # ETL: xlsx → parquet (FR-001) — implemented
    geocode.py           # Nominatim cached geocoding (FR-002) — TODO
    distance.py          # distance/time matrix (FR-003) — TODO
  optimize/              # FR-005..FR-008 — TODO
  paperwork/             # parsing source PDFs + emitting Smart PDFs — TODO
  baseline.py            # baseline reconstruction (FR-004) — TODO
  kpi.py                 # KPI engine (FR-009) — TODO
data/processed/          # parquet output of the ETL (committed)
```
