/**
 * Typed client for the Smart Truck FastAPI backend (FR-012).
 *
 * The shape of `Plan` mirrors the canonical types in
 * `Hackaton/DAMM/PLAN/Specifications.md` § 2.
 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Health = { status: string };

export async function getHealth(): Promise<Health> {
  const r = await fetch(`${API_URL}/health`, { cache: "no-store" });
  if (!r.ok) throw new Error(`health check failed: ${r.status}`);
  return r.json();
}

// TODO (FR-012):
//   export async function postPlan({ ruta, fecha }: { ruta: string; fecha: string }): Promise<Plan>
//   export async function getBaseline({ ruta, fecha }: { ruta: string; fecha: string }): Promise<BaselinePlan>
