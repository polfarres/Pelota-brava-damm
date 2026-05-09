'use client';

import type { StopPlan } from '@/lib/types';

interface Props {
  stop: StopPlan | null;
}

export default function ExplanationCard({ stop }: Props) {
  if (!stop) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <p className="text-sm text-gray-500 italic">
          Selecciona una parada per veure&apos;n l&apos;explicació.
        </p>
      </div>
    );
  }
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-block w-7 h-7 rounded-full bg-damm-red text-white text-xs font-bold flex items-center justify-center">
          {stop.sequence}
        </span>
        <h3 className="font-bold">{stop.customer_name}</h3>
      </div>
      <div className="text-xs text-gray-600 mb-3">
        {stop.address}{stop.city ? `, ${stop.city}` : ''}
      </div>

      {stop.pallet_slots && stop.pallet_slots.length > 0 && (
        <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
          <div className="bg-gray-100 rounded p-2">
            <div className="text-gray-500">Palet</div>
            <div className="font-bold text-base">{stop.pallet_slots.join(', ')}</div>
          </div>
          <div className="bg-gray-100 rounded p-2">
            <div className="text-gray-500">Cortina</div>
            <div className="font-bold text-base capitalize">{stop.curtain_side}</div>
          </div>
        </div>
      )}

      <div className="text-xs text-gray-500 uppercase font-bold mb-1">Per què</div>
      <p className="text-sm text-gray-800 leading-relaxed">
        {stop.explanation || 'Sense explicació generada.'}
      </p>

      <div className="mt-3 pt-3 border-t border-gray-100">
        <div className="text-xs text-gray-500 uppercase font-bold mb-1">
          Línies a lliurar ({stop.delivery_lines.length})
        </div>
        <ul className="text-xs space-y-1">
          {stop.delivery_lines.map((l, i) => (
            <li key={i} className="flex justify-between">
              <span className="truncate">{l.description}</span>
              <span className="text-gray-600 ml-2 flex-shrink-0">
                {l.quantity} {l.unit}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
