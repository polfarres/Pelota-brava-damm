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

### 🔴 MQ-D-01 — Truck pallet geometry

**Ask**: *"¿Cómo es exactamente la disposición física de pallets en un camión de 6 y de 8 palets? ¿Es 2×3 y 2×4? ¿Qué medida de palet usáis (europalet 80×120 o industrial 100×120)? ¿Y para los barriles y las bombonas de CO₂ — van también sobre palet o tienen su propia zona?"*

**Why**: A-01 in the spec is a guess. The hybrid load packer geometry (FR-006) is built on top of this assumption. If barrels go in a separate slot, the load model needs an extra zone type.

**What we do**: lock the truck grid in `backend/smart_truck/optimize/load.py:TRUCK_LAYOUTS`. Decide whether barrels are first-class pallet positions or a separate "barrel zone".

**Fallback**: assume 2×3 / 2×4, EUR pallets, barrels treated as 1 pallet each.

### 🔴 MQ-D-02 — Return rates per SKU class

**Ask**: *"El brief dice que el 60% de productos son retornables. Para un cálculo realista, ¿podríais aproximar el ratio real de devolución de envases por tipo? Por ejemplo: barriles BRL30/BRL20, botellas RET, latas LT, sin retorno SR — ¿qué porcentaje de cada uno vuelve realmente al camión durante la entrega?"*

**Why**: A-07 in the spec drives the entire returns / free-space tracker (FR-007). 60% global is too coarse — barrels are 100% returnable, one-way packs are 0%.

**What we do**: populate `Product.expected_return_rate` per SKU class. Drives the volume of envases the truck must absorb.

**Fallback**: BRL=100%, RET=80%, SR=0%, others=60%.

### 🔴 MQ-D-03 — Ground truth for the demo carga

**Ask**: *"Tenemos los PDFs Hoja Carga y Hoja Ruta de la carga 11764300, ruta DR0027, del 8 de mayo. ¿El orden de los clientes en la Hoja Ruta es el orden real en que Fran entregó? ¿O Fran cambió el orden sobre la marcha?"*

**Why**: A-04 — our entire baseline KPI honesty depends on this. If the printed order isn't the real order, our "Smart Truck saves X%" claim is shaky.

**What we do**: if printed order = real order, use it as-is. If not, ask the mentor for the real sequence (even verbally) and encode it as the baseline.

**Fallback**: use printed order, footnote in pitch as "as-printed baseline".

### ~~MQ-D-04~~ — Resolved 2026-05-09

The `Detalle entrega.Ruta` column uses the standard `DR…` codes throughout — joinable directly with `ZONAS.RutReal` and Hoja Carga. A single legacy `DA…` route exists in a small number of rows; filter it out during ETL. No mentor question needed.

### ~~MQ-D-05~~ — Resolved 2026-05-09

`Horarios Entrega.Deudor` uses the standard 10-digit `9100…` customer IDs from row ~28 onwards (the first rows show legacy 6-digit IDs that we can drop during ETL). Direct join with `Direcciones.Cliente` works. No mentor question needed.

### 🟡 MQ-D-06 — Time window defaults

**Ask**: *"Solo 240 clientes tienen un horario explícito en el fichero de horarios. Los demás, ¿se considera que están abiertos durante el horario HoReCa estándar, o que el chófer ya conoce informalmente sus preferencias? Y los sábados — ¿no hay datos porque no se reparte, o porque ningún cliente tiene horario definido el sábado?"*

**Why**: A-05. Drives time-window feasibility for ~80% of customers.

**What we do**: encode the default window in `backend/smart_truck/optimize/route.py:DEFAULT_WINDOW`.

**Fallback**: 08:00–14:00 + 17:00–22:00; assume Saturday closed.

### 🟡 MQ-D-07 — Volumen Entrega units on Hoja Carga totals

**Ask**: *"En la Hoja Carga, los totales muestran `Total Volumen Entrega: 338.21` y `Total Volumen Devolución: 4`. ¿En qué unidad están — m³, litros, palets-equivalentes? Y ¿por qué la devolución de volumen es solo 4 si el peso de devolución son 2.094 kg?"*

**Why**: We want to display volume KPIs honestly; getting the unit wrong makes the pitch sound wrong.

**What we do**: label our KPI panel correctly; potentially recompute volume ourselves from `ZM040` if the printed totals use a non-obvious unit.

**Fallback**: don't display Hoja Carga's printed volume totals; compute and display only our own from ZM040 dimensions.

### 🟡 MQ-D-08 — `SSTT` column on Hoja Ruta

