import { Users, TrendingUp, Target, Calendar, Award } from 'lucide-react';
import { useEffect, useState } from 'react';

export default function PracticePartners({ limit = 5, className = "" }: { limit?: number, className?: string }) {
  const [partners, setPartners] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`http://localhost:8000/tools/practice_partners?limit=${limit}`)
      .then(res => res.json())
      .then(data => {
        setPartners(data.recommendations || []);
        setLoading(false);
      })
      .catch(e => {
        console.error('Failed to load practice partners:', e);
        setLoading(false);
      });
  }, [limit]);

  if (loading) {
    return (
      <div className="bg-[#1a1a1a] rounded-2xl border border-[#333] p-6 h-full">
        <div className="flex items-center gap-2 mb-6">
          <Users size={20} className="text-[var(--rubber-red)]" />
          <h2 className="text-lg font-bold">Practice Partners</h2>
        </div>
        <div className="space-y-4">
          {[1,2,3].map(i => (
            <div key={i} className="h-20 bg-[#222] animate-pulse rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={`bg-[#1a1a1a] rounded-2xl border border-[#333] p-6 ${className}`}>
      <div className="flex items-center gap-2 mb-6">
        <Users size={20} className="text-[var(--rubber-red)]" />
        <h2 className="text-lg font-bold">Practice Partners</h2>
      </div>

      {partners.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <Users size={48} className="mx-auto mb-4 opacity-20" />
          <p>No practice partner recommendations yet.</p>
          <p className="text-xs mt-2">Play more matches to get recommendations!</p>
        </div>
      ) : (
        <div className="space-y-4">
          {partners.map((partner, i) => (
            <div
              key={i}
              className="bg-[#222] rounded-xl p-4 border border-[#333] hover:border-[var(--rubber-red)] transition-all cursor-pointer group"
            >
              {/* Header with Rank */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg font-bold text-white group-hover:text-[var(--rubber-red)] transition-colors">
                      {partner.player_name}
                    </span>
                    <span className="text-xs font-bold px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      {partner.rating}
                    </span>
                  </div>
                  <div className="text-xs text-gray-400">
                    Record: {partner.wins}-{partner.losses} • {partner.match_count} matches
                  </div>
                </div>
                <div className="text-2xl font-bold text-[var(--rubber-red)]">
                  #{i + 1}
                </div>
              </div>

              {/* Score Breakdown */}
              <div className="grid grid-cols-2 gap-2 mb-3">
                <div className="flex items-center gap-2 text-xs">
                  <Target size={12} className="text-green-400" />
                  <span className="text-gray-400">Skill Match:</span>
                  <span className="font-bold text-green-400">{Math.round((partner.scores?.skill_match || 0) * 100)}%</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <TrendingUp size={12} className="text-yellow-400" />
                  <span className="text-gray-400">Competitive:</span>
                  <span className="font-bold text-yellow-400">{Math.round((partner.scores?.competitiveness || 0) * 100)}%</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <Award size={12} className="text-purple-400" />
                  <span className="text-gray-400">Win Rate:</span>
                  <span className="font-bold text-purple-400">{Math.round((partner.scores?.win_rate_balance || 0) * 100)}%</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <Calendar size={12} className="text-blue-400" />
                  <span className="text-gray-400">Recent:</span>
                  <span className="font-bold text-blue-400">{Math.round((partner.scores?.recent_activity || 0) * 100)}%</span>
                </div>
              </div>

              {/* Reason */}
              <div className="pt-3 border-t border-[#2a2a2a]">
                <p className="text-xs text-gray-300 leading-relaxed">
                  {partner.reason}
                </p>
              </div>

              {/* Overall Score Bar */}
              <div className="mt-3">
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-gray-500 font-bold">Overall Match Score</span>
                  <span className="text-[var(--rubber-red)] font-bold">{Math.round(partner.total_score * 100)}%</span>
                </div>
                <div className="h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-[var(--rubber-red)] to-[var(--rubber-accent)] rounded-full transition-all duration-500"
                    style={{ width: `${partner.total_score * 100}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
