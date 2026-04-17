"use client";
import Sidebar from "@/components/Sidebar";
import CareerGraph from "@/components/CareerGraph";
import RubberrStats from "@/components/RubberrStats";
import { useEffect, useState } from "react";
import { Flame, AlertTriangle, Scale } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function AnalyticsPage() {
  const [matches, setMatches] = useState<any[]>([]);
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<"usatt" | "league">("league");
  const [badgeFilter, setBadgeFilter] = useState("all"); // 'all', 'rally', 'choke', 'tight'

  useEffect(() => {
    setLoading(true);
    // Parallel Fetch
    Promise.all([
        fetch(`${API_URL}/matches`).then(r => r.json()),
        fetch(`${API_URL}/user`).then(r => r.json())
    ]).then(([matchesData, userData]) => {
        // Filter matches based on viewMode
        const targetSources = viewMode === 'usatt' ? ['omnipong'] : ['stadium', 'stadium_league'];
        const filtered = matchesData.filter((m: any) => targetSources.includes(m.source));
        setMatches(filtered);
        setUser(userData);
        setLoading(false);
    });
  }, [viewMode]);

  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      <main className="flex-1 ml-64 p-8 overflow-y-auto h-screen">
        <header className="mb-8 flex justify-between items-end">
          <div>
            <h1 className="text-3xl font-bold mb-2">Performance Analytics</h1>
            <p className="text-gray-400">Deep dive into your match history and rating trends.</p>
          </div>
          
          <div className="flex bg-[#111] p-1 rounded-full border border-[#333] shadow-lg">
              <button 
                onClick={() => setViewMode("usatt")}
                className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${viewMode === 'usatt' ? 'bg-[var(--rubber-red)] text-white shadow-md' : 'text-gray-500 hover:text-white'}`}
              >
                Official USATT
              </button>
              <button 
                onClick={() => setViewMode("league")}
                className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${viewMode === 'league' ? 'bg-[var(--rubber-red)] text-white shadow-md' : 'text-gray-500 hover:text-white'}`}
              >
                Club League
              </button>
           </div>
        </header>

        <div className="flex flex-col gap-8">
            {/* Top Section: Visuals */}
            <div className="grid grid-cols-12 gap-6">
                <div className="col-span-12 lg:col-span-8 h-80">
                    <CareerGraph source={viewMode} hideToggle={true} />
                </div>
                <div className="col-span-12 lg:col-span-4">
                    <RubberrStats rating={user?.rating || 0} source={viewMode} />
                </div>
            </div>

            {/* Bottom Section: Mosaic Match History */}
            <div>
                <div className="flex justify-between items-center mb-6 border-b border-[#333] pb-4">
                    <div className="flex items-center gap-4">
                        <h2 className="text-xl font-bold">Match History</h2>
                        <span className="text-xs text-gray-500 uppercase tracking-widest border-l border-[#333] pl-4">{matches.length} Matches</span>
                    </div>

                    {/* Badge Filters */}
                    <div className="flex gap-2">
                        <button onClick={() => setBadgeFilter("all")} className={`px-3 py-1 rounded-lg text-[10px] font-bold uppercase transition-all border ${badgeFilter === 'all' ? 'bg-white text-black border-white' : 'bg-[#111] text-gray-500 border-[#333] hover:border-gray-500'}`}>All</button>
                        
                        <button onClick={() => setBadgeFilter("rally")} className={`px-3 py-1 rounded-lg text-[10px] font-bold uppercase transition-all border flex items-center gap-1.5 ${badgeFilter === 'rally' ? 'bg-orange-500/20 text-orange-400 border-orange-500' : 'bg-[#111] text-gray-500 border-[#333] hover:border-orange-500/50 hover:text-orange-400'}`}>
                            <Flame size={12} /> Rally
                        </button>
                        
                        <button onClick={() => setBadgeFilter("choke")} className={`px-3 py-1 rounded-lg text-[10px] font-bold uppercase transition-all border flex items-center gap-1.5 ${badgeFilter === 'choke' ? 'bg-blue-500/20 text-blue-400 border-blue-500' : 'bg-[#111] text-gray-500 border-[#333] hover:border-blue-500/50 hover:text-blue-400'}`}>
                            <AlertTriangle size={12} /> Lost Lead
                        </button>
                        
                        <button onClick={() => setBadgeFilter("tight")} className={`px-3 py-1 rounded-lg text-[10px] font-bold uppercase transition-all border flex items-center gap-1.5 ${badgeFilter === 'tight' ? 'bg-gray-500/20 text-gray-300 border-gray-400' : 'bg-[#111] text-gray-500 border-[#333] hover:border-gray-400 hover:text-gray-300'}`}>
                            <Scale size={12} /> Tight
                        </button>
                    </div>
                </div>
                
                {loading ? (
                    <div className="p-8 text-center text-gray-500 animate-pulse">Loading match data...</div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {matches.filter(m => {
                            if (badgeFilter === 'all') return true;
                            if (badgeFilter === 'rally') return m.is_comeback;
                            if (badgeFilter === 'choke') return m.is_choke;
                            if (badgeFilter === 'tight') return m.is_close_game;
                            return true;
                        }).map((m, i) => {
                            // Determine Theme (Liquid Layer)
                            let liquidClass = "bg-abyss"; // Default: Deep Navy 
                            let liquidOpacity = "opacity-0"; // Default: hidden
                            
                            if (m.is_comeback) {
                                liquidClass = "bg-magma animate-liquid";
                                liquidOpacity = "opacity-40";
                            } else if (m.is_choke) {
                                liquidClass = "bg-ice animate-liquid";
                                liquidOpacity = "opacity-40";
                            } else if (m.is_close_game) {
                                liquidClass = "bg-plasma animate-liquid"; // Changed Metal (Grey) to Plasma (Purple)
                                liquidOpacity = "opacity-40";
                            } else {
                                // Standard Win/Loss - subtle
                                const isWin = (m.result === 'Win' || (m.result.includes('-') && parseInt(m.result.split('-')[0]) > parseInt(m.result.split('-')[1])));
                                if (isWin) {
                                    liquidClass = "bg-forest animate-liquid";
                                    liquidOpacity = "opacity-30";
                                } else {
                                    liquidClass = "bg-abyss animate-liquid";
                                    liquidOpacity = "opacity-60"; // Visible Abyss for losses
                                }
                            }

                            return (
                                <div 
                                    key={i} 
                                    className="bg-[#1a1a1a] rounded-xl border border-[#333] p-5 flex flex-col gap-4 relative overflow-hidden group hover:border-[#444] hover:shadow-2xl hover:-translate-y-1 transition-all duration-300"
                                >
                                    {/* Liquid Animation Layer (Overlay) */}
                                    <div className={`absolute inset-0 ${liquidClass} ${liquidOpacity} transition-opacity duration-500 z-0 pointer-events-none`} />
                                    
                                    {/* Header: Date & Event */}
                                    <div className="flex justify-between items-start z-10 relative">
                                        <span className="text-[10px] uppercase font-bold text-white/60 tracking-wider">
                                            {m.date}
                                        </span>
                                        <span className="text-[9px] px-2 py-0.5 rounded bg-black/60 backdrop-blur-sm border border-white/10 text-white/90 font-bold uppercase shadow-sm">
                                            {m.source === 'stadium_league' ? 'League' : 
                                             m.source === 'stadium' ? 'Tourney' : 
                                             m.source === 'omnipong' ? 'USATT' : 'Match'}
                                        </span>
                                    </div>

                                    {/* Main: Opponent */}
                                    <div className="z-10 relative">
                                        <h3 className="text-xl font-bold text-white group-hover:text-[var(--rubber-red)] transition-colors line-clamp-1" title={m.opponent_name}>
                                            {m.opponent_name}
                                        </h3>
                                        <p className="text-sm text-white/60">Rating: <span className="text-white/90 font-bold">{m.opponent_rating}</span></p>
                                    </div>

                                    {/* Scores & Badges */}
                                    <div className="mt-auto pt-4 border-t border-white/10 z-10 relative">
                                        <div className="flex justify-between items-end mb-2">
                                            <div className="flex flex-col gap-1">
                                                <span className={`text-sm font-bold uppercase tracking-wide mb-1 ${
                                                    (m.result === 'Win' || (m.result.includes('-') && parseInt(m.result.split('-')[0]) > parseInt(m.result.split('-')[1]))) 
                                                    ? 'text-green-400' 
                                                    : 'text-red-400'
                                                }`}>
                                                    {m.result}
                                                </span>
                                                
                                                {/* Scorecard Chips */}
                                                <div className="flex flex-wrap gap-1.5 mt-1">
                                                    {(m.score_summary || m.set_scores || "").split(',').map((setScore: string, sIdx: number) => {
                                                        const cleanScore = setScore.trim();
                                                        if (!cleanScore) return null;
                                                        // Highlight the higher number (winner of the set)
                                                        const parts = cleanScore.split('-');
                                                        let p1 = parts[0], p2 = parts[1];
                                                        
                                                        return (
                                                            <div key={sIdx} className="bg-black/40 border border-white/10 px-2 py-1 rounded-md flex items-center gap-1 shadow-sm hover:bg-black/60 transition-colors">
                                                                <span className={`font-mono text-base font-bold ${parseInt(p1) > parseInt(p2) ? 'text-white' : 'text-gray-400'}`}>{p1}</span>
                                                                <span className="text-gray-600 text-xs">-</span>
                                                                <span className={`font-mono text-base font-bold ${parseInt(p2) > parseInt(p1) ? 'text-white' : 'text-gray-400'}`}>{p2}</span>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        </div>
                                        
                                        {/* AI Badges Row */}
                                        <div className="flex flex-wrap gap-2 mt-2 min-h-[20px]">
                                            {m.is_comeback && (
                                                <span className="text-[9px] font-bold uppercase tracking-wider text-orange-400 border border-orange-500/30 px-1.5 py-0.5 rounded flex items-center gap-1 bg-orange-500/10 shadow-[0_0_10px_rgba(249,115,22,0.1)]">
                                                    <Flame size={10} /> Rally Win
                                                </span>
                                            )}
                                            {m.is_choke && (
                                                <span className="text-[9px] font-bold uppercase tracking-wider text-blue-400 border border-blue-500/30 px-1.5 py-0.5 rounded flex items-center gap-1 bg-blue-500/10 shadow-[0_0_10px_rgba(59,130,246,0.1)]">
                                                    <AlertTriangle size={10} /> Lost Lead
                                                </span>
                                            )}
                                            {m.is_close_game && !m.is_comeback && !m.is_choke && (
                                                <span className="text-[9px] font-bold uppercase tracking-wider text-gray-400 border border-gray-600 px-1.5 py-0.5 rounded flex items-center gap-1 bg-gray-500/10">
                                                    <Scale size={10} /> Tight
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>

      </main>
    </div>
  );
}
