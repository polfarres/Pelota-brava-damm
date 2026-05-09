// Hand-built mocks for DR0027 / 2026-05-08 (Sant Julià de Vilatorta → Calldetenes → Folgueroles).
// Six representative stops + a 6-slot truck assignment. Swap these for the real
// `POST /plan` response once Track A ships FR-008.

import type {
  BaselinePlan,
  DeliveryLine,
  PalletAssignment,
  Plan,
  StopPlan,
  VehicleProfile,
} from './types';

export const DEPOT = {
  name: 'DDI Mollet',
  address: 'C/Molí de Can Bassa, Nau Damm 1, Pol. Ind. Can Magarola, 08100 Mollet del Vallès',
  lat: 41.5444,
  lon: 2.2143,
};

const VEHICLE: VehicleProfile = {
  vehicle_id: 'V235045',
  license_plate: '7524KXX',
  profile_name: 'truck_6p_sidecurtain',
  capacity_pallets: 6,
  grid_rows: 2,
  grid_cols: 3,
  has_lift: false,
  ascii_diagram: `
  ┌─────────────────────────┐
  │  P1   P3   P5   (rear) │
  │  P2   P4   P6           │
  └─────────────────────────┘
  side curtain ↑    side curtain ↓
  `,
};

// Six representative deliveries hand-extracted from the DR0027 carga.
const STOPS_BASE: Array<Omit<StopPlan, 'pallet_slots' | 'curtain_side' | 'eta' | 'explanation'>> = [
  {
    sequence: 1,
    customer_id: 9100696143,
    customer_name: 'BAR OLIVEDA',
    address: 'Av. Pau Casals 22',
    city: 'SANT JULIÀ DE VILATORTA',
    lat: 41.9233,
    lon: 2.3091,
    payment_condition: 'CONTADO',
    albaran_id: 828482551,
    proforma_total: 412.55,
    cash_total: 412.55,
    time_window_start: '08:30',
    time_window_end: '11:00',
    delivery_lines: [
      { sku: '0CF0357', description: 'ESTRELLA DAMM 1/3 RET. PP', quantity: 12, unit: 'Caja', ubicacion: 'AA02A1', lote: null, is_envase: false, is_returnable: true },
      { sku: 'BRL30', description: 'BARRIL ESTRELLA 30L', quantity: 2, unit: 'Barril', ubicacion: 'BB04A2', lote: null, is_envase: false, is_returnable: true },
    ],
    pickup_envases: [
      { sku: 'CJ13', description: 'CAJA VACÍA 1/3 RET', quantity: 12, unit: 'Caja', ubicacion: null, lote: null, is_envase: true, is_returnable: false },
    ],
  },
  {
    sequence: 2,
    customer_id: 9100757467,
    customer_name: 'RESTAURANT CA LA MANYANA',
    address: 'C. Sant Roc 8',
    city: 'SANT JULIÀ DE VILATORTA',
    lat: 41.9202,
    lon: 2.3115,
    payment_condition: 'CREDITO',
    albaran_id: 828482558,
    proforma_total: 287.20,
    cash_total: 0,
    time_window_start: '09:00',
    time_window_end: '12:00',
    delivery_lines: [
      { sku: '0CF0357', description: 'ESTRELLA DAMM 1/3 RET. PP', quantity: 8, unit: 'Caja', ubicacion: 'AA02A1', lote: null, is_envase: false, is_returnable: true },
      { sku: 'ED13', description: 'AGUA VICHY 1L', quantity: 6, unit: 'Caja', ubicacion: 'CB06A2', lote: null, is_envase: false, is_returnable: false },
    ],
    pickup_envases: [
      { sku: 'CJ13', description: 'CAJA VACÍA 1/3 RET', quantity: 8, unit: 'Caja', ubicacion: null, lote: null, is_envase: true, is_returnable: false },
    ],
  },
  {
    sequence: 3,
    customer_id: 9100712005,
    customer_name: 'BAR LA PLAÇA',
    address: 'Plaça Major 3',
    city: 'CALLDETENES',
    lat: 41.9263,
    lon: 2.2823,
    payment_condition: 'CONTADO',
    albaran_id: 828482560,
    proforma_total: 153.40,
    cash_total: 153.40,
    time_window_start: '09:30',
    time_window_end: '13:00',
    delivery_lines: [
      { sku: '0CF0357', description: 'ESTRELLA DAMM 1/3 RET. PP', quantity: 5, unit: 'Caja', ubicacion: 'AA02A1', lote: null, is_envase: false, is_returnable: true },
      { sku: '0AM0783', description: 'COCA-COLA 33CL LATA', quantity: 4, unit: 'Pack', ubicacion: 'FA05A2', lote: null, is_envase: false, is_returnable: false },
    ],
    pickup_envases: [
      { sku: 'CJ13', description: 'CAJA VACÍA 1/3 RET', quantity: 5, unit: 'Caja', ubicacion: null, lote: null, is_envase: true, is_returnable: false },
    ],
  },
  {
    sequence: 4,
    customer_id: 9100731122,
    customer_name: 'CAN PERE — BAR',
    address: 'C. Vic 14',
    city: 'CALLDETENES',
    lat: 41.9281,
    lon: 2.2851,
    payment_condition: 'CREDITO',
    albaran_id: 828482563,
    proforma_total: 521.90,
    cash_total: 0,
    time_window_start: '10:00',
    time_window_end: '13:30',
    delivery_lines: [
      { sku: 'BRL20V', description: 'BARRIL VOLL-DAMM 20L', quantity: 3, unit: 'Barril', ubicacion: 'BB04A2', lote: null, is_envase: false, is_returnable: true },
      { sku: 'TB8', description: 'TUBO CO2 8KG', quantity: 1, unit: 'Tubo', ubicacion: 'ZCG', lote: null, is_envase: false, is_returnable: true },
      { sku: 'ED13', description: 'AGUA VICHY 1L', quantity: 4, unit: 'Caja', ubicacion: 'CB06A2', lote: null, is_envase: false, is_returnable: false },
    ],
    pickup_envases: [
      { sku: 'BRL20V', description: 'BARRIL VACÍO 20L', quantity: 3, unit: 'Barril', ubicacion: null, lote: null, is_envase: true, is_returnable: false },
      { sku: 'TB8V', description: 'TUBO CO2 VACÍO', quantity: 1, unit: 'Tubo', ubicacion: null, lote: null, is_envase: true, is_returnable: false },
    ],
  },
  {
    sequence: 5,
    customer_id: 9100689312,
    customer_name: 'HOSTAL FOLGUEROLES',
    address: 'C. Major 22',
    city: 'FOLGUEROLES',
    lat: 41.9399,
    lon: 2.3186,
    payment_condition: 'CREDITO',
    albaran_id: 828482571,
    proforma_total: 698.10,
    cash_total: 0,
    time_window_start: '10:30',
    time_window_end: '14:00',
    delivery_lines: [
      { sku: '0CF0357', description: 'ESTRELLA DAMM 1/3 RET. PP', quantity: 18, unit: 'Caja', ubicacion: 'AA02A1', lote: null, is_envase: false, is_returnable: true },
      { sku: 'ED13', description: 'AGUA VICHY 1L', quantity: 12, unit: 'Caja', ubicacion: 'CB06A2', lote: null, is_envase: false, is_returnable: false },
      { sku: 'BRL30', description: 'BARRIL ESTRELLA 30L', quantity: 1, unit: 'Barril', ubicacion: 'BB04A2', lote: null, is_envase: false, is_returnable: true },
    ],
    pickup_envases: [
      { sku: 'CJ13', description: 'CAJA VACÍA 1/3 RET', quantity: 18, unit: 'Caja', ubicacion: null, lote: null, is_envase: true, is_returnable: false },
      { sku: 'BRL30V', description: 'BARRIL VACÍO 30L', quantity: 1, unit: 'Barril', ubicacion: null, lote: null, is_envase: true, is_returnable: false },
    ],
  },
  {
    sequence: 6,
    customer_id: 9100692087,
    customer_name: 'BAR VERDAGUER',
    address: 'C. Verdaguer 3',
    city: 'FOLGUEROLES',
    lat: 41.9412,
    lon: 2.3201,
    payment_condition: 'CONTADO',
    albaran_id: 828482579,
    proforma_total: 198.75,
    cash_total: 198.75,
    time_window_start: '11:00',
    time_window_end: '14:30',
    delivery_lines: [
      { sku: '0CF0357', description: 'ESTRELLA DAMM 1/3 RET. PP', quantity: 6, unit: 'Caja', ubicacion: 'AA02A1', lote: null, is_envase: false, is_returnable: true },
      { sku: '0AM0783', description: 'COCA-COLA 33CL LATA', quantity: 2, unit: 'Pack', ubicacion: 'FA05A2', lote: null, is_envase: false, is_returnable: false },
    ],
    pickup_envases: [
      { sku: 'CJ13', description: 'CAJA VACÍA 1/3 RET', quantity: 6, unit: 'Caja', ubicacion: null, lote: null, is_envase: true, is_returnable: false },
    ],
  },
];

