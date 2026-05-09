# Smart Truck — Pitch script (5 min)

Companion to `Specifications.md` + `Smart Truck — Hackathon Plan.md`. This is the speaker outline for the final pitch. Total budget: **5 min**, with **30 s slack**.

The team is presenting a **decision-support tool** that jointly optimises the delivery route AND the truck-load configuration for the DDI Mollet warehouse, accounting for time windows, side-curtain access constraints, and reverse-logistics flows. The pitch needs to land four things in order:

1. The operational problem is **real, lived, and unaddressed**.
2. We're proposing the **smallest possible change** to DDI's actual paperwork — no new tools.
3. The technical engine is **honest** (built on real data, real PDFs, real geometry).
4. Quantified impact extrapolated to the 470-vehicle fleet.

Judges weight: **30% applicability · 25% technical · 20% impact · 15% creativity · 10% pitch**.

---

## Demo target — locked

- Carga **`11764300`**, route **`DR0027`**, vehicle **`7524KXX`** (V235045), driver **Fran Romero (850004)**.
- Date **2026-05-08**, 18 stops in **Sant Julià de Vilatorta → Calldetenes → Folgueroles** (Osona, ~70 km north of Mollet).
- Outbound: **837 units / 4 719 kg / 88 line items** across the four Hoja Carga sections.
- Returnable empties: **259 units / 2 094 kg** (~31 % return-by-units, 44 % by weight).
- 7 stops are **CONTADO** (cash-on-delivery), 11 are **CRÉDITO**.
- Three lines are **abonos** (credit notes, negative proforma totals).

This is the *real* paperwork that left the Mollet office that morning. Every metric in the pitch is grounded against it.

---

## 5-minute script

### Beat 1 — The hook (30 s)

> *(Speaker holds up a printed copy of the real `Hoja Carga.pdf` for DR0027 / 2026-05-08.)*

**"This is what Fran Romero got at 6 a.m. yesterday morning. 18 stops. 4.7 tonnes of beverages going out. 2.1 tonnes of empty crates coming back. And one column on this sheet" — point at the empty `Descarga` column — "is blank.**

**Nobody fills it. Fran has to figure out where each pallet goes inside the truck — in his head — every morning. And then he has to remember it for nine hours."**

**Speaker notes**:
- Print the actual page 1 of `Hackaton/DAMM/RECURSOS/Hoja Carga.pdf` at A4 the night before — it's the prop.
- Don't apologise for the technical detail. Hold the paper up. Let it land.

### Beat 2 — Problem reframe (30 s)

**"This isn't a route problem. DAMM's own briefing slide named it: there's a conflict between *magatzem efficient* and *repartiment efficient*. The picker wants the truck loaded by warehouse location. The driver wants it loaded by customer. Today, those two views are reconciled informally, in one human's head, per route, per driver.**

**And there's a third dimension nobody plans for: the truck changes shape during the route. 31 % of what goes out comes back as empties. As the day progresses, the load mutates."**

**Speaker notes**:
- Quote DAMM's wording back to them — slide 6 of their deck named the tension explicitly.
- The "60 %" returnable figure from the brief is the *upper bound* on classes; observed in DR0027 is 31 % by units, which we cite as "real load" in the pitch.

### Beat 3 — Solution walkthrough (90 s)

> *(Switch to the live dashboard at `localhost:3000`. The 3D truck twin is the centerpiece.)*

**"Smart Truck takes one route's orders and produces three things jointly: a stop sequence, a stack-LIFO pallet plan, and a returns plan."**

**(1) Stop sequence** — *(point at map)* — "Optimised against time windows and the driver's habitual order. We respect tribal knowledge with a soft penalty against deviating from the printed route."

**(2) Stack-LIFO pallet plan** — *(point at 3D truck)* — "The truck leaves Mollet **100 % full** — no wasted space for empties. Each pallet position is *typed* — case-pallet or barrel-pallet — and within each pallet the customer cargo is stacked in *reverse delivery order*. The next stop's items are physically at the top of the pallet, ready to lift off. We solve the assignment as a mixed-integer program — minimising how spread out each customer's cargo is across pallets — and CBC finds the optimum in under a second on this scale."

