'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { MOCK_PLAN } from '@/lib/mocks';
import { getPlan } from '@/lib/api';
import { colorForCustomer } from '@/lib/colors';
import type { Plan, StackLayer } from '@/lib/types';

// react-three-fiber must not be SSR'd — Three.js needs the browser's
// WebGL context. Same pattern we use for Leaflet.
const TruckScene3D = dynamic(() => import('@/components/TruckScene3D'), {
  ssr: false,
  loading: () => (
    <div className="w-full bg-gray-100 flex items-center justify-center text-gray-500 rounded-lg" style={{ height: 380 }}>
      Carregant escena 3D…
    </div>
  ),
});

const RUN_ID = 'DR0027-2026-05-08';

// Loading order for warehouse staff. Two principles:
// 1. Innermost slots first (deepest from the curtain). Loading a slot
//    that's blocked by another already-full slot is impossible.
// 2. Within a slot, BOTTOM layer first = last-delivered customer at
//    the bottom, first-delivered on top (A-38 LIFO).
//
// Slot loading order is the REVERSE of curtain access order. Across
// the standard 6p_sidecurtain truck the access order is the back-row
// slots P2/P4/P6 (left curtain) and the front-row P1/P3/P5 (right
// curtain). We just sort by slot label descending — the YAML files
// number the deeper slots higher.
function slotLoadOrder(slotIds: string[]): string[] {
  const sorted = [...slotIds];
  sorted.sort((a, b) => {
    // Pn comes after Pm if n > m, so reverse-numeric.
    const na = parseInt(a.replace(/\D/g, ''), 10) || 0;
    const nb = parseInt(b.replace(/\D/g, ''), 10) || 0;
    return nb - na;
  });
  return sorted;
}

interface LoadStep {
  slotId: string;
  layerIndex: number;        // 0 = bottom of pallet (first to load)
  totalLayers: number;
  customer_id: number | null;  // null = whole-column staple step
  customer_name: string;
  stop_sequence: number | null;
  isStapleColumn: boolean;
  lines: { ubicacion: string | null; sku: string; description: string; quantity: number; unit: string }[];
  totalCe: number;
}

const STAPLE_SKUS = new Set(['CJ13', 'ED13']);

function isStaplePallet(pa: { stack?: StackLayer[]; lines: { sku: string }[] }): boolean {
  const skus = new Set((pa.lines ?? []).map((l) => l.sku));
  if (skus.size === 0 || skus.size > 2) return false;
  // True staple = column dedicated to Tier-1 SKUs across many stops.
  return [...skus].every((s) => STAPLE_SKUS.has(s));
}

function aggregateLinesBySku(
  lines: { ubicacion: string | null; sku: string; description: string; quantity: number; unit: string }[],
): LoadStep['lines'] {
  const byKey = new Map<string, LoadStep['lines'][number]>();
  for (const l of lines) {
    const key = `${l.ubicacion ?? ''}::${l.sku}::${l.unit}`;
    const existing = byKey.get(key);
    if (existing) {
      existing.quantity += l.quantity;
    } else {
      byKey.set(key, { ...l });
    }
  }
  // Round and drop near-zero rows. The carga aggregate distributes
  // quantities by proforma proportion which can produce sub-unit
  // fractions per layer; the picker only ever picks integer cases.
  return [...byKey.values()]
    .map((l) => ({ ...l, quantity: Math.round(l.quantity) }))
    .filter((l) => l.quantity > 0)
    .sort((a, b) => (a.ubicacion ?? '').localeCompare(b.ubicacion ?? ''));
}

