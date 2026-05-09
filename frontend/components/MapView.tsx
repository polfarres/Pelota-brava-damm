'use client';

import { useEffect, useState } from 'react';
import type { StopPlan } from '@/lib/types';
import { CLUSTER_COLORS, DEPOT } from '@/lib/mocks';
import { formatEta } from '@/lib/time';
import { getRouteGeometry } from '@/lib/api';

interface Props {
  stops: StopPlan[];
  selectedSeq: number | null;
  onSelect: (seq: number) => void;
  runId?: string;
}

// When multiple customers share an address (e.g. several bars on the same
// "CALLE GRAN" with no street number resolution), the geocoder hands back
// identical lat/lon and the markers stack into one. Spread overlapping
// markers around their shared point in a small fixed-radius circle so each
// stop is individually clickable.
const JITTER_RADIUS_DEG = 0.0004; // ~45m

function jitterCoincidentMarker(
  stops: StopPlan[],
  current: StopPlan,
): [number, number] {
  if (current.lat == null || current.lon == null) {
    return [current.lat as number, current.lon as number];
  }
  const sameSpot = stops.filter(
    (s) => s.lat === current.lat && s.lon === current.lon,
  );
  if (sameSpot.length <= 1) return [current.lat, current.lon];
  const idx = sameSpot.findIndex((s) => s.sequence === current.sequence);
  const angle = (2 * Math.PI * idx) / sameSpot.length;
  return [
    current.lat + JITTER_RADIUS_DEG * Math.cos(angle),
    current.lon + JITTER_RADIUS_DEG * Math.sin(angle),
  ];
}

export default function MapView({ stops, selectedSeq, onSelect, runId }: Props) {
  const [mounted, setMounted] = useState(false);
  const [Components, setComponents] = useState<any>(null);
  const [routeGeom, setRouteGeom] = useState<Array<[number, number]> | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    getRouteGeometry(runId)
      .then((coords) => !cancelled && setRouteGeom(coords))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([import('react-leaflet'), import('leaflet')]).then(
      ([rl, leafletNs]) => {
        if (cancelled) return;
        const L = leafletNs.default || leafletNs;
        // Build a divIcon factory; avoids Webpack URL gymnastics with Leaflet's default icon.
        const numberedIcon = (n: number, color: string) =>
          L.divIcon({
            className: '',
            html: `<div class="numbered-marker" style="background-color: ${color}">${n}</div>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
          });
        const depotIcon = L.divIcon({
          className: '',
          html: `<div class="depot-marker">DEPOT</div>`,
          iconSize: [40, 32],
          iconAnchor: [20, 16],
        });
        setComponents({
          MapContainer: rl.MapContainer,
          TileLayer: rl.TileLayer,
          Marker: rl.Marker,
          Popup: rl.Popup,
          Polyline: rl.Polyline,
          numberedIcon,
          depotIcon,
        });
        setMounted(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  if (!mounted || !Components) {
    return (
      <div className="w-full h-full bg-gray-100 flex items-center justify-center text-gray-500 rounded-lg">
        Carregant mapa…
      </div>
    );
  }

  const { MapContainer, TileLayer, Marker, Popup, Polyline, numberedIcon, depotIcon } = Components;

  // Road-following polyline from OSRM if available; straight-line fallback.
  const polyline: [number, number][] = routeGeom ?? [
    [DEPOT.lat, DEPOT.lon],
    ...stops
      .filter((s) => s.lat != null && s.lon != null)
      .map((s) => [s.lat as number, s.lon as number] as [number, number]),
    [DEPOT.lat, DEPOT.lon],
  ];

  // Centre between depot and stops.
  const center: [number, number] = [
    (DEPOT.lat + (stops[0]?.lat ?? DEPOT.lat)) / 2,
    (DEPOT.lon + (stops[0]?.lon ?? DEPOT.lon)) / 2,
  ];

  return (
    <MapContainer
      center={center}
      zoom={9}
      scrollWheelZoom
      className="w-full h-full rounded-lg"
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; OpenStreetMap contributors &copy; CARTO'
      />
      <Marker position={[DEPOT.lat, DEPOT.lon]} icon={depotIcon}>
        <Popup>
          <strong>{DEPOT.name}</strong>
          <br />
          {DEPOT.address}
        </Popup>
      </Marker>
      <Polyline positions={polyline} pathOptions={{ color: '#E30613', weight: 3, opacity: 0.7 }} />
      {stops.map((s) => {
        if (s.lat == null || s.lon == null) return null;
        const colour = CLUSTER_COLORS[s.customer_id] || '#666';
        const isSelected = selectedSeq === s.sequence;
        const [latJ, lonJ] = jitterCoincidentMarker(stops, s);
        return (
          <Marker
            key={s.sequence}
            position={[latJ, lonJ]}
            icon={numberedIcon(s.sequence, isSelected ? '#E30613' : colour)}
            eventHandlers={{
              click: () => onSelect(s.sequence),
            }}
          >
            <Popup>
              <strong>
                #{s.sequence} {s.customer_name}
              </strong>
              <br />
              {s.address}{s.city ? `, ${s.city}` : ''}
              {s.eta && (
                <>
                  <br />
                  ETA: {formatEta(s.eta)}
                </>
              )}
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
