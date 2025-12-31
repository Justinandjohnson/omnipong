"use client";
import React, { useEffect, useState } from 'react';
import { Trophy, Skull, Activity, Calendar, Trash2, Shield } from 'lucide-react';
import ScoutingReport from './ScoutingReport';

interface Match {
    id: number;
    opponent_name: string;
    result: string;
    score_summary: string;
    date: string;
    is_win: boolean;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function ArcadeMatchList({ refreshTrigger }: { refreshTrigger: number }) {
    const [matches, setMatches] = useState<Match[]>([]);
    const [loading, setLoading] = useState(true);
    const [scoutingPlayer, setScoutingPlayer] = useState<string | null>(null);

    const fetchMatches = async () => {
        try {
            const res = await fetch(`${API_URL}/matches?source=arcade`);
            const data = await res.json();
            setMatches(data);
        } catch (e) {
            console.error("Failed to fetch arcade matches", e);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (id: number) => {
        if (!confirm("Are you sure you want to delete this match?")) return;
        try {
            await fetch(`${API_URL}/matches/${id}`, { method: 'DELETE' });
            fetchMatches(); // Refresh immediately
        } catch (e) {
            alert("Failed to delete match");
        }
    };

    useEffect(() => {
        fetchMatches();
        
        // Poll every 5 seconds for new SMS matches
        const interval = setInterval(() => {
            fetchMatches();
        }, 5000);
        
        return () => clearInterval(interval);
    }, [refreshTrigger]);

    if (loading) return <div className="text-center text-gray-500 animate-pulse">Loading Arcade History...</div>;

    if (matches.length === 0) {
        return (
            <div className="p-6 border border-[#333] border-dashed rounded-xl text-center text-gray-500">
                <Activity className="mx-auto mb-2 opacity-50" />
                No arcade matches logged yet. <br/> Text the bot or use the form above!
            </div>
        );
    }

    return (
        <div className="space-y-3">
            <h3 className="text-xs font-bold text-[var(--foreground)] uppercase ml-1 opacity-70">Recent Activity</h3>
            {matches.slice(0, 5).map((m, i) => (
                <div key={i} className="bg-[#0f0214] border border-[#333] hover:border-[var(--rubber-red)] p-4 rounded-xl flex justify-between items-center group transition-all relative pr-20">
                    <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${m.is_win ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                            {m.is_win ? <Trophy size={16} /> : <Skull size={16} />}
                        </div>
                        <div>
                            <div className="font-bold text-white flex items-center gap-2">
                                <span className="cursor-help" onClick={() => setScoutingPlayer(m.opponent_name)}>vs {m.opponent_name}</span>
                                <span className={`text-xs px-2 py-0.5 rounded-full ${m.is_win ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                    {m.result}
                                </span>
                            </div>
                            <div className="text-xs text-gray-500 flex items-center gap-2 mt-0.5">
                                <Calendar size={10} />
                                {m.date}
                            </div>
                        </div>
                    </div>
                    
                    <div className="text-right">
                        <div className="text-xl font-mono font-bold text-white tracking-widest">{m.score_summary}</div>
                    </div>

                    <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all">
                        <button 
                            onClick={() => setScoutingPlayer(m.opponent_name)}
                            className="p-2 text-gray-500 hover:text-[var(--rubber-red)] transition-all"
                            title="Scouting Report"
                        >
                            <Shield size={16} />
                        </button>
                        <button 
                            onClick={() => handleDelete(m.id)}
                            className="p-2 text-gray-500 hover:text-red-500 transition-all"
                            title="Delete Match"
                        >
                            <Trash2 size={16} />
                        </button>
                    </div>
                </div>
            ))}

            {scoutingPlayer && (
                <ScoutingReport 
                    playerName={scoutingPlayer} 
                    onClose={() => setScoutingPlayer(null)} 
                />
            )}
        </div>
    );
}

