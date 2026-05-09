// Format helpers for ETA / time strings shipped by the backend.
//
// Backend serialises Python `datetime.time` as a bare "HH:MM:SS" string,
// not an ISO datetime. `new Date("10:25:00")` returns Invalid Date, so
// every ETA renderer must normalise via `formatEta` first.

export function formatEta(eta: string | null | undefined): string {
  if (!eta) return '';
  if (/^\d{2}:\d{2}/.test(eta)) return eta.slice(0, 5);
  const d = new Date(eta);
  return isNaN(d.getTime())
    ? eta
    : d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
}
