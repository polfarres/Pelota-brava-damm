---
marp: true
theme: default
size: 16:9
paginate: true
backgroundColor: '#ffffff'
color: '#1A1A1A'
footer: 'Damm Smart Truck · Interhack BCN 2026'
style: |
  /* ==== Base typography matching the DAMM deck ==== */
  section {
    font-family: 'Helvetica Neue', 'Inter', 'Segoe UI', sans-serif;
    font-size: 22px;
    padding: 70px 90px 60px 90px;
    color: #1A1A1A;
    background: #ffffff;
  }
  section::after {
    color: #999;
    font-size: 14px;
    font-weight: 400;
    bottom: 25px;
    right: 40px;
  }
  footer {
    color: #999;
    font-size: 14px;
    font-weight: 400;
    bottom: 25px;
    left: 40px;
  }

  /* ==== Section eyebrow + big title pattern ==== */
  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #E30613;
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 12px;
  }
  h1 {
    font-size: 56px;
    font-weight: 700;
    line-height: 1.1;
    color: #1A1A1A;
    margin: 0 0 28px 0;
    letter-spacing: -0.5px;
  }
  h2 {
    font-size: 38px;
    font-weight: 700;
    line-height: 1.15;
    color: #1A1A1A;
    margin: 0 0 24px 0;
    letter-spacing: -0.3px;
  }
  h3 {
    font-size: 22px;
    font-weight: 600;
    color: #1A1A1A;
    margin: 0 0 12px 0;
  }
  strong { color: #E30613; font-weight: 700; }
  em { font-style: normal; color: #555; }

  ul, ol { line-height: 1.6; }
  li { margin-bottom: 8px; }

  blockquote {
    font-size: 28px;
    font-style: italic;
    color: #1A1A1A;
    border-left: 4px solid #E30613;
    padding: 8px 0 8px 24px;
    margin: 24px 0;
    line-height: 1.3;
  }

  table {
    font-size: 18px;
    width: 100%;
    border-collapse: collapse;
  }
  table th {
    text-align: left;
    color: #999;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 12px;
    letter-spacing: 1px;
    padding: 10px 14px;
    border-bottom: 2px solid #E30613;
  }
  table td {
    padding: 10px 14px;
    border-bottom: 1px solid #eee;
  }

  pre {
    background: #f7f7f7;
    color: #1A1A1A;
    padding: 18px 22px;
    border-left: 4px solid #E30613;
    border-radius: 0;
    font-size: 15px;
    line-height: 1.5;
    margin: 18px 0;
  }
  code { background: #f3f3f3; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }

  /* ==== Cover slide ==== */
  section.cover {
    background: linear-gradient(135deg, #fff 0%, #f8f8f8 100%);
    padding: 110px 100px;
  }
  section.cover h1 {
    font-size: 96px;
    line-height: 1;
    margin-bottom: 0;
    color: #1A1A1A;
  }
  section.cover h1 strong { color: #E30613; }
  section.cover .tagline {
    font-size: 28px;
    color: #555;
    font-weight: 400;
    margin: 24px 0 64px 0;
    border-left: 4px solid #E30613;
    padding-left: 20px;
  }
  section.cover .meta {
    color: #999;
    font-size: 16px;
    letter-spacing: 1px;
  }

  /* ==== Closing slide ==== */
  section.closing {
    background: #1A1A1A;
    color: #fff;
    padding: 110px 100px;
  }
  section.closing h1 { color: #fff; font-size: 64px; }
  section.closing strong { color: #E30613; }
  section.closing .tagline {
    font-size: 24px;
    color: #ddd;
    border-left: 4px solid #E30613;
    padding-left: 20px;
    margin-top: 20px;
  }

  /* ==== KPI grid ==== */
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 24px;
    margin-top: 24px;
  }
  .kpi {
    background: #f8f8f8;
    border-top: 4px solid #E30613;
    padding: 24px;
  }
  .kpi-eyebrow {
    text-transform: uppercase;
    color: #999;
    font-size: 12px;
    letter-spacing: 1.5px;
    margin-bottom: 8px;
  }
  .kpi-value {
    font-size: 56px;
    font-weight: 700;
    color: #E30613;
    line-height: 1;
    letter-spacing: -1px;
  }
  .kpi-detail {
    font-size: 13px;
    color: #555;
    margin-top: 10px;
    line-height: 1.4;
  }

  /* ==== Two-column ==== */
  .cols {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 40px;
  }
  .col-with-rule {
    border-left: 1px solid #ddd;
    padding-left: 30px;
  }

  /* ==== Pill / chip ==== */
  .pill {
    display: inline-block;
    background: #E30613;
    color: #fff;
    padding: 4px 12px;
    border-radius: 14px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
  }

  /* ==== Big single number for hero stats ==== */
  .hero-num {
    font-size: 140px;
    font-weight: 700;
    color: #E30613;
    line-height: 1;
    letter-spacing: -3px;
  }
---

<!-- _class: cover -->
<!-- _paginate: false -->
<!-- _footer: '' -->

<div class="meta">PELOTA BRAVA · INTERHACK BCN 2026</div>

# Smart **Truck**

<div class="tagline">
Mateix recorregut. Camió impecable.<br/>
Optimització conjunta de ruta i càrrega per a DDI Mollet.
</div>

<div class="meta">Equip Pelota Brava · Repte Damm DDI · 09 oct 2026</div>

<!--
0:00 — Hola. Som Pelota Brava i hem treballat el repte Damm.
La idea: reduir TOT el temps perdut en el procés de distribució —
ruta, càrrega i descàrrega — sense canviar el SAP que ja funciona.
-->

---

<div class="eyebrow">Context · 1 de 9</div>

# El conflicte real

<div class="cols">
<div>

### Magatzem · Mosso

- Carrega **per Ubicació** lex
- Recorregut més curt pels passadissos
- Càrrega rapida, ben apilada

</div>
<div class="col-with-rule">

### Camió · Xofer

- Descàrrega **per parada** LIFO
- Zero rotació entre parades
- Sortida ràpida a cada client

</div>
</div>

<br/>

> *Damm ja ho va escriure: NO és Google Maps + Tetris. **És un sistema de suport a la decisió** que reconcilia magatzem, repartiment i logística inversa.*

<!--
0:20 — El conflicte real: el magatzem vol carregar per ubicació, el
xofer vol descarregar per parada. A sobre el 60% dels productes són
retornables: el camió canvia de forma durant la ruta. Damm ho diu
explícitament al seu deck: cal un sistema que reconcili els dos.
-->

---

<div class="eyebrow">Solució · 2 de 9</div>

# Una sola **columna** del SAP

```
┌──────────┬──────────┬──────────┬──────────┬─────────────┐
│ Ubicació │ Producte │ Cantitat │   Lot    │  Descàrrega │
├──────────┼──────────┼──────────┼──────────┼─────────────┤
│  AA09A1  │  ED13    │  3 Caja  │   ···    │     P1      │ ← omplim
│  AC07A2  │  0AG003  │  1 Caja  │   ···    │     P5      │ ← omplim
│  AA10A1  │  ED30    │  1 Barril│   ···    │     P6      │ ← omplim
└──────────┴──────────┴──────────┴──────────┴─────────────┘
```

El SAP de DDIDGP **ja imprimeix aquesta columna** a la Hoja Carga — sempre buida.
Smart Truck **l'omple** amb el slot òptim del camió.

<br/>

**Adopció ≈ zero**. Mateix paper, mateix mosso, mateix xofer. Una columna addicional.

<!--
0:40 — La nostra intervenció és única: hi ha una columna a la Hoja
Carga del SAP que sempre surt buida — ningú la omple. Smart Truck
calcula i omple aquesta columna amb el slot del camió per a cada
línia. Adopció pràcticament zero.
-->

---

<div class="eyebrow">Demo · 3 de 9 · Tauler</div>

# 15 parades · OSRM real-road

![bg right:54% fit](placeholder-tauler.png)

- Sant Julià de Vilatorta · Calldetenes · Folgueroles
- Ruta optimitzada amb **OR-Tools VRP-TW** + matriu OSRM real
- Polilínia que segueix la **C-25 i N-141** fins l'Osona
- Click → explicació de la parada + ítems a entregar
- Familiarity bias soft (ordre del SAP com a referència)

<!--
1:00 — DEMO. Tauler. 15 parades reals d'Osona. Ruta calculada amb
OR-Tools sobre matriu OSRM (no haversine). El polígon vermell segueix
les carreteres reals.
-->

---

<div class="eyebrow">Demo · 4 de 9 · Magatzem</div>

# Suport visual 3D · per Ubicació

![bg right:54% fit](placeholder-magatzem.png)

- Cada **pas = una Ubicació** del magatzem en lex order
- **Una sola onada** distribueix entre múltiples palets
- **Caixes** com cubs · **Barrils** com cilindres metàl·lics
- Color **per producte**: cross-reference llista ↔ palet 3D

<br/>

<span class="pill">★ Columna staple</span> SKUs universals (ED13) ocupen una columna sencera — un sol palet, una sola onada al magatzem.

<!--
1:20 — Magatzem. El mosso fa el recorregut de sempre per ubicació.
Smart Truck reparteix cada onada entre els slots del camió. Caixes i
barrils discrets, gravetat respectada. Animació de càrrega pas per pas.
-->

---

<div class="eyebrow">Demo · 5 de 9 · Camió</div>

# Distribució òptima dels palets

| Slot | CE | Tipus | Stops | Contingut |
|---|---|---|---|---|
| **P1** | 35 / 60 | CASE staple | 1–15 | Estrella 1/3 — *columna fixa* |
| P3 | 59 / 60 | CASE | 10–15 | Clúster final |
| P5 | 56 / 60 | CASE | 1–9 | Clúster inicial |
| **P6** | 44 / 60 | BARREL | 1, 11, 12, 15 | **Només 4 stops** |

<br/>

> P6 ja no s'obre a totes les parades — només a les que demanen barril.
> P1 dóna a totes — un sol palet front-curtain alimenta el cicle Estrella.

<!--
1:40 — Camió. P1 és la columna staple ED13 que serveix les 15
parades sense rotació. P6 són els barrils, només 4 parades amb barril
real. Cada quantitat un sencer, cap fracció.
-->

---

<div class="eyebrow">Demo · 6 de 9 · Conductor</div>

# Aplicació mòbil funcional

![bg right:54% fit](placeholder-conductor.png)

- Pantalla per cada parada · navegació prev / next
- **Cortina** + **palet** + ítems amb quantitats senceres
- CONTADO · CRÈDIT · finestra horària · ETA real
- "Confirmar lliurament" → salta a la pròxima parada
- Llista lateral amb el progrés del recorregut

<!--
2:00 — Conductor. App de mòbil amb tots els elements: parada, palet,
quantitat. Botó vermell "Confirmar lliurament" que avança al següent.
Llista lateral amb totes les parades + progrés.
-->

---

<div class="eyebrow">Algorisme · 7 de 9</div>

# Pipeline conjunt

```
deliveries.parquet           vehicles/*.yaml          OSRM /table
        │                            │                       │
        ▼                            ▼                       ▼
   demanda                    pressupost                 matriu
   per parada      ──────►    de palets             distància+temps
        │                            │                       │
        └──────────────┬─────────────┘                       │
                       ▼                                     │
              PACKER STACK-LIFO v3                           │
              MILP customer→pallet · CBC 10s                 │
              + columna staple ED13/CJ13          ────►      │
                       │                                     │
                       ▼                                     │
                  capacitat ◄─────────────────────►   VRP-TW + OR-Tools
                    real                            familiarity bias (A-12)
                       │                                     │
                       └──────────────┬──────────────────────┘
                                      ▼
                                ETAs · KPIs
                            Plan + BaselinePlan
```

**Dos optimitzadors encadenats** · sortida coordinada per la capacitat real del camió.

<!--
2:20 — L'algorisme: dos optimitzadors encadenats. El packer Stack-LIFO
+ MILP escull el camió i com s'apila la càrrega. El VRP-TW d'OR-Tools
optimitza l'ordre de parades amb la capacitat real del camió com a
constraint.
-->

---

<div class="eyebrow">Resultats · 8 de 9</div>

# Coeficient global d'optimització

<div class="kpi-grid">
<div class="kpi">
<div class="kpi-eyebrow">C_RUTA</div>
<div class="kpi-value">0.146</div>
<div class="kpi-detail">14.6% de pèrdua eliminada<br/>a la carretera</div>
</div>
<div class="kpi">
<div class="kpi-eyebrow">C_MUNTATGE</div>
<div class="kpi-value">0.712</div>
<div class="kpi-detail">71.2% d'espai de palet<br/>recuperat</div>
</div>
<div class="kpi">
<div class="kpi-eyebrow">C_CONDUCTOR</div>
<div class="kpi-value">0.525</div>
<div class="kpi-detail">52.5% de pèrdua a parades<br/>eliminada</div>
</div>
</div>

<br/>

```
K = 0.35·C_ruta + 0.20·C_muntatge + 0.45·C_conductor = 0.43
```

**43% de la pèrdua operacional ponderada eliminada** — una sola ruta · sense canviar el SAP.

<!--
2:40 — Tres coeficients que mesuren cada font de pèrdua de temps.
C_muntatge és el guany més gran: 71% d'espai del palet recuperat.
C_conductor: 53% menys parada. K = 0.43 = 43% de pèrdua eliminada.
-->

---

<div class="eyebrow">Diferenciador · 9 de 9</div>

# Per què Smart Truck guanya

<div class="cols">
<div>

### Aplicabilitat (30%)
- Construit sobre les **dades reals** de Mollet
- Fa servir el **SAP existent**, no el reemplaça
- Llista de SKUs de DR0027 reals
- Codi obert al repo

### Tècnic (25%)
- Stack-LIFO + **MILP** (PuLP/CBC)
- VRP-TW d'**OR-Tools** + OSRM real
- Re-geocodificació amb bbox català

</div>
<div class="col-with-rule">

### Impacte (20%)
- **5 KPIs** millorats simultàniament
- Coeficient global **K = 0.43**
- Extrapolable a **470 vehicles**

### Creativitat (15%)
- **Columna Descàrrega** del SAP omplerta
- **Cicle Estrella** com a staple universal
- Càrrega per Ubicació + LIFO **híbrid**

### Pitch (10%)
- Tres coeficients · llenguatge Damm

</div>
</div>

<!--
3:00 — Per què guanyem cada criteri: aplicabilitat (dades reals + SAP
existent), tècnic (MILP + OR-Tools + OSRM), impacte (K=0.43, 470
vehicles), creativitat (la columna Descàrrega és la troballa
diferenciadora), pitch (llenguatge Damm + coeficients).
-->

---

<!-- _class: closing -->
<!-- _paginate: false -->
<!-- _footer: '' -->
<!-- _backgroundColor: '#1A1A1A' -->
<!-- _color: '#ffffff' -->

# Smart **Truck**

<div class="tagline">
La columna Descàrrega ja no surt en blanc.
</div>

<br/>

### Següents passos

- Albarans reals per atribució exacta · K esperat **≈ 0.55**
- Multi-camió · multi-dia · re-optimització rolling
- Calibrar `(w_r, w_m, w_d)` amb dades operatives Damm
- Integració amb el sistema d'impressió DDIDGP

<br/>

<div class="meta" style="color:#999;">PELOTA BRAVA · INTERHACK BCN 2026</div>

<!--
3:20 — Tancament. Som al límit del que ens dóna l'agregació
proporcional. Si Damm ens passa Albarans reals, K puja a ~0.55.
Multi-camió i rolling re-optimisation són naturals next steps.
Gràcies. Preguntes.
-->

---

<!-- _footer: 'Apèndix · Q&A' -->

<div class="eyebrow">Apèndix · Q&A preparat</div>

# Preguntes anticipades

| Pregunta | Resposta breu |
|---|---|
| **Quant tarda el càlcul?** | 40 s primera vegada (OSRM + MILP); després **cache instantània**. Fleet completa: 15-20 min/nit. |
| **I sense Albarans reals?** | Pipeline ja funciona amb proforma proportional. Albarans → més precisió a `in_truck_searches`, no canvi qualitatiu. |
| **Escalabilitat?** | 470 vehicles · 1 cache local per ruta · processament **paral·lelitzable** per ruta. |
| **Integració SAP DDIDGP?** | **Smart Truck no reemplaça res.** Emet la mateixa Hoja Carga + columna Descàrrega plena. |
| **Què passa amb els retorns?** | A-35 + A-38: envasos retornats reentren al **mateix slot** que el ple va deixar lliure. P1/P6 mai són absorbidors. |

<!--
APÈNDIX — només si tenim 2 minuts. Contestar curt i directe.
-->
