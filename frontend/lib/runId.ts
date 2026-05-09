'use client';

import { useSearchParams } from 'next/navigation';

export const DEFAULT_RUN_ID = 'DR0027-2026-05-08';

/** Currently-selected ``{ruta}-{fecha}`` shared across pages via the
 * URL ``?run_id=…`` query param. Defaults to the DR0027 demo carga.
 */
export function useRunId(): string {
  const params = useSearchParams();
  return params.get('run_id') || DEFAULT_RUN_ID;
}

/** Split a ``run_id`` into ``[ruta, fecha]``. */
export function splitRunId(runId: string): [string, string] {
  // ruta-YYYY-MM-DD: the fecha is the last 10 chars after the trailing '-'.
  if (runId.length < 12 || runId[runId.length - 11] !== '-') {
    return [runId, ''];
  }
  return [runId.slice(0, -11), runId.slice(-10)];
}
