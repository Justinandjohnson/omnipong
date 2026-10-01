"use client";
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { divIcon, latLngBounds } from 'leaflet';
import { useEffect, useMemo } from 'react';
import { ExternalLink } from 'lucide-react';

// CARTO Basemaps key (from https://carto.com/basemaps/apikey). Appended via the
// documented ?key= param — the raster tile CDN only drops the "API KEY REQUIRED"
// watermark when a valid Basemaps key is present. Empty ⇒ tiles render watermarked.
const CARTO_KEY = process.env.NEXT_PUBLIC_CARTO_KEY;
const TILE_URL = `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png${CARTO_KEY ? `?key=${CARTO_KEY}` : ""}`;

// Tournament markers: green when the rating engine recommends the tournament,
// slate otherwise, so "which ones to sign up for" is visible at a glance.
function tournamentIcon(recommended: boolean) {
  const color = recommended ? "#22c55e" : "#94a3b8";
  const ring = recommended ? "box-shadow:0 0 0 4px rgba(34,197,94,.35);" : "";
  return divIcon({
    className: "",
    html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid #fff;${ring}"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -8],
  });
}
const recommendedPin = tournamentIcon(true);
const normalPin = tournamentIcon(false);

// "You are here" marker — a plain CSS dot so no extra asset is needed.
const userIcon = divIcon({
  className: "",
  html: '<div style="width:16px;height:16px;border-radius:50%;background:#3b82f6;border:3px solid #fff;box-shadow:0 0 0 3px rgba(59,130,246,.4)"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

// Geocode table for the cities this app actually sees. Keys are lowercase
// substrings matched against the tournament's location string. Unknown cities
// fall back to their state centroid (Texas) with a small jitter.
const CITY_COORDS: Record<string, [number, number]> = {
  "plano": [33.0198, -96.6989],
  "austin": [30.2672, -97.7431],
  "round rock": [30.5083, -97.6789],
  "houston": [29.7604, -95.3698],
  "dallas": [32.7767, -96.7970],
  "fort worth": [32.7555, -97.3308],
  "san antonio": [29.4241, -98.4936],
  "katy": [29.7858, -95.8245],
  "frisco": [33.1507, -96.8236],
  "richardson": [32.9483, -96.7299],
  "irving": [32.8140, -96.9489],
  "allen": [33.1032, -96.6706],
  "colleyville": [32.8807, -97.1550],
  "lubbock": [33.5779, -101.8552],
  "el paso": [31.7619, -106.4850],
  "arlington": [32.7357, -97.1081],
  "mckinney": [33.1972, -96.6397],
  "carrollton": [32.9537, -96.8903],
  "garland": [32.9126, -96.6389],
  "denton": [33.2148, -97.1331],
  "waco": [31.5493, -97.1467],
  "college station": [30.6280, -96.3344],
  "pearland": [29.5636, -95.2860],
  "sugar land": [29.6197, -95.6349],
  "the woodlands": [30.1658, -95.4613],
  "spring": [30.0799, -95.4172],
  "mesquite": [32.7668, -96.5992],
  "lewisville": [33.0462, -96.9942],
  "tyler": [32.3513, -95.3011],
  "killeen": [31.1171, -97.7278],
  "temple": [31.0982, -97.3428],
  "georgetown": [30.6333, -97.6779],
  "cedar park": [30.5052, -97.8203],
  "leander": [30.5788, -97.8531],
  "pflugerville": [30.4394, -97.6200],
  "san marcos": [29.8833, -97.9414],
  "new braunfels": [29.7030, -98.1245],
  "conroe": [30.3119, -95.4560],
  "baytown": [29.7355, -94.9774],
  "galveston": [29.3013, -94.7977],
  "port arthur": [29.8849, -93.9399],
  "beaumont": [30.0802, -94.1266],
  "corpus christi": [27.8006, -97.3964],
  "amarillo": [35.2220, -101.8313],
  "laredo": [27.5064, -99.5075],
  "midland": [31.9974, -102.0779],
  "odessa": [31.8457, -102.3676],
  "abilene": [32.4487, -99.7331],
  "san angelo": [31.4638, -100.4370],
  "wichita falls": [33.9137, -98.4934],
  "brownsville": [25.9017, -97.4975],
  "mcallen": [26.2034, -98.2300],
  "humble": [29.9988, -95.2622],
  "texas": [31.9686, -99.9018],
  "phoenix": [33.4484, -112.0740],
  "las vegas": [36.1699, -115.1398],
  "oklahoma city": [35.4676, -97.5164],
};

function geocode(location: string): [number, number] | null {
  if (!location) return null;
  const loc = location.toLowerCase();
  for (const key of Object.keys(CITY_COORDS)) {
    if (loc.includes(key)) return CITY_COORDS[key];
  }
  return null;
}

function haversineMiles(a: [number, number], b: [number, number]): number {
  const R = 3958.8;
  const dLat = ((b[0] - a[0]) * Math.PI) / 180;
  const dLng = ((b[1] - a[1]) * Math.PI) / 180;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a[0] * Math.PI) / 180) *
      Math.cos((b[0] * Math.PI) / 180) *
      Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

interface MapRecEvent {
  name: string;
  fee?: number | string | null;
  competitiveness?: string | null;
  reason?: string | null;
}

interface Tournament {
  title?: string;
  city_state?: string;
  location?: string;
  date_range?: string;
  omnipong_url?: string;
  recommended_events?: MapRecEvent[];
  recommended?: boolean;
  expected_rating_change?: number;
}

interface MapMarker {
  name?: string;
  lat: number;
  lng: number;
  date?: string;
  location: string;
  url?: string;
  recommended: boolean;
  recommendedEvents: MapRecEvent[];
  expectedChange?: number;
}

interface MapViewProps {
  tournaments: Tournament[];
  userLocation?: { lat: number; lng: number } | null;
}

// Fits the viewport to all markers (and the user) once data is present.
function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 10);
      return;
    }
    map.fitBounds(latLngBounds(points).pad(0.2));
  }, [points, map]);
  return null;
}

