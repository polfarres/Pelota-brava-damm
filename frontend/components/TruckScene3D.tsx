'use client';

// 3D animated truck for the warehouse loading view.
//
// Boxes drop into pallet slots as the user advances through the
// loading sequence. Each loaded layer is colour-coded by the
// customer it serves (or DAMM-red for staple columns). Camera
// orbits with mouse drag.

import { Suspense, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { colorForSku } from '@/lib/colors';
import type { Plan, StackLayer } from '@/lib/types';

interface Props {
  plan: Plan;
  // Set of "loaded" layers, identified by `${slotId}::${stop_sequence}`.
  loadedLayerKeys: Set<string>;
  // Set of "loaded" whole-pallet slots — covers staples AND aggregated
  // barrel/non-staple pallets where per-layer rounding zeroed out
  // every layer (so the picker loads the slot in one warehouse wave).
  loadedFullSlots: Set<string>;
  // Slot currently being filled (highlighted).
  currentSlotId: string | null;
}

const STAPLE_SKUS = new Set(['CJ13', 'ED13']);

function isStapleSlot(pa: { lines: { sku: string }[] } | undefined): boolean {
  if (!pa) return false;
  const skus = new Set(pa.lines.map((l) => l.sku));
  if (skus.size === 0 || skus.size > 2) return false;
  return [...skus].every((s) => STAPLE_SKUS.has(s));
}

export default function TruckScene3D({
  plan,
  loadedLayerKeys,
  loadedFullSlots,
  currentSlotId,
}: Props) {
  const grid = plan.vehicle;

  // Pallet positions: 6 slots in 2×3 grid for truck_6p_sidecurtain.
  // Forward (X-) is the cabin side, X+ rear, Z- left curtain, Z+ right.
  const slotLayout = useMemo(() => {
    const slots: { slotId: string; row: number; col: number }[] = [];
    for (let col = 0; col < grid.grid_cols; col++) {
      for (let row = 0; row < grid.grid_rows; row++) {
        const idx = col * grid.grid_rows + row + 1;
        slots.push({ slotId: `P${idx}`, row, col });
      }
    }
    return slots;
  }, [grid.grid_cols, grid.grid_rows]);

  // Truck dimensions in scene units (1 unit ≈ 1 metre).
  const cargoLen = 6;       // 6 m cargo bay
  const cargoWidth = 2.4;
  const cargoHeight = 2.2;
  const cabinLen = 1.6;

  const palletDepth = cargoLen / grid.grid_cols;     // = 2 m for 6p
  const palletWidth = cargoWidth / grid.grid_rows;   // = 1.2 m for 6p

  return (
    <Canvas
      shadows
      camera={{ position: [-7, 5.5, 6.5], fov: 35 }}
      style={{ width: '100%', height: 380, background: 'linear-gradient(180deg,#dbeafe 0%,#f1f5f9 100%)' }}
    >
      <Suspense fallback={null}>
        {/* Lighting */}
        <ambientLight intensity={0.65} />
        <directionalLight
          position={[6, 10, 4]}
          intensity={0.9}
          castShadow
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
        />
        <directionalLight position={[-4, 6, -3]} intensity={0.25} />

        {/* Ground */}
        <mesh receiveShadow rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
          <planeGeometry args={[40, 30]} />
          <meshStandardMaterial color="#cbd5e1" />
        </mesh>

        {/* Cabin */}
        <group position={[-(cargoLen / 2 + cabinLen / 2 + 0.08), cargoHeight / 2 - 0.2, 0]}>
          <mesh castShadow>
            <boxGeometry args={[cabinLen, cargoHeight - 0.4, cargoWidth - 0.1]} />
            <meshStandardMaterial color="#1A1A1A" />
          </mesh>
          {/* Windscreen */}
          <mesh position={[-(cabinLen / 2) + 0.05, 0.45, 0]}>
            <boxGeometry args={[0.05, 0.55, cargoWidth - 0.45]} />
            <meshStandardMaterial color="#7DD3FC" emissive="#0ea5e9" emissiveIntensity={0.2} />
          </mesh>
          {/* DAMM logo strip */}
          <mesh position={[0, cargoHeight / 2 - 0.4, 0]}>
            <boxGeometry args={[cabinLen + 0.02, 0.18, cargoWidth + 0.02]} />
            <meshStandardMaterial color="#E30613" />
          </mesh>
        </group>

        {/* Cargo bay walls (semi-transparent so loaded boxes are visible) */}
        <CargoBay length={cargoLen} width={cargoWidth} height={cargoHeight} />

        {/* Pallet slots + loaded layers */}
        {slotLayout.map(({ slotId, row, col }) => {
          const x = -cargoLen / 2 + palletDepth / 2 + col * palletDepth;
          const z = -cargoWidth / 2 + palletWidth / 2 + row * palletWidth;
          const pa = plan.pallet_assignments.find((p) => p.slot_id === slotId);
          const isCurrent = slotId === currentSlotId;
          const staple = isStapleSlot(pa as { lines: { sku: string }[] } | undefined);
          const stack: StackLayer[] = pa?.stack ?? [];

          return (
            <group key={slotId} position={[x, 0, z]}>
              {/* Pallet base (always visible) */}
              <mesh castShadow position={[0, 0.08, 0]}>
                <boxGeometry args={[palletDepth - 0.15, 0.12, palletWidth - 0.15]} />
                <meshStandardMaterial color={isCurrent ? '#fde68a' : '#a16207'} />
              </mesh>

              {/* Slot label floating above */}
              <SlotLabel slotId={slotId} y={cargoHeight + 0.15} />

              {/* Highlight ring for current slot */}
              {isCurrent && (
                <mesh position={[0, 0.005, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                  <ringGeometry args={[Math.min(palletDepth, palletWidth) / 2 - 0.05, Math.min(palletDepth, palletWidth) / 2 + 0.05, 32]} />
                  <meshBasicMaterial color="#E30613" />
                </mesh>
              )}

              {/* Stack: render each layer that's been "loaded" so far */}
              <PalletStack
                slotId={slotId}
                stack={stack}
                isStaple={staple}
                loadedLayerKeys={loadedLayerKeys}
                loadedFull={loadedFullSlots.has(slotId)}
                width={palletWidth - 0.2}
                depth={palletDepth - 0.2}
                cargoHeight={cargoHeight - 0.3}
              />
            </group>
          );
        })}

        {/* Curtain side labels */}
        <SideLabel text="CORTINA ESQUERRA" position={[0, 0.05, -cargoWidth / 2 - 0.5]} />
        <SideLabel text="CORTINA DRETA" position={[0, 0.05, cargoWidth / 2 + 0.5]} flip />
        <SideLabel text="PORTA POSTERIOR" position={[cargoLen / 2 + 0.5, 0.05, 0]} rotateY={Math.PI / 2} />

        <OrbitControls
          enablePan={false}
          minDistance={6}
          maxDistance={18}
          minPolarAngle={Math.PI / 6}
          maxPolarAngle={Math.PI / 2.2}
        />
      </Suspense>
    </Canvas>
  );
}

function CargoBay({
  length,
  width,
  height,
}: {
  length: number;
  width: number;
  height: number;
}) {
  return (
    <group position={[0, height / 2, 0]}>
      {/* Floor */}
      <mesh receiveShadow position={[0, -height / 2 + 0.005, 0]}>
        <boxGeometry args={[length, 0.02, width]} />
        <meshStandardMaterial color="#475569" />
      </mesh>
      {/* Roof (semi-transparent) */}
      <mesh position={[0, height / 2 - 0.005, 0]}>
        <boxGeometry args={[length, 0.02, width]} />
        <meshStandardMaterial color="#1A1A1A" transparent opacity={0.3} />
      </mesh>
      {/* Rear wall */}
      <mesh position={[length / 2, 0, 0]}>
        <boxGeometry args={[0.05, height, width]} />
        <meshStandardMaterial color="#1A1A1A" transparent opacity={0.6} />
      </mesh>
      {/* Front wall (cabin side) */}
      <mesh position={[-length / 2, 0, 0]}>
        <boxGeometry args={[0.05, height, width]} />
        <meshStandardMaterial color="#1A1A1A" transparent opacity={0.6} />
      </mesh>
      {/* Side curtains — semi-transparent canvas */}
      <mesh position={[0, 0, -width / 2]}>
        <boxGeometry args={[length, height, 0.04]} />
        <meshStandardMaterial color="#fff" transparent opacity={0.18} />
      </mesh>
      <mesh position={[0, 0, width / 2]}>
        <boxGeometry args={[length, height, 0.04]} />
        <meshStandardMaterial color="#fff" transparent opacity={0.18} />
      </mesh>
      {/* DAMM red top stripe */}
      <mesh position={[0, height / 2 - 0.04, 0]}>
        <boxGeometry args={[length, 0.06, width + 0.05]} />
        <meshStandardMaterial color="#E30613" />
      </mesh>
    </group>
  );
}

// Pallet grid: 10 boxes per level (4 + 4 + 2) × 6 levels = 60 boxes max.
//
// User-spec footprint per level:
//   row 0:  [ ][ ][ ][ ]    cellInLevel 0..3   (back, near cabin)
//   row 1:  [ ][ ][ ][ ]    cellInLevel 4..7   (middle)
//   row 2:    [ ][ ]        cellInLevel 8..9   (front, short row, centered)
//
// LIFO loading order = cell index ascending: bottom level first, back
// row first within a level. This way the LAST-delivered customer's
// boxes end up at the bottom-back (least accessible) and the FIRST
// customer's at the top, mirroring A-38.
const PALLET_LEVELS = 6;
const CELLS_PER_LEVEL = 10;
const TOTAL_CELLS = PALLET_LEVELS * CELLS_PER_LEVEL;

interface PalletCell {
  level: number;          // 0 = bottom of the pallet
  cellInLevel: number;    // 0..9
  sku: string;
  customer_id: number;
  stop_sequence: number;
  layerKey: string;       // `${slotId}::${stop_sequence}`
}

function buildPalletCells(slotId: string, stack: StackLayer[]): PalletCell[] {
  // Walk the stack in load order: stack is TOP→BOTTOM so we reverse
  // to get bottom (last-delivered) first.
  const reversed = [...stack].reverse();
  const cells: PalletCell[] = [];
  let cursor = 0;

  for (const layer of reversed) {
    if (cursor >= TOTAL_CELLS) break;
    const layerCells = Math.max(
      1,
      Math.min(TOTAL_CELLS - cursor, Math.round(layer.ce)),
    );

    // Distribute the layer's cells across its SKUs proportionally
    // to each SKU's CE share.
    const skuCe = new Map<string, number>();
    for (const ln of layer.lines) {
      skuCe.set(ln.sku, (skuCe.get(ln.sku) ?? 0) + (ln.ce ?? 1) * ln.quantity);
    }
    const totalCe = [...skuCe.values()].reduce((a, b) => a + b, 0) || 1;
    const perSku: { sku: string; count: number }[] = [];
    for (const [sku, ce] of skuCe) {
      perSku.push({ sku, count: Math.max(1, Math.round((ce / totalCe) * layerCells)) });
    }
    let allocated = perSku.reduce((s, p) => s + p.count, 0);
    while (allocated > layerCells && perSku.length) {
      // Trim from the largest bucket — never below 1 cell.
      const i = perSku.reduce((mi, p, j) => (p.count > perSku[mi].count ? j : mi), 0);
      if (perSku[i].count <= 1) break;
      perSku[i].count--;
      allocated--;
    }

    const layerKey = `${slotId}::${layer.stop_sequence}`;
    for (const { sku, count } of perSku) {
      for (let i = 0; i < count && cursor < TOTAL_CELLS; i++) {
        cells.push({
          level: Math.floor(cursor / CELLS_PER_LEVEL),
          cellInLevel: cursor % CELLS_PER_LEVEL,
          sku,
          customer_id: layer.customer_id,
          stop_sequence: layer.stop_sequence,
          layerKey,
        });
        cursor++;
      }
    }
  }
  return cells;
}

/** Returns ``[localX, localY, localZ]`` and ``[sx, sy, sz]`` (size) for
 * a cell on a pallet of footprint ``depth × width``. The pallet's local
 * origin is centred on the slot floor; +X = rear of truck, +Y = up,
 * +Z = right curtain. */
function cellTransform(
  level: number,
  cellInLevel: number,
  depth: number,
  width: number,
  cellHeight: number,
  palletTop: number,
): { pos: [number, number, number]; size: [number, number, number] } {
  // Map cellInLevel → (rowIdx, colIdx).  Row spans X (depth axis); col
  // spans Z (width axis). Row 2 has only 2 cells, centred (cols 1 & 2).
  let rowIdx: number;
  let colIdx: number;
  if (cellInLevel < 4) {
    rowIdx = 0;
    colIdx = cellInLevel;             // 0..3
  } else if (cellInLevel < 8) {
    rowIdx = 1;
    colIdx = cellInLevel - 4;         // 0..3
  } else {
    rowIdx = 2;
    colIdx = cellInLevel - 8 + 1;     // 1..2 (centred)
  }

  const cellDepth = depth / 3;
  const cellWidth = width / 4;
  const x = -depth / 2 + (rowIdx + 0.5) * cellDepth;
  const z = -width / 2 + (colIdx + 0.5) * cellWidth;
  const y = palletTop + (level + 0.5) * cellHeight;

  return {
    pos: [x, y, z],
    size: [cellDepth * 0.94, cellHeight * 0.92, cellWidth * 0.94],
  };
}

function PalletStack({
  slotId,
  stack,
  isStaple,
  loadedLayerKeys,
  loadedFull,
  width,
  depth,
  cargoHeight,
}: {
  slotId: string;
  stack: StackLayer[];
  isStaple: boolean;
  loadedLayerKeys: Set<string>;
  loadedFull: boolean;
  width: number;
  depth: number;
  cargoHeight: number;
}) {
  const palletTop = 0.16;
  // Each cell is one standard caja. Total stack height = 6 cells.
  const cellHeight = (cargoHeight - 0.2) / PALLET_LEVELS;

  const cells = useMemo(() => buildPalletCells(slotId, stack), [slotId, stack]);

  // Decide which cells to render:
  // - loadedFull → all cells of this slot (whole-pallet wave done).
  // - loadedLayerKeys → cells belonging to that specific layer (LIFO).
  const visibleCells = cells.filter(
    (c) => loadedFull || loadedLayerKeys.has(c.layerKey),
  );

  return (
    <group>
      {visibleCells.map((c) => {
        const { pos, size } = cellTransform(
          c.level,
          c.cellInLevel,
          depth,
          width,
          cellHeight,
          palletTop,
        );
        return (
          <mesh
            key={`${slotId}-${c.level}-${c.cellInLevel}`}
            castShadow
            receiveShadow
            position={pos}
          >
            <boxGeometry args={size} />
            <meshStandardMaterial color={colorForSku(c.sku)} />
          </mesh>
        );
      })}
      {/* Staple star marker — appears once any cell is loaded. */}
      {isStaple && loadedFull && (
        <mesh position={[0, palletTop + cargoHeight - 0.05, 0]}>
          <sphereGeometry args={[0.12, 16, 16]} />
          <meshStandardMaterial color="#E30613" emissive="#E30613" emissiveIntensity={0.5} />
        </mesh>
      )}
    </group>
  );
}

function SlotLabel({ slotId, y }: { slotId: string; y: number }) {
  // Use a thin red disc as a marker; text labels in r3f require Drei <Text>
  // and a font asset, which is overkill for the demo.
  return (
    <mesh position={[0, y, 0]}>
      <sphereGeometry args={[0.07, 16, 16]} />
      <meshStandardMaterial color="#E30613" emissive="#E30613" emissiveIntensity={0.4} />
      <SlotLabelText slotId={slotId} />
    </mesh>
  );
}

function SlotLabelText({ slotId }: { slotId: string }) {
  // Placeholder: SlotLabel uses the marker only; the text overlay lives
  // in the parent <TruckLoadDiagram>'s SVG variant. Keeping it as a
  // no-op here so we don't pull a font into the bundle.
  void slotId;
  return null;
}

function SideLabel({
  text,
  position,
  rotateY = 0,
  flip = false,
}: {
  text: string;
  position: [number, number, number];
  rotateY?: number;
  flip?: boolean;
}) {
  void text; void flip;
  // Simple thin pole as a visual cue for orientation. Text would
  // require a font asset (Drei <Text/>) — not worth the bundle cost.
  return (
    <group position={position} rotation={[0, rotateY, 0]}>
      <mesh>
        <boxGeometry args={[0.06, 0.06, 0.2]} />
        <meshStandardMaterial color="#475569" />
      </mesh>
    </group>
  );
}