**(3) Returns plan** — *(scrub the 3D twin to mid-route)* — "As cargo goes out, each customer's empties go right back into the same pallet position the full cargo just left. **Sixty percent of delivered volume comes back as empties** — that's why the truck ends the day at forty percent capacity, by design. Nobody else models this."

**Speaker notes**:
- The 3D twin animation is the demo. If r3f goes sideways, fall back to the 2D top-down SVG (Track C has a fallback).
- The four technically interesting ideas, in order of "lingering" priority:
  1. *Truck leaves 100 % full* (A-36) — no envase gap.
  2. *Within-pallet reverse-LIFO stacking* (A-38) — top = first delivered.
  3. *Barrel/case segregation* (A-37) — physical reality respected.
  4. *MILP customer-to-pallet assignment* — pitchable as "we solve it as an integer program".
- If a judge asks "why MILP, why not heuristic?" → "Heuristic is ~1 % worse on cluster spread. MILP gives provable optimality in under a second. Both are wired; we use MILP, fall back to heuristic on time-out."

### Beat 4 — The punchline document (45 s)

> *(Hold up two pieces of paper side by side: the original `Hoja Carga.pdf` and our **Smart Hoja Carga**.)*

**"This is what changes for DDI. Same letterhead. Same four sections — `Carga lleno`, `lleno sin ubicación`, `retorno`, `envases`. Same column order. Same picker workflow.**

**The only difference is the `Descarga` column. We populated it.**

**Zero training. Zero new tools. The picker walks the warehouse the same way they did yesterday. The driver opens the truck and his stuff is already in stop order."**

**Speaker notes**:
- This beat is **load-bearing** for the applicability score. Practise the "same…same…same…ONLY difference" cadence.
- Print both PDFs from the running backend (`GET /plan/DR0027-2026-05-08/hoja-carga.pdf`) the night before.

### Beat 5 — Impact (45 s)

> *(Point at the KPI panel on the dashboard.)*

**"On Fran's actual route yesterday:"**

| KPI | Baseline | Smart | Δ |
|---|---|---|---|
| Total km | *(from /baseline)* | *(from /plan)* | – x % |
| Travel + service time | – | – | – x % |
| In-truck searches | **~80** | **18** | – ~75 % |
| Truck space utilisation | – | – | + x pp |

**"Extrapolating across the 470-vehicle fleet — even being conservative on the route side — the in-truck-search reduction alone is the equivalent of one full driver-day per truck per month."**

**Speaker notes**:
- Numbers will firm up once Track A's optimiser is wired and we run it against the real DR0027 baseline. **Update this table from the live dashboard right before pitching.**
- The "in-truck searches" delta is the most defensible: baseline is ~5 zones touched per stop × 18 stops ≈ 80; smart is 1 per stop × 18 = 18. That's the operational core of the saving.

### Beat 6 — Driver mockup (30 s)

> *(Switch to `/driver` on a phone-frame.)*

**"Same plan, driver-side. Three screens. Next stop with the curtain to open. Item list with the empties to collect. Capacity gauge so cash collection isn't a surprise — CONTADO stops are flagged red."**

**Speaker notes**:
- Don't dwell. The frontend mockup is decoration; the algorithm is the substance.
- Real CONTADO count for DR0027: 7 of 18 stops, 2 891 €.

### Beat 7 — Honest limits + next step (30 s)

**"What we'd do with another month:"**

- **Real-time re-optimisation** when a stop slips by more than 15 min.
- **Albarán parsing** for exact per-stop attribution of warehouse zones — today we use a defensible average.
- **Driver-side voice prompts** so the screen isn't in the way during unload.
- **Direct integration with DDIDGP** so the Smart Hoja Carga ships from the same SAP that prints the original today.

**Speaker notes**:
- Don't oversell. The honest-limits beat earns the technical-quality score.
- If asked at Q&A about the optimiser engine: OR-Tools VRP-TW with a soft penalty on driver-familiarity, falling back to a nearest-neighbour + 2-opt heuristic if the install is flaky.

---

## Hero artifacts (print the night before)

1. **Original Hoja Carga page 1** — `Hackaton/DAMM/RECURSOS/Hoja Carga.pdf`. The "blank Descarga" prop.
2. **Smart Hoja Carga page 1** — `curl -o smart-carga.pdf http://localhost:8000/plan/DR0027-2026-05-08/hoja-carga.pdf` once Track A's plan is wired.
3. **Original Hoja Ruta** — same workflow.
4. **Smart Hoja Ruta** — same workflow, reordered to optimised sequence with ETA column.

