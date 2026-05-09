# Smart Truck — Specifications

Companion to `Smart Truck — Hackathon Plan.md`. This document defines, per feature, what it does, what it consumes, what it produces, and how we know it's correct. It also pins down the exact schema of every input file (Excel + PDF) so backend devs can write parsers without guessing.

Requirement IDs:
- `FR-xxx` — functional requirement (a feature of the product)
- `DR-xxx` — data requirement (a parser / canonical schema)
- `NFR-xxx` — non-functional requirement (perf / UX / deploy)

## 0. Glossary

| Term | Meaning |
|---|---|
| DDI | Distribució Directa Integral — DAMM's direct distribution arm. |
| DDIDGP | The header tag on the SAP-printed PDFs (Hoja Carga, Hoja Ruta). Treat as "the source SAP system". |
| Mollet | The DAMM/DDI warehouse our challenge is scoped to. Address: C/Molí de Can Bassa, Nau Damm 1, Pol. Ind. Can Magarola, 08100 Mollet del Vallès. |
| HoReCa | Hotels, Restaurants, Cafés — the customer channel DDI serves. |
| Carga | A "load" — one truck + driver + day's deliveries. Identified by `Nº Carga` (e.g. `11764300`). |
| Viaje | A trip within a carga. Almost always `01` in our data. |
| Ruta | Route code (e.g. `DR0027`). One ruta covers a geographic territory and a fixed driver. |
| Repartidor | Driver, identified by 6-digit ID (e.g. `850004 FRAN ROMERO`). |
| Albarán | Customer delivery note / invoice — one per customer per delivery. |
| Hoja Carga | Warehouse-facing pick + load sheet — one per carga, sorted by warehouse `Ubicación`. |
| Hoja Ruta | Driver-facing route summary — one per carga, listing each albarán with payment terms. |
| Envase | Empty container (crate, bottle, barrel, CO₂ tube). Has its own SKU codes (`3ENV…`, `CJ…`, `BRL…V`, `TB8V`). Goes OUT empty so customers can fill it with their empties. |
| Returnable | Product whose container comes back as an envase. Brief states ~60% of products are returnable. |
| CONTADO | Cash on delivery. |
| CRÉDITO | Invoiced (typically 20-day terms). |
| LIFO | Last-in-first-out: load order is the reverse of delivery order. |
| Hybrid load model | Our proposed model: truck divided into client clusters; within each cluster, products grouped by SKU. |

---

## 1. Data sources — parsing specifications

For each source we define: file path, sheet/section structure, column-by-column schema, observed gotchas, and a canonical Python type that downstream code uses.

### DR-001 — `Hackaton.xlsx`

Path: `Pelota-brava-damm/Hackaton/DAMM/Hackaton.xlsx`. Five sheets.

#### DR-001.A — Sheet `Detalle entrega` (the fact table)

82,849 rows × 18 cols. Every line item ever delivered Feb–Mar 2026.

| Column | Type | Example | Notes |
|---|---|---|---|
| `FECHA` | date | `02/02/2026` | DD/MM/YYYY string. Parse to `datetime.date`. |
| `Transporte` | int | `11420136` | Vehicle/transport ID. ~889 unique values. |
| `Ruta` | str | `DR0027`, `DA0216` | Almost all rows use the standard `DR…` prefix (joinable directly with `ZONAS.RutReal` and the Hoja Carga). A single legacy `DA…` route appears in a small number of rows; **drop it during ETL** to keep the schema clean. Verified with user 2026-05-09. |
| `Repartidor` | int | `855203` | Driver/sales rep ID. 18 unique. |
| `Destinatario mcáa.` | str | `JACINT MAS CORNET` | Customer legal name (utf-8 may show as `mcáa`). |
| `Entrega` | int | `827937019` | Delivery transaction ID — joinable with albarán. |
| `Material` | str | `0CF0357`, `ED13`, `CJ13` | Product SKU. Joinable with `Materiales zubic.Material` and `ZM040.Material`. |
| `Denominación` | str | `ESTRELLA DAMM 1/3 RET. PP` | Product description. |
| `Cantidad entrega` | float | `12` | Quantity delivered. |
| `Un.medida venta` | str | `CAJ`, `UN`, `BRL`, `BOT` | Sales UoM. May differ from `ZM040.UMA`. |
| `Destinatario mcáa..1` | int | `9100696143` | Customer ID (10-digit, leading `9100…`). Joinable with `Direcciones.Cliente`. |
| `Nombre 1` | str | `LOS TERESITOS` | Customer site name. |
| `Nombre 2` | str | `BAR OLIVEDA` | Customer site name (secondary). |
| `Calle` | str | `Av. Pau Casals 22` | Address. |
| `CP` | int | `8500` | Postal code (Spanish 5-digit; leading zero may be lost — pad to 5). |
| `Población` | str | `VIC` | City. |
| `ZonaTransp` | str | `DD13100043` | Zone code. |
| `ZonaTransp.1` | str | `MONTCADA I REIXAC` | Zone label. |

Gotchas:
- Encoding garbles `Destinatario mcáa.` — it's literally `Destinatario máq.`. Treat the column name as opaque; refer by index or normalised slug.
- `CP` arrives as int — pad to 5 digits string before joining or geocoding.
- `Ruta` is overwhelmingly `DR…`, joinable directly with `ZONAS.RutReal` and Hoja Carga. A single legacy `DA…` route appears in a few rows — filter it out during ETL.

Canonical type:
```python
@dataclass
class DeliveryLine:
    fecha: date
    transporte_id: int
    ruta: str        # raw, may need normalisation
    repartidor_id: int
    customer_id: int
    delivery_id: int
    material: str
    description: str
    quantity: float
    uom: str
    address_street: str
    address_postcode: str  # 5-digit zero-padded
    address_city: str
    zone_code: str
    zone_label: str
```

#### DR-001.B — Sheet `Cabecera Transporte`

8,927 rows × 8 cols. One row per (delivery, transport, driver) tuple.

| Column | Type | Notes |
|---|---|---|
| `Entrega` | int | Joins to `Detalle entrega.Entrega`. |
| `N° Transporte.` | int | Joins to `Detalle entrega.Transporte`. |
| `Creado el` | date | Created. |
| `Repartidor` | int | Driver ID. |
| `Unnamed: 5` | str | Driver name (free text). |
| `Destinatario mcáa.` | int | Customer ID. |
| `Destinatario mcáa..1` | str | Customer name. |

Use this only if we need driver names; the fact table already has driver IDs.

#### DR-001.C — Sheet `Direcciones` (customer master)

1,368 rows × 6 cols.

| Column | Type | Notes |
|---|---|---|
| `Cliente` | int | Customer ID. **Primary key**. |
| `Nombre 1` | str | |
| `Nombre 2` | str | |
| `Calle` | str | Street. |
| `CP` | int | Pad to 5. |
| `Población` | str | |

Canonical type:
```python
@dataclass
class Customer:
    customer_id: int
    name: str            # combined Nombre 1 + Nombre 2
    street: str
    postcode: str
    city: str
    lat: float | None    # filled by geocoder
    lon: float | None
```

#### DR-001.D — Sheet `ZONAS`

1,203 rows × 14 cols. Customer-to-zone-to-route mapping.

Key columns: `ZONAS` (zone code, e.g. `DD13100000`), `NOMBRE ZONAS`, `cliente zona` (customer ID), `ZonaTransp`, `Zona Entrega`, `RutReal` (route code, `DR…`), `Denominación` (route description, e.g. `RP235 MOLLET JOSE VELEZ CASTRO`).

Use to map a customer to its `DR…` route and its associated driver.

