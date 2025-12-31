import { Zap, Target, TrendingDown, BookOpen, RefreshCw } from 'lucide-react';
import { useState, useEffect } from 'react';

export default function DrillLab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetchRecommendations = () => {
    setLoading(true);
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/training/recommendations`)
      .then(res => res.json())
      .then(json => {
        setData(json);
        setLoading(false);
      })
      .catch(err => {
        console.error("Training Recommendations Error:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchRecommendations();
  }, []);

  if (loading) {
    return (
      <div className="bg-[#1a1a1a] rounded-2xl border border-[#333] p-6 h-full animate-pulse">
        <div className="h-4 w-32 bg-[#222] rounded mb-4"></div>
        <div className="space-y-3">
          <div className="h-20 bg-[#222] rounded-xl"></div>
          <div className="h-32 bg-[#222] rounded-xl"></div>
        </div>
      </div>
    );
  }

  if (!data || data.status === 'error') {
     return null; // Don't show if error
  }

  return (
    <div className="bg-[#1a1a1a] rounded-2xl border border-[#333] p-6 h-full relative overflow-hidden group">
      {/* Background Decor */}
      <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none group-hover:opacity-10 transition-opacity">
         <BookOpen size={120} />
      </div>

      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Zap size={20} className="text-yellow-400 fill-yellow-400/20" />
          <h2 className="text-lg font-bold">Drill Lab</h2>
        </div>
        <button 
          onClick={fetchRecommendations}
          className="text-gray-500 hover:text-white transition-colors p-1"
          title="Refresh Analysis"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Pattern Analysis Tags */}
      <div className="flex flex-wrap gap-2 mb-6">
         {data.patterns?.chokes > data.patterns?.comebacks && (
            <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/10 text-red-500 text-[10px] font-bold border border-red-500/20 uppercase tracking-wider">
               <TrendingDown size={10} /> Closing Issue
            </span>
         )}
         {data.patterns?.clutch_percent < 50 && (
            <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-orange-500/10 text-orange-400 text-[10px] font-bold border border-orange-500/20 uppercase tracking-wider">
               <Target size={10} /> Deuce Struggles
            </span>
         )}
         {data.patterns?.comebacks > 0 && (
            <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-green-500/10 text-green-500 text-[10px] font-bold border border-green-500/20 uppercase tracking-wider">
               <Zap size={10} /> Comeback King
            </span>
         )}
         <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 text-blue-400 text-[10px] font-bold border border-blue-500/20 uppercase tracking-wider">
            {data.total_matches} Match Analysis
         </span>
      </div>

      {/* Coach's Advice */}
      <div className="space-y-4">
        <div className="bg-[#111] border border-[#222] p-4 rounded-xl relative">
          <div className="text-xs font-bold text-yellow-400/80 mb-2 uppercase tracking-widest flex items-center gap-2">
             <BookOpen size={12} /> Coach's Focus
          </div>
          <div className="text-gray-300 text-sm leading-relaxed italic">
            “{data.coach_advice}”
          </div>
        </div>

        <div className="pt-2 border-t border-[#333]">
           <p className="text-[10px] font-bold text-gray-500 mb-2 uppercase tracking-widest italic">
              AI-Generated Path to Pro
           </p>
        </div>
      </div>
    </div>
  );
}
