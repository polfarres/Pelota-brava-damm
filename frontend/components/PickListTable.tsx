'use client';

import type { Plan, BaselinePlan } from '@/lib/types';
import { CLUSTER_COLORS } from '@/lib/mocks';

interface Props {
  plan: Plan | BaselinePlan;
  mode: 'original' | 'smart';
}

interface Row {
  ubicacion: string;
  sku: string;
  description: string;
  quantity: number;
  unit: string;
  lote: string | null;
  descarga: string | null;
  customer_id: number | null;
  section: 'lleno' | 'envases';
}

export default function PickListTable({ plan, mode }: Props) {
  // Build the rows by walking pallet_assignments in `smart` mode (slot order)
  // or by Ubicación lex order in `original` mode.
  const rows: Row[] = [];

  if (mode === 'smart' && plan.kind === 'optimised') {
    plan.pallet_assignments.forEach((pa) => {
      pa.lines.forEach((l) => {
        rows.push({
          ubicacion: l.ubicacion || (pa.is_envase_zone ? '' : ''),
          sku: l.sku,
          description: l.description,
          quantity: l.quantity,
          unit: l.unit,
          lote: l.lote,
          descarga: pa.slot_id, // ★ this is the intervention
          customer_id: pa.customer_ids[0] ?? null,
          section: pa.is_envase_zone || l.is_envase ? 'envases' : 'lleno',
        });
      });
    });
  } else {
    // Original: iterate stops, group by Ubicación lex order
    const all: Row[] = [];
    plan.stops.forEach((s) => {
      s.delivery_lines.forEach((l) => {
        all.push({
          ubicacion: l.ubicacion || '',
          sku: l.sku,
          description: l.description,
          quantity: l.quantity,
          unit: l.unit,
          lote: l.lote,
          descarga: null, // ★ ALWAYS BLANK in original
          customer_id: s.customer_id,
          section: 'lleno',
        });
      });
      (s.pickup_envases || []).forEach((l) => {
        all.push({
          ubicacion: '',
          sku: l.sku,
          description: l.description,
          quantity: l.quantity,
          unit: l.unit,
          lote: l.lote,
          descarga: null,
          customer_id: s.customer_id,
          section: 'envases',
        });
      });
    });
    all.sort((a, b) => a.ubicacion.localeCompare(b.ubicacion));
    rows.push(...all);
  }

  const llenoRows = rows.filter((r) => r.section === 'lleno');
  const envaseRows = rows.filter((r) => r.section === 'envases');
  const totalLleno = llenoRows.reduce((s, r) => s + r.quantity, 0);
  const totalEnvases = envaseRows.reduce((s, r) => s + r.quantity, 0);

  return (
    <div className="bg-white border border-gray-300 rounded-lg overflow-hidden">
      {/* DDIDGP-style header */}
      <div className="bg-damm-dark text-white px-4 py-2 flex justify-between items-center text-xs">
        <div>
          <div className="font-bold text-sm">HOJA DE CARGA · DDIDGP</div>
          <div>
            Nº Carga {plan.carga_id} · Vehículo {plan.vehicle.license_plate} · Repartidor{' '}
            {plan.driver_id} {plan.driver_name}
          </div>
        </div>
        <div className="text-right">
          <div>Ruta {plan.ruta}</div>
          <div>Fecha {plan.fecha}</div>
          <div className="text-damm-red font-bold mt-1">
            {mode === 'smart' ? 'SMART' : 'ORIGINAL'}
          </div>
        </div>
      </div>

      <Section
        title="Carga lleno"
        rows={llenoRows}
        total={totalLleno}
        mode={mode}
      />
      <Section
        title="Carga envases"
        rows={envaseRows}
        total={totalEnvases}
        mode={mode}
      />
    </div>
  );
}

function Section({
  title,
  rows,
  total,
  mode,
}: {
  title: string;
  rows: Row[];
  total: number;
  mode: 'original' | 'smart';
}) {
  return (
    <div className="border-t border-gray-200">
      <div className="bg-gray-100 px-4 py-1 font-bold text-sm">{title}</div>
      <table className="w-full text-xs">
        <thead className="bg-gray-50 border-b border-gray-300">
          <tr className="text-left">
            <th className="px-3 py-1.5 w-24">Ubicación</th>
            <th className="px-3 py-1.5 w-20">Nº Prod.</th>
            <th className="px-3 py-1.5">Descripción</th>
            <th className="px-3 py-1.5 w-16 text-right">Cantidad</th>
            <th className="px-3 py-1.5 w-20">Unidad</th>
            <th className="px-3 py-1.5 w-16">Lote</th>
            <th
              className={`px-3 py-1.5 w-24 ${
                mode === 'smart' ? 'bg-yellow-100 font-extrabold' : ''
              }`}
            >
              Descarga
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const colour = r.customer_id ? CLUSTER_COLORS[r.customer_id] : null;
            return (
              <tr
                key={i}
                className="border-b border-gray-100 hover:bg-gray-50"
                style={{
                  borderLeft: colour ? `4px solid ${colour}` : undefined,
                }}
              >
                <td className="px-3 py-1.5 font-mono">{r.ubicacion || '—'}</td>
                <td className="px-3 py-1.5 font-mono">{r.sku}</td>
                <td className="px-3 py-1.5">{r.description}</td>
                <td className="px-3 py-1.5 text-right">{r.quantity}</td>
                <td className="px-3 py-1.5">{r.unit}</td>
                <td className="px-3 py-1.5 font-mono">{r.lote || ''}</td>
                <td
                  className={`px-3 py-1.5 ${
                    r.descarga
                      ? 'bg-yellow-50 font-bold text-damm-red'
                      : 'text-gray-300 italic'
                  }`}
                >
                  {r.descarga || (mode === 'original' ? '(vacío)' : '')}
                </td>
              </tr>
            );
          })}
          <tr className="bg-gray-100 font-semibold">
            <td colSpan={3} className="px-3 py-1.5 text-right">
              Total Cantidad:
            </td>
            <td className="px-3 py-1.5 text-right">{total}</td>
            <td colSpan={3}></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
