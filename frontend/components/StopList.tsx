'use client';

import type { StopPlan } from '@/lib/types';
import { CLUSTER_COLORS } from '@/lib/mocks';

function formatEta(eta: string): string {
  // Backend serialises `time` as "HH:MM:SS"; an ISO datetime also works.
  if (/^\d{2}:\d{2}/.test(eta)) return eta.slice(0, 5);
  const d = new Date(eta);
  return isNaN(d.getTime())
    ? eta
    : d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
}

interface Props {
  stops: StopPlan[];
  selectedSeq: number | null;
  onSelect: (seq: number) => void;
}

export default function StopList({ stops, selectedSeq, onSelect }: Props) {
  return (
    <div className="flex flex-col gap-2 overflow-y-auto pr-1">
      {stops.map((s) => {
        const colour = CLUSTER_COLORS[s.customer_id] || '#666';
        const selected = selectedSeq === s.sequence;
        return (
          <button
            key={s.sequence}
            onClick={() => onSelect(s.sequence)}
            className={`text-left rounded-lg p-3 border transition-all ${
              selected
                ? 'border-damm-red bg-white shadow-md'
                : 'border-gray-200 bg-white hover:border-gray-400'
            }`}
          >
            <div className="flex items-start gap-3">
              <div
                className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold"
                style={{ backgroundColor: colour }}
              >
                {s.sequence}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm truncate">{s.customer_name}</div>
                <div className="text-xs text-gray-600 truncate">
                  {s.address}{s.city ? `, ${s.city}` : ''}
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs">
                  {s.eta && (
                    <span className="text-gray-700">
                      {formatEta(s.eta)}
                    </span>
                  )}
                  {s.time_window_start ? (
                    <span className="text-gray-500">
                      [{s.time_window_start}–{s.time_window_end}]
                    </span>
                  ) : (
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-gray-100 text-gray-500"
                      title="Sense finestra horària a Horarios Entrega.XLSX"
                    >
                      Obert
                    </span>
                  )}
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                      s.payment_condition === 'CONTADO'
                        ? 'bg-yellow-200 text-yellow-900'
                        : 'bg-gray-200 text-gray-700'
                    }`}
                  >
                    {s.payment_condition}
                  </span>
                  {s.pallet_slots && s.pallet_slots.length > 0 && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-damm-red text-white">
                      {s.pallet_slots.join(' · ')}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
