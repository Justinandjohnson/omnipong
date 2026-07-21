"use client";

/**
 * Tier-3 local ledger: the ONLY place private Stadium/USATT match data lives.
 * IndexedDB in the user's own browser — never sent to or read from our server.
 * See docs/RELAY_ARCHITECTURE.md §8.2 for the NormalizedMatch shape this stores.
 */

const DB_NAME = "rubberr_ledger";
const DB_VERSION = 1;
const STORE = "matches";

export interface LedgerMatch {
  id: string; // stable id = `${source}|${player_name}|${opponent}|${date}|${match_score}`
  source: "omnipong" | "stadium" | "stadium_league";
  player_name: string;
  opponent: string;
  date: string;
  result: string;
  match_score: string;
  set_scores: string[];
  event: string;
  synced_at: string; // ISO timestamp, local — when this record entered the ledger
}

function makeId(m: Omit<LedgerMatch, "id" | "synced_at">): string {
  return [m.source, m.player_name, m.opponent, m.date, m.match_score].join("|");
}

function openDB(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") {
    return Promise.reject(new Error("IndexedDB is not available in this browser"));
  }
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: "id" });
        store.createIndex("source", "source", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("Failed to open IndexedDB"));
  });
}

/** Write normalized matches from a completed sync into the local ledger (upsert by id). */
export async function saveMatches(
  matches: Array<Omit<LedgerMatch, "id" | "synced_at">>
): Promise<number> {
  if (matches.length === 0) return 0;
  const db = await openDB();
  const syncedAt = new Date().toISOString();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    for (const m of matches) {
      const record: LedgerMatch = { ...m, id: makeId(m), synced_at: syncedAt };
      store.put(record);
    }
    tx.oncomplete = () => resolve(matches.length);
    tx.onerror = () => reject(tx.error ?? new Error("Failed to write ledger"));
  });
}

/** Read every match currently stored in the local ledger, newest sync first. */
export async function getAllMatches(): Promise<LedgerMatch[]> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => {
      const rows = (req.result as LedgerMatch[]).sort((a, b) =>
        b.synced_at.localeCompare(a.synced_at)
      );
      resolve(rows);
    };
    req.onerror = () => reject(req.error ?? new Error("Failed to read ledger"));
  });
}

/** Wipe the local ledger (e.g. user-initiated "forget my synced data"). */
export async function clearMatches(): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).clear();
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error("Failed to clear ledger"));
  });
}
