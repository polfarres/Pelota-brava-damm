'use client';

import type { Plan, BaselinePlan } from '@/lib/types';
import { colorForSku } from '@/lib/colors';

interface Props {
  plan: Plan | BaselinePlan;
  mode: 'original' | 'smart';
}

interface Row {
  ubicacion: string;
  sku: string;
  description: string;
  quantity: number;       // sum of physical units (Caja / Barril / Tubo …)
  unit: string;
  lote: string | null;
  descarga: string | null;
  ce: number;             // total CE = Σ quantity × ce_per_unit
  ce_per_unit: number;
  section: 'lleno' | 'envases';
}

function aggregateRows(rows: Row[]): Row[] {
  // Collapse rows with the same (ubicacion, sku, lote, descarga, section)
  // into one. The v2 packer emits one DeliveredLine per (customer, sku)
  // in a slot, so the same warehouse pick produces N rows of fractional
  // quantities — the picker only ever does ONE physical pick. Sum and
  // round once to give them a single actionable line.
  const map = new Map<string, Row>();
  for (const r of rows) {
    const key = `${r.ubicacion}|${r.sku}|${r.lote ?? ''}|${r.descarga ?? ''}|${r.section}`;
    const existing = map.get(key);
    if (existing) {
      existing.quantity += r.quantity;
      existing.ce += r.ce;
    } else {
      map.set(key, { ...r });
    }
  }
  return [...map.values()]
    .map((r) => ({
      ...r,
      quantity: Math.round(r.quantity),
      ce: Math.round(r.ce),
    }))
    .filter((r) => r.quantity > 0)
    .sort((a, b) => {
      const u = a.ubicacion.localeCompare(b.ubicacion);
      if (u !== 0) return u;
      return a.sku.localeCompare(b.sku);
    });
}

export default function PickListTable({ plan, mode }: Props) {
  // Build the rows by walking pallet_assignments in `smart` mode (slot order)
  // or by Ubicación lex order in `original` mode.
  const rawRows: Row[] = [];

  if (mode === 'smart' && plan.kind === 'optimised') {
    plan.pallet_assignments.forEach((pa) => {
      pa.lines.forEach((l) => {
        const cePerUnit = l.ce ?? 1;
        rawRows.push({
          ubicacion: l.ubicacion || '',
          sku: l.sku,
          description: l.description,
          quantity: l.quantity,
          unit: l.unit,
          lote: l.lote,
          descarga: pa.slot_id, // ★ this is the intervention
          ce: cePerUnit * l.quantity,
          ce_per_unit: cePerUnit,
          section: pa.is_envase_zone || l.is_envase ? 'envases' : 'lleno',
        });
      });
    });
  } else {
    // Original (DDIDGP): walk pallet_assignments — the baseline now ships
    // the full Hoja Carga's lines via slot.contents (one slot per
    // warehouse Ubicació). Descàrrega stays blank ('(buit)') because the
    // SAP paperwork doesn't pre-attribute lines to truck pallets — that's
    // exactly the column the Smart variant adds.
    plan.pallet_assignments.forEach((pa) => {
      pa.lines.forEach((l) => {
        const cePerUnit = l.ce ?? 1;
        rawRows.push({
          ubicacion: l.ubicacion || '',
          sku: l.sku,
          description: l.description,
          quantity: l.quantity,
          unit: l.unit,
          lote: l.lote,
          descarga: null, // ★ ALWAYS BLANK in original
          ce: cePerUnit * l.quantity,
          ce_per_unit: cePerUnit,
          section: pa.is_envase_zone || l.is_envase ? 'envases' : 'lleno',
        });
      });
    });
  }

  const rows = aggregateRows(rawRows);
  const llenoRows = rows.filter((r) => r.section === 'lleno');
  const envaseRows = rows.filter((r) => r.section === 'envases');
  const totalLleno = llenoRows.reduce((s, r) => s + r.ce, 0);
  const totalEnvases = envaseRows.reduce((s, r) => s + r.ce, 0);

  return (
    <div className="bg-white border border-gray-300 rounded-lg overflow-hidden">
      {/* DDIDGP-style header */}
      <div className="bg-damm-dark text-white px-4 py-2 flex justify-between items-center text-xs">
        <div>
          <div className="font-bold text-sm">FULL DE CÀRREGA · DDIDGP</div>
          <div>
            Núm. Càrrega {plan.carga_id ?? '—'} · Vehicle {plan.vehicle.license_plate || '—'} · Repartidor{' '}
            {plan.driver_id ?? ''} {plan.driver_name ?? ''}
          </div>
        </div>
        <div className="text-right">
          <div>Ruta {plan.ruta}</div>
          <div>Data {plan.fecha}</div>
          <div className="text-damm-red font-bold mt-1">
            {mode === 'smart' ? 'SMART' : 'ORIGINAL'}
          </div>
        </div>
      </div>

      <Section
        title="Càrrega ple"
        rows={llenoRows}
        total={totalLleno}
        mode={mode}
      />
      <Section
        title="Càrrega envasos"
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
            <th className="px-3 py-1.5 w-24">Ubicació</th>
            <th className="px-3 py-1.5 w-20">Núm. Prod.</th>
            <th className="px-3 py-1.5">Descripció</th>
            <th className="px-3 py-1.5 w-24 text-right">Quantitat</th>
            <th className="px-3 py-1.5 w-16 text-right" title="Caixes Estadístiques">CE</th>
            <th className="px-3 py-1.5 w-16">Lot</th>
            <th
              className={`px-3 py-1.5 w-24 ${
                mode === 'smart' ? 'bg-yellow-100 font-extrabold' : ''
              }`}
            >
              Descàrrega
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const colour = colorForSku(r.sku);
            return (
              <tr
                key={i}
                className="border-b border-gray-100 hover:bg-gray-50"
                style={{
                  borderLeft: `4px solid ${colour}`,
                }}
              >
                <td className="px-3 py-1.5 font-mono">{r.ubicacion || '—'}</td>
                <td className="px-3 py-1.5 font-mono">{r.sku}</td>
                <td className="px-3 py-1.5">{r.description}</td>
                <td className="px-3 py-1.5 text-right whitespace-nowrap">
                  <strong>{r.quantity}</strong> {r.unit}
                </td>
                <td className="px-3 py-1.5 text-right font-mono">{r.ce}</td>
                <td className="px-3 py-1.5 font-mono">{r.lote || ''}</td>
                <td
                  className={`px-3 py-1.5 ${
                    r.descarga
                      ? 'bg-yellow-50 font-bold text-damm-red'
                      : 'text-gray-300 italic'
                  }`}
                >
                  {r.descarga || (mode === 'original' ? '(buit)' : '')}
                </td>
              </tr>
            );
          })}
          <tr className="bg-gray-100 font-semibold">
            <td colSpan={4} className="px-3 py-1.5 text-right">
              Total CE:
            </td>
            <td className="px-3 py-1.5 text-right font-mono">{total}</td>
            <td colSpan={2}></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
