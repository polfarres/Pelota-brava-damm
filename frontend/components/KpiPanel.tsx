'use client';

import type { KpiDelta } from '@/lib/types';

interface Props {
  delta: KpiDelta;
}

const METRIC_LABELS: Record<string, { label: string; unit: string; lowerIsBetter: boolean }> = {
  total_km: { label: 'Distància total', unit: 'km', lowerIsBetter: true },
  total_minutes: { label: 'Temps total', unit: 'min', lowerIsBetter: true },
  unload_minutes_estimated: { label: 'Temps de descàrrega', unit: 'min', lowerIsBetter: true },
  in_truck_searches: { label: 'Cerques al camió', unit: '', lowerIsBetter: true },
  space_utilisation_pct: { label: "Ús de l'espai", unit: '%', lowerIsBetter: false },
};

export default function KpiPanel({ delta }: Props) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h2 className="text-sm font-bold uppercase tracking-wide text-gray-500 mb-3">
        KPIs · As-is vs Smart
      </h2>
      <div className="space-y-3">
        {delta.improvements.map((imp) => {
          const meta = METRIC_LABELS[imp.metric] || {
            label: imp.metric,
            unit: '',
            lowerIsBetter: true,
          };
          const baseline = (delta.baseline as any)[imp.metric];
          const optimised = (delta.optimised as any)[imp.metric];
          const arrow = imp.is_improvement ? '↓' : '↑';
          const colour = imp.is_improvement ? 'text-green-600' : 'text-red-600';
          // Reverse arrow if higher-is-better metric
          const displayArrow = meta.lowerIsBetter
            ? imp.delta < 0 ? '↓' : '↑'
            : imp.delta > 0 ? '↑' : '↓';
          return (
            <div
              key={imp.metric}
              className={`p-3 rounded border ${
                imp.is_improvement ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
              }`}
            >
              <div className="text-xs text-gray-600">{meta.label}</div>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-sm text-gray-500 line-through">
                  {fmt(baseline)} {meta.unit}
                </span>
                <span className="text-lg font-bold">
                  {fmt(optimised)} {meta.unit}
                </span>
                <span className={`text-sm font-bold ${colour}`}>
                  {displayArrow} {Math.abs(imp.delta_pct).toFixed(1)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function fmt(n: number): string {
  return Number.isInteger(n) ? `${n}` : n.toFixed(1);
}
