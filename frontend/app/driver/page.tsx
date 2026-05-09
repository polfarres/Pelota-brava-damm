'use client';

import { MOCK_PLAN, CLUSTER_COLORS } from '@/lib/mocks';

export default function DriverPage() {
  const plan = MOCK_PLAN;
  // Hard-code data from stop #3 (BAR LA PLAÇA, CALLDETENES) — a representative real DR0027 stop.
  const stop = plan.stops[2];
  const colour = CLUSTER_COLORS[stop.customer_id];
  const totalEnvasesUsed = 38;
  const totalEnvasesCapacity = 60;
  const envasesPct = (totalEnvasesUsed / totalEnvasesCapacity) * 100;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">App Conductor · Mockup</h1>
      <p className="text-sm text-gray-600 mb-6">
        Tres pantallas hardcodeadas con datos reales de la parada #3 de DR0027.
      </p>

      <div className="flex gap-6 flex-wrap justify-center">
        {/* Phone 1: next stop */}
        <Phone title="Próxima parada">
          <div className="px-4 py-3 text-white" style={{ backgroundColor: colour }}>
            <div className="text-xs uppercase opacity-80">Parada {stop.sequence} de {plan.stops.length}</div>
            <div className="text-xl font-bold mt-1">{stop.customer_name}</div>
            <div className="text-sm opacity-90">{stop.address}, {stop.city}</div>
          </div>
          <div className="px-4 py-3 space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">ETA</span>
              <span className="font-bold">
                {new Date(stop.eta!).toLocaleTimeString('es-ES', {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Ventana</span>
              <span className="font-mono text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
                ✓ {stop.time_window_start}–{stop.time_window_end}
              </span>
            </div>
            {stop.payment_condition === 'CONTADO' && (
              <div className="bg-yellow-100 border border-yellow-300 rounded p-2 text-center font-bold text-yellow-900">
                💰 CONTADO · cobrar {stop.cash_total.toFixed(2)} €
              </div>
            )}
            <div className="bg-damm-red text-white rounded-lg p-3 text-center">
              <div className="text-xs uppercase opacity-80">Acción</div>
              <div className="text-lg font-bold">
                Abrir cortina <span className="capitalize">{stop.curtain_side}</span>
              </div>
              <div className="text-2xl font-bold mt-1">
                Pallet {stop.pallet_slots?.join(', ')}
              </div>
            </div>
          </div>
        </Phone>

        {/* Phone 2: at-stop pickup */}
        <Phone title="En la parada">
          <div className="px-4 py-3 bg-damm-dark text-white">
            <div className="text-xs uppercase opacity-80">{stop.customer_name}</div>
            <div className="text-base font-bold mt-1">Entregar / Recoger</div>
          </div>
          <div className="px-4 py-3 text-sm space-y-3">
            <div>
              <div className="text-xs uppercase font-bold text-gray-500 mb-1">Entregar</div>
              <ul className="space-y-1">
                {stop.delivery_lines.map((l, i) => (
                  <li key={i} className="flex justify-between bg-green-50 border-l-2 border-green-500 px-2 py-1">
                    <span className="truncate">{l.description}</span>
                    <span className="ml-2 font-bold">{l.quantity} {l.unit}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <div className="text-xs uppercase font-bold text-gray-500 mb-1">Recoger envases</div>
              <ul className="space-y-1">
                {(stop.pickup_envases || []).map((l, i) => (
                  <li key={i} className="flex justify-between bg-blue-50 border-l-2 border-blue-500 px-2 py-1">
                    <span className="truncate">↺ {l.description}</span>
                    <span className="ml-2 font-bold">{l.quantity} {l.unit}</span>
                  </li>
                ))}
              </ul>
            </div>
            <button className="w-full bg-damm-red text-white py-3 rounded font-bold">
              Confirmar entrega
            </button>
          </div>
        </Phone>

        {/* Phone 3: capacity gauge */}
        <Phone title="Espacio envases">
          <div className="px-4 py-3 bg-damm-dark text-white">
            <div className="text-xs uppercase opacity-80">Camión {plan.vehicle.license_plate}</div>
            <div className="text-base font-bold mt-1">Zona envases · P6</div>
          </div>
          <div className="px-4 py-6 flex flex-col items-center text-sm">
            <Gauge pct={envasesPct} />
            <div className="mt-3 text-center">
              <div className="text-3xl font-bold">{totalEnvasesUsed}</div>
              <div className="text-xs text-gray-500">de {totalEnvasesCapacity} unidades</div>
            </div>
            <div className="mt-4 w-full text-xs space-y-1">
              <div className="flex justify-between">
                <span>Cajas vacías</span>
                <span className="font-bold">26 ud</span>
              </div>
              <div className="flex justify-between">
                <span>Barriles vacíos</span>
                <span className="font-bold">8 ud</span>
              </div>
              <div className="flex justify-between">
                <span>Tubos CO₂ vacíos</span>
                <span className="font-bold">4 ud</span>
              </div>
            </div>
            <div className="mt-3 w-full text-xs bg-green-100 border border-green-300 rounded p-2 text-center text-green-700">
              ✓ Espacio suficiente para próximas {plan.stops.length - stop.sequence} paradas.
            </div>
          </div>
        </Phone>
      </div>
    </div>
  );
}

function Phone({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="text-xs uppercase font-bold text-gray-500">{title}</div>
      <div
        className="bg-white rounded-3xl shadow-2xl border-8 border-damm-dark overflow-hidden"
        style={{ width: 360, height: 640 }}
      >
        <div className="h-full flex flex-col">{children}</div>
      </div>
    </div>
  );
}

function Gauge({ pct }: { pct: number }) {
  // semicircular SVG gauge
  const r = 70;
  const cx = 90;
  const cy = 90;
  const angle = (Math.min(pct, 100) / 100) * 180;
  const rad = ((180 - angle) * Math.PI) / 180;
  const x = cx + r * Math.cos(rad);
  const y = cy - r * Math.sin(rad);
  const colour = pct < 70 ? '#43A047' : pct < 90 ? '#FB8C00' : '#E30613';
  return (
    <svg width={180} height={110} viewBox="0 0 180 110">
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none"
        stroke="#eee"
        strokeWidth={14}
      />
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x} ${y}`}
        fill="none"
        stroke={colour}
        strokeWidth={14}
        strokeLinecap="round"
      />
      <text x={cx} y={cy + 10} textAnchor="middle" fontSize={22} fontWeight="bold" fill="#1A1A1A">
        {pct.toFixed(0)}%
      </text>
    </svg>
  );
}
