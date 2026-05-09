# DAMM Smart Truck — Hackathon Plan (Interhack BCN 2026)

## Context

Your team is competing in **Interhack BCN 2026** on the **DAMM "Smart Truck"** challenge from DDI (Distribució Directa Integral). After studying the brief, the DAMM presentation deck, the INTERHACK 2026 deck, the Mollet layout file and the four data files, the consistent core ask is:

> Jointly optimise the **delivery route** AND the **physical truck-load configuration** for the Mollet warehouse, accounting for time windows, side-curtain lateral access, pallet/volume/weight constraints, and the fact that ~60% of products are returnable so the truck **picks up empties as it unloads**.

Judges weight: **30% real applicability · 25% technical quality · 20% impact · 15% creativity · 10% pitch clarity**.

DAMM's deck (slide 11) explicitly says: it's NOT "Google Maps + Tetris", it IS a *decision-support* tool that combines route + load + reverse logistics, respecting operational reality. Echoing their own framing back at them is your applicability moat.

## Locked decisions

- **Time budget**: 12–24h until pitch.
- **Stack**: Python backend + Next.js frontend. Separate `backend/` and `frontend/` folders. All three teammates can move across folders late in the build.
- **Lead angle**: **Hybrid load + reverse logistics (Option 1)** as the technical engine, **driver-experience storytelling (Option 3)** as the pitch wrapper.
- **Must-have features**: animated 3D truck twin · warehouse pick list sorted by Mollet location · driver mobile UI mockup.
- **Team allocation**: 2 backend devs + 1 frontend dev primarily; everyone converges on integration/pitch in the final 6h.

## Data we'll lean on (from `Pelota-brava-damm/Hackaton/DAMM/`)

