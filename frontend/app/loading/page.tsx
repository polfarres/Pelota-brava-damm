'use client';

import { useEffect, useMemo, useState } from 'react';
import { MOCK_PLAN } from '@/lib/mocks';
import { getPlan } from '@/lib/api';
import { colorForCustomer } from '@/lib/colors';
import type { PalletAssignment, Plan, StackLayer } from '@/lib/types';

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
  customer_id: number;
  customer_name: string;
  stop_sequence: number;
  isStapleColumn: boolean;
  lines: { ubicacion: string | null; sku: string; description: string; quantity: number; unit: string }[];
  totalCe: number;
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

    const isStaple = pa.customer_ids.length >= 5;
    // Stack is TOP→BOTTOM in the plan. To load bottom-first we walk it
    // in reverse: stack[N-1] is the floor of the pallet.
    for (let i = stack.length - 1; i >= 0; i--) {
      const layer = stack[i];
      const layerIndex = stack.length - 1 - i;  // 0 = bottom
      const customer = customerNameById.get(layer.customer_id) ?? `client #${layer.customer_id}`;
      // Sort lines by Ubicació so the picker walks the warehouse in lex order.
      const sortedLines = [...layer.lines].sort((a, b) =>
        (a.ubicacion ?? '').localeCompare(b.ubicacion ?? ''),
      );
      steps.push({
        slotId,
        layerIndex,
        totalLayers: stack.length,
        customer_id: layer.customer_id,
        customer_name: customer,
        stop_sequence: layer.stop_sequence,
        isStapleColumn: isStaple,
        lines: sortedLines,
        totalCe: layer.ce,
      });
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
  const activeStopIds = useMemo(() => {
    const ids = new Set<number>();
    for (let i = 0; i <= activeStep; i++) {
      if (steps[i]) ids.add(steps[i].customer_id);
    }
    return ids;
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
        {/* Truck diagram (sticky) */}
        <div className="col-span-5 bg-white border border-gray-200 rounded-lg p-3 self-start sticky top-3">
          <h2 className="font-bold text-sm mb-2">Estat del camió</h2>
          <TruckLoadDiagram
            plan={plan}
            currentSlotId={currentStep?.slotId ?? null}
            loadedSlotIds={new Set(steps.slice(0, activeStep + 1).map((s) => s.slotId))}
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
        <div className="col-span-7 flex flex-col gap-2">
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
      {activeStopIds.size > 0 && null /* unused for now, future highlight */}
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
  const colour = colorForCustomer(step.customer_id);
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
              ? `Tota la columna del producte`
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

function TruckLoadDiagram({
  plan,
  currentSlotId,
  loadedSlotIds,
}: {
  plan: Plan;
  currentSlotId: string | null;
  loadedSlotIds: Set<string>;
}) {
  const grid = plan.vehicle;
  const slotPositions: { slotId: string; row: number; col: number }[] = [];
  for (let col = 0; col < grid.grid_cols; col++) {
    for (let row = 0; row < grid.grid_rows; row++) {
      const idx = col * grid.grid_rows + row + 1;
      slotPositions.push({ slotId: `P${idx}`, row, col });
    }
  }

  const W = 480;
  const H = 240;
  const cellW = (W - 80) / grid.grid_cols;
  const cellH = (H - 80) / grid.grid_rows;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded" style={{ background: 'linear-gradient(180deg,#f8fafc 0%,#e2e8f0 100%)' }}>
      <rect x={10} y={20} width={W - 20} height={H - 40} rx={10} fill="#fff" stroke="#1A1A1A" strokeWidth={2} />
      <rect x={10} y={50} width={45} height={H - 100} rx={6} fill="#1A1A1A" />
      <rect x={16} y={58} width={33} height={22} rx={3} fill="#7DD3FC" opacity={0.7} />
      <rect x={60} y={20} width={W - 80} height={5} fill="#E30613" rx={2} />
      <text x={W / 2} y={14} textAnchor="middle" fontSize={9} fill="#475569" fontWeight="bold">CABINA ◄ Sentit de la marxa</text>
      <text x={W - 12} y={H / 2} textAnchor="middle" fontSize={9} fill="#475569" fontWeight="bold" transform={`rotate(90 ${W - 12} ${H / 2})`}>PORTA POSTERIOR</text>

      {slotPositions.map(({ slotId, row, col }) => {
        const x = 65 + col * cellW + 4;
        const y = 38 + row * cellH + 4;
        const w = cellW - 8;
        const h = cellH - 8;
        const pa = plan.pallet_assignments.find((p) => p.slot_id === slotId);
        const customerIds = pa?.customer_ids ?? [];
        const isStaple = customerIds.length >= 5;
        const isLoaded = loadedSlotIds.has(slotId);
        const isCurrent = slotId === currentSlotId;

        let fill: React.ReactNode;
        if (!pa || customerIds.length === 0) {
          fill = <rect x={x} y={y} width={w} height={h} rx={4} fill="#E5E7EB" stroke="#1A1A1A" strokeWidth={1} />;
        } else if (isStaple) {
          const stripeW = w / Math.min(customerIds.length, 8);
          fill = (
            <>
              {customerIds.slice(0, 8).map((cid, i) => (
                <rect
                  key={cid}
                  x={x + i * stripeW}
                  y={y}
                  width={stripeW}
                  height={h}
                  fill={colorForCustomer(cid)}
                  opacity={isLoaded ? 1 : 0.25}
                />
              ))}
              <rect x={x} y={y} width={w} height={h} rx={4} fill="none" stroke={isCurrent ? '#E30613' : '#1A1A1A'} strokeWidth={isCurrent ? 3 : 1.2} />
            </>
          );
        } else {
          const sorted = [...customerIds].sort((a, b) => {
            const sa = plan.stops.find((s) => s.customer_id === a)?.sequence ?? 999;
            const sb = plan.stops.find((s) => s.customer_id === b)?.sequence ?? 999;
            return sa - sb;
          });
          const bandH = h / sorted.length;
          fill = (
            <>
              {sorted.map((cid, i) => (
                <rect
                  key={cid}
                  x={x}
                  y={y + i * bandH}
                  width={w}
                  height={bandH}
                  fill={colorForCustomer(cid)}
                  opacity={isLoaded ? 1 : 0.25}
                />
              ))}
              <rect x={x} y={y} width={w} height={h} rx={4} fill="none" stroke={isCurrent ? '#E30613' : '#1A1A1A'} strokeWidth={isCurrent ? 3 : 1.2} />
            </>
          );
        }

        return (
          <g key={slotId}>
            {fill}
            <text x={x + w / 2} y={y + h / 2 + 4} textAnchor="middle" fontSize={14} fontWeight="bold" fill="#fff" stroke="#1A1A1A" strokeWidth={0.4}>
              {slotId}
            </text>
            {isCurrent && (
              <circle cx={x + w - 8} cy={y + 8} r={5} fill="#E30613">
                <animate attributeName="opacity" values="1;0.3;1" dur="1.2s" repeatCount="indefinite" />
              </circle>
            )}
          </g>
        );
      })}
    </svg>
  );
}