#### DR-001.E — Sheet `Materiales zubic` (Mollet warehouse product mini-master)

1,489 rows × 8 cols.

| Column | Type | Example | Notes |
|---|---|---|---|
| `Material` | str | `0AM0783`, `0RF0088`, `ED13` | SKU. |
| `Número de material` | str | `LOTUS BISCOFF 300U` | Description. |
| `Ce.` | str | `D131` | Centre (mostly D131 = Mollet). |
| `Alm.` | float | `1.0`, `5.0`, NaN | Aisle. |
| `UMB` | str | `CAJ`, `UN` | Base unit. |
| `Fabricante` | int | | Manufacturer ID. |
| `Número de un fabricante` | str | | Manufacturer name. |
| `Ubic.` | str | `FA05A2`, `CB06A2`, `ZCG`, `AAAAAA` | **Warehouse location code — drives Smart Hoja Carga sort order.** |

`Ubic.` decoding (hypothesis to validate with mentor MQ-D-09): two letters = rack column, two digits = bay, one letter = shelf, one digit = position. Special codes: `A0DISTRIDA` (Distrida zone), `ZCG` (Comergrup), `AAAAAA` (placeholder/no slot).

### DR-002 — `Horarios Entrega.XLSX`

Path: `Pelota-brava-damm/Hackaton/DAMM/Horarios Entrega.XLSX`. One sheet, 1,015 rows × 13 cols. **The file is complete: every customer × weekday combination is represented.**

Schema (verified with user 2026-05-09):

| Col | Header | Type | Notes |
|---|---|---|---|
| A | `Deudor` | int | Customer ID. Joins directly to `Direcciones.Cliente` (10-digit `9100…` IDs from row ~28 onwards; the small handful of leading 6-digit legacy rows can be dropped during ETL). |
| B | `Organización ventas` | int | Irrelevant (always 235). |
| C | `Canal distribución` | int | Irrelevant (always 1). |
| D | `Sector` | int | Irrelevant (always 8). |
| E | `Día semana` | int | **1 = Monday … 5 = Friday.** Saturday is absent because customers are closed; Sunday (7) appears for the few customers open then. |
| F | `Turno` | int | Always 1. |
| G | `Nombre 1` | str | Customer name. |
| H–J | `Descripción*` | str | Labels (DDI / channel / DDI MOLLET). Informational. |
| K | `Horario inicia a` | time | Window start. |
| L | `Horario termina a` | time | Window end. |
| M | `Cierre Si/No` | str/NaN | Closure flag. Mostly empty. |

**Critical rule**: a row with `K = L = 00:00:00` means the customer **does NOT accept delivery on that weekday**. Treat it as a hard closure, not as an open window from midnight to midnight.

There is therefore **no "default" window concept** — every (customer, weekday) is explicit. If a customer is missing from this file entirely, we treat them as unknown and surface a warning during ETL.

Canonical type:
```python
@dataclass
class TimeWindow:
    customer_id: int
    weekday: int     # 1-7
    start: time
    end: time
```

### DR-003 — `ZM040.XLSX` (SAP material master)

Path: `Pelota-brava-damm/Hackaton/DAMM/ZM040.XLSX`. One sheet, 48,457 rows × 22 cols, 7,478 unique SKUs.

A given material has multiple rows — one per UoM (CAJ, PAL, UN, BOT, KG, L, ZCE, ZPR…).

Critical columns:

| Column | Type | Notes |
|---|---|---|
| `Material` | str | SKU. |
| `TpMt` | str | `ZFIN`, `ZPLV`, NaN. Material type. |
| `UMA` | str | UoM. ~53 unique. |
| `Contador` / `Denom.` | float | Conversion ratio (units per UoM). |
| `Código EAN/UPC` | str | Barcode. |
| `Longitud`, `Ancho`, `Altura` | float | Dimensions in cm. Standard pallet shows 100×120×169. |
| `Volumen` | float | Volume (interpret by UoM — pallet level shows ~475 L). |
| `Peso bruto`, `Peso neto` | float | Weights in kg. Standard pallet ~1020 kg gross. |
| `Jquía.productos` | str | Hierarchy code. |

Canonical type (after collapsing rows per material):
```python
@dataclass
class Product:
    sku: str
    description: str
    base_uom: str            # UMB from Materiales zubic
    case_dim_cm: tuple[float, float, float] | None      # CAJ row
    case_volume_l: float | None
    case_weight_kg: float | None
    pallet_dim_cm: tuple[float, float, float] | None    # PAL row
    pallet_volume_l: float | None
    pallet_weight_kg: float | None
    units_per_case: float | None
    cases_per_pallet: float | None
    is_returnable: bool      # heuristic from description: "RET" in name
    is_envase: bool          # SKU starts with 3ENV/CJ/BRL.V/TB8V
    warehouse_location: str | None  # from Materiales zubic.Ubic.
```

### DR-004 — `Layout Mollet.xlsx`

Path: `Pelota-brava-damm/Hackaton/DAMM/Layout Mollet.xlsx`. Five sheets.

- `DDI MOLLET`, `Detalle`: 193×98 sparse spatial grid. Treat as opaque image; **do not parse for v1**. Use only the `Ubic.` lex order from `Materiales zubic` for picking optimisation.
- `RESUMEN DDI MOLLET`: 7×14 capacity summary. Total interior 2,055 + exterior 305 = 2,360 pallet positions, split across Floor / ALT(2) / ALT(3) / ALT(4) / ALT(9) levels.
- `Hoja5`: legend (`A0DISTRIDA` = Distrida supplier zone, `ZCG` = Comergrup zone).

We will quote the 2,360 capacity number in the pitch but not model the grid.

### DR-005 — `Albarán.pdf` (customer-facing invoice)

Path: `Pelota-brava-damm/Hackaton/DAMM/RECURSOS/Albaran.pdf`.

#### Structure (per page; multi-page if line count exceeds one page)

**Header block (top-left)** — DDI Mollet identity (constant): `Distri.de Begudes Movi SL · C/Molí de Can Bassa, Nau Damm 1 · Pol. Ind. Can Magarola · 08100, MOLLET DEL VALLÈS · 935939309 · B59477968 · ddimollet@ddidistribucion.com`.

**Customer block (top-middle)** — `Razón Social` (legal name + tax ID + billing address) + `Dirección Entrega` (delivery address; may differ from billing).

**Payment block (top-right)** — `Forma de Pago`, `Recibo Domiciliado`, `Fecha vto`, `Resp`, `Horario Servicio` (often blank), title `Albarán-Factura`.

**Identifier table** (one row of 11 cells):

| Field | Example | Notes |
|---|---|---|
| `Número` | `7581848917` | Document number. |
| `Albarán` | `828482558` | Albarán sequence — joins to `Hoja Ruta.Nº Doc.`. |
| `Fecha` | `08.05.2026` | DD.MM.YYYY. |
| `Cliente` | `9100757467` | Customer ID. |
| `N.ºCarga` | `11764336` | Carga ID — joins to `Hoja Carga.Nº Carga`. |
| `Viaje` | `01` | Trip number. |
| `Cial.` | `540687` | Sales rep. |
| `Vend.` | `540687` | Vendor / seller. |
| `Ruta` | `DR0031` | Route. |
| `Rep.` | `850021` | Driver ID. |

**Line items table:** `Producto | (description) | UM | Cdad. | Precio | Dto | P.V. | I.P. | I.A. | Importe | IVA | Promoción`. UoMs observed: `CAJ`, `BRL`, `UN`, `BOT`, `PAK`, `CAM`, `LAT`, `KG`. `Promoción` carries a promo code (e.g. `81801711`).

