"use client";
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Flame, Scale, AlertTriangle } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface PatternData {
    comebacks: number;
    chokes: number;
    close_game_win_rate: number;
}

export default function PatternAnalysis({ source = "usatt" }: { source?: string }) {
  const [patterns, setPatterns] = useState<PatternData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API_URL}/stats?source=${source}`)
      .then(res => res.json())
      .then(d => {
        setPatterns(d.patterns);
        setLoading(false);
      })
      .catch(e => {
        console.error(e);
        setLoading(false);
      });
  }, [source]);

  if (loading || !patterns) return <div className="h-48 bg-[#111] rounded-2xl animate-pulse"></div>;

  return (
    <div className="bg-[#111] rounded-2xl border border-[#333] p-6 h-full flex flex-col">
       <div className="flex justify-items-start mb-4">
           <h3 className="text-gray-400 font-bold text-sm uppercase tracking-wider flex items-center gap-2">
               <Scale size={16} /> Pattern Analysis
           </h3>
       </div>

       <div className="grid grid-cols-1 gap-3">
           {/* Comebacks */}
           <div className="bg-[#1a1a1a] rounded-lg p-3 flex justify-between items-center border border-[#333] hover:border-orange-500/50 transition-colors group relative overflow-hidden">
               <div className="flex items-center gap-3 relative z-10 w-full">
                   <div className="p-1.5 rounded-lg bg-orange-500/10 text-orange-500 group-hover:bg-orange-500 group-hover:text-white transition-colors">
                       <Flame size={16} />
                   </div>
                   <div className="flex-1">
                       <div className="flex justify-between items-end mb-1">
                           <p className="text-xs font-bold text-gray-300">Rally Wins</p>
                           <span className="text-lg font-bold text-white">{patterns.comebacks}</span>
                       </div>
                       <div className="h-1 w-full bg-[#333] rounded-full overflow-hidden">
                           <motion.div 
                              initial={{ width: 0 }}
                              animate={{ width: `${Math.min(patterns.comebacks * 20, 100)}%` }} 
                              transition={{ duration: 1, delay: 0.2 }}
                              className="h-full bg-orange-500 rounded-full"
                           />
                       </div>
                   </div>
               </div>
           </div>

           {/* Close Games */}
           <div className="bg-[#1a1a1a] rounded-lg p-3 flex justify-between items-center border border-[#333] hover:border-blue-500/50 transition-colors group relative overflow-hidden">
                <div className="flex items-center gap-3 relative z-10 w-full">
                   <div className="p-1.5 rounded-lg bg-blue-500/10 text-blue-500 group-hover:bg-blue-500 group-hover:text-white transition-colors">
                       <Scale size={16} />
                   </div>
                   <div className="flex-1">
                       <div className="flex justify-between items-end mb-1">
                           <p className="text-xs font-bold text-gray-300">Pressure Play</p>
                           <span className="text-lg font-bold text-white">{patterns.close_game_win_rate}%</span>
                       </div>
                       <div className="h-1 w-full bg-[#333] rounded-full overflow-hidden">
                           <motion.div 
                              initial={{ width: 0 }}
                              animate={{ width: `${patterns.close_game_win_rate}%` }}
                              transition={{ duration: 1, delay: 0.4 }}
                              className="h-full bg-blue-500 rounded-full"
                           />
                       </div>
                   </div>
               </div>
           </div>

           {/* Chokes */}
           <div className="bg-[#1a1a1a] rounded-lg p-3 flex justify-between items-center border border-[#333] hover:border-red-500/50 transition-colors group relative overflow-hidden">
                <div className="flex items-center gap-3 relative z-10 w-full">
                   <div className="p-1.5 rounded-lg bg-red-500/10 text-red-500 group-hover:bg-red-500 group-hover:text-white transition-colors">
                       <AlertTriangle size={16} />
                   </div>
                   <div className="flex-1">
                       <div className="flex justify-between items-end mb-1">
                           <p className="text-xs font-bold text-gray-300">Lost Leads</p>
                           <span className="text-lg font-bold text-white">{patterns.chokes}</span>
                       </div>
                       <div className="h-1 w-full bg-[#333] rounded-full overflow-hidden">
                           <motion.div 
                              initial={{ width: 0 }}
                              animate={{ width: `${Math.min(patterns.chokes * 10, 100)}%` }}
                              transition={{ duration: 1, delay: 0.6 }}
                              className="h-full bg-red-500 rounded-full"
                           />
                       </div>
                   </div>
               </div>
           </div>
       </div>

       {/* Insight Text */}
       <div className="mt-4 pt-4 border-t border-[#222]">
           <p className="text-xs text-gray-400 italic">
               "{patterns.close_game_win_rate > 50 ? "You thrive under pressure." : "Focus on closing out tight games."} 
                {patterns.comebacks > 0 ? " Never count you out!" : ""}"
           </p>
       </div>
    </div>
  );
}