// Smart (optimised) plan — same stops, but pallet slots assigned + curtain sides + ETAs + explanations.
const SMART_STOPS: StopPlan[] = STOPS_BASE.map((s, i) => {
  const slotMap: Record<number, { slots: string[]; curtain: StopPlan['curtain_side'] }> = {
    0: { slots: ['P1'], curtain: 'right' },
    1: { slots: ['P2'], curtain: 'right' },
    2: { slots: ['P3'], curtain: 'left' },
    3: { slots: ['P4'], curtain: 'left' },
    4: { slots: ['P5'], curtain: 'right' },
    5: { slots: ['P5', 'P6'], curtain: 'rear' },
  };
  const eta = new Date(`2026-05-08T${s.time_window_start}:00`);
  eta.setMinutes(eta.getMinutes() + 15 * i);
  return {
    ...s,
    pallet_slots: slotMap[i].slots,
    curtain_side: slotMap[i].curtain,
    eta: eta.toISOString(),
    explanation: explanationFor(s.sequence, slotMap[i].slots[0], s.customer_name),
  };
});

function explanationFor(seq: number, slot: string, customer: string): string {
  const total = STOPS_BASE.length;
  const reasons = [
    `${customer} colocado en ${slot} porque es la parada ${seq}/${total}.`,
    seq <= 2 ? 'Se entrega temprano por su ventana 08:30–11:00.' : null,
    seq === 1 ? 'Cortina derecha + slot frontal: acceso LIFO inmediato sin reorganizar.' : null,
    seq >= 5 ? 'Slot trasero porque la zona de envases queda libre tras las primeras paradas.' : null,
    'Agrupado con las cajas Estrella 1/3 RET para minimizar búsquedas en bodega.',
  ].filter(Boolean);
  return reasons.join(' ');
}

