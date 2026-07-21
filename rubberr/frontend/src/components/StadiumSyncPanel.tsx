"use client";
import { useRef, useState } from "react";
import { RefreshCw, ShieldCheck, ExternalLink, AlertTriangle } from "lucide-react";
import { getAIHeaders, getStoredKey } from "@/components/DemoBar";
import { saveMatches } from "@/lib/ledger";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Tier-3 private sync: kicks off the browser-agent run on the backend
 * (POST /tools/sync/stadium), then listens for gate prompts pushed from the
 * backend over SSE (GET /tools/sync/stadium/events) so the user knows when
 * to go solve a login/2FA/Cloudflare gate in their own companion-launched
 * Chrome. See docs/RELAY_ARCHITECTURE.md §3, §8, §9.
 *
 * Contract this component assumes from Agent F's backend (not yet built at
 * the time this was written — documented here so B/F can match it):
 *
 *   POST /tools/sync/stadium
 *     headers: X-User-Api-Key: <user's OpenRouter key>
 *     body:    { player_name: string }
 *     resp:    { session_id: string } | { error: { type, detail } }
 *
 *   GET /tools/sync/stadium/events/{session_id}   (text/event-stream; S5: path
 *   segment, not a query string, so the relay session token never lands in
 *   proxy/access logs — see RELAY_ARCHITECTURE.md §5)
 *     event: gate_open    data: { gate_id, kind, hint, url_host }
 *     event: gate_cleared data: { gate_id }
 *     event: gate_timeout data: { gate_id }
 *     event: done         data: BrowserTaskResult  (§8.2: status, matches, steps_used, error)
 */

type GateInfo = { gate_id: string; kind: string; hint: string; url_host: string } | null;

type Phase = "idle" | "starting" | "running" | "gate" | "done" | "error";

/**
 * S1: the events endpoint is now owner-gated behind X-Operator-Token
 * (main.py's _require_operator_token). The browser's native EventSource
 * can't send custom headers, so the stream is read via fetch + a manual
 * ReadableStream/SSE parser instead — same "event: X\ndata: Y\n\n" wire
 * format the backend emits, one method, no EventSource fallback path left
 * dangling.
 */
