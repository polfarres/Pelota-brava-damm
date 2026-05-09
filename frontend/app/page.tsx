'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import StopList from '@/components/StopList';
import KpiPanel from '@/components/KpiPanel';
import ExplanationCard from '@/components/ExplanationCard';
import { MOCK_BASELINE, MOCK_PLAN } from '@/lib/mocks';
import { getBaseline } from '@/lib/api';
import type { BaselinePlan } from '@/lib/types';

// Leaflet must not be SSR'd.
const MapView = dynamic(() => import('@/components/MapView'), { ssr: false });

export default function Dashboard() {
  const [baseline, setBaseline] = useState<BaselinePlan>(MOCK_BASELINE);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(1);
  const [apiOk, setApiOk] = useState<'pending' | 'ok' | 'fallback'>('pending');

  // Try to hydrate from real backend; fall back to mock cleanly.
  useEffect(() => {
    let cancelled = false;
    getBaseline('DR0027', '2026-05-08')
      .then((b) => {
        if (!cancelled) {
          setBaseline(b);
          setApiOk('ok');
        }
      })
      .catch(() => {
        if (!cancelled) setApiOk('fallback');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The dashboard always shows the optimised stops on the map (FR-013).
  const plan = MOCK_PLAN;
  const selectedStop = useMemo(
    () => plan.stops.find((s) => s.sequence === selectedSeq) ?? null,
    [plan.stops, selectedSeq],
  );

  return (
    <div className="grid grid-cols-12 gap-3 p-3" style={{ height: 'calc(100vh - 56px)' }}>
      {/* Left column: stop list */}
      <aside className="col-span-3 bg-white rounded-lg border border-gray-200 p-3 overflow-y-auto">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold uppercase tracking-wide text-gray-500">
            Paradas optimizadas
          </h2>
          <span
            className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
              apiOk === 'ok'
                ? 'bg-green-100 text-green-700'
                : apiOk === 'fallback'
                  ? 'bg-yellow-100 text-yellow-700'
                  : 'bg-gray-100 text-gray-500'
            }`}
          >
            {apiOk === 'ok' ? 'API conectada' : apiOk === 'fallback' ? 'Mock data' : 'Cargando…'}
          </span>
        </div>
        <StopList
          stops={plan.stops}
          selectedSeq={selectedSeq}
          onSelect={setSelectedSeq}
        />
      </aside>

      {/* Centre: map */}
      <section className="col-span-6 rounded-lg border border-gray-200 overflow-hidden">
        <MapView
          stops={plan.stops}
          selectedSeq={selectedSeq}
          onSelect={setSelectedSeq}
        />
      </section>

      {/* Right column: KPI + explanation */}
      <aside className="col-span-3 flex flex-col gap-3 overflow-y-auto">
        <KpiPanel delta={plan.kpi_delta} />
        <ExplanationCard stop={selectedStop} />
      </aside>
    </div>
  );
}
