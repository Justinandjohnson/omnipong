import { Shield, Target, Zap, X, TrendingUp, Info } from 'lucide-react';
import { useState, useEffect } from 'react';

export default function ScoutingReport({ playerName, onClose }: { playerName: string, onClose: () => void }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/players/${playerName}/scouting`)
      .then(res => res.json())
      .then(json => {
        setData(json);
        setLoading(false);
      })
      .catch(err => {
        console.error("Scouting Error:", err);
        setLoading(false);
      });
  }, [playerName]);

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
        <div className="bg-[#1a1a1a] border border-[#333] rounded-2xl p-8 max-w-md w-full text-center">
          <div className="animate-spin mb-4 inline-block">🏓</div>
          <p className="text-gray-400">Rubberr is analyzing patterns for {playerName}...</p>
        </div>
      </div>
    );
  }

  if (!data || data.status === 'error') {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
        <div className="bg-[#1a1a1a] border border-[#333] rounded-2xl p-6 max-w-md w-full relative">
          <button onClick={onClose} className="absolute top-4 right-4 text-gray-500 hover:text-white"><X size={20}/></button>
          <div className="text-center">
            <Info size={48} className="mx-auto text-yellow-500 mb-4 opacity-50" />
            <h3 className="text-lg font-bold mb-2">No Scouting Data</h3>
            <p className="text-gray-400 text-sm">{data?.message || "Could not find enough match history to generate a report."}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-[#1a1a1a] border border-[#333] rounded-2xl max-w-2xl w-full my-8 relative shadow-2xl">
        {/* Header */}
        <div className="p-6 border-b border-[#333] flex items-center justify-between bg-gradient-to-r from-[var(--rubber-red)]/10 to-transparent rounded-t-2xl">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[var(--rubber-red)] rounded-lg">
              <Shield className="text-white" size={20} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white uppercase tracking-tight">Scouting Report</h2>
              <p className="text-[var(--rubber-red)] font-bold text-sm tracking-widest">{playerName.toUpperCase()}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors bg-[#222] p-2 rounded-full border border-[#333]">
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-8">
          {/* Stats Bar */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-[#222] p-4 rounded-xl border border-[#333] text-center">
              <p className="text-xs text-gray-500 font-bold mb-1">RECORD</p>
              <p className="text-lg font-bold text-white">{data.stats.record}</p>
            </div>
            <div className="bg-[#222] p-4 rounded-xl border border-[#333] text-center">
              <p className="text-xs text-gray-500 font-bold mb-1">WIN RATE</p>
              <p className="text-lg font-bold text-white">{data.stats.win_rate}</p>
            </div>
            <div className="bg-[#222] p-4 rounded-xl border border-[#333] text-center">
              <p className="text-xs text-gray-500 font-bold mb-1">MATCHES</p>
              <p className="text-lg font-bold text-white">{data.stats.total_matches}</p>
            </div>
          </div>

          {/* Analysis Text */}
          <div className="bg-[#111] border border-[#222] rounded-xl p-6 relative overflow-hidden group">
             <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                <Target size={120} />
             </div>
             
             <h3 className="flex items-center gap-2 text-[var(--rubber-red)] font-bold text-sm mb-4">
                <Zap size={14} /> AI STYLE PROFILE & STRATEGY
             </h3>
             
             <div className="prose prose-invert prose-sm max-w-none text-gray-300 whitespace-pre-line leading-relaxed">
                {data.analysis}
             </div>
          </div>

          {/* Tips Footer */}
          <div className="flex items-center gap-4 bg-blue-500/10 border border-blue-500/20 p-4 rounded-xl">
             <div className="bg-blue-500/20 p-2 rounded-lg">
                <Info size={16} className="text-blue-400" />
             </div>
             <p className="text-xs text-blue-200/80 leading-normal">
                This report is based on your specific match history and pattern recognition. Always adapt your strategy in real-time as the opponent adjusts.
             </p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-[#333] text-center">
           <button 
             onClick={onClose}
             className="w-full bg-[#222] hover:bg-[#333] text-white py-3 rounded-xl font-bold transition-all border border-[#333]"
           >
              CLOSE DOSSIER
           </button>
        </div>
      </div>
    </div>
  );
}