Print both pairs at A4 portrait, full colour. Glue or staple side-by-side so a single sheet shows "before / after" for each.

---

## Numbers to memorise

| Datum | Value | Provenance |
|---|---|---|
| DDI fleet size | **470 vehicles** | INTERHACK BCN deck slide 3 |
| Mollet trucks | **11× 6-pallet · 4× 8-pallet · 4× 8-pallet w/ tail-lift · 1× furgo** | DAMM mentor session |
| Mollet warehouse capacity | **~2 360 pallet positions** | `Layout Mollet.xlsx` |
| Pallet capacity | **60 CE** (caixes estadístiques) | A-31 |
| Vertical stack limit | **1.80 m** per pallet position | A-30 |
| DR0027 outbound | 837 units / 4 719 kg / 88 lines | source Hoja Carga |
| DR0027 returns | 259 units / 2 094 kg | source Hoja Carga |
| DR0027 stops | 18 | source Hoja Ruta |
| DR0027 total carga | 7 832,38 € | source Hoja Ruta footer |
| DR0027 cash collection | 2 891,08 € (7 stops) | source Hoja Ruta footer |
| Geocode hit rate | 189 / 228 = 83 % | Photon on the customer cohort |

---

## Demo dry-run checklist (last 30 minutes before pitch)

- [ ] Backend up: `uvicorn smart_truck.api:app --port 8000` — `GET /health` returns `{"status":"ok"}`.
- [ ] Frontend up: `npm run dev` → `http://localhost:3000`.
- [ ] `GET /baseline?ruta=DR0027&fecha=2026-05-08` returns 18 stops + 51 slots.
- [ ] `POST /plan {"ruta":"DR0027","fecha":"2026-05-08"}` returns 200 (Track A wired).
- [ ] Smart Hoja Carga PDF downloads and prints with populated Descarga.
- [ ] 3D truck twin animates from depot to stop 1 to stop 18 to depot.
- [ ] KPI panel populates with non-zero deltas.
- [ ] Driver mockup loads on phone or phone-framed laptop.
- [ ] Both printed paper props on the table.
- [ ] One spare laptop and a deployed-pdf fallback in case localhost dies on stage.

## Q&A prep — likely questions

**Q. Why not just optimise the route?**
A. DAMM's drivers already optimise the route — they live the territory. The unsolved problem is the *load* configuration, which today is improvised in the picker's head. We make the load decision explicit and show it on the existing paperwork.

**Q. What if a driver doesn't want to follow the new order?**
A. The optimiser carries a soft penalty for deviating from the historical order — there's a UI toggle "familiar mode" / "optimal mode". The driver always wins when they push back.

**Q. How do you handle the 60 % returnable rate not being uniform?**
A. v1 uses the flat 60 % global from the brief (A-35). The mentor flagged seasonal variation; v2 would parameterise per SKU class once we have empirical return data per truck per day.

**Q. Can this scale beyond Mollet?**
A. The vehicle profile YAMLs in `data/vehicles/` are the only Mollet-specific config. Add new profiles for other centres' fleets and the same engine runs.

**Q. What about the access constraints — the *reixa* partition?**
A. The 6P / 8P side-curtain trucks have a central partition that blocks cross-row access. The hybrid load packer respects `slots[].blocked_by` references in the YAML, so a customer's pallet must be reachable from a curtain face when their stop's turn comes.

**Q. Why not a database, why parquet files in the repo?**
A. Hackathon scope. Same backend code runs against a database with one swap of the data layer.

---

## If something breaks on stage

- **3D twin doesn't render**: the dashboard has a 2D top-down SVG fallback. Switch the toggle. Keep talking.
- **Backend dies**: open the pre-rendered Smart Hoja Carga PDF directly. The paper props still work.
- **Map tiles don't load** (offline): zoom out to the Catalonia view; the polyline + numbered markers don't need tiles.
- **Optimiser times out**: skip the 90-second walkthrough beat; lead with the punchline-document beat (which only needs the parsed paperwork). Those slides survive without an optimiser.
