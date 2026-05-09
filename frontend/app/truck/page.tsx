'use client';

import { useEffect, useState } from 'react';
import TruckTwin3D from '@/components/TruckTwin3D';
import { MOCK_PLAN, CLUSTER_COLORS } from '@/lib/mocks';
import { getPlan } from '@/lib/api';
import type { Plan } from '@/lib/types';

const RUN_ID = 'DR0027-2026-05-08';

export default function TruckPage() {
  const [plan, setPlan] = useState<Plan>(MOCK_PLAN);
  useEffect(() => {
    let cancelled = false;
    getPlan(RUN_ID)
      .then((p) => !cancelled && setPlan(p))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Camió · DR0027</h1>
      <p className="text-sm text-gray-600 mb-4">
        Visualització de l&apos;estat del camió al llarg de la ruta. Mou el control per veure com
        es descarreguen els palets i s&apos;alliberen slots per a envasos buits.
      </p>

      <TruckTwin3D plan={plan} />

      <div className="mt-6 grid grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="font-bold text-sm mb-2">Llegenda</h3>
          <ul className="text-xs space-y-1">
            {plan.stops.map((s) => (
              <li key={s.sequence} className="flex items-center gap-2">
                <span
                  className="inline-block w-3 h-3 rounded"
                  style={{ backgroundColor: CLUSTER_COLORS[s.customer_id] }}
                />
                <span className="font-mono">#{s.sequence}</span>
                <span>{s.customer_name}</span>
              </li>
            ))}
            <li className="flex items-center gap-2">
              <span className="inline-block w-3 h-3 rounded bg-gray-500" />
              <span>↺ Zona envasos</span>
            </li>
          </ul>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="font-bold text-sm mb-2">Palets assignats</h3>
          <ul className="text-xs space-y-1.5">
            {plan.pallet_assignments.map((pa) => (
              <li key={pa.slot_id} className="flex justify-between border-b border-gray-100 pb-1">
                <span className="font-mono font-bold">{pa.slot_id}</span>
                <span className="text-right text-gray-700">
                  {pa.is_envase_zone
                    ? 'Envasos'
                    : pa.customer_ids
                        .map(
                          (cid) =>
                            plan.stops.find((s) => s.customer_id === cid)?.customer_name || '?',
                        )
                        .join(' + ')}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="font-bold text-sm mb-2">Especificacions</h3>
          <dl className="text-xs space-y-1">
            <div className="flex justify-between">
              <dt className="text-gray-500">Matrícula</dt>
              <dd className="font-mono">{plan.vehicle.license_plate}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Perfil</dt>
              <dd>{plan.vehicle.profile_name}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Capacitat</dt>
              <dd>{plan.vehicle.capacity_pallets} palets</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Disposició</dt>
              <dd>
                {plan.vehicle.grid_rows} × {plan.vehicle.grid_cols}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Plataforma</dt>
              <dd>{plan.vehicle.has_lift ? 'Sí' : 'No'}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}