**Ask**: *"En la Hoja Ruta hay una columna `SSTT` que en nuestro ejemplo siempre es `NO`. ¿Qué representa? ¿Es una bandera operativa que pueda condicionar la ruta?"*

**Why**: We don't want to ignore an operational flag that the driver actually acts on.

**What we do**: if it's relevant (e.g. "S" means "send via subcontractor") we model it; otherwise we skip.

**Fallback**: ignore the column.

### 🟡 MQ-D-09 — Warehouse location code structure

**Ask**: *"Los códigos de ubicación tipo `AA02A1`, `FA05A2`, `ZCG`, `A0DISTRIDA` — ¿siguen un esquema regular? ¿Las dos primeras letras son el pasillo y los siguientes dígitos la posición? Conocerlo nos permitiría ordenar la lista de picking de forma más natural para el preparador."*

**Why**: We sort the Smart Hoja Carga by `Ubicación` lex order — confirming the structure means we can do something smarter (e.g. group by aisle).

**What we do**: implement aisle-aware sort in FR-010.

**Fallback**: lex sort.

### 🟡 MQ-D-10 — Service time per stop

**Ask**: *"¿Cuánto tarda Fran de media en una parada — desde que aparca hasta que arranca? ¿Y qué porcentaje de ese tiempo es buscar producto dentro del camión vs. descargar vs. cobrar / firmar?"*

**Why**: A-06. Calibrates the unload-time-savings KPI. If currently 12 min/stop and 4 min is searching, our model can claim a credible reduction.

**What we do**: encode the breakdown in `KpiEngine.SERVICE_TIME_MODEL`.

**Fallback**: 10 min base + 2 min per distinct in-truck zone (our current assumption).

### 🟡 MQ-D-11 — How does the warehouse currently load the truck?

**Ask**: *"En la práctica, ¿cómo decide el preparador qué pallet va dónde dentro del camión? ¿Existe alguna convención (los retornables atrás, las bebidas frías cerca de la puerta) o es totalmente libre? ¿La columna `Descarga` de la Hoja Carga la rellena alguien manualmente alguna vez?"*

**Why**: This is the heart of our pitch. If `Descarga` is *never* used, our intervention is genuinely free. If some drivers fill it themselves, we have to pitch our tool as automation, not introduction.

**What we do**: tune the pitch wording; potentially show a v0 of the Smart Hoja Carga that mimics any existing convention.

**Fallback**: assume `Descarga` is always blank.

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

### 🟢 MQ-D-14 — CONTADO operational preference

**Ask**: *"Las paradas CONTADO (cobro en efectivo) — ¿hay alguna preferencia operativa? ¿Se intentan agrupar al inicio del turno, o se hacen como caen en la ruta?"*

**Why**: If there's a real-world preference, the optimiser can incorporate it as a soft constraint.

**What we do**: add an optional "prefer-CONTADO-early" mode.

**Fallback**: just flag CONTADO in the driver UI; no routing impact.

### 🟢 MQ-D-15 — Driver familiarity

**Ask**: *"Los chóferes que llevan años haciendo la misma ruta — ¿qué pasaría si nuestro sistema les sugiere un orden distinto al que ellos siempre usan? ¿Lo aceptarían si está justificado, o prefieren mantener su orden conocido?"*

**Why**: Validates the "driver familiarity bias" knob in FR-005.

**What we do**: tune the soft penalty weight; pitch the tool as "decision support" not "instruction".

**Fallback**: leave the soft penalty at a default and explain the choice in the pitch.

---

## Technical / infra mentor

Open with: *"Estamos construyendo una app web (FastAPI backend + Next.js frontend) y queremos que la demo del pitch corra en una URL pública. Necesitamos algunas piezas de infra que tienen lead time."*

### 🟢 MQ-T-01 — Live demo deployment (deferred)

Decision 2026-05-09: **demo runs on localhost** for v1. Pitch will use the team's laptop + projector. We can ask the technical mentor for a live URL later if time and the demo are stable enough to warrant it.

**Fallback (only if we revisit)**: Vercel free tier (frontend) + Render free tier (backend) on default subdomains.

### 🔴 MQ-T-02 — Geocoding + map API key

**Ask**: *"¿Nos podéis facilitar una API key de Mapbox o Google Maps para el evento? La usaremos para (a) geocodificar 1.200 direcciones de clientes y (b) renderizar el mapa de ruta en el frontend. Sin key, dependemos de Nominatim que tiene rate-limit y puede no terminar a tiempo."*

**Why**: The 1,200-address geocode against Nominatim takes ~20 minutes if it doesn't get blocked; against Mapbox it takes seconds.