function buildLoadingSteps(plan: Plan): LoadStep[] {
  const customerNameById = new Map<number, string>();
  for (const s of plan.stops) customerNameById.set(s.customer_id, s.customer_name);

  const slotIds = plan.pallet_assignments
    .filter((p) => (p.stack && p.stack.length > 0))
    .map((p) => p.slot_id);
  const orderedSlots = slotLoadOrder(slotIds);

  const steps: LoadStep[] = [];
  for (const slotId of orderedSlots) {
    const pa = plan.pallet_assignments.find((p) => p.slot_id === slotId)!;
    const stack: StackLayer[] = pa.stack ?? [];
    if (stack.length === 0) continue;

    if (isStaplePallet(pa)) {
      // ONE summary step per staple column — the picker brings the whole
      // SKU as a single warehouse wave, no layering matters.
      const totalCe = pa.ce_used ?? stack.reduce((s, l) => s + l.ce, 0);
      const allLines = stack.flatMap((l) => l.lines);
      const aggregated = aggregateLinesBySku(allLines);
      if (aggregated.length === 0) continue;
      steps.push({
        slotId,
        layerIndex: 0,
        totalLayers: 1,
        customer_id: null,
        customer_name: '',
        stop_sequence: null,
        isStapleColumn: true,
        lines: aggregated,
        totalCe,
      });
      continue;
    }

    // LIFO pallet: stack is TOP→BOTTOM. Load bottom-first so we walk in
    // reverse: stack[N-1] is the pallet floor (last-delivered customer).
    const layerSteps: LoadStep[] = [];
    for (let i = stack.length - 1; i >= 0; i--) {
      const layer = stack[i];
      const layerIndex = stack.length - 1 - i;  // 0 = bottom
      const customer = customerNameById.get(layer.customer_id) ?? `client #${layer.customer_id}`;
      const aggregated = aggregateLinesBySku(layer.lines);
      if (aggregated.length === 0) continue;
      layerSteps.push({
        slotId,
        layerIndex,
        totalLayers: stack.length,
        customer_id: layer.customer_id,
        customer_name: customer,
        stop_sequence: layer.stop_sequence,
        isStapleColumn: false,
        lines: aggregated,
        totalCe: layer.ce,
      });
    }

    if (layerSteps.length > 0) {
      steps.push(...layerSteps);
    } else {
      // Every per-layer aggregation rounded to zero (typical for the
      // barrel pallet, where ~6-8 total caixes are distributed across
      // 15 stops in fractional shares). Emit ONE whole-pallet step so
      // the picker still loads the cargo.
      const allLines = stack.flatMap((l) => l.lines);
      const aggregated = aggregateLinesBySku(allLines);
      if (aggregated.length > 0) {
        const totalCe = pa.ce_used ?? stack.reduce((s, l) => s + l.ce, 0);
        steps.push({
          slotId,
          layerIndex: 0,
          totalLayers: 1,
          customer_id: null,
          customer_name: '',
          stop_sequence: null,
          isStapleColumn: false,
          lines: aggregated,
          totalCe,
        });
      }
    }
  }
  return steps;
}