const PALLETS_SMART: PalletAssignment[] = [
  {
    slot_id: 'P1',
    customer_ids: [9100696143],
    is_envase_zone: false,
    lines: SMART_STOPS[0].delivery_lines,
  },
  {
    slot_id: 'P2',
    customer_ids: [9100757467],
    is_envase_zone: false,
    lines: SMART_STOPS[1].delivery_lines,
  },
  {
    slot_id: 'P3',
    customer_ids: [9100712005],
    is_envase_zone: false,
    lines: SMART_STOPS[2].delivery_lines,
  },
  {
    slot_id: 'P4',
    customer_ids: [9100731122],
    is_envase_zone: false,
    lines: SMART_STOPS[3].delivery_lines,
  },
  {
    slot_id: 'P5',
    customer_ids: [9100689312, 9100692087],
    is_envase_zone: false,
    lines: [...SMART_STOPS[4].delivery_lines, ...SMART_STOPS[5].delivery_lines],
  },
  {
    slot_id: 'P6',
    customer_ids: [],
    is_envase_zone: true,
    lines: [
      { sku: '3ENV-MIX', description: 'ZONA ENVASES VACÍOS', quantity: 52, unit: 'Caja', ubicacion: null, lote: null, is_envase: true, is_returnable: false },
    ],
  },
];

// Baseline: ubicación-sorted load (no slot assignment), original sequence from Hoja Ruta.
const BASELINE_STOPS: StopPlan[] = STOPS_BASE.map((s) => ({
  ...s,
  pallet_slots: undefined, // baseline does not annotate Descarga
  curtain_side: undefined,
}));

