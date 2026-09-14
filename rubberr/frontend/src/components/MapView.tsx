"use client";
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { Icon } from 'leaflet';
import { useEffect, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// CARTO Basemaps key (from https://carto.com/basemaps/apikey). Appended via the
// documented ?key= param — the raster tile CDN only drops the "API KEY REQUIRED"
// watermark when a valid Basemaps key is present. Empty ⇒ tiles render watermarked.
const CARTO_KEY = process.env.NEXT_PUBLIC_CARTO_KEY;
const TILE_URL = `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png${CARTO_KEY ? `?key=${CARTO_KEY}` : ""}`;

// Fix for default marker icon in Leaflet/Next.js
const customIcon = new Icon({
  iconUrl: "https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41]
});

// Manual Geocode Cache for MVP (Avoids Rate Limits/Backend Complexity for now)
const CITY_COORDS: Record<string, [number, number]> = {
    "Austin, TX": [30.2672, -97.7431],
    "Round Rock, TX": [30.5083, -97.6789],
    "Houston, TX": [29.7604, -95.3698],
    "Dallas, TX": [32.7767, -96.7970],
    "Fort Worth, TX": [32.7555, -97.3308],
    "San Antonio, TX": [29.4241, -98.4936],
    "Katy, TX": [29.7858, -95.8245],
    "Plano, TX": [33.0198, -96.6989],
    "Frisco, TX": [33.1507, -96.8236],
    // Fallbacks
    "Texas": [31.9686, -99.9018],
    "Phoenix, AZ": [33.4484, -112.0740],
    "Las Vegas, NV": [36.1699, -115.1398] 
};

export default function MapView() {
  const [isMounted, setIsMounted] = useState(false);
  const [markers, setMarkers] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setIsMounted(true);
    setError(null);

    // Fetch Real Tournaments from Backend
    fetch(`${API_URL}/tournaments`)
        .then(res => {
            if (!res.ok) throw new Error(`GET /tournaments → ${res.status}`);
            return res.json();
        })
        .then((data: any[]) => {
            const mappedMarkers = data.map(t => {
                // Try to match location string
                // Clean input: "Austin, TX " -> "Austin, TX"
                const locKey = t.location ? t.location.trim() : "";
                const coords = CITY_COORDS[locKey];

                if (coords) {
                    return {
                        name: t.title,
                        lat: coords[0] + (Math.random() * 0.01), // Jitter slightly if same location
                        lng: coords[1] + (Math.random() * 0.01),
                        type: "Tournament",
                        date: t.date_range
                    };
                }
                return null;
            }).filter(Boolean); // Remove nulls

            setMarkers(mappedMarkers);
        })
        .catch(err => {
            console.error("Failed to map tournaments:", err);
            setMarkers([]);
            setError(`Couldn't load tournament map from ${API_URL}/tournaments: ${err instanceof Error ? err.message : String(err)}`);
        });
  }, []);

  if (!isMounted) return <div className="h-full w-full bg-[#0a0a0a] animate-pulse rounded-2xl" />;

  if (error) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-[#0a0a0a] p-4 text-center text-sm text-red-300">
        {error}
      </div>
    );
  }

  // Default Center (Austin/TX) usually good for this user
  const center: [number, number] = [30.5, -97.7]; 

  return (
    <div className="h-full w-full overflow-hidden bg-[#0a0a0a]">
       <MapContainer center={center} zoom={7} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url={TILE_URL} // Dark mode tiles (CARTO); ?key= appended when NEXT_PUBLIC_CARTO_KEY is set
        />
        {markers.map((loc, i) => (
          <Marker key={i} position={[loc.lat, loc.lng]} icon={customIcon}>
            <Popup>
              <div className="text-black font-bold font-sans">{loc.name}</div>
              <div className="text-gray-600 text-xs font-sans font-medium">{loc.type} • {loc.date}</div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
