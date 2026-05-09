'use client';

// 2D top-down SVG implementation of the truck pallet grid.
// (We chose the SVG fallback over react-three-fiber to stay within the time-box;
// the FR-015 spec explicitly allows this fallback when r3f gives trouble.)

import { useState } from 'react';
import type { Plan } from '@/lib/types';
import { colorForCustomer } from '@/lib/colors';

interface Props {
  plan: Plan;
}

export default function TruckTwin3D({ plan }: Props) {
  const [stopIdx, setStopIdx] = useState(0); // 0 = "before first delivery"
  const totalStops = plan.stops.length;

  // For each pallet, compute whether it's been delivered yet (sequence < stopIdx),
  // is about to be delivered (sequence == stopIdx), or future (> stopIdx).
  const palletState = (slotId: string) => {
    const pa = plan.pallet_assignments.find((p) => p.slot_id === slotId);
    if (!pa) return { state: 'empty' as const, customerSeqs: [] as number[] };
    if (pa.is_envase_zone) return { state: 'envase' as const, customerSeqs: [] };
    const seqs = pa.customer_ids
      .map(
        (cid) =>
          plan.stops.find((s) => s.customer_id === cid)?.sequence ?? 999,
      )
      .sort((a, b) => a - b);
    const minSeq = seqs[0] ?? 999;
    const maxSeq = seqs[seqs.length - 1] ?? 999;
    if (stopIdx >= maxSeq) return { state: 'delivered' as const, customerSeqs: seqs };
    if (stopIdx >= minSeq && stopIdx < maxSeq)
      return { state: 'partial' as const, customerSeqs: seqs };
    if (stopIdx + 1 === minSeq)
      return { state: 'next' as const, customerSeqs: seqs };
    return { state: 'loaded' as const, customerSeqs: seqs };
  };

  const grid = plan.vehicle; // grid_rows x grid_cols
  // Slot layout for a 6p truck: P1 P3 P5 / P2 P4 P6 (front → rear)
  const slotPositions: { slotId: string; row: number; col: number }[] = [];
  for (let col = 0; col < grid.grid_cols; col++) {
    for (let row = 0; row < grid.grid_rows; row++) {
      const idx = col * grid.grid_rows + row + 1;
      slotPositions.push({ slotId: `P${idx}`, row, col });
    }
  }

  const W = 600;
  const H = 320;
  const cellW = (W - 80) / grid.grid_cols;
  const cellH = (H - 100) / grid.grid_rows;

  const currentStop = stopIdx >= 1 && stopIdx <= totalStops ? plan.stops[stopIdx - 1] : null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex justify-between items-center mb-3">
        <div>
          <h2 className="font-bold text-lg">Camió · {plan.vehicle.license_plate}</h2>
          <div className="text-xs text-gray-500">
            {plan.vehicle.profile_name} · {plan.vehicle.capacity_pallets} palets
          </div>
        </div>
        <div className="text-right text-sm">
          <div className="text-gray-500">Parada</div>
          <div className="text-2xl font-bold">
            {stopIdx} <span className="text-base text-gray-400">/ {totalStops}</span>
          </div>
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded" style={{ background: 'linear-gradient(180deg,#f8fafc 0%,#e2e8f0 100%)' }}>
        {/* Truck body */}
        <rect
          x={20}
          y={30}
          width={W - 40}
          height={H - 60}
          rx={10}
          fill="#fff"
          stroke="#1A1A1A"
          strokeWidth={2}
        />
        {/* Cabin */}
        <rect x={20} y={60} width={50} height={H - 120} rx={6} fill="#1A1A1A" />
        <rect x={26} y={68} width={38} height={28} rx={3} fill="#7DD3FC" opacity={0.7} />
        <text x={45} y={H / 2 + 30} textAnchor="middle" fontSize={9} fill="#fff" fontWeight="bold">
          CABINA
        </text>
        {/* DAMM red roof stripe */}
        <rect x={70} y={30} width={W - 90} height={6} fill="#E30613" rx={2} />
        {/* Curtain labels */}
        <text x={W / 2} y={20} textAnchor="middle" fontSize={11} fill="#475569" fontWeight="bold">
          ⇧ Cortina esquerra ⇧
        </text>
        <text x={W / 2} y={H - 5} textAnchor="middle" fontSize={11} fill="#475569" fontWeight="bold">
          ⇩ Cortina dreta ⇩
        </text>
        <text x={W - 15} y={H / 2} textAnchor="middle" fontSize={10} fill="#475569" fontWeight="bold" transform={`rotate(90 ${W - 15} ${H / 2})`}>
          PORTA POSTERIOR
        </text>

        {/* Pallets */}
        {slotPositions.map(({ slotId, row, col }) => {
          const x = 80 + col * cellW + 5;
          const y = 50 + row * cellH + 5;
          const w = cellW - 10;
          const h = cellH - 10;
          const { state, customerSeqs } = palletState(slotId);
          const pa = plan.pallet_assignments.find((p) => p.slot_id === slotId);
          const customerIds = pa?.customer_ids ?? [];
          const isStaple = customerIds.length >= 5;  // staple column spans most/all stops

          const opacity =
            state === 'delivered' ? 0.25 : state === 'partial' ? 0.7 : 1;
          const stroke =
            state === 'next' ? '#E30613' : '#1A1A1A';
          const strokeWidth = state === 'next' ? 3 : 1.2;

          // Staple pallet → striped gradient. Multi-stop pallet → split into
          // horizontal bands by customer (each delivered first emptier).
          let palletFill: React.ReactNode = null;
          if (state === 'envase') {
            palletFill = (
              <rect x={x} y={y} width={w} height={h} rx={4} fill="#94A3B8" opacity={opacity} />
            );
          } else if (isStaple) {
            // Vertical stripes — one stripe per customer to signal "shared column".
            const stripeW = w / Math.min(customerIds.length, 8);
            palletFill = (
              <>
                {customerIds.slice(0, 8).map((cid, i) => (
                  <rect
                    key={cid}
                    x={x + i * stripeW}
                    y={y}
                    width={stripeW}
                    height={h}
                    fill={colorForCustomer(cid)}
                    opacity={opacity}
                  />
                ))}
                <rect x={x} y={y} width={w} height={h} rx={4} fill="none" stroke={stroke} strokeWidth={strokeWidth} />
              </>
            );
          } else if (customerIds.length === 0) {
            palletFill = (
              <rect x={x} y={y} width={w} height={h} rx={4} fill="#E5E7EB" stroke={stroke} strokeWidth={strokeWidth} />
            );
          } else {
            // Horizontal bands: one row per customer (top = first delivered).
            const sortedCids = [...customerIds].sort((a, b) => {
              const sa = plan.stops.find((s) => s.customer_id === a)?.sequence ?? 999;
              const sb = plan.stops.find((s) => s.customer_id === b)?.sequence ?? 999;
              return sa - sb;
            });
            const bandH = h / sortedCids.length;
            palletFill = (
              <>
                {sortedCids.map((cid, i) => {
                  const cseq = plan.stops.find((s) => s.customer_id === cid)?.sequence ?? 999;
                  const bandOpacity =
                    state === 'partial' && cseq <= stopIdx ? 0.25 : opacity;
                  return (
                    <rect
                      key={cid}
                      x={x}
                      y={y + i * bandH}
                      width={w}
                      height={bandH}
                      fill={colorForCustomer(cid)}
                      opacity={bandOpacity}
                    />
                  );
                })}
                <rect x={x} y={y} width={w} height={h} rx={4} fill="none" stroke={stroke} strokeWidth={strokeWidth} />
              </>
            );
          }

          return (
            <g key={slotId}>
              {palletFill}
              <text
                x={x + w / 2}
                y={y + h / 2 - 6}
                textAnchor="middle"
                fontSize={16}
                fontWeight="bold"
                fill="#fff"
                stroke="#1A1A1A"
                strokeWidth={0.4}
                opacity={opacity}
              >
                {slotId}
              </text>
              <text
                x={x + w / 2}
                y={y + h / 2 + 12}
                textAnchor="middle"
                fontSize={9}
                fill="#fff"
                stroke="#1A1A1A"
                strokeWidth={0.3}
                fontWeight="bold"
                opacity={opacity}
              >
                {state === 'envase'
                  ? '↺ envasos'
                  : state === 'delivered'
                    ? '✓ lliurat'
                    : isStaple
                      ? '★ staple'
                      : `parada ${customerSeqs.join(',')}`}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="mt-4">
        <input
          type="range"
          min={0}
          max={totalStops}
          value={stopIdx}
          onChange={(e) => setStopIdx(Number(e.target.value))}
          className="w-full accent-damm-red"
        />
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>Sortida</span>
          {plan.stops.map((s) => (
            <span key={s.sequence}>{s.sequence}</span>
          ))}
        </div>
      </div>

      {currentStop && (
        <div className="mt-3 p-3 bg-gray-50 rounded text-sm">
          <div className="font-bold">
            #{currentStop.sequence} {currentStop.customer_name}
          </div>
          <div className="text-xs text-gray-600">
            {currentStop.address}{currentStop.city ? `, ${currentStop.city}` : ''}
          </div>
          {currentStop.pallet_slots && (
            <div className="mt-1 text-xs">
              Obrir cortina <strong>{currentStop.curtain_side}</strong>, palet{' '}
              <strong>{currentStop.pallet_slots.join(', ')}</strong>.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
