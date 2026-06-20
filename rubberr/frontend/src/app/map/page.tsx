"use client";
import Sidebar from "@/components/Sidebar";
import dynamic from 'next/dynamic';

// Dynamic import for Leaflet map to avoid SSR issues
const MapView = dynamic(() => import('@/components/MapView'), { 
  ssr: false,
  loading: () => <div className="h-full w-full bg-[#0a0a0a] animate-pulse flex items-center justify-center text-gray-500">Loading Map Intelligence...</div>
});

export default function MapPage() {
  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      <main className="flex-1 md:ml-64 pt-14 md:pt-0 h-screen flex flex-col">
        <div className="flex-1 p-0 relative">
             <MapView />
             
             {/* Overlay Controls */}
             <div className="absolute top-8 left-16 z-[1000] pointer-events-none">
                <h1 className="text-4xl font-bold text-white drop-shadow-md">Tournament Map</h1>
                <p className="text-gray-300 drop-shadow-md font-medium text-sm bg-black/50 px-2 py-1 rounded inline-block">Visualizing upcoming opportunities</p>
             </div>
        </div>
      </main>
    </div>
  );
}
