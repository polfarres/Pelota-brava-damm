'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import StopList from '@/components/StopList';
import ExplanationCard from '@/components/ExplanationCard';
import { MOCK_PLAN } from '@/lib/mocks';
import { getPlan } from '@/lib/api';
import type { Plan } from '@/lib/types';

const RUN_ID = 'DR0027-2026-03-30';

// Leaflet must not be SSR'd.
const MapView = dynamic(() => import('@/components/MapView'), { ssr: false });

export default function Dashboard() {
  const [plan, setPlan] = useState<Plan>(MOCK_PLAN);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(1);
  const [apiOk, setApiOk] = useState<'pending' | 'ok' | 'fallback'>('pending');

  useEffect(() => {
    let cancelled = false;
    getPlan(RUN_ID)
      .then((p) => {
        if (!cancelled) {
          setPlan(p);
          setApiOk('ok');
          setSelectedSeq(p.stops[0]?.sequence ?? 1);
        }
      })
      .catch(() => {
        if (!cancelled) setApiOk('fallback');
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
            Parades optimitzades
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
            {apiOk === 'ok' ? 'API connectada' : apiOk === 'fallback' ? 'Dades de prova' : 'Carregant…'}
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
          runId={apiOk === 'ok' ? RUN_ID : undefined}
        />
      </section>

      {/* Right column: explanation */}
      <aside className="col-span-3 flex flex-col gap-3 overflow-y-auto">
        <ExplanationCard stop={selectedStop} />
      </aside>
    </div>
  );
}
