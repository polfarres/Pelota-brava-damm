'use client';

import { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { getRoutes, type RouteOption } from '@/lib/api';
import { DEFAULT_RUN_ID, splitRunId, useRunId } from '@/lib/runId';

/** Header dropdowns to pick the active route + date. Selection is
 * pushed to the URL ``?run_id=`` query param, which all pages read
 * via :func:`useRunId`.
 */
export default function RouteSelector() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const runId = useRunId();
  const [ruta, fecha] = splitRunId(runId);
  const [routes, setRoutes] = useState<RouteOption[]>([]);

  useEffect(() => {
    let cancelled = false;
    getRoutes()
      .then((r) => !cancelled && setRoutes(r))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const datesByRoute = useMemo(() => {
    const m = new Map<string, RouteOption[]>();
    for (const r of routes) {
      const list = m.get(r.ruta) ?? [];
      list.push(r);
      m.set(r.ruta, list);
    }
    for (const list of m.values()) list.sort((a, b) => b.fecha.localeCompare(a.fecha));
    return m;
  }, [routes]);

  const rutas = useMemo(
    () => Array.from(datesByRoute.keys()).sort(),
    [datesByRoute],
  );

  function setRunId(newRunId: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (newRunId === DEFAULT_RUN_ID) {
      params.delete('run_id');
    } else {
      params.set('run_id', newRunId);
    }
    const qs = params.toString();
    router.push(`${pathname}${qs ? `?${qs}` : ''}`);
  }

  function onRutaChange(newRuta: string) {
    const dates = datesByRoute.get(newRuta) ?? [];
    if (dates.length === 0) return;
    setRunId(dates[0].run_id);
  }

  function onFechaChange(newFecha: string) {
    setRunId(`${ruta}-${newFecha}`);
  }

  const dates = datesByRoute.get(ruta) ?? [];

  return (
    <div className="flex items-center gap-2 text-sm">
      <select
        value={ruta}
        onChange={(e) => onRutaChange(e.target.value)}
        className="bg-damm-dark border border-gray-600 rounded px-2 py-1 text-white text-xs"
        disabled={routes.length === 0}
      >
        {/* Always render the current ruta even if /routes hasn't loaded yet
            so the dropdown doesn't snap-flicker on hydrate. */}
        {!rutas.includes(ruta) && <option value={ruta}>{ruta}</option>}
        {rutas.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      <select
        value={fecha}
        onChange={(e) => onFechaChange(e.target.value)}
        className="bg-damm-dark border border-gray-600 rounded px-2 py-1 text-white text-xs"
        disabled={dates.length === 0}
      >
        {dates.length === 0 && <option value={fecha}>{fecha}</option>}
        {dates.map((d) => (
          <option key={d.fecha} value={d.fecha}>
            {d.fecha} · {d.n_customers} clients
          </option>
        ))}
      </select>
    </div>
  );
}
