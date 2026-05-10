'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { MOCK_PLAN } from '@/lib/mocks';
import { getPlan } from '@/lib/api';
import { colorForSku } from '@/lib/colors';
import type { Plan } from '@/lib/types';

const TruckScene3D = dynamic(() => import('@/components/TruckScene3D'), {
  ssr: false,
  loading: () => (
    <div className="w-full bg-gray-100 flex items-center justify-center text-gray-500 rounded-lg" style={{ height: 380 }}>
      Carregant escena 3D…
    </div>
  ),
});

const RUN_ID = 'DR0027-2026-05-08';

// ---------------------------------------------------------------------------
// Step builder — by warehouse Ubicació, distributing across pallets.
//
// The picker walks the warehouse in lex order of Ubicació (A → Z, the same
// path they take to fill a regular Hoja Carga). At each rack they pick all
// the items destined for any of the truck's pallets in this carga, then
// distribute those items across the right slots. Compared to the old
// pallet-by-pallet ordering, this reflects what the warehouse staff
// actually do and exposes Smart Truck's value: the SAME walk, just with
// boxes going to several pallets each stop.
// ---------------------------------------------------------------------------

interface AggregatedLine {
  sku: string;
  description: string;
  unit: string;
  quantity: number;
  ce: number;
}

interface PalletDestination {
  slotId: string;
  lines: AggregatedLine[];
  cellsAdded: number;
}

interface UbicacioStep {
  index: number;
  ubicacion: string;
  destinations: PalletDestination[];
  totalCe: number;
  totalCells: number;
}

function aggregateBySku(
  recs: { sku: string; description: string; unit: string; quantity: number; ce?: number }[],
): AggregatedLine[] {
  const map = new Map<string, AggregatedLine>();
  for (const r of recs) {
    const key = `${r.sku}::${r.unit}`;
    const cellCe = (r.ce ?? 1) * r.quantity;
    const existing = map.get(key);
    if (existing) {
      existing.quantity += r.quantity;
      existing.ce += cellCe;
    } else {
      map.set(key, {
        sku: r.sku,
        description: r.description,
        unit: r.unit,
        quantity: r.quantity,
        ce: cellCe,
      });
    }
  }
  return [...map.values()]
    .map((l) => ({ ...l, quantity: Math.round(l.quantity), ce: Math.round(l.ce) }))
    .filter((l) => l.quantity > 0)
    .sort((a, b) => b.ce - a.ce);
}

function buildUbicacionSteps(plan: Plan): UbicacioStep[] {
  // Flatten: (ubicacion, slotId, line)
  type Rec = {
    ubicacion: string;
    slotId: string;
    sku: string;
    description: string;
    unit: string;
    quantity: number;
    ce?: number;
  };
  const records: Rec[] = [];
  for (const pa of plan.pallet_assignments) {
    if (!pa.lines) continue;
    for (const l of pa.lines) {
      records.push({
        ubicacion: l.ubicacion ?? '(sense ubicació)',
        slotId: pa.slot_id,
        sku: l.sku,
        description: l.description,
        unit: l.unit,
        quantity: l.quantity,
        ce: l.ce,
      });
    }
  }

  // Group by Ubicació
  const byUbic = new Map<string, Rec[]>();
  for (const r of records) {
    const list = byUbic.get(r.ubicacion) ?? [];
    list.push(r);
    byUbic.set(r.ubicacion, list);
  }

  // Within each Ubicació, group by destination slot, then aggregate by SKU.
  const ubicacions = [...byUbic.keys()].sort((a, b) => a.localeCompare(b));
  const steps: UbicacioStep[] = [];
  for (const [idx, ubic] of ubicacions.entries()) {
    const recs = byUbic.get(ubic)!;
    const bySlot = new Map<string, Rec[]>();
    for (const r of recs) {
      const list = bySlot.get(r.slotId) ?? [];
      list.push(r);
      bySlot.set(r.slotId, list);
    }
    const destinations: PalletDestination[] = [];
    let totalCells = 0;
    let totalCe = 0;
    for (const [slotId, slotRecs] of bySlot) {
      const lines = aggregateBySku(slotRecs);
      if (lines.length === 0) continue;
      const cellsAdded = lines.reduce(
        (s, l) => s + Math.max(1, l.ce),
        0,
      );
      totalCells += cellsAdded;
      totalCe += lines.reduce((s, l) => s + l.ce, 0);
      destinations.push({ slotId, lines, cellsAdded });
    }
    if (destinations.length === 0) continue;
    destinations.sort((a, b) => a.slotId.localeCompare(b.slotId));
    steps.push({
      index: idx,
      ubicacion: ubic,
      destinations,
      totalCells,
      totalCe,
    });
  }
  return steps;
}

// ---------------------------------------------------------------------------
// Cell building for the 3D scene.
//
// Each cell still represents 1 CE of one product in one slot. We tag each
// cell with its source Ubicació so the 3D scene can show the cells of the
// currently-picked Ubicacions filled, regardless of which slot they're in.
// ---------------------------------------------------------------------------

