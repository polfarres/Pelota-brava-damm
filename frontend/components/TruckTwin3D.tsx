'use client';

// 2D top-down SVG implementation of the truck pallet grid.
// (We chose the SVG fallback over react-three-fiber to stay within the time-box;
// the FR-015 spec explicitly allows this fallback when r3f gives trouble.)

import { useState } from 'react';
import type { Plan } from '@/lib/types';
import { CLUSTER_COLORS } from '@/lib/mocks';

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

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full bg-gray-50 rounded">
        {/* Truck silhouette */}
        <rect
          x={20}
          y={30}
          width={W - 40}
          height={H - 60}
          rx={8}
          fill="#fff"
          stroke="#1A1A1A"
          strokeWidth={2}
        />
        {/* Cabin */}
        <rect
          x={20}
          y={60}
          width={50}
          height={H - 120}
          fill="#1A1A1A"
          opacity={0.1}
        />
        <text x={45} y={H / 2} textAnchor="middle" fontSize={10} fill="#666">
          CABINA
        </text>
        {/* Curtain labels */}
        <text x={W / 2} y={20} textAnchor="middle" fontSize={11} fill="#666">
          ↑ Cortina esquerra ↑
        </text>
        <text x={W / 2} y={H - 5} textAnchor="middle" fontSize={11} fill="#666">
          ↓ Cortina dreta ↓
        </text>
        <text x={W - 15} y={H / 2} textAnchor="middle" fontSize={10} fill="#666" transform={`rotate(90 ${W - 15} ${H / 2})`}>
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
          const primaryCustomerId = pa?.customer_ids[0];
          const fillColour =
            state === 'envase'
              ? '#9E9E9E'
              : primaryCustomerId
                ? CLUSTER_COLORS[primaryCustomerId] || '#999'
                : '#ddd';
          const opacity =
            state === 'delivered' ? 0.2 : state === 'partial' ? 0.55 : 1;
          const stroke =
            state === 'next' ? '#E30613' : '#1A1A1A';
          const strokeWidth = state === 'next' ? 3 : 1;

          return (
            <g key={slotId}>
              <rect
                x={x}
                y={y}
                width={w}
                height={h}
                rx={4}
                fill={fillColour}
                opacity={opacity}
                stroke={stroke}
                strokeWidth={strokeWidth}
              />
              <text
                x={x + w / 2}
                y={y + h / 2 - 6}
                textAnchor="middle"
                fontSize={16}
                fontWeight="bold"
                fill="#fff"
                opacity={opacity}
              >
                {slotId}
              </text>
              <text
                x={x + w / 2}
                y={y + h / 2 + 12}
                textAnchor="middle"
                fontSize={10}
                fill="#fff"
                opacity={opacity}
              >
                {state === 'envase'
                  ? '↺ envasos'
                  : state === 'delivered'
                    ? '✓ lliurat'
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