**What we do**: kick off the geocode batch as soon as we have the key.

**Fallback**: Nominatim with 1 req/sec backoff, started at hour 0.

### 🟡 MQ-T-03 — Tile / map service

**Ask**: *"Para el mapa interactivo del frontend, ¿usamos las tiles de Mapbox (mismas que el geocoder), Google Maps, o algo OSM como Leaflet+Carto? ¿El evento tiene preferencia o cuenta de prueba?"*

**Why**: Mapbox/Google look polished; OSM tiles look amateur next to them.

**What we do**: standardise on whatever we get a key for.

**Fallback**: Leaflet + OSM tiles.

### 🟡 MQ-T-04 — HTTPS + CORS

**Ask**: *"Si frontend y backend están en dominios diferentes, ¿qué configuración de CORS y certificados HTTPS recomiendas para el deploy? Queremos evitar sorpresas el día del pitch."*

**Why**: Mixed-content errors and CORS rejections kill demos.

**What we do**: configure FastAPI CORS middleware and force HTTPS in both deploys.

**Fallback**: deploy frontend and backend under the same domain via Vercel rewrites.

### 🟡 MQ-T-05 — Print-to-PDF on the deploy target

**Ask**: *"Vamos a generar PDFs en el backend para reproducir las Hoja Carga y Hoja Ruta de DAMM con nuestras anotaciones. Pensábamos usar WeasyPrint (HTML/CSS → PDF) — ¿tiene problemas en Render/Fly/etc.? Si sí, ¿qué alternativa recomiendas?"*

**Why**: WeasyPrint depends on Pango/Cairo system libs; some serverless platforms don't have them. Better to learn early than at hour 18.

**What we do**: pick the toolchain (WeasyPrint vs. ReportLab vs. headless Chrome) based on advice.

**Fallback**: ReportLab (pure Python, ugly but reliable).

### 🟢 MQ-T-06 — Backend persistence

**Ask**: *"¿Necesitamos una base de datos managed para la demo, o es suficiente con archivos parquet en disco / volumen montado? Sería un volumen de unos 200 MB."*

**Why**: A managed DB adds setup time we don't have.

**What we do**: probably just files; ask anyway in case the platform has a free Postgres they recommend.

**Fallback**: parquet on the container's local disk; reload on cold start (acceptable since data is static).

### 🟢 MQ-T-07 — Observability for the demo

**Ask**: *"¿Recomiendas algún logging / error-tracking ligero para el día del pitch? Si la API revienta delante de los jueces, queremos saberlo en 2 segundos."*

**Why**: Sentry free tier or similar catches the embarrassing crash before the panel notices.

**What we do**: integrate it if it's a 5-minute setup.

**Fallback**: structured logs to stdout; check before the pitch.

### 🟢 MQ-T-08 — Domain & SSL ownership

**Ask**: *"Si nos dan la subruta `smart-truck.<dominio-del-evento>`, ¿quién es el owner del dominio, y a quién hay que escribir si hay un problema con el certificado SSL durante el evento?"*

**Why**: When something breaks at hour 23 we want a name, not a process.

**What we do**: save the contact in `README.md`.

---

## Suggested meeting plan

If we get 30 minutes total per mentor, here's the order:

**DAMM (30 min)**:
1. Set context (1 min) — DR0027 / 2026-05-08 as our case.
2. MQ-D-01 (3 min)
3. MQ-D-02 (3 min)
4. MQ-D-03 (4 min) — possibly the longest because we walk through the actual paperwork.
5. MQ-D-11 (3 min) — central to pitch.
6. MQ-D-06, 07, 08, 09, 10 in rapid fire (10 min) — minor calibrations.
7. Buffer for follow-ups (6 min).
8. The 🟢 questions only if minutes remain.

**Technical (15 min)**:
1. MQ-T-01 + MQ-T-02 (8 min) — both have lead time and need to start *during* this conversation.
2. MQ-T-04 + MQ-T-05 (5 min) — pick toolchain.
3. The rest if minutes remain (2 min).

## After the meetings

For each answer received, write a one-liner into `Specifications.md` § 5 *Open assumptions* either confirming or replacing the assumption (e.g. *"A-01 confirmed: 6-pallet trucks are 2×3, EUR pallets, barrels go on dedicated rear pallet slots — see meeting notes 2026-05-09 14:00."*).

If a 🔴 question comes back blocked or the answer is ambiguous, *don't guess* — surface it in the team chat immediately so we can pick the fallback consciously rather than discover it at hour 14.