interface SceneCell {
  sku: string;
  customer_id: number | null;
  ubicacion: string;
  unit: string;
}

function buildCellsBySlot(plan: Plan): Map<string, SceneCell[]> {
  // Cells are laid out per slot in load order (same as before): bottom-back
  // up to top-front. This preserves the LIFO discipline visually — the
  // picker may pick an upper-level cell first (because its Ubicació comes
  // earlier in lex), but the cell still shows up at its physically correct
  // position in the slot. Floating cells are accepted as a simplification:
  // in real life the picker uses a worktable to buffer until the bottom
  // levels are ready.
  const map = new Map<string, SceneCell[]>();
  for (const pa of plan.pallet_assignments) {
    if (!pa.lines || pa.lines.length === 0) continue;
    const list: SceneCell[] = [];
    // Walk the contents in their backend-emitted order (already in
    // load order from the v3 packer: bottom→top by stack position).
    for (const l of pa.lines) {
      const cellsForLine = Math.max(1, Math.round((l.ce ?? 1) * l.quantity));
      for (let i = 0; i < cellsForLine; i++) {
        list.push({
          sku: l.sku,
          customer_id: pa.customer_ids[0] ?? null,
          ubicacion: l.ubicacion ?? '(sense ubicació)',
          unit: l.unit,
        });
      }
    }
    if (list.length > 60) list.length = 60;
    map.set(pa.slot_id, list);
  }
  return map;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function LoadingPage() {
  const [plan, setPlan] = useState<Plan>(MOCK_PLAN);
  // -1 = initial state (empty truck, no Ubicació picked yet).
  const [activeStep, setActiveStep] = useState(-1);
  const [apiOk, setApiOk] = useState<'pending' | 'ok' | 'fallback'>('pending');

  useEffect(() => {
    let cancelled = false;
    getPlan(RUN_ID)
      .then((p) => {
        if (!cancelled) {
          setPlan(p);
          setApiOk('ok');
          setActiveStep(-1);
        }
      })
      .catch(() => !cancelled && setApiOk('fallback'));
    return () => {
      cancelled = true;
    };
  }, []);

  const steps = useMemo(() => buildUbicacionSteps(plan), [plan]);
  const totalSteps = steps.length;

  const cellsBySlot = useMemo(() => buildCellsBySlot(plan), [plan]);

  // Set of Ubicacions already picked at the current step.
  const pickedUbics = useMemo(() => {
    const set = new Set<string>();
    for (let i = 0; i <= activeStep; i++) {
      const s = steps[i];
      if (s) set.add(s.ubicacion);
    }
    return set;
  }, [steps, activeStep]);

  // Visible cells per slot are those whose ubicacion has already been picked.
  const visibleCellsPerSlot = useMemo(() => {
    const out = new Map<string, SceneCell[]>();
    for (const [slotId, cells] of cellsBySlot) {
      out.set(
        slotId,
        cells.filter((c) => pickedUbics.has(c.ubicacion)),
      );
    }
    return out;
  }, [cellsBySlot, pickedUbics]);

  // Slots fully loaded so far (visible == total).
  const slotFullCellsTarget = useMemo(() => {
    const m = new Map<string, number>();
    for (const [slotId, cells] of cellsBySlot) m.set(slotId, cells.length);
    return m;
  }, [cellsBySlot]);

  const slotsFullyLoaded = useMemo(() => {
    let n = 0;
    for (const [slotId, target] of slotFullCellsTarget) {
      if ((visibleCellsPerSlot.get(slotId)?.length ?? 0) >= target) n++;
    }
    return n;
  }, [visibleCellsPerSlot, slotFullCellsTarget]);

  const currentStep = activeStep >= 0 ? steps[activeStep] : null;

  // Pallet types (CASE / BARREL) used by the 3D scene to switch geometry.
  const palletTypes = useMemo(() => {
    const m = new Map<string, 'CASE' | 'BARREL' | null>();
    for (const pa of plan.pallet_assignments) {
      m.set(pa.slot_id, pa.pallet_type ?? null);
    }
    return m;
  }, [plan.pallet_assignments]);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h1 className="text-2xl font-bold">Pla de càrrega · suport magatzem</h1>
          <p className="text-sm text-gray-600 mt-1">
            Cada pas és una <strong>ubicació al magatzem</strong> en ordre de
            recorregut. Smart Truck reparteix cada onada de pick entre els
            palets del camió: el mosso fa el mateix recorregut de sempre,
            però els productes acaben repartits intel·ligentment.
          </p>
        </div>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
            apiOk === 'ok'
              ? 'bg-green-100 text-green-700'
              : apiOk === 'fallback'
                ? 'bg-yellow-100 text-yellow-700'
                : 'bg-gray-100 text-gray-500'
          }`}
        >
          {apiOk === 'ok' ? 'API connectada' : apiOk === 'fallback' ? 'Dades de prova' : 'Carregant…'}
        </span>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* 3D truck scene (sticky) */}
        <div className="col-span-6 bg-white border border-gray-200 rounded-lg p-3 self-start sticky top-3">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-bold text-sm">Estat del camió · 3D</h2>
            <span className="text-[10px] text-gray-500">arrossega per girar</span>
          </div>
          <TruckScene3D
            plan={plan}
            cellsBySlot={cellsBySlot}
            visibleCellsPerSlot={visibleCellsPerSlot}
            palletTypes={palletTypes}
            currentSlotIds={
              new Set(currentStep?.destinations.map((d) => d.slotId) ?? [])
            }
          />
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <Counter
              label="Pas (ubicació)"
              value={
                activeStep < 0
                  ? `Camió buit · 0 / ${totalSteps}`
                  : `${activeStep + 1} / ${totalSteps}`
              }
            />
            <Counter
              label="Palets ja carregats"
              value={`${slotsFullyLoaded} / ${slotFullCellsTarget.size}`}
            />
          </div>
          <div className="mt-3">
            <input
              type="range"
              min={-1}
              max={Math.max(0, totalSteps - 1)}
              value={activeStep}
              onChange={(e) => setActiveStep(Number(e.target.value))}
              className="w-full accent-damm-red"
            />
            <div className="flex gap-2 mt-2">
              <button
                className="text-xs bg-damm-dark text-white px-3 py-1.5 rounded disabled:opacity-40"
                onClick={() => setActiveStep((s) => Math.max(-1, s - 1))}
                disabled={activeStep <= -1}
              >
                ← Anterior
              </button>
              <button
                className="text-xs bg-damm-red text-white px-3 py-1.5 rounded disabled:opacity-40"
                onClick={() => setActiveStep((s) => Math.min(totalSteps - 1, s + 1))}
                disabled={activeStep >= totalSteps - 1}
              >
                Següent →
              </button>
              <button
                className="text-xs bg-gray-200 text-gray-700 px-3 py-1.5 rounded ml-auto"
                onClick={() => setActiveStep(-1)}
                title="Reinicia: camió buit"
              >
                ⟲
              </button>
            </div>
          </div>
        </div>

        {/* Steps list */}
        <div className="col-span-6 flex flex-col gap-2 max-h-[calc(100vh-7rem)] overflow-y-auto pr-1">
          {steps.map((s, i) => (
            <UbicacioCard
              key={s.ubicacion}
              step={s}
              index={i}
              active={i === activeStep}
              done={i < activeStep}
              onClick={() => setActiveStep(i)}
            />
          ))}
          {totalSteps === 0 && (
            <div className="text-sm text-gray-500 italic p-4 bg-white border border-gray-200 rounded">
              Carregant pla del camió…
            </div>
          )}
        </div>
      </div>

      <p className="text-xs text-gray-500 mt-4">
        El codi de colors és <strong>per producte</strong>: cada SKU té el seu
        color, així el mosso pot creuar el quadradet de color del pas amb les
        caixes (o barrils circulars) del palet 3D directament.
      </p>
    </div>
  );
}

function Counter({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded p-2">
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className="font-bold text-sm">{value}</div>
    </div>
  );
}

function UbicacioCard({
  step,
  index,
  active,
  done,
  onClick,
}: {
  step: UbicacioStep;
  index: number;
  active: boolean;
  done: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`text-left rounded-lg p-3 border transition-all ${
        active
          ? 'border-damm-red bg-white shadow-md'
          : done
            ? 'border-gray-200 bg-gray-50 opacity-60'
            : 'border-gray-200 bg-white hover:border-gray-400'
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-bold ${
            done ? 'bg-gray-500' : 'bg-damm-dark'
          }`}
        >
          {done ? '✓' : index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono font-bold text-sm">{step.ubicacion}</span>
            <span className="text-[10px] bg-gray-200 text-gray-700 px-1.5 py-0.5 rounded">
              {Math.round(step.totalCe)} CE
            </span>
            <span className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
              {step.destinations.length === 1
                ? `→ ${step.destinations[0].slotId}`
                : `→ ${step.destinations.length} palets`}
            </span>
          </div>
          {step.destinations.map((d) => (
            <div key={d.slotId} className="mb-1.5 last:mb-0">
              <div className="text-[10px] uppercase font-bold text-gray-500 mb-0.5 flex items-center gap-2">
                <span>destí · </span>
                <span className="bg-damm-red text-white px-1.5 py-0.5 rounded font-mono">
                  {d.slotId}
                </span>
              </div>
              <ul className="space-y-0.5">
                {d.lines.map((l) => (
                  <li key={l.sku} className="flex items-center bg-gray-50 px-2 py-1 rounded text-xs">
                    <span
                      className="inline-block w-3 h-3 rounded-sm flex-shrink-0"
                      style={{ backgroundColor: colorForSku(l.sku) }}
                      title={l.sku}
                    />
                    <span className="font-mono text-gray-500 ml-2 flex-shrink-0">{l.sku}</span>
                    <span className="flex-1 truncate ml-2">{l.description}</span>
                    <span className="ml-2 font-bold whitespace-nowrap">
                      {l.quantity} {l.unit}
                    </span>
                    <span className="text-[10px] text-gray-500 ml-2 font-mono">{l.ce} CE</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </button>
  );
}
