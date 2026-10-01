"use client";

// Agent Console — the GUI half of the OmniPong agent. It POSTs to
// /agent/action, which runs omnipong_agent.run_action() in-process: the same
// six actions the MCP server exposes (omnipong_mcp_server.py). So the app tab
// and any MCP client drive one code path. See docs/OMNIPONG_AGENT.md.

import React, { useState } from "react";
import {
  Bot,
  Trophy,
  Search,
  RefreshCw,
  CalendarClock,
  ListChecks,
  Play,
  Loader2,
  AlertTriangle,
  Swords,
} from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ActionName =
  | "check"
  | "tournaments"
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
    id: "check",
    label: "Check for tournaments",
    blurb: "Scout your area for new tournaments and (unless dry-run) raise alerts.",
    icon: <CalendarClock size={18} />,
  },
  {
    id: "tournaments",
    label: "List area tournaments",
    blurb: "Show tournaments in your configured area, optionally with events.",
    icon: <Trophy size={18} />,
  },
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
  const [action, setAction] = useState<ActionName>("check");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);

  // Per-action inputs
  const [dryRun, setDryRun] = useState(false);
  const [deep, setDeep] = useState(false);
  const [limit, setLimit] = useState(5);
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [events, setEvents] = useState("");

  const active = ACTIONS.find((a) => a.id === action)!;

  function buildParams(): Record<string, unknown> {
    switch (action) {
      case "check":
        return { dry_run: dryRun, deep, limit };
      case "tournaments":
        return { deep };
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
  const checkCls = "h-4 w-4 accent-[var(--rubber-red)]";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
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
          {action === "check" && (
            <>
              <label className="flex items-center gap-3 text-sm text-gray-300">
                <input
                  type="checkbox"
                  className={checkCls}
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                />
                Dry run (report only — write no alerts)
              </label>
              <label className="flex items-center gap-3 text-sm text-gray-300">
                <input
                  type="checkbox"
                  className={checkCls}
                  checked={deep}
                  onChange={(e) => setDeep(e.target.checked)}
                />
                Deep scan (fetch events for each new tournament)
              </label>
              <div>
                <label className="block text-xs text-gray-500 mb-1">
                  Limit (max tournaments, 0 = all)
                </label>
                <input
                  type="number"
                  className={inputCls}
                  value={limit}
                  min={0}
                  onChange={(e) => setLimit(Number(e.target.value))}
                />
              </div>
            </>
          )}

          {action === "tournaments" && (
            <label className="flex items-center gap-3 text-sm text-gray-300">
              <input
                type="checkbox"
                className={checkCls}
                checked={deep}
                onChange={(e) => setDeep(e.target.checked)}
              />
              Include events for each tournament
            </label>
          )}

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
