'use client';

import { useEffect, useState } from 'react';
import PickListTable from '@/components/PickListTable';
import { MOCK_BASELINE, MOCK_PLAN } from '@/lib/mocks';
import { getBaseline, getPlan, hojaCargaPdfUrl } from '@/lib/api';
import type { BaselinePlan, Plan } from '@/lib/types';

const RUN_ID = 'DR0027-2026-05-08';

export default function PickListPage() {
  const [mode, setMode] = useState<'original' | 'smart'>('smart');
  const [plan, setPlan] = useState<Plan>(MOCK_PLAN);
  const [baseline, setBaseline] = useState<BaselinePlan>(MOCK_BASELINE);

  useEffect(() => {
    let cancelled = false;
    getBaseline('DR0027', '2026-05-08')
      .then((b) => !cancelled && setBaseline(b))
      .catch(() => {});
    getPlan(RUN_ID)
      .then((p) => !cancelled && setPlan(p))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const data = mode === 'smart' ? plan : baseline;
  const runId = `${plan.ruta}-${plan.fecha}`;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">Hoja de Carga · DR0027 · 2026-05-08</h1>
          <p className="text-sm text-gray-600 mt-1">
            La columna <code className="bg-gray-200 px-1 rounded">Descarga</code> sale en blanco
            del SAP. Smart Truck la rellena con el slot del camión por línea.
          </p>
        </div>
        <a
          href={hojaCargaPdfUrl(runId)}
          target="_blank"
          rel="noreferrer"
          className="text-sm bg-damm-dark text-white px-3 py-2 rounded hover:bg-damm-red transition-colors"
        >
          Descargar PDF
        </a>
      </div>

      {/* Toggle */}
      <div className="inline-flex rounded-lg border border-gray-300 bg-white overflow-hidden mb-4">
        <button
          onClick={() => setMode('original')}
          className={`px-4 py-2 text-sm font-semibold ${
            mode === 'original'
              ? 'bg-damm-dark text-white'
              : 'text-gray-600 hover:bg-gray-50'
          }`}
        >
          Original (DDIDGP)
        </button>
        <button
          onClick={() => setMode('smart')}
          className={`px-4 py-2 text-sm font-semibold ${
            mode === 'smart'
              ? 'bg-damm-red text-white'
              : 'text-gray-600 hover:bg-gray-50'
          }`}
        >
          Smart
        </button>
      </div>

      <PickListTable plan={data} mode={mode} />

      <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-sm">
        <strong>Pitch tip:</strong> al alternar entre <em>Original</em> y <em>Smart</em>, la
        columna Descarga pasa de estar vacía a indicar el pallet (P1…P6) donde cada línea está
        cargada. Los colores agrupan los productos por cliente.
      </div>
    </div>
  );
}