const PALLETS_BASELINE: PalletAssignment[] = [
  // Baseline: items grouped by Ubicación (warehouse-pick order). Each "pallet" is a wave from a rack.
  {
    slot_id: 'AA02A1',
    customer_ids: STOPS_BASE.map((s) => s.customer_id),
    is_envase_zone: false,
    lines: STOPS_BASE.flatMap((s) =>
      s.delivery_lines.filter((l) => l.ubicacion === 'AA02A1'),
    ),
  },
  {
    slot_id: 'BB04A2',
    customer_ids: STOPS_BASE.map((s) => s.customer_id),
    is_envase_zone: false,
    lines: STOPS_BASE.flatMap((s) =>
      s.delivery_lines.filter((l) => l.ubicacion === 'BB04A2'),
    ),
  },
  {
    slot_id: 'CB06A2',
    customer_ids: STOPS_BASE.map((s) => s.customer_id),
    is_envase_zone: false,
    lines: STOPS_BASE.flatMap((s) =>
      s.delivery_lines.filter((l) => l.ubicacion === 'CB06A2'),
    ),
  },
  {
    slot_id: 'FA05A2',
    customer_ids: STOPS_BASE.map((s) => s.customer_id),
    is_envase_zone: false,
    lines: STOPS_BASE.flatMap((s) =>
      s.delivery_lines.filter((l) => l.ubicacion === 'FA05A2'),
    ),
  },
  {
    slot_id: 'ZCG',
    customer_ids: STOPS_BASE.map((s) => s.customer_id),
    is_envase_zone: false,
    lines: STOPS_BASE.flatMap((s) =>
      s.delivery_lines.filter((l) => l.ubicacion === 'ZCG'),
    ),
  },
];

const TOTALS = {
  units: 837,
  weight_kg: 4719.12,
  volume_l: 338.21,
};

export const MOCK_BASELINE: BaselinePlan = {
  kind: 'baseline',
  ruta: 'DR0027',
  fecha: '2026-05-08',
  carga_id: 11764300,
  vehicle: VEHICLE,
  driver_id: 850004,
  driver_name: 'FRAN ROMERO',
  stops: BASELINE_STOPS,
  pallet_assignments: PALLETS_BASELINE,
  totals: TOTALS,
  kpi: {
    total_km: 162.4,
    total_minutes: 412,
    unload_minutes_estimated: 198,
    in_truck_searches: 41,
    space_utilisation_pct: 71.2,
  },
};

export const MOCK_PLAN: Plan = {
  kind: 'optimised',
  ruta: 'DR0027',
  fecha: '2026-05-08',
  carga_id: 11764300,
  vehicle: VEHICLE,
  driver_id: 850004,
  driver_name: 'FRAN ROMERO',
  stops: SMART_STOPS,
  pallet_assignments: PALLETS_SMART,
  totals: TOTALS,
  generated_at: new Date().toISOString(),
  kpi_delta: {
    baseline: MOCK_BASELINE.kpi,
    optimised: {
      total_km: 138.2,
      total_minutes: 348,
      unload_minutes_estimated: 132,
      in_truck_searches: 18,
      space_utilisation_pct: 84.5,
    },
    improvements: [
      { metric: 'total_km', delta: -24.2, delta_pct: -14.9, is_improvement: true },
      { metric: 'total_minutes', delta: -64, delta_pct: -15.5, is_improvement: true },
      { metric: 'unload_minutes_estimated', delta: -66, delta_pct: -33.3, is_improvement: true },
      { metric: 'in_truck_searches', delta: -23, delta_pct: -56.1, is_improvement: true },
      { metric: 'space_utilisation_pct', delta: 13.3, delta_pct: 18.7, is_improvement: true },
    ],
  },
};

// Cluster colours used to colour-code rows in the Smart Hoja Carga viewer + the truck twin.
export const CLUSTER_COLORS: Record<number, string> = {
  9100696143: '#E30613', // BAR OLIVEDA — damm-red
  9100757467: '#1E88E5', // CA LA MANYANA — blue
  9100712005: '#43A047', // BAR LA PLAÇA — green
  9100731122: '#FB8C00', // CAN PERE — orange
  9100689312: '#8E24AA', // HOSTAL FOLGUEROLES — purple
  9100692087: '#00ACC1', // BAR VERDAGUER — cyan
};
