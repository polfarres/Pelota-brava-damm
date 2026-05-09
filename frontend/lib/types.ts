// TypeScript mirror of backend smart_truck/models.py
// Matches the Plan / BaselinePlan contract described in PLAN/Specifications.md (FR-004 / FR-008).

export interface Customer {
  customer_id: number;
  name: string;
  street: string;
  postcode: string;
  city: string;
  lat: number | null;
  lon: number | null;
}

export interface DeliveryLine {
  sku: string;
  description: string;
  quantity: number;
  unit: string; // Caja / Barril / Tubo / Unidad / Pack / Botella
  ubicacion: string | null; // warehouse pick location
  lote: string | null;
  is_envase: boolean;
  is_returnable: boolean;
}

export interface PalletAssignment {
  slot_id: string; // e.g. "P1", "P2"
  customer_ids: number[];
  lines: DeliveryLine[];
  is_envase_zone: boolean;
}

export interface VehicleProfile {
  vehicle_id: string;
  license_plate: string;
  profile_name: string; // furgo_3p / truck_6p_sidecurtain / ...
  capacity_pallets: number;
  grid_rows: number;
  grid_cols: number;
  has_lift: boolean;
  ascii_diagram?: string;
}

export interface StopPlan {
  sequence: number; // 1-indexed
  customer_id: number;
  customer_name: string;
  address: string;
  city: string;
  lat: number | null;
  lon: number | null;
  payment_condition: 'CONTADO' | 'CREDITO';
  albaran_id: number;
  proforma_total: number;
  cash_total: number;
  // Optimised fields (may be empty for baseline-only ETAs):
  eta?: string; // ISO datetime
  time_window_start?: string; // HH:mm
  time_window_end?: string;
  pallet_slots?: string[]; // which pallets serve this stop
  curtain_side?: 'left' | 'right' | 'rear' | 'both';
  delivery_lines: DeliveryLine[];
  pickup_envases?: DeliveryLine[];
  explanation?: string;
}

export interface Kpi {
  total_km: number;
  total_minutes: number;
  unload_minutes_estimated: number;
  in_truck_searches: number;
  space_utilisation_pct: number;
}

export interface KpiDelta {
  baseline: Kpi;
  optimised: Kpi;
  improvements: {
    metric: keyof Kpi;
    delta: number; // optimised - baseline
    delta_pct: number;
    is_improvement: boolean;
  }[];
}

export interface PlanBase {
  ruta: string;
  fecha: string; // ISO date
  carga_id: number;
  vehicle: VehicleProfile;
  driver_id: number;
  driver_name: string;
  stops: StopPlan[];
  pallet_assignments: PalletAssignment[];
  totals: {
    units: number;
    weight_kg: number;
    volume_l: number;
  };
}

export interface BaselinePlan extends PlanBase {
  kind: 'baseline';
  kpi: Kpi;
}

export interface Plan extends PlanBase {
  kind: 'optimised';
  kpi_delta: KpiDelta;
  generated_at: string;
}
