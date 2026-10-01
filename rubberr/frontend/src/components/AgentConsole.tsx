"use client";

// Agent Console — the GUI half of the OmniPong agent. It POSTs to
// /agent/action, which runs omnipong_agent.run_action() in-process: the same
// six actions the MCP server exposes (omnipong_mcp_server.py). So the app tab
// and any MCP client drive one code path. See docs/OMNIPONG_AGENT.md.

import React, { useEffect, useState } from "react";
import {
  Bot,
  Search,
  RefreshCw,
  ListChecks,
  Play,
  Loader2,
  AlertTriangle,
  Swords,
  User,
  MapPin,
} from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ActionName =
  | "search"
  | "signup"
  | "matches"
  | "sync";

interface ActionMeta {
  id: ActionName;
  label: string;
  blurb: string;
  icon: React.ReactNode;
  danger?: boolean;
}

const ACTIONS: ActionMeta[] = [
  {
    id: "search",
    label: "Search a player",
    blurb: "Look up a player by name and return their rating and state.",
    icon: <Search size={18} />,
  },
  {
    id: "signup",
    label: "Sign up for a tournament",
    blurb: "Register you — real, irreversible. Events default to rating match.",
    icon: <Swords size={18} />,
    danger: true,
  },
  {
    id: "matches",
    label: "My matches",
    blurb: "Pull your latest tournament match results.",
    icon: <ListChecks size={18} />,
  },
  {
    id: "sync",
    label: "Sync everything",
    blurb: "Full crawl: tournaments, leagues, camps, events, details, matches.",
    icon: <RefreshCw size={18} />,
  },
];

