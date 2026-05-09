'use client';

import { useEffect, useMemo, useState } from 'react';
import { MOCK_PLAN } from '@/lib/mocks';
import { getPlan } from '@/lib/api';
import { colorForCustomer, colorForSku } from '@/lib/colors';
import type { Plan, StopPlan, DeliveryLine } from '@/lib/types';
import { formatEta } from '@/lib/time';

const RUN_ID = 'DR0027-2026-05-08';

interface AggregatedLine {
  sku: string;
  description: string;
  unit: string;
  quantity: number;
  ce: number;
}

function aggregateLines(lines: DeliveryLine[]): AggregatedLine[] {
  // Same trick as the loading page: the v2 packer emits one line per
  // (customer, SKU) per layer, so a single bottle order can show up
  // as many fractional rows. Sum + round before showing the driver.
  const map = new Map<string, AggregatedLine>();
  for (const l of lines) {
    const key = `${l.sku}::${l.unit}`;
    const existing = map.get(key);
    const ce = (l.ce ?? 1) * l.quantity;
    if (existing) {
      existing.quantity += l.quantity;
      existing.ce += ce;
    } else {
      map.set(key, {
        sku: l.sku,
        description: l.description,
        unit: l.unit,
        quantity: l.quantity,
        ce,
      });
    }
  }
  return [...map.values()]
    .map((l) => ({ ...l, quantity: Math.round(l.quantity), ce: Math.round(l.ce) }))
    .filter((l) => l.quantity > 0)
    .sort((a, b) => b.ce - a.ce);
}

