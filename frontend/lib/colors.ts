// Stable colour mapping for customers and pallet slots.
//
// CLUSTER_COLORS in mocks.ts only covered 6 hand-picked customer IDs;
// real DR0027 / DR0001 customer IDs aren't in that dict so they all
// fell back to grey. Here we derive a deterministic hue from the
// customer_id so any route's stops get a stable, distinct colour.

const PALETTE = [
  '#E30613', // damm-red
  '#1E88E5', // blue
  '#43A047', // green
  '#FB8C00', // orange
  '#8E24AA', // purple
  '#00ACC1', // cyan
  '#D81B60', // pink
  '#3949AB', // indigo
  '#7CB342', // lime
  '#F4511E', // deep orange
  '#5E35B1', // deep purple
  '#00897B', // teal
  '#C0CA33', // lime-yellow
  '#6D4C41', // brown
  '#546E7A', // blue-grey
  '#EC407A', // rose
];

export function colorForCustomer(customerId: number | string): string {
  // Simple hash → palette index. Stable across reloads.
  const s = String(customerId);
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) >>> 0;
  }
  return PALETTE[h % PALETTE.length];
}

export function colorForStopSequence(seq: number): string {
  // Deterministic colour by route position: stop 1 always damm-red,
  // stop 2 always blue, etc. Useful when we want neighbouring stops to
  // be visually distinct rather than hash-based.
  return PALETTE[(seq - 1) % PALETTE.length];
}

export function colorForSku(sku: string): string {
  // Same hash-by-string approach as colorForCustomer. Used in the 3D
  // warehouse loading scene where the picker thinks in SKU terms.
  let h = 0;
  for (let i = 0; i < sku.length; i++) {
    h = (h * 31 + sku.charCodeAt(i)) >>> 0;
  }
  return PALETTE[h % PALETTE.length];
}

export const PALETTE_FALLBACK = '#9CA3AF'; // gray-400 for unknowns
