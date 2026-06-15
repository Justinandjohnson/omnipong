"use client";
import { useState, useEffect } from "react";

const STORAGE_KEY = "rubberr_user_ai_key";

export function getStoredKey(): string | null {
  try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
}

export function setStoredKey(key: string | null) {
  try {
    if (key) localStorage.setItem(STORAGE_KEY, key);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {}
}

export function getAIHeaders(): Record<string, string> {
  const key = getStoredKey();
  return key ? { "X-User-Api-Key": key } : {};
}

function KeyModal({ onClose }: { onClose: () => void }) {
  const [val, setVal] = useState(() => getStoredKey() ?? "");
  const [saved, setSaved] = useState(false);

  const save = () => {
    setStoredKey(val.trim() || null);
    setSaved(true);
    setTimeout(() => { setSaved(false); onClose(); }, 700);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--card-background)] p-6 shadow-2xl">
        <h2 className="text-base font-bold text-[var(--foreground)] mb-1">Your AI API Key</h2>
        <p className="text-xs text-[var(--muted-foreground)] mb-4">
          Rubberr uses your{" "}
          <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener noreferrer" className="underline text-blue-400">
            Anthropic
          </a>{" "}
          or{" "}
          <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="underline text-blue-400">
            OpenRouter
          </a>{" "}
          key for AI coaching. Stored locally in your browser only.
        </p>
        <input
          autoFocus
          type="password"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--foreground)] placeholder-[var(--muted-foreground)] focus:outline-none focus:border-blue-500 mb-4"
          placeholder="sk-ant-... or sk-or-v1-..."
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => e.key === "Enter" && save()}
        />
        <div className="flex gap-2">
          <button onClick={save} className="flex-1 rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-500 transition-colors">
            {saved ? "✓ Saved!" : "Save"}
          </button>
          {getStoredKey() && (
            <button onClick={() => { setStoredKey(null); onClose(); }} className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
              Clear
            </button>
          )}
          <button onClick={onClose} className="rounded-lg border border-[var(--border)] px-4 py-2 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export function DemoBar() {
  const [hasKey, setHasKey] = useState(false);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    setHasKey(Boolean(getStoredKey()));
  }, [showModal]);

  return (
    <>
      <div className="flex items-center justify-between border-b border-[var(--border)] bg-[var(--card-background)]/80 backdrop-blur-sm px-4 py-2 text-xs">
        <span className="text-[var(--muted-foreground)]">
          👁 Viewing <strong className="text-[var(--foreground)]">demo profile</strong> — read-only public data
        </span>
        <button
          onClick={() => setShowModal(true)}
          className={`rounded-md px-3 py-1 font-semibold transition-colors ${
            hasKey
              ? "bg-green-900/40 text-green-400 border border-green-800 hover:bg-green-900/60"
              : "bg-amber-900/40 text-amber-400 border border-amber-800 hover:bg-amber-900/60"
          }`}
        >
          {hasKey ? "✓ AI Key Set" : "⚡ Add AI Key to unlock coaching"}
        </button>
      </div>
      {showModal && <KeyModal onClose={() => setShowModal(false)} />}
    </>
  );
}
