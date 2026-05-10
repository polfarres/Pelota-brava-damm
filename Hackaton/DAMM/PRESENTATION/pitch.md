---
marp: true
theme: default
size: 16:9
paginate: true
backgroundColor: #fff
color: #1A1A1A
header: '**Smart Truck** · Pelota Brava · Interhack BCN 2026'
footer: 'DAMM challenge · DDI Mollet'
style: |
  section {
    font-family: 'Helvetica Neue', sans-serif;
    padding: 60px;
  }
  h1 { color: #E30613; font-size: 60px; }
  h2 { color: #E30613; font-size: 40px; }
  h3 { color: #1A1A1A; }
  strong { color: #E30613; }
  .red { color: #E30613; }
  .small { font-size: 0.7em; color: #555; }
  table { font-size: 0.75em; }
  pre { font-size: 0.55em; line-height: 1.2; }
  .kpi-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 20px;
    margin-top: 30px;
  }
  .kpi {
    background: #f8f9fa;
    border-left: 6px solid #E30613;
    padding: 16px;
    border-radius: 4px;
  }
  .kpi-value { font-size: 2em; color: #E30613; font-weight: bold; }
  .kpi-label { font-size: 0.85em; color: #555; }
---

<!--
SPEAKER NOTES (3 min total · ≈20s/slide):
Total slides: 10 + 1 closing.
Pace yourself: skip the over-detail slides if running long.
-->

# Smart Truck

### Mateix recorregut. Camió impecable.

Equip **Pelota Brava** · Interhack BCN 2026
Repte: **DAMM Distribució Directa Integral**

<!--
0:00 — Hola. Som l'equip Pelota Brava i hem treballat el repte de DAMM.
La nostra premissa: reduir el temps perdut a tota la cadena, sense
canviar el SAP que els mossos ja fan servir.
-->

---

## El problema, en una imatge

> *"Una mateixa hora, dues optimitzacions oposades."*

| Magatzem (mosso) | Camió (xofer) |
|---|---|
| Volem **carregar per Ubicació** lex (recorregut més curt pels passadissos) | Volem **descarregar per parada** (LIFO, sense rotacions) |
| Empila igual, recull ràpid | Cada parada ≠ desfer i tornar a fer |

A sobre: **60% de retorns** d'envasos. El camió **canvia de forma** durant la ruta.

DAMM ho diu: **NO és Google Maps + Tetris**. És un **sistema de suport a la decisió**.

<!--
0:20 — El repte real no és "google maps + tetris". El que el magatzem
vol (ordre per Ubicació) entra en conflicte amb el que el xofer vol
(ordre per parada, LIFO). Plus: el 60% del que va, torna. La nostra
solució resol els tres alhora.
-->

---

## La intervenció: una sola columna

```
┌──────────────────────────────────────────────────┐
│   HOJA DE CARGA · DDIDGP (estandard)             │
├──────┬─────────┬──────────┬──────┬───────────────┤
│ Ubic │ Núm.Prod│ Cantitat │ Lot  │  Descàrrega   │
├──────┼─────────┼──────────┼──────┼───────────────┤
│AA09A1│ ED13    │  3 Caja  │  ··  │      P1       │  ← Smart
│AC07A2│ 0AG003  │  1 Caja  │  ··  │      P5       │  ← Smart
│AA10A1│ ED30    │  1 Barril│  ··  │      P6       │  ← Smart
└──────┴─────────┴──────────┴──────┴───────────────┘
                                    └─ avui surt sempre BUIDA
```

**Adopció = 0**. Mateix paper, mateix mosso, mateix xofer. Una columna més.

<!--
0:40 — Aquesta és la idea clau. La hoja de càrrega del SAP de DAMM ja
té una columna "Descàrrega" que SEMPRE surt en blanc. El SAP no la
omple. Smart Truck l'omple. El picker veu el mateix paper, però amb
una columna més que li diu directament a quin slot del camió va cada
caixa.
-->

---

## Demo · 1 de 4 — Tauler

![bg right:55% 90%](placeholder-tauler.png)

- **15 parades** reals: Sant Julià · Calldetenes · Folgueroles
- **Ruta optimitzada** per OSRM (carreteres reals, no haversine)
- Polilínia segueix la C-25 i N-141 fins l'Osona
- Click a una parada → explicació + ítems a entregar

<!--
1:00 — Demostració. Tauler principal. La ruta optimitzada per OR-Tools
+ OSRM, agrupant els 15 stops en un cercle tancat. Click a una parada
i veus els productes que rep aquest client.
-->

---

## Demo · 2 de 4 — Magatzem

![bg right:55% 90%](placeholder-magatzem.png)

- Suport visual **3D animat** per al mosso
- Cada **pas = una Ubicació** (recorregut lex pel magatzem)
- Una sola **onada** distribueix entre múltiples palets
- **Caixes** com cubs · **Barrils** com cilindres
- Color **per producte** (cross-reference llista ↔ palet 3D)

<!--
1:20 — La pestanya Magatzem. Cada pas és una ubicació al magatzem.
El mosso fa el recorregut de sempre però Smart Truck li diu a quin
palet va cada producte. Animació de boxes apilant-se de baix cap a
dalt en LIFO. Barrils com cilindres metàl·lics.
-->

---

## Demo · 3 de 4 — Camió

![bg right:55% 90%](placeholder-camio.png)

| Slot | CE | Tipus | Stops | Què hi va |
|---|---|---|---|---|
| **P1** | 35/60 | CASE staple | 1-15 | Estrella 1/3 — *columna fixa* |
| P3 | 59/60 | CASE | 10-15 | Clúster final |
| P5 | 56/60 | CASE | 1-9 | Clúster inicial |
| **P6** | 44/60 | BARREL | 1, 11, 12, 15 | **Només 4 stops!** |

**P6 ja no s'obre a totes les parades** ← bug abans de l'algorisme

<!--
1:40 — Camió 3D. P1 = la columna staple ED13 que serveix les 15
parades sense rotació. P6 = barrils, només 4 parades amb barril real.
La part important: tots els integers, tots els barrils sencers.
-->

---

## Demo · 4 de 4 — Conductor

![bg right:55% 90%](placeholder-conductor.png)

- App de mòbil **funcional**: navegació + confirmació
- Per cada parada: cortina · palet · ítems · CONTADO/CRÈDIT
- "Confirmar lliurament" → salta a la pròxima
- Llista lateral de **15 parades** amb indicador de progrés

<!--
2:00 — Pestanya Conductor. Aplicació mòbil amb pantalla per parada,
botó "Confirmar lliurament" que avança al següent. Llista lateral amb
totes les parades + progrés. ETA, finestra horària, palet a obrir,
ítems amb quantitats senceres.
-->

---

## Algorisme — pipeline conjunt

```
deliveries.parquet         vehicles/*.yaml         OSRM /table
       │                          │                     │
       ▼                          ▼                     ▼
   demanda          ─────►   pressupost           matriu
   per parada               de palets         distància+temps
       │                          │                     │
       └──────────────┬───────────┘                     │
                     ▼                                  │
            **PACKER v3**                               │
            Stack-LIFO + MILP + columna staple ───┐     │
                     │                            │     │
                     ▼                            ▼     ▼
                cap. real                **VRP-TW + OR-Tools**
                     │                  familiarity bias (A-12)
                     │                            │
                     └──────────────┬─────────────┘
                                    ▼
                            ETAs · KPIs
                          Plan + BaselinePlan
```

**MILP** minimitza Σ(seq_max − seq_min) per slot · **CBC** wall-time 10s · **Heurística** fallback

<!--
2:20 — L'algorisme: dos optimitzadors encadenats. El packer Stack-LIFO
amb MILP decideix la mida del camió i l'assignació client→palet.
Després el VRP-TW d'OR-Tools optimitza l'ordre amb la capacitat real
del camió com a constraint.
-->

---

## Resultats — coeficient global K

<div class="kpi-grid">

<div class="kpi">
<div class="kpi-label">C_ruta</div>
<div class="kpi-value">0.146</div>
<div class="small">14.6% temps perdut a la carretera eliminat</div>
</div>

<div class="kpi">
<div class="kpi-label">C_muntatge</div>
<div class="kpi-value">0.712</div>
<div class="small">71.2% espai malbaratat al palet eliminat</div>
</div>

<div class="kpi">
<div class="kpi-label">C_conductor</div>
<div class="kpi-value">0.525</div>
<div class="small">52.5% temps perdut a parades eliminat</div>
</div>

</div>

```
K = 0.35·C_ruta + 0.20·C_muntatge + 0.45·C_conductor = 0.43
```

**43% de la pèrdua operacional ponderada eliminada · 1 sola ruta · sense canviar el SAP**

<!--
2:40 — El nostre KPI consolidat. Tres coeficients que mesuren cada
font de pèrdua de temps al procés. C_muntatge és el guany més gran:
71% de l'espai del palet ja no es malbarata. C_conductor: 53% menys
parada. K global = 0.43 = 43% de pèrdua operacional eliminada en una
sola ruta.
-->

---

## Tancament

> **Smart Truck — La columna Descàrrega ja no surt en blanc.**

- Mateix paper. Mateix flux. Mateixa adopció ≈ zero.
- 5 KPIs millorats simultàniament en una sola ruta.
- Algorisme reproduïble: codi obert al repo `Pelota-brava-damm/`

**Següents passos**:
- Albarans reals (atribució exacta) → K esperat ≈ 0.55
- Multi-camió / multi-dia (rolling)
- Calibrar pesos `(w_r, w_m, w_d)` amb dades operatives DAMM

<!--
3:00 — Tancament. Som al límit del que el SAP ens dóna sense Albarans
reals. Si DAMM ens passa 2-3 dies de Albarans, podem afinar el packer
i pujar el K a ~0.55. Gràcies, preguntes.
-->

---

## Apèndix · Q&A preparat

### **«Quant tarda el càlcul?»**
Primera càrrega ~40 s (OSRM + MILP). Després **cache instantània**.
Amb un VRP de 50 stops cau a 1-2 min — viable per a la flota completa.

### **«I si no tenim els Albarans?»**
La pipeline ja funciona amb l'agregat del Hoja Carga. Avui és el camí
del demo. Atribuïm per proforma. Albarans reals → tret marginal de la
mètrica `in_truck_searches`.

### **«Com escala a tota la flota DAMM?»**
470 vehicles × 1 cache local per ruta. El packer i el VRP corren en paral·lel
per ruta (independents). 15-20 min per a tota una nit de planificació.

### **«Quina és la integració amb el SAP DDIDGP?»**
Smart Truck **emet** un PDF amb la mateixa estructura que el Hoja Carga
del SAP, però amb la columna Descàrrega plena. **No reemplaça res**;
afegeix.

### **«Què passa amb els retorns?»**
A-35 + A-38: els envasos retornats reentren al **mateix slot** que els
caixons plens van deixar lliure. P1/P6 = palets que es buiden poc =
no els fem servir per absorbir retorns. Roadmap.

<!--
APÈNDIX preguntes Q&A. Si tenim 2 minuts, prepara't a:
- Performance: 40s primera vegada, després instantani.
- Albarans: ja funciona sense, millora amb.
- Escalat: paral·lelitzable per ruta.
- Integració: emet la mateixa hoja, afegeix una columna.
- Retorns: reentren al mateix slot per A-35/A-38.
-->