async function consumeSse(
  url: string,
  headers: Record<string, string>,
  signal: AbortSignal,
  onEvent: (eventName: string, data: string) => void
): Promise<void> {
  const res = await fetch(url, { headers, signal });
  if (!res.ok || !res.body) {
    throw new Error(`HTTP ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) return;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (!block.trim() || block.startsWith(":")) continue; // ignore SSE keepalive comments
      let eventName = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) data = line.slice(5).trim();
      }
      onEvent(eventName, data);
    }
  }
}

export default function StadiumSyncPanel({ playerName }: { playerName: string }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [gate, setGate] = useState<GateInfo>(null);
  const [savedCount, setSavedCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const hasKey = Boolean(getStoredKey());

  function closeStream() {
    abortRef.current?.abort();
    abortRef.current = null;
  }

  async function startSync() {
    if (!hasKey) {
      setPhase("error");
      setError("Add your OpenRouter key first (top bar) — the browser agent needs it.");
      return;
    }
    if (!playerName.trim()) {
      setPhase("error");
      setError("We don't know your name yet — set it in your profile first.");
      return;
    }

    setPhase("starting");
    setGate(null);
    setError(null);
    setSavedCount(null);

    let sessionId: string;
    try {
      const res = await fetch(`${API_URL}/tools/sync/stadium`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAIHeaders() },
        body: JSON.stringify({ player_name: playerName }),
      });
      const data = await res.json();
      if (!res.ok || !data.session_id) {
        throw new Error(data?.error?.detail || `HTTP ${res.status}`);
      }
      sessionId = data.session_id;
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Failed to start sync");
      return;
    }

    setPhase("running");
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await consumeSse(
        `${API_URL}/tools/sync/stadium/events/${encodeURIComponent(sessionId)}`,
        getAIHeaders(),
        controller.signal,
        (eventName, data) => {
          if (eventName === "gate_open") {
            setGate(JSON.parse(data));
            setPhase("gate");
          } else if (eventName === "gate_cleared") {
            setGate(null);
            setPhase("running");
          } else if (eventName === "gate_timeout") {
            setGate(null);
            setPhase("error");
            setError("Gate wasn't solved in time — nothing was scraped. Try again.");
            closeStream();
          } else if (eventName === "done") {
            const result = JSON.parse(data);
            closeStream();
            if (result.status !== "ok") {
              setPhase("error");
              setError(result.error?.detail || `Sync ended: ${result.status}`);
              return;
            }
            saveMatches(result.matches ?? [])
              .then((count) => {
                setSavedCount(count);
                setPhase("done");
              })
              .catch((e) => {
                setPhase("error");
                setError(e instanceof Error ? e.message : "Failed to save to your local ledger");
              });
          }
        }
      );
    } catch (e) {
      // Guard against firing after we've already closed the stream ourselves
      // (e.g. right after "done"/"gate_timeout"): an aborted fetch also
      // rejects, and that's an intentional close, not a lost connection.
      if (abortRef.current === controller) {
        setPhase("error");
        setError(e instanceof Error ? e.message : "Lost connection to the sync stream.");
        closeStream();
      }
    }
  }

  return (
    <div className="p-4 bg-[#111] rounded-xl border border-[#333] space-y-3">
      <div className="flex justify-between items-start">
        <div>
          <div className="font-bold flex items-center gap-2">
            <ShieldCheck size={16} className="text-green-500" />
            Sync my Stadium data
          </div>
          <p className="text-xs text-gray-500 mt-1">
            An AI agent drives your own, already-logged-in browser to pull your private
            match history. Nothing is stored on our server — results are saved only to
            this browser&apos;s local ledger.
          </p>
        </div>
        <button
          onClick={startSync}
          disabled={phase === "starting" || phase === "running" || phase === "gate"}
          className="flex items-center gap-2 rounded-lg bg-[var(--rubber-red)] px-3 py-2 text-xs font-bold text-white disabled:opacity-40 disabled:cursor-not-allowed hover:brightness-110 transition-all whitespace-nowrap"
        >
          {phase === "starting" || phase === "running" ? (
            <RefreshCw size={14} className="animate-spin" />
          ) : (
            <ShieldCheck size={14} />
          )}
          {phase === "starting"
            ? "Starting..."
            : phase === "running"
            ? "Syncing..."
            : phase === "gate"
            ? "Waiting on you..."
            : "Sync my Stadium data"}
        </button>
      </div>

      {phase === "gate" && gate && (
        <div className="rounded-lg border border-amber-800 bg-amber-900/20 p-3 text-xs text-amber-300 space-y-1">
          <p className="font-bold flex items-center gap-1.5">
            <AlertTriangle size={13} /> Action needed on {gate.url_host}
          </p>
          <p>{gate.hint}</p>
          <p className="text-amber-400/70">
            Solve it in the Chrome window the companion opened for you, then click
            &ldquo;Continue&rdquo; there — this page will pick back up automatically.
          </p>
        </div>
      )}

      {phase === "done" && (
        <div className="rounded-lg border border-green-800 bg-green-900/20 p-3 text-xs text-green-400">
          Saved {savedCount ?? 0} match{savedCount === 1 ? "" : "es"} to your local ledger.{" "}
          <a href="/scoreboard" className="underline inline-flex items-center gap-1">
            View scoreboard <ExternalLink size={11} />
          </a>
        </div>
      )}

      {phase === "error" && error && (
        <div className="rounded-lg border border-red-800 bg-red-900/20 p-3 text-xs text-red-400">
          {error}
        </div>
      )}
    </div>
  );
}
