"use client";
import { useEffect, useState } from 'react';
import { TrendingUp, Activity, Trophy, Award } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface StatProps {
  label: string;
  value: string;
  subtext: string;
  icon: React.ReactNode;
  trend?: "up" | "down" | "neutral";
}

const StatCard = ({ label, value, subtext, icon }: StatProps) => (
  <div className="bg-[#171717] border border-[#333] p-4 rounded-xl flex items-start justify-between hover:border-[var(--rubber-red)] transition-all group">
    <div>
      <p className="text-gray-400 text-xs font-medium uppercase tracking-wider">{label}</p>
      <h3 className="text-2xl font-bold mt-1 text-white group-hover:text-[var(--rubber-red)] transition-colors">{value}</h3>
      <p className="text-xs text-gray-500 mt-1">{subtext}</p>
    </div>
    <div className="p-2 bg-[#222] rounded-lg text-gray-300 group-hover:bg-[var(--rubber-red)] group-hover:text-white transition-all">
      {icon}
    </div>
  </div>
);

export default function RubberrStats({ rating, source = "usatt" }: { rating: number, source?: string }) {
  const [stats, setStats] = useState<{ win_rate: string, wins: number, losses: number, tournaments: string, trend: string, rating_context: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API_URL}/stats?source=${source}`)
      .then(res => res.json())
      .then(data => {
        setStats(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("Stats fetch error:", err);
        setLoading(false);
      });
  }, [source]);

  if (loading) {
    return <div className="grid grid-cols-2 gap-4 animate-pulse">
      {[1, 2, 3, 4].map(i => <div key={i} className="h-24 bg-[#171717] rounded-xl border border-[#333]"></div>)}
    </div>;
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      <StatCard 
        label="Current Rating" 
        value={rating.toString()} 
        subtext={stats?.rating_context || "Official USATT"} 
        icon={<Trophy size={20} />} 
      />
      <StatCard 
        label="Win Rate" 
        value={stats?.win_rate || "0%"} 
        subtext={stats ? `${stats.wins}W - ${stats.losses}L` : "Match History"} 
        icon={<Activity size={20} />} 
      />
      <StatCard 
        label="Activities" 
        value={stats?.tournaments || "0"} 
        subtext="Unique Sessions" 
        icon={<Award size={20} />} 
      />
      <StatCard 
        label="Trend" 
        value={stats?.trend || "+0"} 
        subtext="Recent Points" 
        icon={<TrendingUp size={20} />} 
      />
    </div>
  );
}