export default function LoadingPage() {
  const [plan, setPlan] = useState<Plan>(MOCK_PLAN);
  const [activeStep, setActiveStep] = useState(0);
  const [apiOk, setApiOk] = useState<'pending' | 'ok' | 'fallback'>('pending');

  useEffect(() => {
    let cancelled = false;
    getPlan(RUN_ID)
      .then((p) => {
        if (!cancelled) {
          setPlan(p);
          setApiOk('ok');
        }
      })
      .catch(() => !cancelled && setApiOk('fallback'));
    return () => {
      cancelled = true;
    };
  }, []);

  const steps = useMemo(() => buildLoadingSteps(plan), [plan]);
  const totalSteps = steps.length;

  const { loadedLayerKeys, loadedFullSlots } = useMemo(() => {
    const layers = new Set<string>();
    const fullSlots = new Set<string>();
    for (let i = 0; i <= activeStep; i++) {
      const s = steps[i];
      if (!s) continue;
      if (s.customer_id == null) {
        // Whole-pallet step — covers staples and aggregated barrel pallets.
        fullSlots.add(s.slotId);
      } else if (s.stop_sequence != null) {
        layers.add(`${s.slotId}::${s.stop_sequence}`);
      }
    }
    return { loadedLayerKeys: layers, loadedFullSlots: fullSlots };
  }, [steps, activeStep]);

  const currentStep = steps[activeStep];

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h1 className="text-2xl font-bold">Pla de càrrega · suport magatzem</h1>
          <p className="text-sm text-gray-600 mt-1">
            Segueix els passos en l&apos;ordre marcat. Carrega de més fons (lluny
            de la cortina) cap a fora, i de baix a dalt dins de cada palet.
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
            loadedLayerKeys={loadedLayerKeys}
            loadedFullSlots={loadedFullSlots}
            currentSlotId={currentStep?.slotId ?? null}
          />
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <Counter label="Pas" value={`${activeStep + 1} / ${totalSteps}`} />
            <Counter
              label="Palets ja carregats"
              value={`${new Set(steps.slice(0, activeStep + 1).map((s) => s.slotId)).size} / ${
                new Set(steps.map((s) => s.slotId)).size
              }`}
            />
          </div>
          <div className="mt-3">
            <input
              type="range"
              min={0}
              max={Math.max(0, totalSteps - 1)}
              value={activeStep}
              onChange={(e) => setActiveStep(Number(e.target.value))}
              className="w-full accent-damm-red"
            />
            <div className="flex gap-2 mt-2">
              <button
                className="text-xs bg-damm-dark text-white px-3 py-1.5 rounded disabled:opacity-40"
                onClick={() => setActiveStep((s) => Math.max(0, s - 1))}
                disabled={activeStep === 0}
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
            </div>
          </div>
        </div>

        {/* Steps list */}
        <div className="col-span-6 flex flex-col gap-2">
          {steps.map((s, i) => (
            <StepCard
              key={`${s.slotId}-${s.layerIndex}-${s.stop_sequence}`}
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
        Nota: els passos d&apos;una columna staple agrupen totes les caixes del
        mateix SKU en una sola onada al magatzem (el camió rep tota la
        columna del producte). Els palets LIFO es carreguen pel terra (última
        parada) cap a dalt (primera parada).
      </p>
    </div>
  );
}

function Counter({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded p-2">
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className="font-bold text-base">{value}</div>
    </div>
  );
}

function StepCard({
  step,
  index,
  active,
  done,
  onClick,
}: {
  step: LoadStep;
  index: number;
  active: boolean;
  done: boolean;
  onClick: () => void;
}) {
  const isWholePalletAggregate = step.customer_id == null;
  const colour = !isWholePalletAggregate
    ? colorForCustomer(step.customer_id as number)
    : step.isStapleColumn
      ? '#E30613'         // damm-red for the staple column
      : '#78716C';        // stone-500 for aggregated barrel pallets
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
          className="flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-bold"
          style={{ backgroundColor: done ? '#6B7280' : colour }}
        >
          {done ? '✓' : index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-bold text-sm">
              {step.isStapleColumn
                ? `★ Columna staple · ${step.slotId}`
                : `Palet ${step.slotId}`}
            </span>
            {!step.isStapleColumn && (
              <span className="text-[10px] bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded font-mono">
                capa {step.layerIndex + 1}/{step.totalLayers}
              </span>
            )}
            <span className="text-[10px] bg-gray-200 text-gray-700 px-1.5 py-0.5 rounded">
              {step.totalCe.toFixed(0)} CE
            </span>
          </div>
          <div className="text-xs text-gray-700">
            {step.isStapleColumn
              ? 'Una sola onada de magatzem · tota la columna del producte'
              : `Per a parada #${step.stop_sequence} · ${step.customer_name}`}
          </div>
          <ul className="mt-2 text-xs space-y-0.5">
            {step.lines.map((l, i) => (
              <li key={i} className="flex justify-between bg-gray-50 px-2 py-1 rounded">
                <span className="font-mono text-gray-500 w-20 flex-shrink-0">
                  {l.ubicacion || '—'}
                </span>
                <span className="flex-1 truncate ml-2">{l.description || l.sku}</span>
                <span className="ml-2 font-bold whitespace-nowrap">
                  {l.quantity} {l.unit}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </button>
  );
}