export default function DriverPage() {
  const [plan, setPlan] = useState<Plan>(MOCK_PLAN);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [completed, setCompleted] = useState<Set<number>>(new Set());
  const [apiOk, setApiOk] = useState<'pending' | 'ok' | 'fallback'>('pending');

  useEffect(() => {
    let cancelled = false;
    getPlan(RUN_ID)
      .then((p) => {
        if (!cancelled) {
          setPlan(p);
          setApiOk('ok');
          setCurrentIdx(0);
          setCompleted(new Set());
        }
      })
      .catch(() => !cancelled && setApiOk('fallback'));
    return () => {
      cancelled = true;
    };
  }, []);

  const stops = plan.stops;
  const total = stops.length;
  const currentStop = stops[currentIdx] ?? stops[0];
  const isCurrentDone = completed.has(currentStop?.sequence ?? -1);
  const allDone = completed.size === total && total > 0;

  function confirmDelivery() {
    if (!currentStop) return;
    const next = new Set(completed);
    next.add(currentStop.sequence);
    setCompleted(next);
    // Auto-advance to the first not-yet-done stop ahead of us.
    const nextIdx = findNextOpen(stops, completed, currentStop.sequence, currentIdx);
    if (nextIdx >= 0) setCurrentIdx(nextIdx);
  }

  function gotoPrev() {
    setCurrentIdx((i) => Math.max(0, i - 1));
  }

  function gotoNext() {
    setCurrentIdx((i) => Math.min(total - 1, i + 1));
  }

  function reset() {
    setCompleted(new Set());
    setCurrentIdx(0);
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h1 className="text-2xl font-bold">Aplicació Conductor · {plan.ruta}</h1>
          <p className="text-sm text-gray-600 mt-1">
            Vehicle <span className="font-mono">{plan.vehicle.license_plate || '—'}</span> ·
            {' '}{total} parades · {Math.round((completed.size / Math.max(1, total)) * 100)}% completat
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

      {/* Progress bar */}
      <div className="w-full bg-gray-200 rounded-full h-2 mb-4 overflow-hidden">
        <div
          className="bg-damm-red h-2 transition-all duration-300"
          style={{ width: `${(completed.size / Math.max(1, total)) * 100}%` }}
        />
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Phone — main interaction */}
        <div className="col-span-7 flex flex-col items-center">
          {currentStop ? (
            <>
              <Phone>
                <DriverScreen
                  stop={currentStop}
                  isDone={isCurrentDone}
                  totalStops={total}
                  allDone={allDone}
                  onConfirm={confirmDelivery}
                />
              </Phone>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={gotoPrev}
                  disabled={currentIdx === 0}
                  className="text-sm bg-damm-dark text-white px-4 py-2 rounded disabled:opacity-40"
                >
                  ← Anterior
                </button>
                <button
                  onClick={gotoNext}
                  disabled={currentIdx >= total - 1}
                  className="text-sm bg-damm-dark text-white px-4 py-2 rounded disabled:opacity-40"
                >
                  Següent →
                </button>
                <button
                  onClick={reset}
                  className="text-sm bg-gray-200 text-gray-700 px-4 py-2 rounded ml-2"
                  title="Reinicia: cap parada feta"
                >
                  ⟲ Reinicia
                </button>
              </div>
            </>
          ) : (
            <div className="text-gray-500 italic">Carregant pla…</div>
          )}
        </div>

        {/* Stop list — side panel */}
        <div className="col-span-5">
          <h2 className="font-bold text-sm uppercase text-gray-500 mb-2">Totes les parades</h2>
          <div className="flex flex-col gap-1.5 max-h-[640px] overflow-y-auto pr-1">
            {stops.map((s, i) => (
              <StopRow
                key={s.sequence}
                stop={s}
                done={completed.has(s.sequence)}
                active={i === currentIdx}
                onClick={() => setCurrentIdx(i)}
              />
            ))}
          </div>
          {allDone && (
            <div className="mt-3 p-3 bg-green-100 border border-green-300 text-green-800 rounded text-sm font-bold text-center">
              ✓ Ruta completada · {total} / {total} parades
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function findNextOpen(
  stops: StopPlan[],
  completed: Set<number>,
  justDoneSeq: number,
  fromIdx: number,
): number {
  // Look forward first, then wrap to start. Skip the just-marked one.
  const justDone = new Set(completed);
  justDone.add(justDoneSeq);
  for (let i = fromIdx + 1; i < stops.length; i++) {
    if (!justDone.has(stops[i].sequence)) return i;
  }
  for (let i = 0; i < fromIdx; i++) {
    if (!justDone.has(stops[i].sequence)) return i;
  }
  return -1;
}

function Phone({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="bg-white rounded-3xl shadow-2xl border-8 border-damm-dark overflow-hidden"
      style={{ width: 380, height: 700 }}
    >
      <div className="h-full flex flex-col">{children}</div>
    </div>
  );
}

function DriverScreen({
  stop,
  isDone,
  totalStops,
  allDone,
  onConfirm,
}: {
  stop: StopPlan;
  isDone: boolean;
  totalStops: number;
  allDone: boolean;
  onConfirm: () => void;
}) {
  const colour = colorForCustomer(stop.customer_id);
  const aggregated = useMemo(() => aggregateLines(stop.delivery_lines), [stop.delivery_lines]);
  const cashTotal = stop.cash_total ?? stop.proforma_total ?? 0;

  return (
    <>
      {/* Header with cluster colour */}
      <div className="px-4 py-3 text-white relative" style={{ backgroundColor: colour }}>
        <div className="flex items-center justify-between text-xs uppercase opacity-80">
          <span>Parada {stop.sequence} de {totalStops}</span>
          {isDone && (
            <span className="bg-white text-green-700 px-2 py-0.5 rounded font-bold">
              ✓ Lliurada
            </span>
          )}
        </div>
        <div className="text-lg font-bold mt-1 leading-tight">{stop.customer_name}</div>
        <div className="text-xs opacity-90 mt-0.5">
          {stop.address}{stop.city ? `, ${stop.city}` : ''}
        </div>
      </div>

      {/* Body — scrollable */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 text-sm">
        {/* ETA & window */}
        <div className="grid grid-cols-2 gap-2">
          <Pill label="ETA" value={stop.eta ? formatEta(stop.eta) : '—'} accent={colour} />
          {stop.time_window_start ? (
            <Pill
              label="Finestra"
              value={`${stop.time_window_start}–${stop.time_window_end ?? '—'}`}
              accent="#16a34a"
            />
          ) : (
            <Pill label="Finestra" value="Obert" accent="#9CA3AF" />
          )}
        </div>

        {/* Cash collection */}
        {stop.payment_condition === 'CONTADO' && (
          <div className="bg-yellow-100 border-2 border-yellow-300 rounded-lg p-3">
            <div className="text-xs uppercase font-bold text-yellow-900">💰 Cobrament en metàl·lic</div>
            <div className="text-2xl font-bold text-yellow-900 mt-0.5">
              {Number(cashTotal).toFixed(2)} €
            </div>
          </div>
        )}

        {/* Action: which curtain + which slot */}
        <div className="bg-damm-red text-white rounded-lg p-3 text-center">
          <div className="text-xs uppercase opacity-80">Acció al camió</div>
          <div className="text-base font-bold mt-1">
            Obrir cortina <span className="capitalize">{stop.curtain_side ?? '— qualsevol'}</span>
          </div>
          <div className="text-2xl font-bold mt-1">
            Palet {stop.pallet_slots && stop.pallet_slots.length > 0
              ? stop.pallet_slots.join(' · ')
              : '—'}
          </div>
        </div>

        {/* Delivery lines */}
        <div>
          <div className="flex items-center justify-between text-xs uppercase font-bold text-gray-500 mb-1">
            <span>Lliurar</span>
            <span>{aggregated.length} línies</span>
          </div>
          {aggregated.length === 0 ? (
            <div className="text-xs text-gray-400 italic px-2 py-1">Sense ítems atribuïts.</div>
          ) : (
            <ul className="space-y-1">
              {aggregated.map((l) => (
                <li
                  key={l.sku}
                  className="flex items-center bg-green-50 border-l-4 px-2 py-1.5 rounded-r"
                  style={{ borderColor: colorForSku(l.sku) }}
                >
                  <span
                    className="inline-block w-3 h-3 rounded-sm flex-shrink-0"
                    style={{ backgroundColor: colorForSku(l.sku) }}
                  />
                  <div className="flex-1 ml-2 min-w-0">
                    <div className="font-mono text-[10px] text-gray-500">{l.sku}</div>
                    <div className="text-xs truncate">{l.description}</div>
                  </div>
                  <div className="text-right ml-2 flex-shrink-0">
                    <div className="font-bold text-sm">{l.quantity} {l.unit}</div>
                    <div className="text-[10px] text-gray-500">{l.ce} CE</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Pickup envases (placeholder for future v3 albarán parsing) */}
        {stop.pickup_envases && stop.pickup_envases.length > 0 && (
          <div>
            <div className="text-xs uppercase font-bold text-gray-500 mb-1">Recollir envasos</div>
            <ul className="space-y-1">
              {stop.pickup_envases.map((l, i) => (
                <li key={i} className="flex justify-between bg-blue-50 border-l-4 border-blue-400 px-2 py-1 rounded-r">
                  <span className="truncate text-xs">↺ {l.description}</span>
                  <span className="ml-2 font-bold text-xs">{l.quantity} {l.unit}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Confirm button — sticky at bottom */}
      <div className="px-4 py-3 border-t border-gray-200 bg-white">
        {isDone ? (
          <div className="bg-green-100 text-green-800 text-center py-3 rounded-lg font-bold">
            ✓ Lliurament confirmat
          </div>
        ) : allDone ? (
          <div className="bg-gray-100 text-gray-600 text-center py-3 rounded-lg font-bold">
            Ruta completada
          </div>
        ) : (
          <button
            onClick={onConfirm}
            className="w-full bg-damm-red hover:bg-red-700 transition-colors text-white py-3 rounded-lg font-bold text-base"
          >
            Confirmar lliurament →
          </button>
        )}
      </div>
    </>
  );
}

function Pill({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-2 text-center">
      <div className="text-[10px] uppercase text-gray-500">{label}</div>
      <div className="font-bold text-sm" style={{ color: accent }}>{value}</div>
    </div>
  );
}

function StopRow({
  stop,
  done,
  active,
  onClick,
}: {
  stop: StopPlan;
  done: boolean;
  active: boolean;
  onClick: () => void;
}) {
  const colour = colorForCustomer(stop.customer_id);
  return (
    <button
      onClick={onClick}
      className={`text-left rounded-lg p-2.5 border transition-all flex items-center gap-2.5 ${
        active
          ? 'border-damm-red bg-white shadow-md'
          : done
            ? 'border-gray-200 bg-gray-50 opacity-70'
            : 'border-gray-200 bg-white hover:border-gray-400'
      }`}
    >
      <div
        className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold"
        style={{ backgroundColor: done ? '#16a34a' : colour }}
      >
        {done ? '✓' : stop.sequence}
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-semibold text-xs truncate">{stop.customer_name}</div>
        <div className="text-[10px] text-gray-500 truncate">
          {stop.address}{stop.city ? `, ${stop.city}` : ''}
        </div>
      </div>
      <div className="flex flex-col items-end text-[10px] gap-0.5">
        {stop.eta && (
          <span className="font-mono text-gray-600">{formatEta(stop.eta)}</span>
        )}
        {stop.payment_condition === 'CONTADO' && (
          <span className="bg-yellow-200 text-yellow-900 px-1 rounded font-bold">€</span>
        )}
        {stop.pallet_slots && stop.pallet_slots.length > 0 && (
          <span className="bg-damm-red text-white px-1 rounded font-mono">
            {stop.pallet_slots.join(' ')}
          </span>
        )}
      </div>
    </button>
  );
}
