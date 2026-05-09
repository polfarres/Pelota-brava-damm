// Typed API client for the Smart Truck backend.
// Backend ships at NEXT_PUBLIC_API_URL (default http://localhost:8000).

import type { BaselinePlan, Customer, Plan } from './types';

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function safeFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_URL}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.headers || {}),
    },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function getHealth(): Promise<{ status: string }> {
  return safeFetch('/health');
}

export async function getBaseline(
  ruta: string,
  fecha: string,
): Promise<BaselinePlan> {
  return safeFetch<BaselinePlan>(
    `/baseline?ruta=${encodeURIComponent(ruta)}&fecha=${encodeURIComponent(
      fecha,
    )}`,
  );
}

export async function getCustomer(id: number): Promise<Customer> {
  return safeFetch<Customer>(`/customers/${id}`);
}

export async function postPlan(
  ruta: string,
  fecha: string,
): Promise<Plan> {
  return safeFetch<Plan>(`/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ruta, fecha }),
  });
}

export function hojaCargaPdfUrl(runId: string): string {
  return `${API_URL}/plan/${runId}/hoja-carga.pdf`;
}

export function hojaRutaPdfUrl(runId: string): string {
  return `${API_URL}/plan/${runId}/hoja-ruta.pdf`;
}
