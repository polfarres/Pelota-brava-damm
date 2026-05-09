// Typed API client for the Smart Truck backend.
// Backend ships at NEXT_PUBLIC_API_URL (default http://localhost:8000).

import type {
  BaselinePlan,
  Customer,
  DeliveryLine,
  Kpi,
  KpiDelta,
  PalletAssignment,
  Plan,
  StopPlan,
  VehicleProfile,
} from './types';

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function safeFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_URL}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.headers || {}),
    },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function getHealth(): Promise<{ status: string }> {
  return safeFetch('/health');
}

export async function getBaseline(
  ruta: string,
  fecha: string,
): Promise<BaselinePlan> {
  const raw = await safeFetch<BackendPlan>(
    `/baseline?ruta=${encodeURIComponent(ruta)}&fecha=${encodeURIComponent(
      fecha,
    )}`,
  );
  return adaptBaseline(raw);
}

export async function getCustomer(id: number): Promise<Customer> {
  return safeFetch<Customer>(`/customers/${id}`);
}

export async function getPlan(runId: string): Promise<Plan> {
  const raw = await safeFetch<{ plan: BackendPlan; kpi: BackendKpi }>(
    `/plan/${encodeURIComponent(runId)}`,
  );
  return adaptPlan(raw.plan, raw.kpi);
}

