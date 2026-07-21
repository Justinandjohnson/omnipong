"use client";
import Sidebar from "@/components/Sidebar";
import { useState } from "react";
import { Search, User, Trophy, TrendingUp, Loader2, AlertCircle } from "lucide-react";
import { getAIHeaders, getStoredKey } from "@/components/DemoBar";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Tier-1 public lookup — no login. Type a name, we ask the backend to look
 * up the real USATT rating/history/tournaments (real browser via the relay
 * on the backend side, since USATT is Cloudflare-walled to plain fetch —
 * see docs/AGENT_PLATFORM_BUILD_PLAN.md Tier 1). This page only calls the
 * backend and renders what it returns.
 *
 * Contract this page assumes from Agent F's backend (documented here since
 * it wasn't frozen in the architecture spec — flag if F picks something else):
 *
 *   GET /tools/lookup/usatt?name=<name>
 *     resp success: { status: "success", player: { name, usatt_id, rating, state },
 *                      rating_history: [{ date, rating }],
 *                      tournaments: [{ title, date_range, location, result }] }
 *     resp miss:    { status: "not_found", message: string }
 *     resp error:   { error: { type, detail } }
 */

interface Player {
  name: string;
  usatt_id?: string | number;
  rating?: number;
  state?: string;
}
interface RatingPoint {
  date: string;
  rating: number;
}
interface TournamentResult {
  title: string;
  date_range?: string;
  location?: string;
  result?: string;
}

type Status = "idle" | "loading" | "found" | "not_found" | "error";

export default function LookupPage() {
  const [name, setName] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [player, setPlayer] = useState<Player | null>(null);
  const [history, setHistory] = useState<RatingPoint[]>([]);
  const [tournaments, setTournaments] = useState<TournamentResult[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  async function handleSearch() {
    const trimmed = name.trim();
    if (!trimmed || status === "loading") return;

    if (!getStoredKey()) {
      setStatus("error");
      setMessage(
        "Add your OpenRouter key first (top bar) — the browser agent needs it to look you up. " +
          '(This is separate from USATT login — USATT itself needs "No login required".)'
      );
      return;
    }

    setStatus("loading");
    setMessage(null);

    try {
      const res = await fetch(`${API_URL}/tools/lookup/usatt?name=${encodeURIComponent(trimmed)}`, {
        headers: { ...getAIHeaders() },
      });
      const data = await res.json();

      if (!res.ok || data.error) {
        throw new Error(data?.error?.detail || `HTTP ${res.status}`);
      }
      if (data.status === "not_found") {
        setStatus("not_found");
        setMessage(data.message || `No USATT record found for "${trimmed}"`);
        setPlayer(null);
        setHistory([]);
        setTournaments([]);
        return;
      }

      setPlayer(data.player ?? null);
      setHistory(data.rating_history ?? []);
      setTournaments(data.tournaments ?? []);
      setStatus("found");
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Lookup failed");
    }
  }

  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      <main className="flex-1 md:ml-64 pt-14 md:pt-0 p-8 overflow-y-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Search className="text-[var(--rubber-red)]" size={28} />
            Find Yourself
          </h1>
          <p className="text-gray-400">
            Type your name to look up your real USATT rating, history, and tournaments.
            No login required.
          </p>
        </header>

        <div className="max-w-xl mb-8">
          <div className="flex gap-2">
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Your full name, e.g. Ada Lovelace"
              className="flex-1 p-3 bg-[#111] rounded-lg border border-[#333] text-sm text-gray-200 placeholder:text-gray-600 focus:border-[var(--rubber-red)] focus:outline-none transition-colors"
            />
            <button
              onClick={handleSearch}
              disabled={!name.trim() || status === "loading"}
              className="flex items-center gap-2 rounded-lg bg-[var(--rubber-red)] px-5 py-3 text-sm font-bold text-white disabled:opacity-40 disabled:cursor-not-allowed hover:brightness-110 transition-all"
            >
              {status === "loading" ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
              {status === "loading" ? "Looking..." : "Find me"}
            </button>
          </div>
        </div>

        {status === "not_found" && (
          <div className="max-w-xl p-6 text-center border border-dashed border-[#333] rounded-xl text-gray-500">
            <AlertCircle className="mx-auto mb-2 opacity-50" />
            {message}
          </div>
        )}

        {status === "error" && (
          <div className="max-w-xl p-6 text-center border border-red-800/30 bg-red-900/10 rounded-xl text-red-400">
            Lookup failed: {message}
          </div>
        )}

        {status === "found" && player && (
          <div className="max-w-4xl space-y-6">
            {/* Player card */}
            <section className="bg-[var(--card)] p-6 rounded-2xl border border-[#333] flex items-center gap-6">
              <div className="w-16 h-16 rounded-full bg-gradient-to-br from-[var(--rubber-red)] to-[var(--rubber-accent)] flex items-center justify-center">
                <User size={28} className="text-white" />
              </div>
              <div className="flex-1 grid grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-gray-500 uppercase font-bold tracking-wider">Name</label>
                  <div className="text-lg font-bold text-white">{player.name}</div>
                </div>
                <div>
                  <label className="text-xs text-gray-500 uppercase font-bold tracking-wider">USATT #</label>
                  <div className="text-lg text-gray-300">{player.usatt_id ?? "N/A"}</div>
                </div>
                <div>
                  <label className="text-xs text-gray-500 uppercase font-bold tracking-wider">Rating</label>
                  <div className="text-lg font-bold text-[var(--rubber-red)]">{player.rating ?? "N/A"}</div>
                </div>
              </div>
            </section>

            {/* Rating history */}
            {history.length > 0 && (
              <section className="bg-[var(--card)] p-6 rounded-2xl border border-[#333]">
                <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <TrendingUp size={16} /> Rating History
                </h2>
                <div className="space-y-2">
                  {history.map((p, i) => (
                    <div key={i} className="flex justify-between text-sm border-b border-[#222] pb-2 last:border-0">
                      <span className="text-gray-400 font-mono text-xs">{p.date}</span>
                      <span className="font-bold text-white">{p.rating}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Tournaments */}
            {tournaments.length > 0 && (
              <section className="bg-[var(--card)] p-6 rounded-2xl border border-[#333]">
                <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <Trophy size={16} /> Tournaments
                </h2>
                <div className="space-y-3">
                  {tournaments.map((t, i) => (
                    <div key={i} className="p-3 bg-[#111] rounded-lg border border-[#333]">
                      <div className="flex justify-between items-start">
                        <span className="font-medium text-white">{t.title}</span>
                        {t.result && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-gray-300">
                            {t.result}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {[t.date_range, t.location].filter(Boolean).join(" · ")}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