**Tax summary footer:** rows of `Imp. Bruto | S.L. | Dto. Fact. | Base | %IVA | Imp. IVA | % RE | Imp. REC` — one per VAT bracket (4%, 10%, 21%). Plus `Importe` and `TOTAL`.

For our purposes:
- **In v1 we DO NOT regenerate albaranes.** We only consume their identifiers (`Albarán`, `N.ºCarga`, `Cliente`, `Ruta`) to cross-reference with Hoja Ruta / Hoja Carga.
- If time permits in v2: render a Smart Albarán with a `Pallet` annotation per line indicating which truck pallet each item is on (helps the customer's receiving staff).

### DR-006 — `Hoja Carga.pdf` (warehouse load sheet) ★

Path: `Pelota-brava-damm/Hackaton/DAMM/RECURSOS/Hoja Carga.pdf`. **The most important file in the project.**

#### Header (constant per carga, repeats on every page)

| Field | Example |
|---|---|
| `Nº Carga / Nº precarga` | `11764300 / D131999991` |
| `Vehículo` | `V235045` (internal vehicle ID — license plate is on Hoja Ruta) |
| `Repartidor / Proveedor` | `850004 / 30432 FRAN ROMERO` |
| `Nº Viaje` | `01` |
| `Fecha Envío` | `08.05.2026` |
| `Ruta` | `DR0027` |
| Page number | `Página N` |
| System tag | `DDIDGP` (top-right) |
| Print timestamp | e.g. `12:23:24` |

#### Body — four sections in fixed order

Each section has the same column header: `Ubicación | Nº Prod. | Descripción | Cantidad | Unidad | Lote | Descarga`.

1. **`Carga lleno`** — full outbound, with assigned warehouse location.
   - Sorted by `Ubicación` ascending (e.g. `A0DISTRIDA`, `AA02A1`, …, `ZCG`).
   - `Unidad`: `Caja`, `Barril`, `Tubo`, `Unidad`, `Pack`, `Botella`.
   - **`Lote`: ALWAYS EMPTY in current paperwork** (confirmed 2026-05-09). We don't read or write this column; pass through unchanged.
   - **`Descarga`: ALWAYS EMPTY in current paperwork** (confirmed 2026-05-09). This is our intervention slot — Smart Hoja Carga populates it with the truck pallet target.
   - Section ends with `Total Cantidad: <n>` row.

2. **`Carga lleno sin ubicación`** — outbound items without a warehouse slot (typically third-party / direct-cross-dock items).
   - Same columns; `Ubicación` blank.
   - Section ends with `Total Cantidad: <n>`.

3. **`Carga retorno lleno`** — outbound items being shipped back to suppliers (e.g. defective product). Has an extra `Estado` column (`NO APTO` etc.).
   - Often very short (1–3 items) or absent.
   - Section ends with `Total Cantidad: <n>`.

4. **`Carga envases`** — outbound empty containers (crates, barrels, CO₂ tubes) being sent so customers can fill them with returns.
   - SKU codes: `3ENV…` (empty containers like `C.C. AGUA 1/2 VICHY-FONT D'OR`), `CJ11V`, `CJ13`, `CJ15` (empty case stacks), `BRL30V`, `BRL20V` (empty barrels), `TB8V` (empty CO₂ tubes).
   - `Ubicación` blank.
   - Often the largest count by quantity (in DR0027/2026-05-08: 258 units).
   - Section ends with `Total Cantidad: <n>`.

#### Carga totals (final block, last page)

```
Total Cantidad Entrega: <n>     Total Cantidad Devolución: <n>
Total Volumen Entrega: <v>      Total Volumen Devolución: <v>
Total Peso Entrega: <kg>        Total Peso Devolución: <kg>
```

Observed for DR0027/2026-05-08: 837 / 259 units; 338.21 / 4 (volume; the units of volumen are unclear — confirm MQ-D-07); 4,719.12 / 2,094.28 kg.

#### Parser implementation note

Use `pdfplumber` or `camelot` for the table extraction. Grouping cue: a row is a section header when it matches `^(Carga lleno|Carga lleno sin ubicación|Carga retorno lleno|Carga envases)$`. A row is a section footer when its first non-empty cell is `Total Cantidad:`. Everything between is data.

Canonical type:
```python
@dataclass
class HojaCargaLine:
    section: Literal["lleno", "lleno_sin_ubic", "retorno", "envases"]
    ubicacion: str | None
    sku: str
    description: str
    quantity: float
    unit: str             # Caja / Barril / Tubo / Unidad / Pack / Botella
    lote: str | None
    estado: str | None    # only populated in retorno section
    descarga: str | None  # ★ ALWAYS NONE in source; populated by our optimiser

@dataclass
class HojaCarga:
    nº_carga: int
    nº_precarga: str
    vehiculo: str
    repartidor_id: int
    repartidor_name: str
    nº_viaje: int
    fecha: date
    ruta: str
    lines: list[HojaCargaLine]
    totals_entrega: TotalsBlock
    totals_devolucion: TotalsBlock
```

### DR-007 — `Hoja Ruta.pdf` (driver route sheet)

Path: `Pelota-brava-damm/Hackaton/DAMM/RECURSOS/Hoja Ruta.pdf`.

#### Header (constant)

| Field | Example |
|---|---|
| Title | `RELACIÓN DE DOCUMENTOS DE LA CARGA POR FORMA DE PAGO` |
| `Nº Carga` | `11764300` |
| `Fecha de entrega` | `08.05.2026` |
| `Vehículo` | `7524KXX` (license plate — different from `Hoja Carga.Vehículo` which is internal V-ID) |
| `Repartidor / Nombre` | `850004 FRAN ROMERO` |
| `Preparador` | (often empty) |
| `Nº viaje` | `01` |

#### Body — delivery list

Columns: `SSTT | Condición de pago | Nº Doc. | Nº Cliente | Nombre 2 | Dirección | Total Proforma (IVA Incl.) | Total Cobro`.

- `SSTT` is a flag column (always `NO` in our sample — confirm meaning MQ-D-08).
- `Condición de pago` ∈ `CONTADO | CREDITO`. Negative `Total Proforma` rows are credit notes (abonos) — `Nº Doc.` for these starts with `8410…` instead of `8284…`.
- `Total Cobro` is non-zero only for CONTADO; CREDITO rows show 0.
- Rows are presumed to be in **expected delivery order** (confirm MQ-D-03 — this is our as-is baseline ordering).

Footer: `Nº de pedidos: 18 · T. Carga: 7,832.38 · 2,891.08`.

Second page: payment-condition rollup.

Canonical type:
```python
@dataclass
class HojaRutaStop:
    sequence: int          # row order in source PDF
    sstt: str
    payment_condition: Literal["CONTADO", "CREDITO"]
    albaran_id: int        # joins DR-005.Albarán
    customer_id: int
    customer_name: str
    address: str
    proforma_total: Decimal  # may be negative (abono)
    cash_total: Decimal      # 0 for CREDITO
```

### DR-008 — Vehicle profile schema + four concrete profiles ★

Supersedes the flat M×N grid in original A-01. Profiles live as YAML in `backend/smart_truck/data/vehicles/` and are loaded once into `VehicleProfile` instances.

#### Schema

```python
class SlotType(str, Enum):
    PALLET_FLOOR = "PALLET_FLOOR"   # full pallet position; 60 CE max (A-31)
    SHELF        = "SHELF"
    FLOOR_KEG    = "FLOOR_KEG"
    OVERFLOW     = "OVERFLOW"

class AccessFace(str, Enum):
    REAR = "REAR"; LEFT = "LEFT"; RIGHT = "RIGHT"; TOP = "TOP"

class CurtainAccess(str, Enum):
    NONE                    = "NONE"
    SINGLE_SIDE             = "SINGLE_SIDE"
    BOTH_SIDES_PARTITIONED  = "BOTH_SIDES_PARTITIONED"   # central reixa (A-33)
    BOTH_SIDES_OPEN         = "BOTH_SIDES_OPEN"

@dataclass
class AccessMechanism:
    rear_doors: bool
    rear_lift: bool                  # ascensor (TRUCK_8P_LIFT only, A-34)
    curtain: CurtainAccess
    partition: bool                  # central reixa? blocks cross-side reach

@dataclass
class Slot:
    id: str                          # "P1", "P3", "K1", "S2-L1"
    type: SlotType
    pos_cm: tuple[float,float,float] # origin = front-left-floor
    size_cm: tuple[float,float,float]
    accepts: list[LoadUnitClass]     # whitelist (DR-009)
    capacity_ce: float               # 60 for PALLET_FLOOR; scaled for shelves/kegs
    max_weight_kg: float             # informational only — A-30
    reachable_from: list[AccessFace]
    blocked_by_per_face: dict[AccessFace, list[str]] = field(default_factory=dict)
    can_host_returns_of: list[LoadUnitClass] = field(default_factory=list)
    notes: str = ""

@dataclass
class VehicleProfile:
    profile_id: str                  # FURGO_3P / TRUCK_6P_SC / TRUCK_8P_SC / TRUCK_8P_LIFT
    display_name: str
    fleet_count: int                 # 1 / 11 / 4 / 4 (slide 3 + mentor)
    external_dim_cm: tuple[float,float,float]
    internal_dim_cm: tuple[float,float,float]
    access: AccessMechanism
    slots: list[Slot]
    total_capacity_ce: float         # = sum(slot.capacity_ce)
    nominal_payload_kg: float        # informational only — A-30
    envase_zone_slot_ids: list[str]  # default landing zone for outbound envases
    lifo_order_per_face: dict[AccessFace, list[str]] = field(default_factory=dict)
    schema_version: str = "1.1"
```

The key invariant: **`Slot.blocked_by_per_face` is the only adjacency model**. Side-partitioned vehicles (A-33) encode the partition by giving left-side slots `reachable_from=[LEFT]` only and right-side slots `reachable_from=[RIGHT]` only — there is no cross-row LEFT/RIGHT.

#### Profile files

| File | Profile | Fleet | Access | Slots | Total CE |
|---|---|---|---|---|---|
| `furgo_3p.yaml` | `FURGO_3P` | 1 | LEFT (P1 only) + REAR (P2/P3 LIFO) | 3 PALLET_FLOOR | 180 |
| `truck_6p_sidecurtain.yaml` | `TRUCK_6P_SC` | 11 | LEFT (P1/P3/P5) ∥ RIGHT (P2/P4/P6); central partition | 6 PALLET_FLOOR | 360 |
| `truck_8p_sidecurtain.yaml` | `TRUCK_8P_SC` | 4 | LEFT (P1/P3/P5/P7) ∥ RIGHT (P2/P4/P6/P8); central partition | 8 PALLET_FLOOR | 480 |
| `truck_8p_lift.yaml` | `TRUCK_8P_LIFT` | 4 | as 8P_SC + REAR with `ascensor` (LIFO P7..P1) | 8 PALLET_FLOOR | 480 |

#### Loader & validation

`backend/smart_truck/domain/vehicle_loader.py::load_all() -> dict[str, VehicleProfile]`. Round-trip test [`backend/tests/test_vehicle_profiles.py`](../backend/tests/test_vehicle_profiles.py): unique slot IDs; every `blocked_by_per_face` reference resolves to an existing slot; `total_capacity_ce == sum(s.capacity_ce)`; every `lifo_order_per_face` slot matches a `reachable_from` declaration.

### DR-009 — LoadUnit taxonomy

DAMM organises picking by four product categories (slide 3 of `INTERHACK Barcelona 2026.pptx`): **Barriles, Retornables, Latas, Cajas**, with rotation by volume. The packer's load-unit primitives encode this:

```python
class LoadCategory(str, Enum):           # DAMM's official 4 categories
    BARRIL     = "BARRIL"
    RETORNABLE = "RETORNABLE"
    LATA       = "LATA"
    CAJA       = "CAJA"

class LoadUnitClass(str, Enum):          # placement granularity
    EUR_PALLET        = "EUR_PALLET"
    INDUSTRIAL_PALLET = "INDUSTRIAL_PALLET"
    CASE              = "CASE"           # cardboard "Caja"
    BRL               = "BRL"            # plastic returnable crate
    KEG_FULL          = "KEG_FULL"
    KEG_EMPTY         = "KEG_EMPTY"
    BARREL_EMPTY      = "BARREL_EMPTY"   # BRL30V / BRL20V
    TUBE              = "TUBE"           # TB8 / TB8V CO₂ tube

@dataclass(frozen=True)
class LoadUnit:
    cls: LoadUnitClass
    category: LoadCategory
    sku: str | None
    ce_per_unit: float                   # caixes estadístiques per delivery unit (A-31)
    weight_kg: float                     # informational — A-30
    is_envase: bool = False              # outbound empty (3ENV/CJV/BRL30V/TB8V)
```

`LoadUnit` instances are *derived* from `Product` (DR-003) at packer time: a stop's qty for SKU `0CF0054` becomes one `EUR_PALLET` LU when the per-stop CE total ≥ 60, else N `CASE` LUs that the consolidator stage merges.

### DR-010 — CE (caixa estadística) capacity model + CE master ETL ★

A pallet holds **60 CE** (A-31).

#### Source priority (resolved 2026-05-09)

1. **Primary (authoritative)** — DAMM mentor delivers a dedicated Excel with CE per delivery unit for every SKU at `Pelota-brava-damm/Hackaton/DAMM/Caixes_Estadístiques.xlsx`. This is the source of truth.
2. **Fallback (if Primary missing for an SKU)** — derive from `ZM040.XLSX`: `ce_per_unit = ZCE_row.Denominator / 100`. Coverage in ZM040 = 93.4 % (6,988 / 7,478) and at least one known data bug (`0CF0054` shows 0.16 instead of 1.0 — see below).
3. **Default (if both missing)** — `ce_per_unit = 1.0`, log warning, surface in the data-quality panel.

#### Formula

```
units_per_pallet = 60 / ce_per_unit
```

#### ETL extractor

`backend/smart_truck/etl/ce_master.py::ce_per_unit`:

```python
def ce_per_unit(sku: str, ce_master: dict[str, float],
                zm040_row_group, overrides: dict[str, float]
                ) -> tuple[float, str]:
    """Returns (ce_value, source) where source ∈ {OVERRIDE, CE_MASTER, ZCE_ROW, DEFAULT}.
       1. If SKU is in overrides table → return overrides[sku], "OVERRIDE".
       2. Else if SKU is in CE master Excel → return ce_master[sku], "CE_MASTER".
       3. Else if ZM040 has a ZCE UoM row → return Denominator/100, "ZCE_ROW".
       4. Else → return 1.0, "DEFAULT" + log warning."""
```

#### Mentor reference cases (verified)

| SKU | Description | CE | Units/pallet | Status |
|---|---|---:|---:|---|
| (any 1/3 RET case) | Caixa Damm 1/3 | 1.0 | 60  | ✓ mentor reference |
| `0AG0007` | AGUA VERI 1.5L | 1.5 | 40  | ✓ verified vs. ZM040 |
| `GBD20`   | Barril 30 L | 4.0 | 15  | ✓ verified vs. ZM040 |
| `0CF0054` | Estrella Damm 1/3 RET | 1.0 | 60 | ⚠️ ZM040 ZCE row buggy (encodes 0.16); CE master will fix |

#### Override table

`backend/smart_truck/data/ce_overrides.yaml` is reserved for emergency manual fixes only. It starts empty when the CE master Excel is in place, and is populated only when the master is missing AND ZM040 is wrong (e.g. `0CF0054` until the master arrives).

#### Acceptance

- Unit test [`backend/tests/test_ce_master.py`](../backend/tests/test_ce_master.py) asserts the three mentor reference cases against whichever source resolves them, plus the precedence order (override > master > ZCE > default).
- ETL emits a coverage report at `backend/data/processed/ce_coverage.json` with counts of each `source` and lists SKUs falling back to `DEFAULT`.

---

## 2. Domain model — canonical types after ETL

End state of the data layer: we materialise these as parquet files in `backend/data/processed/`.

```python
# customers.parquet      — DR-001.C + geocoded lat/lon
# products.parquet       — DR-001.E + DR-003 (collapsed) + envase flags
# time_windows.parquet   — DR-002
# zones.parquet          — DR-001.D
# routes.parquet         — derived; one row per (ruta, repartidor)
# deliveries.parquet     — DR-001.A normalised
# baseline_loads.parquet — DR-006 + DR-007 parsed for our demo carga(s)
```

---

## 3. Functional requirements

### FR-001 — Data ETL pipeline
- **Input**: raw xlsx + RECURSOS PDFs.
- **Output**: 7 parquet files (see §2), reproducible from `python -m smart_truck.data.load`.
- **Acceptance**:
  - Row count of `deliveries.parquet` equals row count of `Detalle entrega` minus header.
  - Every `customer_id` in `deliveries.parquet` exists in `customers.parquet`.
  - Every `material` in `deliveries.parquet` resolves to a `products.parquet` row with non-null `case_weight_kg` for at least 95% of materials (the rest get a fallback estimate logged).
  - Encoding artefacts (`mcáa`) normalised to clean utf-8.
  - Postcodes zero-padded to 5 chars.
- **Owner**: backend dev A.
- **Depends on**: DR-001…DR-004.

### FR-002 — Geocoding
- **Input**: `customers.parquet` rows missing lat/lon.
- **Output**: same file with lat/lon filled.
- **Provider** (locked 2026-05-09): **Nominatim** (OpenStreetMap), no key required.
  - Endpoint: `https://nominatim.openstreetmap.org/search`
  - Send a real `User-Agent` header (e.g. `smart-truck/0.1 (contact@muvyt.ai)`).
  - Throttle to **1 req/sec** to respect the public usage policy.
  - Region bias: pass `countrycodes=es`.
  - Run as a one-off batch when the customer list is finalised (~20 min for 1,200 addresses); commit the resulting cache so teammates don't re-geocode.
- **Acceptance**:
  - ≥ 95% of demo-route customers (those on DR0027) geocoded successfully.
  - Cache file `backend/data/geo_cache.json` keyed by `f"{street}, {postcode} {city}, Spain"` — a hit returns instantly.
  - Failure mode: log + skip + record `null` in the cache so we don't retry; do not crash the ETL.
- **Owner**: backend dev A.
- **Depends on**: FR-001.

### FR-003 — Distance/time matrix
- **Input**: list of (lat, lon) for the demo carga's stops + Mollet depot.
- **Output**: NxN matrix of (km, minutes).
- **Acceptance**: matrix built in <10s for 20 points; symmetric within 5% (asymmetric only allowed with real road routing).
- **Provider**: OSRM (public or self-hosted) or Mapbox Directions Matrix; fallback haversine × 1.4 detour factor + 25 km/h average.
- **Owner**: backend dev A.

### FR-004 — Baseline reconstruction
- **Input**: DR-006 + DR-007 PDFs for DR0027/2026-05-08.
- **Output**: `baseline_loads.parquet` row + a derived `BaselinePlan` object containing:
  - Stop sequence (from Hoja Ruta order).
  - Per-stop deliveries (joined Hoja Carga → albaranes → albarán line items).
  - As-is load configuration: by `Ubicación` lex sort (mirrors warehouse pick order — assume that's how it ended up loaded).
  - As-is KPIs: total km (computed via FR-003), total time (km/avg-speed + service-time-per-stop assumption), in-truck searches (= number of distinct `Ubicación` values touched per stop, summed), space utilisation (sum of pallet-equivalents / truck capacity).
- **Acceptance**:
  - Stop count matches Hoja Ruta `Nº de pedidos`.
  - Sum of line quantities matches Hoja Carga `Total Cantidad Entrega` ± 0.
  - Sum of line weights matches `Total Peso Entrega` ± 1%.
- **Owner**: backend dev B.
- **Depends on**: FR-001, FR-002, FR-003, DR-005, DR-006, DR-007.

### FR-005 — Route optimiser (VRP-TW)
- **Input**: list of stops (each with lat/lon, time window per weekday, demand in pallet-equivalents), depot, vehicle capacity.
- **Output**: ordered stop sequence with arrival ETAs.
- **Solver**: Google OR-Tools `RoutingModel`.
- **Constraints**:
  - Capacity dimension (pallet-equivalents).
  - Time dimension with per-stop time windows + service time. Stops where `K=L=00:00:00` for the chosen weekday are excluded from the route entirely.
  - **Driver familiarity bias** (locked 2026-05-09): soft penalty on deviating from the as-is order, with a UI-toggleable weight ("familiar" vs "optimal" mode).
- **Service time model** (locked 2026-05-09): `service_time_min = 10 + 2 * distinct_in_truck_zones_touched`. The hybrid load packer (FR-006) reduces zones-touched per stop, which is what materialises the unload-time KPI saving.
- **Acceptance**:
  - Returns a feasible solution within 30 s wall-clock for 20 stops.
  - Respects all time windows or reports infeasibility with an explanation.
- **Owner**: backend dev A.
- **Depends on**: FR-003.

### FR-006 — Stack-LIFO load packer (rewritten 2026-05-09 evening for v2)

**Supersedes** the v1 hybrid packer described in earlier revisions of
this file. v1's envase zone, fungible-slot model, and flat-bag slot
contents are all replaced by the v2 invariants A-36, A-37, A-38.

- **Input**: optimised stop sequence (FR-005), per-stop delivery lines
  (FR-004), `VehicleProfile` (DR-008). The legacy ``envase_lines``
  argument is preserved on `pack_truck` for signature compat but is
  ignored under A-36.
- **Truck grids** (DR-008 — unchanged):
  - **Furgoneta (3-pallet van)**: 1×3 single row.
  - **6-pallet truck**: 2×3, partitioned by central *reixa*.
  - **8-pallet truck**: 2×4, partitioned by central *reixa*.
  - **8-pallet w/ tail-lift**: 2×4 with rear access via *ascensor*.
  - Pallet footprint: EUR 80×120 cm. Vertical stack ≤ 1.80 m per slot.
- **Output**: `LoadPlan` with one `SlotAssignment` per pallet position:
  - `slot_id` (matches Vehicle YAML).
  - `pallet_type ∈ {CASE, BARREL}` (A-37).
  - `stack: list[StackEntry]` ordered TOP→BOTTOM = ascending delivery
    sequence (A-38).
  - `contents` (flattened top-to-bottom for legacy consumers).
  - `ce_used / ce_capacity`.
  - `is_envase_zone = False` always (A-36).
  - `LoadPlan.estimated_driver_minutes` — sum of per-stop driver time
    estimates from the cost model below.

- **Algorithm** (7 phases — full description in
  `optimize/load.py` docstring):
  1. **Categorise** each stop's lines into CASE vs BARREL by UoM (A-37).
  2. **Pallet-count budget**: `n_case = ⌈Σ case_ce / 60⌉`,
     `n_barrel = ⌈Σ barrel_ce / 60⌉`. Reject if total exceeds
     `len(profile.slots)`.
  3. **Slot-type heuristic**: walk slots in `lifo_order_per_face`
     (deepest-first); pick the *shallowest-end* `n_barrel` slots
     accepting BARREL (heavy → close to access face); rest go to CASE.
  4. **Customer-to-pallet assignment** = MILP with PuLP/CBC.
     Variables: `x[c, s] ∈ {0, 1}` (customer in slot), `seq_min[s]`,
     `seq_max[s]`, `pal[s]`. Constraints: each customer → exactly one
     slot; capacity 60 CE per slot; type compatibility (zeroed
     up-front). Objective: minimise `Σ_s (seq_max[s] - seq_min[s])`
     with a 0.01 tie-break per opened pallet. Time limit 10 s; on
     timeout / infeasibility, fall back to a reverse-sequential
     greedy heuristic. Pre-process: split customers >60 CE into
     virtual sub-customers sharing the same `seq` so all virtual
     customers fit in one slot.
  5. **Within-pallet stack order** = ascending delivery sequence
     (A-38). Materialise `stack[]` top-to-bottom.
  6. **Verify access** with the FR-006a check (re-used unchanged from
     v1: `verify_access`).
  7. **Driver-minutes estimate** per stop:
     `t = T_BASE + T_OPEN·n_pallets + T_ROT·n_rotations + T_PER_LINE·n_lines`
     with `(T_BASE, T_OPEN, T_ROT, T_PER_LINE) = (5, 1, 0.05, 0.4)` min.
     `n_rotations` for stop *k* = sum of CE × 0.6 over earlier-delivered
     customer layers above *k*'s layer in shared pallets (the
     accumulated empties from A-35 returns).

- **Acceptance** (locked 2026-05-09 evening):
  - `is_envase_zone == False` for every slot (A-36).
  - `pallet_type` set on every used slot; no slot mixes barrel and case
    cargo (A-37).
  - Each used slot's `stack` is sorted ascending by `stop_sequence`
    (A-38).
  - `Σ slot.ce_used ≤ slot.ce_capacity` for every slot. No weight
    constraint (A-30).
  - All used slots pass `verify_access` (FR-006a).
  - `LoadPlan.estimated_driver_minutes > 0` whenever any cargo is
    packed.
- **Owner**: backend.
- **Depends on**: FR-005, DR-008, DR-009, DR-010.
- **Reference implementation**: `backend/smart_truck/optimize/load.py`
  (~700 LOC). Public surface: `pack_truck`, `verify_access`,
  `StopDemand`, `LoadPlan`, `LoadPlanError`, `CE_PER_PALLET`.

### FR-006a — Access-driven feasibility check (extends FR-006)

The packer signature changes from `(stops, pallet_grid)` to `(stops, vehicle: VehicleProfile, products)`. Three new pieces:

1. **`decompose_stop_demand(stop, products) -> list[LoadUnit]`** — uses the per-SKU CE factor from DR-010 to size each LoadUnit. Emits one `EUR_PALLET` LU when a stop's per-category CE total ≥ 60; else a CE-typed `CASE` / `BRL` / `KEG_FULL` mix that the consolidator stage merges.
2. **`first_compatible_slot(plan, vehicle, lu, stop_id) -> Slot | None`** — replaces the grid-index lookup. Compatibility = `lu.cls in slot.accepts` ∧ `slot.ce_used + lu.ce_per_unit ≤ slot.capacity_ce` ∧ `is_reachable` for `stop_id`. **No weight check** (A-30). Tie-break: minimise `distinct_in_truck_zones_touched per stop` — the FR-005 service-time saving lever.
3. **`is_reachable(plan, vehicle, slot, stop_index, sequence) -> bool`** — for each face in `slot.reachable_from`, the face is unblocked iff every slot in `slot.blocked_by_per_face[face]` is empty by `stop_index`. For `TRUCK_6P_SC` and `TRUCK_8P_SC` (A-33) this collapses to `True` (no rear, no within-side blocking) — the only feasibility constraint is per-side capacity. For `FURGO_3P` (A-32) and `TRUCK_8P_LIFT` (A-34) the full reachability logic runs.

**Feature flag** `STRICT_REACHABILITY=False` downgrades violations to logged warnings (escape hatch for the pitch demo if mentor input is incomplete).

**Acceptance** (in addition to FR-006):
- A synthetic overweight load (Σ kg > nominal_payload_kg) **must still pack successfully** — confirms A-30.
- Furgoneta plans pass `lifo_order_per_face[REAR]` strictly.
- Side-curtain truck plans report `unload_face_per_stop[stop_id] ∈ {LEFT, RIGHT}`.

### FR-007 — Per-pallet returns absorption (rewritten 2026-05-09 evening for v2)

**Supersedes** the v1 envase-zone-pool model. Under A-36 there is no
dedicated envase zone; empties absorb into the freed space of the same
pallet position the cargo just left.

- **Input**: `LoadPlan` (FR-006 v2), per-stop returnable CE volumes.
- **Return rate**: flat 60 % global (A-35).
- **Output**: list of `ReturnsTrace`, one per stop, with
  `cumulative_returns_ce`, `cumulative_freed_ce`, `free_ce_after`.
- **Per-stop freed CE** is now read from `SlotAssignment.stack`
  granularity: when stop *k* is delivered, all stack layers with
  `stop_sequence == k` free their CE. v1-style legacy SlotAssignments
  with `is_envase_zone=True` are still understood (envase zone freed
  from sequence 0) for backward compat.
- **Acceptance**:
  - `cumulative_returns ≤ cumulative_freed` at every stop (always true
    at 60 % rate × full-truck-out invariant; defensive
    `ReturnsInfeasibleError` raised only on programming error).
  - `free_ce_after` monotonically grows by `0.4 × delivered_ce` per
    stop, ending at `0.4 × total_outbound_ce` after the last stop.
- **Reference implementation**:
  `backend/smart_truck/optimize/returns.py`. Public surface:
  `simulate_returns`, `estimate_returnable_ce_per_stop`,
  `ReturnsInfeasibleError`, `RETURN_RATE_FLAT`.

### FR-007a — Slot-typed return absorption (deprecated 2026-05-09 evening)

The slot-typed return absorption originally extended FR-007 to route
returns into the most appropriate slot type (e.g., empty kegs into
`FLOOR_KEG` slots). Under v2 this is implicit: returns flow into the
freed space of the *same* pallet that delivered the corresponding
cargo, so type matching is automatic by construction. Kept here as
context for v3 if multi-slot rebalancing of returns becomes needed.

### FR-008 — Plan pipeline
- **Input**: `(ruta_id, fecha)` tuple.
- **Output**: end-to-end `Plan` object combining the optimised route, load, returns timeline, KPIs vs. baseline, and a list of `Explanation` records ("we placed customer X at P3 because…").
- **Acceptance**: Single function `pipeline.plan(ruta, fecha) -> Plan` returns in <60 s end-to-end on demo data.
- **Owner**: backend dev B.
- **Depends on**: FR-004 … FR-007.

### FR-009 — KPI engine
- **Compares**: `BaselinePlan` (FR-004) vs. `Plan` (FR-008).
- **Metrics** (locked 2026-05-09 — volume KPI dropped because the printed Hoja Carga unit is ambiguous; weight + count are unambiguous and sufficient):
  - `total_km` — from distance matrix along the chosen sequence.
  - `total_minutes` — travel + service.
  - `unload_minutes_estimated` — `10 + 2 * distinct_in_truck_zones_per_stop`, summed across stops. Smart plan should reduce this because each customer's items are clustered in fewer zones.
  - `in_truck_searches` — count of distinct `Ubicación`-equivalent zones touched per stop, summed.
  - `space_utilisation_pct` — sum of pallet-equivalents / truck capacity.
- **Output**: deltas (signed) per metric.
- **Acceptance**: at least 3 of 5 metrics show improvement on demo carga (verification target).
- **Owner**: backend dev B.

### FR-010 — Smart Hoja Carga emitter
- **Input**: `Plan` (FR-008) + parsed source `HojaCarga` (FR-004).
- **Output**: a PDF that reproduces the DDIDGP layout (header, four sections, totals) with the `Descarga` column populated for every line. Optionally colour-codes rows by destination customer cluster.
- **Acceptance**:
  - Visual diff against the source PDF: only the `Descarga` column has new content.
  - Same total counts in section footers.
  - Renders in <5 s for ≤ 100 lines.
- **Tech** (locked 2026-05-09): **ReportLab** (pure Python, no system-library dependencies). Use `Platypus` `Table` flowables; mimic the DDIDGP fonts and column widths from the source PDF.
- **Owner**: backend dev B.

### FR-011 — Smart Hoja Ruta emitter
- **Input**: `Plan` + parsed source `HojaRuta`.
- **Output**: PDF mirroring the source layout, but rows reordered to the optimised sequence and annotated with: ETA, time-window status (✓ / ⚠), CONTADO highlight.
- **Acceptance**:
  - All original albarán IDs present, no duplicates.
  - Row order matches `Plan.sequence`.
- **Tech** (locked 2026-05-09): **ReportLab**, same toolchain as FR-010.
- **Owner**: backend dev B.

### FR-012 — REST API
- **Endpoints**:
  - `POST /plan` — body `{ ruta: string, fecha: ISODate }` → returns `Plan` JSON.
  - `GET /plan/{run_id}/hoja-carga.pdf` — Smart Hoja Carga.
  - `GET /plan/{run_id}/hoja-ruta.pdf` — Smart Hoja Ruta.
  - `GET /baseline?ruta=…&fecha=…` — `BaselinePlan` JSON.
  - `GET /customers/{id}` — for click-through in the map.
- **Tech**: FastAPI, served on `:8000`. CORS open to the frontend origin.
- **Owner**: backend dev B.

### FR-013 — Frontend dashboard (`/`)
- **Layout**: 3-column on desktop. Left: stop list with ETA chips. Centre: map. Right: KPI panel + explanation card for selected stop.
- **Interactions**: click a stop → highlights it on map, shows explanation, scrubs truck twin to that stop.
- **Owner**: frontend dev.
- **Depends on**: FR-012.

### FR-014 — Map view (`MapView.tsx`)
- **Tech** (locked 2026-05-09): **Leaflet** (or `react-leaflet`) with **CartoDB Positron** tiles — no API key, clean light style.
  - Tile URL: `https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png`
  - Attribution: `© OpenStreetMap contributors © CARTO`
- **Renders**: depot marker (Mollet), stop markers numbered in optimised order, polyline animated on play.
- **Acceptance**: 18 stops render in <500 ms; pan/zoom smooth.

### FR-015 — 3D truck twin (`TruckTwin3D.tsx`)
- **Tech**: react-three-fiber + drei.
- **Model**: an open-top truck box (proportions per truck type), with cuboid pallets in their grid positions, coloured by customer.
- **Animation**: time slider 0…N (N = number of stops). At each frame:
  - Pallets that have been delivered fade to 20% opacity.
  - Empties (envases) appear in freed positions, coloured grey with a `↺` symbol.
  - Lateral curtains fade open on the side relevant to the current stop.
- **Acceptance**: 60fps on a recent laptop; falls back to 2D top-down SVG if WebGL unavailable.

### FR-016 — Smart Hoja Carga viewer (`/pick-list`)
- **Tech**: HTML table mirroring the PDF layout, colour-coded by destination cluster, with a toggle "Original / Smart".
- **Acceptance**: judge can read this on a phone screen.

### FR-017 — Driver mobile mockup (`/driver`)
- **Pages**: 3 phone-sized screens.
  1. **Next stop**: customer name, address, ETA, time window status, CONTADO badge if applicable, big "Open right curtain — pallet P3" instruction.
  2. **At stop — pickup**: list of items to deliver (from albarán) + items to collect (empties from this stop).
  3. **Empties capacity**: a gauge showing free zone usage.
- **Acceptance**: static (no real backend connection required), but data hard-coded from one real demo stop on DR0027.

### FR-018 — Explanation cards (`ExplanationCard.tsx`)
- **Renders** the `Explanation` records emitted by FR-008.
- **Format**: "{stop_name} placed at {pallet} because: stop {k}/{N}; {time_window_reason}; {pairing_reason}; {LIFO_reason}".

### FR-019 — Local demo (was: live deployment)
- Decision 2026-05-09: **demo runs on localhost** for v1. Pitch runs from the team's laptop on the projector.
- **Backend**: `uvicorn smart_truck.api:app --port 8000`.
- **Frontend**: `npm run dev` (Next.js dev server on `:3000`).
- **Acceptance**: end-to-end demo (open the dashboard, hit the API, render the map and truck twin, download Smart Hoja Carga PDF) runs cleanly on a freshly-cloned machine after `setup.sh`.

---

## 4. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-001 | Plan-pipeline end-to-end <60 s on demo carga. |
| NFR-002 | All UI in Spanish or Catalan strings (judges + DAMM ops are Spanish/Catalan-speaking). Code comments in English. |
| NFR-003 | No secrets in repo. API keys in `.env` and platform env vars only. |
| NFR-004 | The repo runs cold on a clean machine with `pip install -r requirements.txt && python -m smart_truck.data.load && uvicorn smart_truck.api:app` and `cd frontend && npm i && npm run dev`. |
| NFR-005 | Smart Hoja Carga PDF is visually within 5% of the original DDIDGP layout (font sizes, column widths, header block). Rendered via ReportLab `Platypus` tables. |
| NFR-006 | Frontend works on Chrome, Safari, Firefox latest. |

---

## 5. Locked decisions and remaining assumptions

Most of the table below was resolved in the user-led decision session on 2026-05-09. Items still requiring DAMM-mentor confirmation are flagged.

| ID | Status | Decision / assumption |
|---|---|---|
| A-01 | ⚠️ Superseded 2026-05-09 | Originally locked as furgoneta 1×3, 6-pallet 2×3, 8-pallet 2×4 (EUR 80×120 cm, ≤ 1.80 m stack). **Superseded by DR-008 + A-30..A-34** following mentor input: topology and access mechanism are now per-vehicle, fleet has 4 distinct profiles, capacity is volumetric (CE) per A-31. |
| A-02 | ❌ Refuted 2026-05-09 | Mentor confirmed the opposite: **6P and 8P trucks have a central partition (reixa)** between the two lateral rows; you cannot reach one side from the other. Furgoneta has 1 lateral-only slot + 2 rear-only slots. **Superseded by A-32, A-33.** |
| A-03 | ✅ Resolved 2026-05-09 | Route codes in `Detalle entrega` are standard `DR…`, joinable directly with `ZONAS.RutReal` and Hoja Carga. The single `DA…` legacy route is filtered out during ETL. |
| A-04 | ✅ Confirmed 2026-05-09 | Stop order on the source Hoja Ruta IS the actual delivery order. Drivers cannot re-sequence on the road because the truck load is built specifically for the printed order. The route order itself already reflects driver local experience baked in by the planner. |
| A-05 | ✅ Resolved 2026-05-09 | `Horarios Entrega` is **complete** — every customer × weekday is explicit. `K = L = 00:00:00` means closed that day. No "default window" needed. |
| A-06 | ✅ Locked 2026-05-09 | Service time per stop = `10 + 2 × distinct_in_truck_zones_touched` minutes. Drives the unload-time KPI delta. |
| A-07 | ⚠️ Superseded 2026-05-09 | Originally per-class (BRL 100%, RET 80%, SR 0%, other 60%). **Superseded by A-35**: flat 60% global return rate. Mentor noted seasonal nuance — summer < 60%, winter > 60% — reserved for the pitch only, not modelled. |
| A-08 | ⚠️ Geocode at ETL | Mollet depot lat/lon will be geocoded via Nominatim from the address `C/Molí de Can Bassa, Nau Damm 1, 08100 Mollet del Vallès`. Sanity-check the result. |
| A-09 | ✅ Logged | The carga `11764336` referenced on the example Albarán is a **different carga** from `11764300` on the example Hoja Carga / Hoja Ruta. We use only `11764300` for the demo. |
| A-10 | ✅ Logged | "icired" branding on the Albarán is the e-invoicing platform; not relevant to our build. |
| A-11 | ✅ Locked 2026-05-09 | **Volume KPI is dropped**. We display weight + count only because the printed Hoja Carga's `Total Volumen` unit is ambiguous. |
| A-12 | ✅ Locked 2026-05-09 | **Driver familiarity bias**: soft penalty on deviating from the as-is order, with a UI toggle exposing "familiar" vs "optimal" mode. |
| A-13 | ✅ Locked 2026-05-09 | **Warehouse `Ubicación` codes are treated as opaque**. Pick-list ordering is plain lex sort; no aisle parsing. |
| A-14 | ✅ Locked 2026-05-09 | **Hoja Ruta `SSTT` column** is ignored (always `NO` in our sample). |
| A-15 | ✅ Locked 2026-05-09 | **CONTADO** is surfaced in the driver UI as a flag, but does not affect routing in v1. |
| A-16 | ✅ Locked 2026-05-09 | **Geocoder = Nominatim**, no key, 1 req/sec, cached to `backend/data/geo_cache.json`. |
| A-17 | ✅ Locked 2026-05-09 | **Map tiles = CartoDB Positron** via Leaflet, no key. |
| A-18 | ✅ Locked 2026-05-09 | **PDF rendering = ReportLab** (pure Python). |
| A-19 | ✅ Locked 2026-05-09 | **Persistence = parquet files committed to the repo**. ETL runs on demand to regenerate. |
| A-20 | ✅ Locked 2026-05-09 | **Demo runs on localhost** (no live URL for v1). |
| A-21 | ✅ Confirmed 2026-05-09 | The `Descarga` column on Hoja Carga is **always blank** today. Our intervention populates it; zero-friction adoption. The `Lote` column is also always blank — we leave it untouched in our output. |
| A-22 | ✅ Locked 2026-05-09 | **Pitch narrative**: today, route order and truck load are *implicitly* coupled (the load is arranged around the order, and the order reflects driver experience). Smart Truck makes that coupling explicit, jointly optimised, and reproducible — instead of relying on tribal knowledge per route, per driver. |
| A-30 | ✅ Locked 2026-05-09 | **Volume is the only binding capacity constraint. Weight is informational; do not enforce.** The packer must accept loads that exceed the truck's nominal weight rating; it must reject only on volume (CE) overflow. Drives FR-006a / FR-007a feasibility logic. |
| A-31 | ✅ Locked 2026-05-09 | **Pallet capacity = 60 caixes estadístiques (CE).** Per-SKU CE comes from `Caixes_Estadístiques.xlsx` (authoritative, delivered by mentor); fallback to ZM040 `ZCE` row (`Denominator / 100`); final fallback CE = 1.0 with warning. Verified mentor cases: caixa Damm 1/3 = 1.0 CE → 60 cases/pallet; Veri = 1.5 CE → 40 cases/pallet; barril 30 L = 4.0 CE → 15 barrels/pallet. See DR-010. |
| A-32 | ✅ Locked 2026-05-09 | **Furgoneta (1 unit, 3 pallets in line)**: position 1 (deepest) is accessible *only* via lateral curtain (one side); positions 2 & 3 (middle and rear) are accessible *only* via rear doors and obey LIFO (P3 out before P2). |
| A-33 | ✅ Locked 2026-05-09 | **6P (×11, 2×3) and 8P (×4, 2×4) trucks**: open *only* from the two side curtains, with a **central partition (reixa)**. Left-row pallets are reachable only from LEFT; right-row pallets only from RIGHT; no cross-row access; no rear access. Within a row, all pallets are equally reachable along the curtain length. |
| A-34 | ✅ Locked 2026-05-09 | **8P + tail-lift variant (×4, 2×4)**: as A-33, *plus* rear doors with an `ascensor` (tail-lift). Slots are reachable from both their side curtain and from REAR (with rear-blocking adjacency: rearmost pallets unblock first). Modelled as the `TRUCK_8P_LIFT` profile in DR-008. |
| A-35 | ✅ Locked 2026-05-09 | **Returns rate = 60 % flat global** (replaces the per-class A-07). Applied to outbound CE per stop. Pitch-only nuance: empirically lower in summer, higher in winter; we don't model seasonality in v1. |
| A-36 | ✅ Locked 2026-05-09 (evening) | **No envase zone — truck leaves Mollet 100 % full of outbound product.** The dedicated empties slot of v1 is removed. Outbound envases (`Carga envases` SKUs) ride along with delivered cases on case-pallets — they're physically EUR-pallet stackable. Returns absorb opportunistically into the freed space inside each pallet position as deliveries happen; at 60 % return rate (A-35) the math always fits. |
| A-37 | ✅ Locked 2026-05-09 (evening) | **Barrel/case segregation per pallet.** Each truck pallet position takes a single `pallet_type ∈ {CASE, BARREL}` for one route. Cases and barrels never share a pallet (physical stacking is forbidden). UoM-to-type mapping: `Barril, Tubo` → BARREL; `Caja, Pack, Botella, Unidad, Lat` → CASE. |
| A-38 | ✅ Locked 2026-05-09 (evening) | **Within-pallet stack order = ascending delivery sequence (top = first delivered).** Inside each pallet the customer cluster is stacked so that the next stop's items sit on top of the next-next stop's, and so on. The driver lifts the top off without rotation when their turn comes. Returns from earlier-delivered customers go back on top of the freed space, and may impose rotation cost for subsequent customers in the same pallet — that rotation cost is what FR-006/v2 minimises. |

---

## 6. Out of scope (v1)

- Multi-day rolling re-optimisation when stops slip.
- Driver-side voice prompts.
- Live integration with DDIDGP/SAP printing.
- Modelling the 193×98 Mollet warehouse grid (we use Ubic. lex sort instead).
- Real-time GPS tracking.
- Multi-vehicle / multi-route optimisation across the 470-vehicle fleet (we extrapolate impact verbally).
- Generating customer-facing Smart Albaranes (mentioned as v2 idea).
