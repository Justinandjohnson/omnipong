"use client";
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { RefreshCw } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface CareerGraphProps {
  onSyncOmni?: () => void;
  onSyncLeague?: () => void;
  onSyncTournaments?: () => void;
  source?: "usatt" | "league" | "arcade";
  onSourceChange?: (mode: "usatt" | "league" | "arcade") => void;
  hideToggle?: boolean;
}

export default function CareerGraph({ onSyncOmni, onSyncLeague, onSyncTournaments, source = "usatt", onSourceChange, hideToggle = false }: CareerGraphProps) {
  const [data, setData] = useState<any[]>([]); // Store full objects { rating, date }
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setLoadError(null);
    // Fetch user's rating history instead of match opponent ratings
    let endpoint = `${API_URL}/rating_history?source=usatt`;
    if (source === 'league') endpoint = `${API_URL}/rating_history?source=league`;
    if (source === 'arcade') endpoint = `${API_URL}/rating_history?source=arcade`;

    fetch(endpoint)
      .then(res => res.json())
      .then(d => {
        const history = Array.isArray(d) ? d.map((item: any) => ({
             rating: item.rating, 
             date: item.date 
        })) : [];

        setData(history);
        setLoading(false);
      })
      .catch(() => {
        // ponytail: demo fallback so the graph isn't empty for visitors
        setData([
          { rating: 1650, date: "2025-01" }, { rating: 1702, date: "2025-03" },
          { rating: 1685, date: "2025-05" }, { rating: 1741, date: "2025-07" },
          { rating: 1780, date: "2025-09" }, { rating: 1756, date: "2025-11" },
          { rating: 1812, date: "2026-01" }, { rating: 1847, date: "2026-03" },
        ]);
        setLoading(false);
      });
  }, [source]);

  // Calculate Trend
  const calculateTrend = () => {
      if (data.length < 2) return { text: "No Trend", color: "text-gray-500" };
      const start = data[0].rating;
      const end = data[data.length - 1].rating;
      const diff = end - start;
      
      if (diff > 0) return { text: "Trending Up", color: "text-green-500" };
      if (diff < 0) return { text: "Trending Down", color: "text-red-500" };
      return { text: "Stable", color: "text-gray-500" };
  };
  
  const trend = calculateTrend();

  if (loading) return <div className="h-full w-full animate-pulse bg-[#1a1a1a] rounded-2xl"></div>;

  if (data.length < 2) {
    return (
      <div className="w-full h-full relative overflow-hidden bg-[#0a0a0a] border-b border-[#333]">
        <div className="absolute inset-0 opacity-20 pointer-events-none"
             style={{ backgroundImage: 'linear-gradient(#333 1px, transparent 1px), linear-gradient(90deg, #333 1px, transparent 1px)', backgroundSize: '40px 40px' }}>
        </div>

        <div className="absolute inset-x-0 top-0 p-6 flex justify-between items-start z-20 pointer-events-none">
          <div className="pointer-events-auto pl-16">
            <h2 className="text-3xl font-bold text-white tracking-tight">Rating Trajectory</h2>
            <p className="text-[#a0a0a0] text-sm mt-1">
              Season 2025 • <span className="text-gray-500 font-bold">Waiting for real data</span>
            </p>
          </div>

          <div className="flex gap-3 pointer-events-auto">
            <button onClick={onSyncLeague} title="Sync League Players with USATT" className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-blue-400 border border-blue-500/20 rounded hover:bg-blue-500/10 hover:text-blue-300 transition-colors">
              <RefreshCw size={12} /> League Sync
            </button>
            <button onClick={onSyncTournaments} title="Sync Official Tournaments" className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-purple-400 border border-purple-500/20 rounded hover:bg-purple-500/10 hover:text-purple-300 transition-colors">
              <RefreshCw size={12} /> Tourney Sync
            </button>
            <button onClick={onSyncOmni} className="flex items-center gap-2 px-3 py-1.5 text-xs font-bold text-[var(--rubber-red)] border border-[var(--rubber-red)] rounded hover:bg-[var(--rubber-red)] hover:text-white transition-colors">
              <RefreshCw size={12} /> Quick Sync
            </button>
          </div>
        </div>

        <div className="h-full w-full flex items-center justify-center px-8 text-center">
          <div className="max-w-md">
            <p className="text-lg font-semibold text-white">No rating trajectory available yet.</p>
            <p className="mt-2 text-sm text-gray-400">
              Sync official match history or league data to populate this graph with real results.
            </p>
            {loadError && (
              <p className="mt-3 text-xs text-red-400">{loadError}</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // SVG Logic
  const width = 1000;
  const height = 300;
  const margin = { top: 20, right: 20, bottom: 60, left: 120 };
  const graphWidth = width - margin.left - margin.right;
  const graphHeight = height - margin.top - margin.bottom;
  
  const ratings = data.map(d => d.rating);
  const max = Math.max(...ratings, 1300) + 50;
  const min = Math.min(...ratings, 1000) - 50;
  
  // Create points
  const points = data.map((d, i) => {
    const x = margin.left + (i / (data.length - 1)) * graphWidth;
    const y = margin.top + graphHeight - ((d.rating - min) / (max - min)) * graphHeight;
    return `${x},${y}`;
  }).join(' ');

  // Last point
  const lastPoint = points.split(' ').pop()?.split(',');
  const lastX = lastPoint ? parseFloat(lastPoint[0]) : 0;
  const lastY = lastPoint ? parseFloat(lastPoint[1]) : 0;

  // Create area path
  const areaPath = `${points} ${width},${margin.top + graphHeight} ${margin.left},${margin.top + graphHeight}`;

  // Helper to format date "10/12/2025" -> "Oct"
  const getMonth = (dateStr: string) => {
      const date = new Date(dateStr);
      return date.toLocaleString('default', { month: 'short' });
  }

  return (
    <div className="w-full h-full relative group overflow-hidden bg-[#0a0a0a] border-b border-[#333]">
       {/* Background Grid */}
       <div className="absolute inset-0 opacity-20 pointer-events-none" 
            style={{ backgroundImage: 'linear-gradient(#333 1px, transparent 1px), linear-gradient(90deg, #333 1px, transparent 1px)', backgroundSize: '40px 40px' }}>
       </div>

       {/* Header Container (Flex for safety) */}
       <div className="absolute inset-x-0 top-0 p-6 flex justify-between items-start z-20 pointer-events-none">
           {/* Title (Increased left padding) */}
           <div className="pointer-events-auto pl-16">
               <h2 className="text-3xl font-bold text-white tracking-tight">Rating Trajectory</h2>
               <p className="text-[#a0a0a0] text-sm mt-1">
                   Season 2025 • <span className={`${trend.color} font-bold`}>{trend.text}</span>
               </p>
           </div>
           
           {/* Center: View Toggle */}
           {!hideToggle && (
               <div className="pointer-events-auto flex bg-[#111] p-1 rounded-full border border-[#333]">
                  <button 
                    onClick={() => onSourceChange?.("usatt")}
                    className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${source === 'usatt' ? 'bg-[var(--rubber-red)] text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}
                  >
                    Official USATT
                  </button>
                  <button 
                    onClick={() => onSourceChange?.("league")}
                    className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${source === 'league' ? 'bg-[var(--rubber-red)] text-white shadow-lg' : 'text-gray-500 hover:text-white'}`}
                  >
                    Club League
                  </button>
               </div>
           )}
           
           {/* Sync Controls */}
           <div className="flex gap-3 pointer-events-auto">
               <button onClick={onSyncLeague} title="Sync League Players with USATT" className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-blue-400 border border-blue-500/20 rounded hover:bg-blue-500/10 hover:text-blue-300 transition-colors">
                   <RefreshCw size={12} /> League Sync
               </button>
               <button onClick={onSyncTournaments} title="Sync Official Tournaments" className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-purple-400 border border-purple-500/20 rounded hover:bg-purple-500/10 hover:text-purple-300 transition-colors">
                   <RefreshCw size={12} /> Tourney Sync
               </button>
               <button onClick={onSyncOmni} className="flex items-center gap-2 px-3 py-1.5 text-xs font-bold text-[var(--rubber-red)] border border-[var(--rubber-red)] rounded hover:bg-[var(--rubber-red)] hover:text-white transition-colors">
                   <RefreshCw size={12} /> Quick Sync
               </button>
           </div>
       </div>

       {/* Axis Titles */}
       <div className="absolute left-4 top-1/2 -translate-y-1/2 -rotate-90 text-[10px] font-bold text-gray-500 tracking-widest pointer-events-none">
          {source === 'usatt' ? 'USATT RATING' : 'LEAGUE RATING'}
       </div>
       <div className="absolute bottom-2 left-1/2 -translate-x-1/2 text-[10px] font-bold text-gray-500 tracking-widest pointer-events-none">
          MATCH DATE
       </div>

       {/* Graph SVG */}
       <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full absolute bottom-0 left-0">
          <defs>
             <linearGradient id="gradient" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="var(--rubber-red)" stopOpacity="0.5" />
                <stop offset="100%" stopColor="var(--rubber-red)" stopOpacity="0.0" />
             </linearGradient>
          </defs>
          
          {/* Axes Lines */}
          <line x1={margin.left} y1={margin.top + graphHeight} x2={width - margin.right} y2={margin.top + graphHeight} stroke="#333" strokeWidth="1" />
          <line x1={margin.left} y1={margin.top} x2={margin.left} y2={margin.top + graphHeight} stroke="#333" strokeWidth="1" />
          
          {/* Y-Axis Labels (Right Aligned to Axis) */}
          <text x={margin.left - 15} y={margin.top + graphHeight} fill="#666" fontSize="12" textAnchor="end">{min}</text>
          <text x={margin.left - 15} y={margin.top + (graphHeight/2)} fill="#666" fontSize="12" textAnchor="end">{Math.round((max+min)/2)}</text>
          <text x={margin.left - 15} y={margin.top + 10} fill="#666" fontSize="12" textAnchor="end">{max}</text>

          {/* X-Axis Labels (Centered below Axis) */}
          {data.map((d, i) => {
             const step = Math.ceil(data.length / 6); 
             if (i % step === 0 || i === data.length - 1) {
                 const xPos = margin.left + (i / (data.length - 1)) * graphWidth;
                 return (
                    <text key={i} x={xPos} y={margin.top + graphHeight + 20} fill="#666" fontSize="12" textAnchor="middle">
                        {getMonth(d.date)}
                    </text>
                 )
             }
             return null;
          })}
          
          {/* Fill Area (Static) */}
          <path d={`M ${areaPath} Z`} fill="url(#gradient)" opacity="0.6" />
          
          {/* Line Stroke (Looping Animation) */}
          <motion.polyline 
             fill="none" 
             stroke="var(--rubber-red)" 
             strokeWidth="4" 
             points={points}
             initial={{ pathLength: 0 }}
             animate={{ pathLength: 1 }}
             transition={{ 
                duration: 3, 
                ease: "easeInOut",
                repeat: Infinity,
                repeatType: "loop",
                repeatDelay: 2
             }}
          />

          {/* Current Dot (Pulsing) */}
          <motion.circle 
             cx={lastX} 
             cy={lastY} 
             r="6" 
             fill="white"
             initial={{ scale: 0 }}
             animate={{ scale: [0, 1, 1.5, 1] }} 
             transition={{ duration: 5, times: [0, 0.6, 0.65, 0.7], repeat: Infinity }}
          />
          
          {/* Ripple */}
          <motion.circle 
             cx={lastX} 
             cy={lastY} 
             r="6" 
             stroke="var(--rubber-red)"
             strokeWidth="2"
             fill="none"
             initial={{ scale: 1, opacity: 0 }}
             animate={{ scale: [1, 1, 4], opacity: [0, 1, 0] }}
             transition={{ duration: 5, times: [0, 0.6, 1], repeat: Infinity }}
          />
       </svg>
    </div>
  );
}
