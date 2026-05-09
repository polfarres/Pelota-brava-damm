# Pelota Brava — DAMM Smart Truck (Interhack BCN 2026)

Joint route + truck-load optimisation for the DDI Mollet warehouse.
Decision-support tool that takes a real route's orders and produces:

- An optimised stop sequence (VRP with time windows).
- A hybrid client-cluster + LIFO truck load that absorbs returnable empties.
- A **Smart Hoja Carga** PDF that mirrors today's DDIDGP layout but populates
  the (currently blank) `Descarga` column with truck pallet targets.
- A **Smart Hoja Ruta** PDF reordered to the optimised sequence.
- A 3D truck twin animation, a driver mobile mockup, and a KPI panel
  comparing against the as-is paperwork.

## Repository layout

```
Hackaton/                     # raw materials provided by DAMM and the hackathon
  DAMM/
    PLAN/                     # team docs — start here
      Smart Truck — Hackathon Plan.md
      Specifications.md       # functional requirements + parsing schemas
      Mentor Questions.md
    RECURSOS/                 # real DDIDGP paperwork samples
    Hackaton.xlsx
    Horarios Entrega.XLSX
    ZM040.XLSX
    Layout Mollet.xlsx
    ...
  INFO GENERAL/
    Interhack_BCN_2026_Challenges_EN.pdf

backend/                      # FastAPI + OR-Tools + ReportLab
frontend/                     # Next.js + Tailwind + Leaflet + react-three-fiber
```

## Quick start

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m smart_truck.data.load                     # generate parquet files
uvicorn smart_truck.api:app --reload                # http://localhost:8000

# Frontend (in another shell)
cd frontend
npm install
npm run dev                                         # http://localhost:3000
```

## Demo target

Carga `11764300`, route `DR0027`, vehicle `7524KXX`, driver Fran Romero
(`850004`), 2026-05-08. 18 stops in Sant Julià de Vilatorta → Calldetenes →
Folgueroles. The actual `Hoja Carga` and `Hoja Ruta` PDFs for that day are in
`Hackaton/DAMM/RECURSOS/` — they are our as-is baseline.

## Branches

- `main` — production-ready / pitch-day artefacts only.
- `develop` — integration branch.
- `feature/*` — work in progress.
