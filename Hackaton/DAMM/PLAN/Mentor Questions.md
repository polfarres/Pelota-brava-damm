# Mentor Questions — Smart Truck

Two mentors. Different agendas. Don't mix them — book separate slots.

For every question:
- **Ask** = what to read aloud (Spanish/Catalan-friendly phrasing).
- **Why** = why we need it (don't read this aloud; here so you can defend the question if pushed back).
- **What we do with the answer** = the concrete decision the answer unblocks.
- **Fallback** = what we do if they don't know or can't say.

Question IDs:
- `MQ-D-xx` = DAMM domain mentor.
- `MQ-T-xx` = Technical/infra mentor.

Priorities:
- 🔴 **Critical** — blocks build progress; ask first.
- 🟡 **Important** — affects correctness; ask in same session if time.
- 🟢 **Nice-to-have** — improves polish; ask only if mentor still has time.

---

## DAMM domain mentor

Open with one sentence to set context: *"Estamos optimizando ruta y carga conjuntamente para una carga real, la `11764300` del 8 de mayo del repartidor Fran Romero, ruta DR0027. Vamos a usarla como caso de estudio. Tenemos algunas dudas operativas para que el modelo refleje la realidad."*

### ✅ MQ-D-01 — Truck pallet geometry — Locked 2026-05-09 (still ask mentor to confirm)

**Locked**: furgoneta 1×3, 6-pallet truck 2×3, 8-pallet truck 2×4. EUR 80×120 cm pallets. Vertical stack ≤ 1.80 m per slot. Barrels = 1 slot each (stack vertically up to 1.80 m).

**Ask the mentor anyway** (5 min) to confirm and to learn whether kegs are loaded somewhere physically distinct from cases (e.g. floor near the back door): *"Hemos asumido furgo 1×3, camión 6 palets 2×3 y de 8 palets 2×4, EUR 80×120 con apilado vertical hasta 1,80 m. Barriles ocupan slot completo. ¿Coincide con la realidad?"*

### ✅ MQ-D-02 — Return rates per SKU class — Locked 2026-05-09 (still ask mentor for refinement)

**Locked**: BRL = 100%, RET = 80%, SR = 0%, other = 60%. Drives the returns / free-space tracker.

**Ask the mentor anyway** (3 min): *"Estamos asumiendo BRL 100%, RET 80%, SR 0%, otros 60%. ¿Veis bien esos números o hay categorías con un ratio de devolución sustancialmente distinto?"*

### 🔴 MQ-D-03 — Ground truth for the demo carga — STILL OPEN, ask mentor

We've decided to **trust the printed Hoja Ruta order** as Fran's actual sequence for v1, but we still want a sanity check from the mentor.

**Ask**: *"Tenemos los PDFs Hoja Carga y Hoja Ruta de la carga 11764300, ruta DR0027, del 8 de mayo. ¿El orden de los clientes en la Hoja Ruta es el orden real en que Fran entregó? ¿O Fran cambió el orden sobre la marcha?"*

**If mentor says "no, Fran resequences in the field"**: ask for the real sequence verbally and encode it as the baseline; otherwise our pitch's KPI delta is overstated.

### ~~MQ-D-04~~ — Resolved 2026-05-09

The `Detalle entrega.Ruta` column uses the standard `DR…` codes throughout — joinable directly with `ZONAS.RutReal` and Hoja Carga. A single legacy `DA…` route exists in a small number of rows; filter it out during ETL. No mentor question needed.

### ~~MQ-D-05~~ — Resolved 2026-05-09

`Horarios Entrega.Deudor` uses the standard 10-digit `9100…` customer IDs from row ~28 onwards (the first rows show legacy 6-digit IDs that we can drop during ETL). Direct join with `Direcciones.Cliente` works. No mentor question needed.

### ✅ MQ-D-06 — Time window defaults — Resolved 2026-05-09

`Horarios Entrega` is **complete**: every customer × weekday is explicit. `K = L = 00:00:00` means closed that day. No "default window" concept needed. Saturday is absent simply because customers are closed; Sunday (7) appears for the few customers open then.

No mentor question required.

### ✅ MQ-D-07 — Volumen Entrega units on Hoja Carga totals — Locked 2026-05-09

We **drop the volume KPI** for v1 and display weight + count only. Hoja Carga's printed `Total Volumen` numbers are not surfaced. No mentor question required.

### ✅ MQ-D-08 — `SSTT` column on Hoja Ruta — Locked 2026-05-09

Decision: ignore the column entirely. No mentor question required.

### ✅ MQ-D-09 — Warehouse location code structure — Locked 2026-05-09

Decision: lex sort, treat as opaque. No mentor question required.

### ✅ MQ-D-10 — Service time per stop — Locked 2026-05-09

Locked model: `service_time_min = 10 + 2 × distinct_in_truck_zones_touched`. Hybrid load packer reduces zones-touched per stop, materialising the unload-time saving.

**Ask the mentor anyway** (3 min) to calibrate the constants: *"Estamos modelando el tiempo por parada como 10 minutos base + 2 minutos por zona distinta del camión a la que tiene que acceder. ¿Coincide con tu intuición? ¿Cuánto tarda Fran de media en una parada hoy?"*

### 🔴 MQ-D-11 — How does the warehouse currently load the truck? — STILL OPEN, ask mentor

Decision 2026-05-09: pitch leads with "Descarga always blank, free intervention slot". This still needs mentor confirmation — it's the heart of the pitch.

**Ask**: *"En la práctica, ¿cómo decide el preparador qué pallet va dónde dentro del camión? ¿Existe alguna convención (los retornables atrás, las bebidas frías cerca de la puerta) o es totalmente libre? ¿La columna `Descarga` de la Hoja Carga la rellena alguien manualmente alguna vez?"*

**If mentor says some preparers fill it informally**: soften pitch wording from "free slot" to "automation of an existing manual practice" — both work, just different framing.

### 🟢 MQ-D-12 — More demo data

**Ask**: *"Si fuera posible, ¿podríamos tener Hoja Carga / Hoja Ruta de 2 o 3 días más para la misma ruta DR0027? Nos permitiría validar que el optimizador no solo funciona en un día cherry-picked."*

**Why**: A 3-day validation in the pitch is much more credible than 1-day.

**What we do**: run the pipeline on each day; show consistent KPI deltas.

**Fallback**: run on the one day we have.

### 🟢 MQ-D-13 — Internal lat/lon

**Ask**: *"¿DAMM tiene internamente las coordenadas (lat/lon) de los clientes ya geocodificadas? Nos ahorraría tener que geocodificar 1.200 direcciones."*

**Why**: Removes the geocoding risk entirely.

**What we do**: import the CSV and skip Nominatim.

**Fallback**: geocode ourselves with the technical mentor's API key.

### ✅ MQ-D-14 — CONTADO operational preference — Locked 2026-05-09

Decision: flag in driver UI only, no routing impact. Mentor question optional — only ask if there's an obvious operational pattern they want us to encode.

### ✅ MQ-D-15 — Driver familiarity — Locked 2026-05-09

Decision: soft penalty (medium weight) on deviating from baseline, with a UI toggle ("familiar" vs "optimal"). Mentor question optional — useful as colour for the pitch, not blocking.

---

## Technical / infra mentor

Open with: *"Estamos construyendo una app web (FastAPI backend + Next.js frontend) y queremos que la demo del pitch corra en una URL pública. Necesitamos algunas piezas de infra que tienen lead time."*

### 🟢 MQ-T-01 — Live demo deployment (deferred)

Decision 2026-05-09: **demo runs on localhost** for v1. Pitch will use the team's laptop + projector. We can ask the technical mentor for a live URL later if time and the demo are stable enough to warrant it.

**Fallback (only if we revisit)**: Vercel free tier (frontend) + Render free tier (backend) on default subdomains.

### ✅ MQ-T-02 — Geocoding — Locked 2026-05-09

Decision: **Nominatim** (OpenStreetMap), no key, 1 req/sec, results cached to `backend/data/geo_cache.json`. No mentor question required.

### ✅ MQ-T-03 — Tile / map service — Locked 2026-05-09

Decision: **Leaflet + CartoDB Positron** tiles, no key. No mentor question required.

### 🟢 MQ-T-04 — HTTPS + CORS — Deferred (localhost only for v1)

Localhost demo: backend at `:8000`, frontend at `:3000`. Configure FastAPI CORS to allow `http://localhost:3000`. Trivial; no mentor needed.

### ✅ MQ-T-05 — PDF rendering — Locked 2026-05-09

Decision: **ReportLab** (pure Python). No mentor question required.

### ✅ MQ-T-06 — Backend persistence — Locked 2026-05-09

Decision: parquet files in repo, regenerated by ETL. No DB. No mentor question required.

### 🟢 MQ-T-07 — Observability — Defer

Stdout logs are sufficient for a localhost demo. Skip Sentry / error-tracking unless we have spare time at hour 20+.

### 🟢 MQ-T-08 — Domain & SSL ownership — N/A (localhost only)

---

## Suggested meeting plan (post 2026-05-09 user lock-in)

Most questions are now locked by team decision. Use the DAMM mentor as a sanity check + to unblock the few remaining open items. The technical mentor session is no longer necessary for v1 since localhost + free providers cover everything.

**DAMM mentor (15 min, focused)**:
1. Set context (1 min) — DR0027 / 2026-05-08, walk in with the printed Hoja Carga in hand.
2. **🔴 MQ-D-03** ground truth on the as-printed order (3 min) — the only critical open item.
3. **🔴 MQ-D-11** the Descarga column convention (3 min) — pitch-critical.
4. **MQ-D-01** quick confirm of truck grids + barrel handling (2 min).
5. **MQ-D-02** confirm return rate ranges (2 min).
6. **MQ-D-10** sanity-check the 10 + 2×zones service-time model (2 min).
7. Buffer (2 min) — let them volunteer anything we haven't asked.

**Bonus asks if mentor offers more time**:
- More demo days for DR0027 (validation set).
- Internal lat/lon (would let us drop Nominatim).
- Per-customer informal preferences not in the Horarios file.

## After the meeting

For each answer received, update `Specifications.md` § 5 *Locked decisions* with a confirmation note (or, if mentor contradicts, a replacement). Surface contradictions in team chat so we adjust consciously.