export async function postPlan(ruta: string, fecha: string): Promise<Plan> {
  const raw = await safeFetch<{ plan: BackendPlan; kpi: BackendKpi }>(`/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ruta, fecha }),
  });
  return adaptPlan(raw.plan, raw.kpi);
}

export function hojaCargaPdfUrl(runId: string): string {
  return `${API_URL}/plan/${runId}/hoja-carga.pdf`;
}

export function hojaRutaPdfUrl(runId: string): string {
  return `${API_URL}/plan/${runId}/hoja-ruta.pdf`;
}

// ---------------------------------------------------------------------------
// Backend → frontend shape adapters.
//
// The backend ships dataclasses faithfully (see backend smart_truck/models.py).
// The frontend has a slightly richer / nested shape (e.g. ``vehicle`` as a
// VehicleProfile object rather than a profile-name string, ``delivery_lines``
// rather than ``delivered_lines``). These adapters translate without loss.
// ---------------------------------------------------------------------------

interface BackendDeliveredLine {
  sku: string;
  description: string;
  quantity: number;
  unit: string;
  ce: number;
  weight_kg: number;
  source_ubicacion: string | null;
}

interface BackendStopPlan {
  sequence: number;
  customer_id: number;
  customer_name: string;
  address: string;
  lat: number | null;
  lon: number | null;
  eta: string | null;
  time_window: [string, string] | null;
  payment_condition: 'CONTADO' | 'CREDITO';
  proforma_total: string; // Decimal serialised
  delivered_lines: BackendDeliveredLine[];
  returns_estimated_ce: number;
  in_truck_zones_touched: number;
}

interface BackendSlotAssignment {
  slot_id: string;
  is_envase_zone: boolean;
  pallet_type: 'CASE' | 'BARREL' | null;
  stack: Array<{
    stop_sequence: number;
    customer_id: number;
    ce: number;
    lines: BackendDeliveredLine[];
  }>;
  stop_sequences: number[];
  contents: BackendDeliveredLine[];
  ce_used: number;
  ce_capacity: number;
}

interface BackendPlan {
  ruta: string;
  fecha: string;
  vehicle_profile: string;
  stops: BackendStopPlan[];
  slot_assignments: BackendSlotAssignment[];
  explanations?: Array<{ target: string; target_id: string; reason: string }>;
}

interface BackendKpi {
  deltas: Array<{ metric: keyof Kpi; baseline: number; proposed: number }>;
  baseline_metrics: Partial<Record<keyof Kpi, number>>;
  proposed_metrics: Partial<Record<keyof Kpi, number>>;
}

const VEHICLE_PROFILE_PRESETS: Record<string, Omit<VehicleProfile, 'profile_name'>> = {
  furgo_3p: {
    vehicle_id: '',
    license_plate: '',
    capacity_pallets: 3,
    grid_rows: 1,
    grid_cols: 3,
    has_lift: false,
  },
  truck_6p_sidecurtain: {
    vehicle_id: 'V235045',
    license_plate: '7524KXX',
    capacity_pallets: 6,
    grid_rows: 2,
    grid_cols: 3,
    has_lift: false,
  },
  truck_8p_sidecurtain: {
    vehicle_id: '',
    license_plate: '',
    capacity_pallets: 8,
    grid_rows: 2,
    grid_cols: 4,
    has_lift: false,
  },
  truck_8p_lift: {
    vehicle_id: '',
    license_plate: '',
    capacity_pallets: 8,
    grid_rows: 2,
    grid_cols: 4,
    has_lift: true,
  },
};

function adaptVehicle(profileName: string): VehicleProfile {
  const preset = VEHICLE_PROFILE_PRESETS[profileName];
  return {
    profile_name: profileName,
    vehicle_id: preset?.vehicle_id ?? '',
    license_plate: preset?.license_plate ?? '',
    capacity_pallets: preset?.capacity_pallets ?? 0,
    grid_rows: preset?.grid_rows ?? 0,
    grid_cols: preset?.grid_cols ?? 0,
    has_lift: preset?.has_lift ?? false,
  };
}

function adaptDeliveryLine(l: BackendDeliveredLine): DeliveryLine {
  return {
    sku: l.sku,
    description: l.description,
    quantity: l.quantity,
    unit: l.unit,
    ubicacion: l.source_ubicacion,
    lote: null,
    is_envase: false,
    is_returnable: false,
  };
}

function buildStopsToSlots(
  slots: BackendSlotAssignment[],
): Map<number, string[]> {
  const out = new Map<number, string[]>();
  for (const sa of slots) {
    for (const seq of sa.stop_sequences) {
      const list = out.get(seq) ?? [];
      list.push(sa.slot_id);
      out.set(seq, list);
    }
  }
  for (const list of out.values()) list.sort();
  return out;
}

function adaptStop(
  s: BackendStopPlan,
  stopsToSlots: Map<number, string[]>,
): StopPlan {
  return {
    sequence: s.sequence,
    customer_id: s.customer_id,
    customer_name: s.customer_name,
    address: s.address,
    lat: s.lat,
    lon: s.lon,
    payment_condition: s.payment_condition,
    proforma_total: parseFloat(s.proforma_total),
    delivery_lines: s.delivered_lines.map(adaptDeliveryLine),
    eta: s.eta ?? undefined,
    time_window_start: s.time_window?.[0],
    time_window_end: s.time_window?.[1],
    pallet_slots: stopsToSlots.get(s.sequence) ?? [],
  };
}

function adaptPallet(sa: BackendSlotAssignment): PalletAssignment {
  // Derive customer_ids from stack layers (preferred) or fall back to
  // stop_sequences (one entry per sequence — frontend treats the value
  // as a label, not a strict customer_id).
  const customer_ids = sa.stack.length
    ? Array.from(new Set(sa.stack.map((entry) => entry.customer_id)))
    : sa.stop_sequences;
  return {
    slot_id: sa.slot_id,
    customer_ids,
    lines: sa.contents.map(adaptDeliveryLine),
    is_envase_zone: sa.is_envase_zone,
  };
}

function totalsFromStops(stops: BackendStopPlan[]) {
  let units = 0;
  let weight = 0;
  for (const s of stops) {
    for (const l of s.delivered_lines) {
      units += l.quantity;
      weight += l.weight_kg;
    }
  }
  return { units, weight_kg: weight, volume_l: 0 };
}

function emptyKpi(): Kpi {
  return {
    total_km: 0,
    total_minutes: 0,
    unload_minutes_estimated: 0,
    in_truck_searches: 0,
    space_utilisation_pct: 0,
  };
}

function adaptKpiDelta(kpi: BackendKpi): KpiDelta {
  const baseline: Kpi = { ...emptyKpi(), ...kpi.baseline_metrics };
  const optimised: Kpi = { ...emptyKpi(), ...kpi.proposed_metrics };
  const improvements = kpi.deltas.map((d) => {
    const delta = d.proposed - d.baseline;
    const delta_pct = d.baseline === 0 ? 0 : (delta / d.baseline) * 100;
    const is_improvement =
      d.metric === 'space_utilisation_pct' ? delta > 0 : delta < 0;
    return { metric: d.metric, delta, delta_pct, is_improvement };
  });
  return { baseline, optimised, improvements };
}

function adaptPlan(plan: BackendPlan, kpi: BackendKpi): Plan {
  const stopsToSlots = buildStopsToSlots(plan.slot_assignments);
  return {
    kind: 'optimised',
    ruta: plan.ruta,
    fecha: plan.fecha,
    vehicle: adaptVehicle(plan.vehicle_profile),
    stops: plan.stops.map((s) => adaptStop(s, stopsToSlots)),
    pallet_assignments: plan.slot_assignments.map(adaptPallet),
    totals: totalsFromStops(plan.stops),
    kpi_delta: adaptKpiDelta(kpi),
    generated_at: new Date().toISOString(),
  };
}

function adaptBaseline(plan: BackendPlan): BaselinePlan {
  const stopsToSlots = buildStopsToSlots(plan.slot_assignments);
  return {
    kind: 'baseline',
    ruta: plan.ruta,
    fecha: plan.fecha,
    vehicle: adaptVehicle(plan.vehicle_profile),
    stops: plan.stops.map((s) => adaptStop(s, stopsToSlots)),
    pallet_assignments: plan.slot_assignments.map(adaptPallet),
    totals: totalsFromStops(plan.stops),
  };
}
