"use client";
import Sidebar from "@/components/Sidebar";
import { useEffect, useState } from "react";
import { Trophy, TrendingUp, TrendingDown } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Match {
  id: number;
  date: string;
  opponent_name: string;
  opponent_rating: number;
  score_summary: string;
  set_scores: string;
  result: string;
  source: string;
}

function ResultBadge({ result }: { result: string }) {
  const isWin =
    result === 'Win' ||
    result === 'W' ||
    (result.includes('-') && parseInt(result.split('-')[0]) > parseInt(result.split('-')[1]));

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold ${
        isWin ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'
      }`}
    >
      {isWin ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
      {isWin ? 'Win' : 'Loss'}
    </span>
  );
}

export default function ScoreboardPage() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<'all' | 'omnipong' | 'stadium' | 'arcade'>('all');

  useEffect(() => {
    setLoading(true);
    setError(null);
    const url = source === 'all'
      ? `${API_URL}/matches`
      : `${API_URL}/matches?source=${source}`;

    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setMatches(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [source]);

  const wins = matches.filter(m =>
    m.result === 'Win' || m.result === 'W' ||
    (m.result.includes('-') && parseInt(m.result.split('-')[0]) > parseInt(m.result.split('-')[1]))
  ).length;
  const losses = matches.length - wins;

  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      <main className="flex-1 ml-64 p-8 overflow-y-auto">
        <header className="mb-8 flex justify-between items-end">
          <div>
            <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
              <Trophy className="text-[var(--rubber-red)]" size={28} />
              Scoreboard
            </h1>
            <p className="text-gray-400">Your complete match record.</p>
          </div>

          {/* Source Filter */}
          <div className="flex bg-[#111] p-1 rounded-full border border-[#333] shadow-lg gap-1">
            {(['all', 'omnipong', 'stadium', 'arcade'] as const).map(s => (
              <button
                key={s}
                onClick={() => setSource(s)}
                className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all capitalize ${
                  source === s ? 'bg-[var(--rubber-red)] text-white shadow-md' : 'text-gray-500 hover:text-white'
                }`}
              >
                {s === 'omnipong' ? 'USATT' : s === 'stadium' ? 'Club' : s}
              </button>
            ))}
          </div>
        </header>

        {/* Summary Stats */}
        {!loading && !error && (
          <div className="grid grid-cols-4 gap-4 mb-8">
            {[
              { label: 'Total Matches', value: matches.length.toString() },
              { label: 'Wins', value: wins.toString(), color: 'text-green-400' },
              { label: 'Losses', value: losses.toString(), color: 'text-red-400' },
              {
                label: 'Win Rate',
                value: matches.length > 0 ? `${Math.round((wins / matches.length) * 100)}%` : '—',
                color: wins / matches.length >= 0.5 ? 'text-green-400' : 'text-red-400',
              },
            ].map(stat => (
              <div key={stat.label} className="bg-[#171717] border border-[#333] rounded-xl p-4">
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{stat.label}</p>
                <p className={`text-2xl font-bold ${stat.color || 'text-white'}`}>{stat.value}</p>
              </div>
            ))}
          </div>
        )}

        {/* Match Table */}
        {loading && (
          <div className="space-y-3">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="h-14 bg-[#171717] border border-[#333] rounded-xl animate-pulse" />
            ))}
          </div>
        )}

        {error && (
          <div className="p-8 text-center border border-red-800/30 bg-red-900/10 rounded-xl text-red-400">
            Failed to load match history: {error}
            <br />
            <span className="text-gray-500 text-sm">Make sure the backend is running at {API_URL}</span>
          </div>
        )}

        {!loading && !error && matches.length === 0 && (
          <div className="p-12 text-center border border-dashed border-[#333] rounded-xl text-gray-500">
            No matches found. Run a Sync from the Dashboard to import your match history.
          </div>
        )}

        {!loading && !error && matches.length > 0 && (
          <div className="bg-[#111] border border-[#333] rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#333] text-xs text-gray-500 uppercase tracking-wider">
                  <th className="text-left px-5 py-3">Date</th>
                  <th className="text-left px-5 py-3">Opponent</th>
                  <th className="text-right px-5 py-3">Opp. Rating</th>
                  <th className="text-left px-5 py-3">Score</th>
                  <th className="text-left px-5 py-3">Sets</th>
                  <th className="text-left px-5 py-3">Result</th>
                  <th className="text-left px-5 py-3">Source</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m, i) => (
                  <tr
                    key={m.id ?? i}
                    className="border-b border-[#222] hover:bg-[#1a1a1a] transition-colors"
                  >
                    <td className="px-5 py-3 text-gray-400 font-mono text-xs">{m.date}</td>
                    <td className="px-5 py-3 font-medium text-white">{m.opponent_name}</td>
                    <td className="px-5 py-3 text-right text-gray-400">{m.opponent_rating ?? '—'}</td>
                    <td className="px-5 py-3 font-mono font-bold">{m.score_summary || '—'}</td>
                    <td className="px-5 py-3 text-gray-400 text-xs">{m.set_scores || '—'}</td>
                    <td className="px-5 py-3">
                      <ResultBadge result={m.result} />
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500">
                        {m.source === 'stadium_league' ? 'League'
                          : m.source === 'stadium' ? 'Club Tourney'
                          : m.source === 'omnipong' ? 'USATT'
                          : m.source === 'arcade' ? 'Arcade'
                          : m.source}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