export default function AgentConsole() {
  const [action, setAction] = useState<ActionName>("search");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);

  // Per-action inputs
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [events, setEvents] = useState("");

  // Player identity — who the agent scouts/ranks for.
  const [playerName, setPlayerName] = useState("");
  const [playerRating, setPlayerRating] = useState<number | null>(null);
  const [playerUsatt, setPlayerUsatt] = useState<string | null>(null);
  const [savingPlayer, setSavingPlayer] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [playerMsg, setPlayerMsg] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/user`)
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => {
        if (u?.full_name) setPlayerName(u.full_name);
        if (typeof u?.rating === "number") setPlayerRating(u.rating);
        if (u?.usatt_number) setPlayerUsatt(u.usatt_number);
      })
      .catch(() => {});
  }, []);

  async function savePlayer() {
    setSavingPlayer(true);
    setPlayerMsg(null);
    try {
      const res = await fetch(`${API_URL}/settings/player`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: playerName.trim() }),
      });
      const data = await res.json();
      if (!res.ok || data?.status === "error") {
        throw new Error(data?.message || `Save failed (HTTP ${res.status})`);
      }
      // Jump straight to the map so the recommendations are front and center.
      window.location.href = "/tournaments?view=map";
    } catch (e) {
      setPlayerMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingPlayer(false);
    }
  }

  async function syncAccount() {
    setSyncing(true);
    setPlayerMsg(null);
    try {
      // 1) Official rating from USATT (via the relay).
      let ratingMsg = "USATT rating unavailable.";
      try {
        const r = await fetch(`${API_URL}/tools/sync/usatt`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: playerName.trim() || undefined }),
        });
        const d = await r.json();
        if (d?.status === "success") {
          const rating = d?.player?.rating;
          if (typeof rating === "number") setPlayerRating(rating);
          if (d?.player?.usatt_id) setPlayerUsatt(String(d.player.usatt_id));
          ratingMsg = `USATT rating ${rating}.`;
        } else {
          ratingMsg = `USATT: ${d?.message || "unavailable"}.`;
        }
      } catch {
        ratingMsg = "USATT: request failed.";
      }
      // 2) OmniPong account number + finished history.
      const res = await fetch(`${API_URL}/tools/sync/account`, { method: "POST" });
      const data = await res.json();
      const no = data?.account_number ?? data?.account?.account_number;
      if (no) setPlayerUsatt(String(no));
      const count = data?.finished_count ?? 0;
      setPlayerMsg(`${ratingMsg} Account #${no ?? "—"} (${count} finished events).`);
    } catch (e) {
      setPlayerMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(false);
    }
  }

  const active = ACTIONS.find((a) => a.id === action)!;

  function buildParams(): Record<string, unknown> {
    switch (action) {
      case "search":
        return { name };
      case "signup":
        return {
          title,
          events: events
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        };
      default:
        return {};
    }
  }

  async function run() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/agent/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, params: buildParams() }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || `Agent request failed (HTTP ${res.status})`);
      }
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const inputCls =
    "w-full rounded-lg bg-[#1a1a1a] border border-[#333] px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-[var(--rubber-red)]";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
      {/* Player identity — who the agent scouts and ranks for */}
      <div className="lg:col-span-2 rounded-2xl border border-[#2a2a2a] bg-[#141414] p-5">
        <div className="flex items-center gap-2 mb-3">
          <User size={18} className="text-[var(--rubber-accent)]" />
          <h2 className="font-semibold text-white">Player</h2>
          <span className="text-xs text-gray-500">
            Who the agent scouts, ranks, and recommends events for
          </span>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs text-gray-500 mb-1">Name</label>
            <input
              className={inputCls}
              placeholder="e.g. Justin Johnson"
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">USATT #</label>
            <div className="rounded-lg border border-[#333] px-3 py-2 text-sm text-white min-w-[110px]">
              {playerUsatt || "—"}
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Rating (from results)</label>
            <div className="rounded-lg border border-[#333] px-3 py-2 text-sm text-white min-w-[110px]">
              {playerRating ?? "—"}
            </div>
          </div>
          <button
            onClick={syncAccount}
            disabled={syncing}
            className="inline-flex items-center gap-2 rounded-lg border border-[#333] px-4 py-2 text-sm font-medium text-white
              hover:bg-[#1a1a1a] disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {syncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            {syncing ? "Syncing…" : "Sync account"}
          </button>
          <button
            onClick={savePlayer}
            disabled={savingPlayer || !playerName.trim()}
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--rubber-red)] px-4 py-2 text-sm font-medium text-white
              hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {savingPlayer ? <Loader2 size={16} className="animate-spin" /> : <MapPin size={16} />}
            {savingPlayer ? "Saving…" : "Save & open map"}
          </button>
        </div>
        {playerMsg && <div className="mt-3 text-sm text-red-300">{playerMsg}</div>}
      </div>

      {/* Action picker */}
      <div className="space-y-2">
        {ACTIONS.map((a) => (
          <button
            key={a.id}
            onClick={() => {
              setAction(a.id);
              setResult(null);
              setError(null);
            }}
            className={`w-full text-left flex items-start gap-3 rounded-xl px-4 py-3 border transition-all
              ${
                action === a.id
                  ? "border-[var(--rubber-red)] bg-[#1f1f1f]"
                  : "border-[#2a2a2a] hover:bg-[#1a1a1a]"
              }`}
          >
            <span
              className={`mt-0.5 ${
                a.danger ? "text-amber-400" : "text-[var(--rubber-accent)]"
              }`}
            >
              {a.icon}
            </span>
            <span>
              <span className="block font-medium text-white">{a.label}</span>
              <span className="block text-xs text-gray-500">{a.blurb}</span>
            </span>
          </button>
        ))}
      </div>

      {/* Runner */}
      <div className="rounded-2xl border border-[#2a2a2a] bg-[#141414] p-6">
        <div className="flex items-center gap-2 mb-4">
          <Bot size={20} className="text-[var(--rubber-red)]" />
          <h2 className="text-lg font-semibold text-white">{active.label}</h2>
        </div>

        {/* Inputs */}
        <div className="space-y-4 mb-5">
          {action === "search" && (
            <div>
              <label className="block text-xs text-gray-500 mb-1">Player name</label>
              <input
                className={inputCls}
                placeholder="e.g. Justin Johnson"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
          )}

          {action === "signup" && (
            <>
              <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                This registers you for real. Confirm the tournament and events
                before running.
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">
                  Tournament title
                </label>
                <input
                  className={inputCls}
                  placeholder="Exact title as listed"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">
                  Events (comma-separated; leave blank to auto-match by rating)
                </label>
                <input
                  className={inputCls}
                  placeholder="U1500, U1750"
                  value={events}
                  onChange={(e) => setEvents(e.target.value)}
                />
              </div>
            </>
          )}

          {(action === "matches" || action === "sync") && (
            <p className="text-sm text-gray-400">{active.blurb}</p>
          )}
        </div>

        <button
          onClick={run}
          disabled={loading || (action === "signup" && !title.trim())}
          className="inline-flex items-center gap-2 rounded-lg bg-[var(--rubber-red)] px-4 py-2 text-sm font-medium text-white
            hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          {loading ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Play size={16} />
          )}
          {loading ? "Running…" : "Run action"}
        </button>

        {error && (
          <div className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        {result !== null && (
          <div className="mt-5">
            <div className="text-xs uppercase tracking-wider text-gray-500 mb-2">
              Result
            </div>
            <pre className="max-h-[420px] overflow-auto rounded-lg bg-black/40 border border-[#2a2a2a] p-4 text-xs text-gray-200 whitespace-pre-wrap">
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