- **`Hackaton.xlsx` → "Detalle entrega"** — 82,849 line items, 58 days (Feb–Mar 2026), 18 routes, 1,203 active customers, 1,489 SKUs. The fact table.
- **`Hackaton.xlsx` → "Direcciones"** — 1,368 customer master with addresses (we'll geocode).
- **`Hackaton.xlsx` → "ZONAS"** — customer-to-route assignments (DR0001…).
- **`Hackaton.xlsx` → "Materiales zubic"** — 1,489 SKUs with Mollet warehouse `Ubic.` codes (FA05A2, CB06A2…). Drives the pick list.
- **`Horarios Entrega.XLSX`** — delivery time windows for 240 customers, Mon–Fri + Sun.
- **`ZM040.XLSX`** — SAP material master, 7,478 SKUs with **L×W×H, volume, weight, EAN, UMA conversions** (CAJ/PAL/UN/BOT/KG/L/ZCE/ZPR). Critical for load packing.
- **`Layout Mollet.xlsx`** — 193×98 sparse spatial grid (treat as opaque; we'll just sort the pick list by `Ubic.` lex order and ask a mentor about the grid only if time permits).
- **Fleet at Mollet** (from INTERHACK BCN deck slide 3): 11× six-pallet trucks, 4× eight-pallet trucks, 1× three-pallet van.

### `RECURSOS/` — operational paperwork DDI uses today (★ the most important folder)

These three PDFs are the existing SAP/DDIDGP outputs. Our solution will produce **enhanced versions of the same three documents**, which is the cleanest possible adoption path.

- **`Hoja Carga.pdf`** — Warehouse load sheet given to the picker. Sorted by warehouse `Ubicación` (e.g. AA09A1, AC07A2, FA05A2, ZCG). Columns: `Ubicación | Nº Prod. | Descripción | Cantidad | Unidad | Lote | Descarga`. **The `Descarga` column is currently blank.** That column is exactly where our optimiser writes the truck pallet target. Sections per load: `Carga lleno` (outbound, with location), `Carga lleno sin ubicación` (outbound, no warehouse slot), `Carga retorno lleno` (outbound returns, e.g. defective product going back to supplier), `Carga envases` (empty containers, crates, barrels going out for collection — codes 3ENV…, CJ13, CJ15, BRL30V, BRL20V, TB8V).

  Real example we have: load 11764300, vehicle V235045 (license `7524KXX`), driver 850004 FRAN ROMERO, route DR0027, viaje 01, date 2026-05-08. Totals: **Entrega 837 units / 4,719 kg** vs **Devolución 259 units / 2,094 kg** — i.e. ~31% return-to-outbound by units, ~44% by weight. The 60% returnable claim from the brief is real.

- **`Hoja Ruta.pdf`** — Driver's route sheet. Header: `Nº Carga | Fecha | Vehículo (license plate) | Repartidor | Preparador | Nº viaje`. Body: one row per delivery doc with `SSTT | Condición de pago (CONTADO/CREDITO) | Nº Doc | Nº Cliente | Nombre | Dirección | Total Proforma | Total Cobro`. Same example load DR0027 has **18 stops, 7,832.38 € total carga, 2,891.08 € to collect cash (CONTADO)**. Customers cluster geographically: Sant Julià de Vilatorta → Calldetenes → Folgueroles (Osona, ~70 km north of Mollet). Some lines are negative — credit notes (abonos, doc numbers prefix `8410…`) attached to a delivery.

- **`Albaran.pdf`** — Customer-facing delivery note / invoice. Header includes `Número | Albarán | Fecha | Cliente | N.ºCarga | Viaje | Cial. | Vend. | Ruta | Rep. | Forma de Pago | Recibo Domiciliado | Horario Servicio`. Lines: `Producto | UM | Cdad. | Precio | Dto | P.V. | I.P. | I.A. | Importe | IVA | Promoción`. Example: customer 412 COFFEE&BEER (Sant Fost de Campsentelles), 1,839.26 € on credit-20-days. Issued under "icired" e-invoice platform.

### Insights from the paperwork (drives multiple plan changes below)

1. **Adoption path = enhance, don't replace.** Our deliverables should be three artefacts that LOOK like the current Hoja Carga / Hoja Ruta / Albarán with new columns/markers added. Judges from DAMM ops will recognise the format instantly.
2. **The `Descarga` column is the single point of intervention** that costs DAMM almost nothing to adopt: same picker, same paper, one extra value per row.
3. **Envases (empty-container outbound) is a real second outbound flow** the brief understated. The picker actually loads outgoing empty crates and barrels (the 3ENV/CJ/BRL codes) into the truck before the route, in addition to the full product. Our load packer needs a dedicated zone for these because they go OUT but come back full of customer empties.
4. **Payment condition is operational metadata** the route sheet exposes (CONTADO vs CREDITO). Stops with cash collection have a real-world preference (visible cashier, daylight). Worth flagging in the driver mockup.
5. **Real demo numbers**: load DR0027 on 2026-05-08, 18 stops, 4.7 t outbound + 2.1 t returns. We will use this exact load as the demo case — every output we produce can be compared to the actual paper that left the Mollet office that morning.

Mentor questions to chase in the first hour: exact pallet dims by truck, return-rate per SKU class, current per-stop service time, lat/lon if DAMM has them, **and confirm that "Descarga" column is the right semantic slot for our output**.

## Solution: "Smart Truck"

A **decision-support web app** that, given one Mollet route's orders for a given day, outputs:

1. **Optimised stop sequence** — VRP-TW respecting time windows and zones.
2. **Hybrid pallet plan** — truck divided into client clusters in **reverse delivery order (LIFO)**. Whole-pallet stops get their own positions; partial-pallet stops share *consolidator pallets*, where products are SKU-grouped inside the pallet but the pallet itself is client-grouped. This is the literal answer to DAMM's "warehouse vs. delivery" tension on slide 6.
3. **Returns plan** — a free-space tracker that ensures empties picked up at stop *N* fit into space freed by deliveries at stops 1…*N*. Treats the *outbound envases* (empty crates/barrels DDI sends out) as a separate dedicated zone that doubles as ballast for inbound empties.
4. **Smart Hoja Carga (enhanced warehouse sheet)** — same DDIDGP layout, but the `Descarga` column is now populated with truck pallet codes (e.g. `P3-front-left`). Zero-friction adoption.
5. **Smart Hoja Ruta (enhanced route sheet)** — same DDIDGP layout, but rows are reordered to the optimised sequence and annotated with ETA, time-window status, and a CONTADO highlight.
6. **3D truck twin** — animates the load through the route: pallets fade as delivered, empties slide into freed positions.
7. **Driver mobile UI mockup** — static screens showing next stop, curtain side, pallet position, empties capacity remaining; CONTADO stops flagged for cash-collection awareness.
8. **KPI comparison vs. baseline** — km, route time, unload time, in-truck searches, space utilisation. Baseline is reconstructed from the actual DR0027 / 2026-05-08 paperwork we have.

### Why this wins on each criterion

- **Applicability (30%)**: built on DAMM's real 58-day Mollet data, real SKU dimensions, real time windows, real fleet sizes; framing mirrors DAMM's own deck.
- **Technical (25%)**: two-stage optimiser (VRP-TW → hybrid 3D placement) with a feedback loop on the returns model.
- **Impact (20%)**: quantified delta on a real route and extrapolated to the 470-vehicle fleet.
- **Creativity (15%)**: hybrid client-cluster + LIFO + dynamic free-space-for-returns is the genuinely novel insight; few teams will model returns at all.
- **Pitch (10%)**: opens with a driver's bad morning, ends with the same morning under Smart Truck. The 3D twin and the mobile mockup do the visual heavy-lifting.

## Repository layout

```
smart-truck/
  backend/
    pyproject.toml | requirements.txt
    smart_truck/
      __init__.py
      data/
        load.py            # ETL: read xlsx → cleaned parquet
        geocode.py         # cache addresses → lat/lon (Nominatim, file-cached)
        distance.py        # OSRM/ORS or haversine fallback
      optimize/
        route.py           # OR-Tools VRP-TW
        load.py            # hybrid pallet packer
        returns.py         # free-space tracker
        pipeline.py        # orchestrates route → load → returns
      baseline.py          # reproduce current (by-reference, driver-chosen) for KPI delta
      api.py               # FastAPI: POST /plan { route_id, date } → JSON plan
    tests/
      test_route.py
      test_load.py
      test_returns.py
  frontend/
    package.json
    next.config.js
    app/
      page.tsx             # main dashboard
      truck/page.tsx       # 3D truck twin (react-three-fiber)
      pick-list/page.tsx   # warehouse picker view
      driver/page.tsx      # mobile mockup screens
    components/
      MapView.tsx          # Mapbox/Leaflet route polyline + stops
      TruckTwin3D.tsx      # react-three-fiber pallet animation
      KpiPanel.tsx         # baseline vs. proposed
      ExplanationCard.tsx  # why-this-stop-here
    lib/api.ts             # typed client for backend
  data/                    # raw xlsx (gitignored), cleaned parquet committed
  README.md
  pitch.md                 # outline + speaker notes
```

## Implementation plan (24h timeline; compress proportionally for 12h)

### Hour 0–2 — kickoff (everyone)
- **DAMM mentor**: walk the hit list (see Mentor strategy below). Top three answers we *need*: real pallet geometry per truck, return-rate per SKU class, ground-truth as-is order for DR0027/2026-05-08.
- **Technical mentor**: get the live demo subdomain provisioned and a geocoding API key issued — both have lead time, kick off in hour 0.
- **Demo target locked**: route `DR0027` on **2026-05-08**, vehicle `7524KXX` / `V235045`, driver Fran Romero (`850004`), 18 stops in Sant Julià de Vilatorta + Calldetenes + Folgueroles, 4.7 t outbound, 2.1 t returns. We have the actual `Hoja Carga` and `Hoja Ruta` PDFs for this exact load — they ARE our baseline.
- Set up repo with `backend/` and `frontend/` folders.

### Hour 2–10 — parallel build
**Backend dev A — data + optimisation**
- `data/load.py`: read `Hackaton.xlsx` and `ZM040.XLSX`, join on `Material`, persist clean parquet.
- `data/geocode.py`: geocode 1,200 addresses with Nominatim, save to `data/geo_cache.json`. **Start this first**, it runs in the background.
- `optimize/route.py`: OR-Tools `RoutingModel` with capacity (pallet equivalents) + time-window dimensions. Cap solver at 30s.
- `optimize/load.py`: hybrid packer
  1. compute per-stop pallet count;
  2. allocate whole-pallet stops to truck positions in reverse delivery order;
  3. share partial stops on consolidator pallets, SKU-grouped within;
  4. assert lateral reachability (each stop touches a curtain face when its turn comes).
- Unit tests as you go (3-stop toy, capacity violation, time-window violation).

**Backend dev B — returns model + API + baseline + paperwork emitter**
- `optimize/returns.py`: track free space stop-by-stop; if returns at stop *N* exceed cumulative free space, raise + suggest reorder. Reserve a dedicated zone for outbound envases that doubles as inbound-empties absorber.
- `optimize/pipeline.py`: tie route → load → returns; iterate once if returns model rejects the load.
- `baseline.py`: parse the actual `RECURSOS/Hoja Carga.pdf` and `Hoja Ruta.pdf` for DR0027 / 2026-05-08 to extract the as-is order and load. Same KPI shape so frontend can compare apples-to-apples.
- `paperwork.py`: emit the **Smart Hoja Carga** and **Smart Hoja Ruta** as PDFs (or HTML print views) that mirror the DDIDGP layout but with our enhancements. ReportLab or WeasyPrint.
- `api.py`: FastAPI with `POST /plan` returning JSON (route, pallet positions, pick list, KPIs, explanations) + `GET /plan/{id}/hoja-carga.pdf` and `GET /plan/{id}/hoja-ruta.pdf`.

**Frontend dev — Next.js shell + 3D twin + driver mockup**
- Scaffold Next.js, set up Tailwind, set up react-three-fiber + drei.
- `MapView.tsx`: Mapbox or Leaflet, animated polyline, click-to-show stop detail.
- `TruckTwin3D.tsx`: top-down or perspective view of the truck cuboid with pallet boxes coloured by client. Slider/play to step through stops; pallet opacity drops on delivery; empties appear in freed positions.
- `app/driver/page.tsx`: 3 static screens — "next stop", "open right curtain — pallet 3", "empties capacity 4 of 6 used". Phone-frame styling.

### Hour 10–14 — integration
- Wire `lib/api.ts` to the FastAPI endpoint.
- KPI panel reads both baseline (from real Hoja Carga PDF) and proposed.
- `ExplanationCard.tsx` shows the per-stop "why" strings the backend emits.
- `app/pick-list/page.tsx`: visual rendering of the **Smart Hoja Carga** — same column shape as the real DDIDGP sheet (`Ubicación | Nº Prod. | Descripción | Cantidad | Unidad | Lote | Descarga`), with the `Descarga` column now filled with truck pallet codes and colour-coded by client cluster. Side-by-side toggle "Original vs. Smart" so judges see the minimal-diff adoption story.

### Hour 14–20 — polish + pitch material
- Pick a hero stop in the demo route; write the explanation card content for it manually if the auto-generated text is weak.
- Pre-record a 60s screencast of the dashboard + truck twin as a fallback in case live demo fails.
- `pitch.md`: 5-minute speaker outline.
- Practice the pitch end-to-end at least twice.

### Hour 20–24 — buffer + pitch rehearsal
- Buffer for the inevitable bug.
- Final pitch run-through in front of a mentor; iterate on the framing.

## Pitch flow (5 minutes)

1. **30s hook — Fran Romero's morning (Option 3 wrapper)**: hold up a printed copy of the real `Hoja Carga` for DR0027 / 2026-05-08. "This is what Fran got at 6am yesterday. 18 stops. 4.7 tonnes out, 2.1 tonnes back. And one column on this sheet — `Descarga` — is empty. Nobody fills it. The driver figures it out in his head, every morning."
2. **30s problem reframe**: this isn't a route problem. It's the conflict DAMM's own deck names — *magatzem efficient vs. repartiment efficient*. Plus a third dimension nobody plans for: **the truck changes shape during the route** as empties come back.
3. **90s solution walkthrough (Option 1 engine)**: hybrid client-cluster + LIFO load, free-space tracker for returns + outbound envases. Show the 3D twin animating through the route.
4. **45s the punchline document**: hold up the **Smart Hoja Carga** — same DAMM letterhead, same columns, same picker workflow. Only difference: the `Descarga` column is filled. "Zero training. Zero new tools. The picker walks the warehouse the same way; the driver opens the truck and his stuff is already in stop order."
5. **45s impact**: KPIs vs. the real DR0027 baseline. Extrapolate to the 470-vehicle network.
6. **30s driver mobile mockup**: same data, driver-side. CONTADO stops flagged so cash collection isn't a surprise.
7. **30s honest limits + next step**: real geocoding accuracy, longer history, rolling re-optimisation when a stop runs late, integration with DDIDGP / SAP printing.

## Differentiators (creativity 15%)

- **Output is the existing paperwork**, not a new tool — the `Descarga` column trick. No team that hasn't read the RECURSOS folder closely will think of this.
- **Reverse-logistics-aware packing** — most teams will optimise outbound only.
- **Outbound envases as ballast for inbound empties** — turns a problem (those bulky empty crates the picker has to load too) into the solution (where return empties go).
- **Curtain-aware lateral accessibility** as a hard constraint, not a soft preference.
- **Driver familiarity bias** as an optional optimiser knob — respect tribal knowledge in v1.
- **CONTADO awareness** — cash-collection stops surfaced in the driver UI.
- **Per-recommendation explanation cards** — judges trust what they understand.
- **Apple-to-apple baseline** from the actual DR0027 / 2026-05-08 paperwork, not a synthetic reconstruction.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Geocoding 1,200 addresses hits Nominatim rate limits | Ask the technical mentor for a Mapbox/Google key in hour 0; cache results; Nominatim fallback only if no key available |
| Live demo URL not ready in time | Have the technical mentor start provisioning in hour 0; localhost screencast as fallback |
| OR-Tools doesn't converge in 30s | Restrict demo to one route (DR0027 / 2026-05-08); cap solver time; fall back to nearest-neighbour heuristic if needed |
| 3D truck twin eats more dev time than budgeted | Keep a 2D top-down fallback in `TruckTwin3D.tsx`; don't let viz block the optimiser |
| `Layout Mollet.xlsx` grid unparseable | Sort pick list by `Ubic.` lex order — captures spatial locality cheaply; only model the grid if a mentor explains it |
| Truck pallet dims unknown | Assume 6-pallet = 2×3, 8-pallet = 2×4, EUR pallets 80×120 cm; validate hour 0–2 with mentor |
| Reverse-logistics rate per SKU unknown | Use the 60% global average from the brief; expose as a slider in the UI |
| Frontend dev solo on Next.js | The two backend devs help with React components in hour 14–20 |

## Verification

- **Unit tests**: 3-stop toy VRP, capacity-overflow rejection, returns-overflow rejection.
- **End-to-end**: run on `DR0027` for 2026-05-08; the proposed plan must (a) be visibly different from the actual Hoja Carga / Hoja Ruta baseline, (b) post a positive KPI delta on at least 3 of 5 metrics, (c) survive a 2-minute review by a DAMM mentor without operational red flags.
- **Demo dry run**: full pitch performed for a mentor at hour 22; iterate on the framing.

## Mentor strategy

We have two mentors available; use them deliberately, don't burn them on questions we can answer ourselves.

### DAMM domain mentor (hour 0–2 hit list — go in with these written down)

1. **Pallet geometry** per truck type (6-pallet and 8-pallet): position grid, exact pallet footprint (EUR 80×120 vs. industrial 100×120), side-curtain reach distances, how barrels/kegs (BRL30, BRL20, TB8) are stowed differently from cases.
2. **Return rates per SKU class** — what fraction of beer-on-tap (BRL), bottled-returnable (RET), one-way (SR) actually comes back, by class. The 60% global average isn't enough.
3. **Service time per stop** today — average minutes parked per stop, peak vs off-peak, and what dominates it (paperwork? unloading? customer interaction?).
4. **Per-customer preferences** beyond the 240 rows in `Horarios Entrega` — are there informal preferences (door codes, alley access, prefer-morning notes) the driver knows but the system doesn't?
5. **Load DR0027 / 2026-05-08** specifically — if a DDI ops person was in the room that day, walk them through our planned baseline reconstruction and ask "did Fran actually deliver in this order?" so we know our as-is benchmark is right.
6. **`Descarga` column semantics** — confirm it's the right slot for our truck-position output, and ask what format DDI would prefer (pallet number? zone code? side+row?).
7. **Layout Mollet 193×98 grid** — only ask if time remains; we have a fallback that doesn't need this.
8. **More data** — can they share another 2–3 days of Hoja Carga / Hoja Ruta for the same route? Lets us validate the optimiser on multiple instances, not just one cherry-picked day.
9. **Lat/lon** — do they have geocoded customer coordinates internally? Saves us the Nominatim risk entirely.

### Technical mentor (domains, APIs, infra)

1. **Live deployment URL** for the demo — a memorable subdomain (`smart-truck.<event-domain>`) hosted somewhere stable so we can demo from the projector laptop without local-network risk. Way more impressive than localhost.
2. **Geocoding API key** — Mapbox or Google Maps key for the duration of the event removes the Nominatim rate-limit risk entirely. Ask early; provisioning may take an hour.
3. **Tile/map service** — same source as the geocoder ideally, for the route map.
4. **Deployment platform** — Vercel for Next.js + Render/Fly.io for FastAPI is fine; ask if the event has preferred infra (some hackathons sponsor Vercel/AWS credits).
5. **HTTPS / CORS** between frontend and backend — boring but blocks the demo if not set up early.
6. **Print-to-PDF** for the Smart Hoja Carga / Hoja Ruta — confirm WeasyPrint or ReportLab is fine on the deploy target, or if we need a different toolchain.

Have the technical mentor working on (1) and (2) in parallel from hour 0; both are gating for the polished demo and have lead time we can't compress.