export default function MapView({ tournaments, userLocation }: MapViewProps) {
  const markers = useMemo(
    () =>
      (tournaments || [])
        .map((t, i): MapMarker | null => {
          const loc = t.city_state || t.location || "";
          const base = geocode(loc);
          if (!base) return null;
          // Deterministic jitter so several events in one city don't stack exactly.
          const jitter = ((i % 7) - 3) * 0.006;
          return {
            name: t.title,
            lat: base[0] + jitter,
            lng: base[1] - jitter,
            date: t.date_range,
            location: loc,
            url: t.omnipong_url,
            recommended: Boolean(t.recommended),
            recommendedEvents: t.recommended_events || [],
            expectedChange: t.expected_rating_change,
          };
        })
        .filter((m): m is MapMarker => m !== null),
    [tournaments],
  );

  const points = useMemo(() => {
    const pts: [number, number][] = markers.map((m) => [m.lat, m.lng]);
    if (userLocation) pts.push([userLocation.lat, userLocation.lng]);
    return pts;
  }, [markers, userLocation]);

  const center: [number, number] = userLocation
    ? [userLocation.lat, userLocation.lng]
    : [30.5, -97.7];

  return (
    <div className="h-full w-full overflow-hidden rounded-2xl bg-[#0a0a0a]">
      <MapContainer center={center} zoom={7} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url={TILE_URL}
        />
        <FitBounds points={points} />

        {userLocation && (
          <Marker position={[userLocation.lat, userLocation.lng]} icon={userIcon}>
            <Popup>
              <div className="text-black font-bold">You are here</div>
            </Popup>
          </Marker>
        )}

        {markers.map((loc, i) => {
          const dist = userLocation
            ? haversineMiles([userLocation.lat, userLocation.lng], [loc.lat, loc.lng])
            : null;
          return (
            <Marker
              key={i}
              position={[loc.lat, loc.lng]}
              icon={loc.recommended ? recommendedPin : normalPin}
            >
              <Popup>
                <div className="text-black font-bold font-sans leading-snug">{loc.name}</div>
                <div className="text-gray-600 text-xs font-sans font-medium mt-1">
                  Tournament • {loc.date}
                </div>
                {loc.location && (
                  <div className="text-gray-500 text-xs font-sans">{loc.location}</div>
                )}
                {dist !== null && (
                  <div className="text-gray-500 text-xs font-sans">~{dist.toFixed(0)} mi away</div>
                )}
                {loc.recommended && (
                  <div style={{ marginTop: 6, fontSize: 12, fontWeight: 800, color: "#16a34a" }}>
                    Good fit
                    {typeof loc.expectedChange === "number"
                      ? ` · ${loc.expectedChange > 0 ? "+" : ""}${loc.expectedChange} pts expected`
                      : ""}
                  </div>
                )}
                {loc.recommendedEvents.length > 0 && (
                  <div style={{ marginTop: 6 }}>
                    <div
                      style={{
                        fontSize: 10,
                        textTransform: "uppercase",
                        letterSpacing: ".06em",
                        color: "#6b7280",
                        fontWeight: 800,
                      }}
                    >
                      AI recommends
                    </div>
                    {loc.recommendedEvents.map((e, j) => (
                      <div key={j} style={{ fontSize: 12, color: "#111827", marginTop: 2 }}>
                        <span style={{ fontWeight: 700 }}>{e.name}</span>
                        {e.competitiveness ? (
                          <span style={{ color: "#6b7280" }}> · {e.competitiveness}</span>
                        ) : null}
                        {e.fee ? <span style={{ color: "#6b7280" }}> · ${e.fee}</span> : null}
                      </div>
                    ))}
                  </div>
                )}
                {loc.url && (
                  <a
                    href={loc.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      marginTop: 8,
                      padding: "4px 10px",
                      background: "#ef4444",
                      color: "#fff",
                      borderRadius: 6,
                      fontSize: 12,
                      fontWeight: 700,
                      textDecoration: "none",
                    }}
                  >
                    Sign up on OmniPong <ExternalLink size={12} />
                  </a>
                )}
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>
    </div>
  );
}
