"use client";
import Sidebar from "@/components/Sidebar";
import TournamentCard from "@/components/TournamentCard";
import CalendarView from "@/components/CalendarView";
import dynamic from "next/dynamic";
import { useEffect, useState, useCallback, useMemo } from "react";
import {
  Search,
  MapPin,
  Sparkles,
  RefreshCw,
  List as ListIcon,
  CalendarDays,
  Map as MapIcon,
  Swords,
  ExternalLink,
  Trophy,
  type LucideIcon,
} from "lucide-react";

// Leaflet touches `window`, so it must not render on the server.
const MapView = dynamic(() => import("@/components/MapView"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full bg-[#0a0a0a] animate-pulse flex items-center justify-center text-gray-500">
      Loading map…
    </div>
  ),
});

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const LAST_CHECK_KEY = "rubberr:lastTournamentCheck";
const AUTO_CHECK_HOURS = 6;

// Cities used for the client-side "Local" filter for the detected state.
const CITY_MAP: Record<string, string[]> = {
  TX: ["plano","austin","houston","san antonio","dallas","richardson","irving","katy","allen","colleyville","round rock","fort worth","lubbock","el paso","arlington","pearland","sugar land","frisco","mckinney"],
  CA: ["los angeles","san francisco","san diego","sacramento","san jose","fremont","irvine"],
  NY: ["new york","brooklyn","queens","manhattan","bronx","staten island","flushing","westchester"],
};

const STATE_NAMES: Record<string, string> = { tx: "texas", ca: "california", ny: "new york" };

const isLocal = (location: string, state: string) => {
  if (!location) return false;
  const loc = location.toLowerCase();
  const code = state.toLowerCase();
  if (loc.includes(` ${code}`) || loc.includes(`, ${code}`)) return true;
  if (STATE_NAMES[code] && loc.includes(STATE_NAMES[code])) return true;
  return (CITY_MAP[state] || []).some((c) => loc.includes(c));
};

type View = "list" | "calendar" | "map" | "matches";

type Tournament = {
  title?: string;
  city_state?: string;
  location?: string;
  date_range?: string;
  status?: string;
  flyer_url?: string;
  omnipong_url?: string;
};

type RecommendedEvent = { name: string; fee?: number | string; competitiveness?: string };

type Recommendation = {
  tournament: string;
  recommended_events?: RecommendedEvent[];
  difficulty_score?: number;
  doubles_partner_suggestions?: { name: string; rating?: number | string }[];
  known_players_likely_attending?: { name: string; your_record?: string }[];
};

type AiInsights = { user_rating?: number; recommendations?: Recommendation[] } | null;

type MatchRow = {
  is_win?: boolean;
  opponent_name?: string;
  opponent_rating?: number | string;
  score_summary?: string;
  set_scores?: string;
  date?: string;
};

type MatchYear = {
  year: string | number;
  wins: number;
  losses: number;
  win_rate: number;
  tournaments: number;
  matches: MatchRow[];
};

type MatchSummary = {
  overall?: { total?: number; wins?: number; losses?: number; win_rate?: number };
  years?: MatchYear[];
} | null;

export default function TournamentsPage() {
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"local" | "all">("all");
  const [view, setView] = useState<View>("list");
  const [aiInsights, setAiInsights] = useState<AiInsights>(null);
  const [userState, setUserState] = useState("TX");
  const [userRating, setUserRating] = useState(1500);
  const [userLocation, setUserLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [matches, setMatches] = useState<MatchSummary>(null);
  const [matchesSyncing, setMatchesSyncing] = useState(false);

  const fetchTournaments = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/tournaments?region=all`);
      const data = await res.json();
      setTournaments(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Failed to load tournaments", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchInsights = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/tools/tournament_intelligence?limit=200`);
      const data = await res.json();
      setAiInsights(data);
      if (data?.user_rating) setUserRating(data.user_rating);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const fetchMatches = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/matches/summary`);
      setMatches(await res.json());
    } catch (e) {
      console.error("Failed to load matches", e);
    }
  }, []);

  // Ask the backend to look for new tournaments. Runs in the background; the
  // DB is the source of truth so we just refetch when it returns.
  const runCheck = useCallback(
    async (showSpinner: boolean) => {
      if (showSpinner) setRefreshing(true);
      try {
        const res = await fetch(`${API_URL}/tools/check-tournaments`, { method: "POST" });
        const data = await res.json();
        if (data?.status === "success" || res.ok) {
          setNotice("Up to date.");
        } else {
          setNotice("Check finished with warnings.");
        }
      } catch {
        setNotice("Couldn't reach the backend to check for new tournaments.");
      } finally {
        localStorage.setItem(LAST_CHECK_KEY, String(Date.now()));
        await fetchTournaments();
        await fetchInsights();
        setLastSync(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
        if (showSpinner) setRefreshing(false);
      }
    },
    [fetchTournaments, fetchInsights],
  );

  // Initial load + auto-check (at most once every AUTO_CHECK_HOURS).
  useEffect(() => {
    fetchTournaments();
    fetchInsights();
    fetchMatches();

    fetch(`${API_URL}/user`)
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => u?.rating && setUserRating(u.rating))
      .catch(() => {});

    if (typeof window !== "undefined") {
      const last = Number(localStorage.getItem(LAST_CHECK_KEY) || 0);
      const stale = Date.now() - last > AUTO_CHECK_HOURS * 3600 * 1000;
      if (stale) runCheck(false);
    }

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const { latitude, longitude } = pos.coords;
          setUserLocation({ lat: latitude, lng: longitude });
          try {
            const res = await fetch(
              `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`,
            );
            const data = await res.json();
            const state = data?.address?.state as string | undefined;
            let code = "TX";
            if (state) {
              if (state.toLowerCase() === "texas") code = "TX";
              else if (state.toLowerCase() === "california") code = "CA";
              else if (state.toLowerCase() === "new york") code = "NY";
              else code = state.substring(0, 2).toUpperCase();
            }
            setUserState(code);
          } catch {
            /* keep default */
          }
        },
        () => {},
      );
    }
  }, [fetchTournaments, fetchInsights, fetchMatches, runCheck]);

  // Sync just the user's own match history via the agent.
  const syncMatches = useCallback(async () => {
    setMatchesSyncing(true);
    setNotice(null);
    try {
      await fetch(`${API_URL}/agent/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "matches", params: {} }),
      });
      await fetchMatches();
      setNotice("Match history synced.");
    } catch {
      setNotice("Match sync failed — is the backend running?");
    } finally {
      setMatchesSyncing(false);
    }
  }, [fetchMatches]);

  const getInsightsForTournament = (title: string) => {
    if (!aiInsights?.recommendations) return null;
    return aiInsights.recommendations.find((r) => r.tournament === title);
  };

  const filtered = useMemo(
    () =>
      tournaments.filter((t) => {
        const loc = t.city_state || t.location || "";
        const matchesSearch =
          (t.title || "").toLowerCase().includes(search.toLowerCase()) ||
          loc.toLowerCase().includes(search.toLowerCase());
        const matchesFilter = filter === "all" ? true : isLocal(loc, userState);
        return matchesSearch && matchesFilter;
      }),
    [tournaments, search, filter, userState],
  );

  const TABS: { id: View; label: string; icon: LucideIcon }[] = [
    { id: "list", label: "List", icon: ListIcon },
    { id: "calendar", label: "Calendar", icon: CalendarDays },
    { id: "map", label: "Map", icon: MapIcon },
    { id: "matches", label: "My Matches", icon: Swords },
  ];

  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      <main className="flex-1 md:ml-64 pt-14 md:pt-0 p-8 overflow-y-auto h-screen">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold mb-1">Tournaments</h1>
            <p className="text-gray-400">
              Everything in one place — calendar, map, list, and your match history.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {lastSync && <span className="text-xs text-gray-500">Updated {lastSync}</span>}
            <button
              onClick={() => runCheck(true)}
              disabled={refreshing}
              className="px-4 py-2.5 rounded-xl bg-[var(--rubber-red)] text-white font-bold text-sm flex items-center gap-2 hover:bg-red-600 transition-colors disabled:opacity-70"
            >
              <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
              {refreshing ? "Checking…" : "Refresh"}
            </button>
          </div>
        </header>

        {notice && (
          <div className="mb-4 text-xs text-gray-400 flex items-center gap-2">
            <Sparkles size={14} className="text-purple-400" /> {notice}
          </div>
        )}

        {/* Toolbar: view tabs + search + region filter */}
        <div className="flex flex-wrap items-center gap-4 mb-6">
          <div className="flex bg-[#1a1a1a] rounded-xl p-1 border border-[#333]">
            {TABS.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.id}
                  onClick={() => setView(t.id)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                    view === t.id ? "bg-[#333] text-white" : "text-gray-400 hover:text-white"
                  }`}
                >
                  <Icon size={15} /> {t.label}
                </button>
              );
            })}
          </div>

          {view !== "matches" && (
            <>
              <div className="relative flex-1 min-w-[220px]">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
                <input
                  type="text"
                  placeholder="Search tournaments…"
                  className="w-full bg-[#1a1a1a] border border-[#333] rounded-xl pl-10 pr-4 py-2.5 text-white focus:outline-none focus:border-[var(--rubber-red)] transition-colors"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div className="flex bg-[#1a1a1a] rounded-xl p-1 border border-[#333]">
                <button
                  onClick={() => setFilter("local")}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    filter === "local" ? "bg-[var(--rubber-red)] text-white" : "text-gray-400 hover:text-white"
                  }`}
                >
                  {userState === "TX" ? "Texas Only" : `${userState} Only`}
                </button>
                <button
                  onClick={() => setFilter("all")}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    filter === "all" ? "bg-[#333] text-white" : "text-gray-400 hover:text-white"
                  }`}
                >
                  All
                </button>
              </div>
            </>
          )}
        </div>

        {/* View content */}
        {view === "list" && (
          <>
            {loading ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <div key={i} className="h-48 bg-[#1a1a1a] animate-pulse rounded-2xl" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-12">
                {filtered.map((t, i) => (
                  <TournamentCard
                    key={i}
                    title={t.title || "Untitled"}
                    location={t.city_state || t.location || ""}
                    date={t.date_range || ""}
                    status={t.status || "Open"}
                    flyer_url={t.flyer_url}
                    url={t.omnipong_url}
                    aiInsights={getInsightsForTournament(t.title || "")}
                  />
                ))}
              </div>
            )}
            {!loading && filtered.length === 0 && (
              <div className="text-center py-20 text-gray-500">
                <MapPin size={48} className="mx-auto mb-4 opacity-20" />
                <p>No tournaments found. Hit Refresh to check for new ones.</p>
              </div>
            )}
          </>
        )}

        {view === "calendar" && (
          <div className="h-[70vh]">
            <CalendarView tournaments={filtered} userRating={userRating} />
          </div>
        )}

        {view === "map" && (
          <div className="h-[75vh]">
            <MapView tournaments={filtered} userLocation={userLocation} />
          </div>
        )}

        {view === "matches" && (
          <MatchesPanel
            matches={matches}
            syncing={matchesSyncing}
            onSync={syncMatches}
            onOpenTournaments={() => setView("list")}
          />
        )}
      </main>
    </div>
  );
}

function MatchesPanel({
  matches,
  syncing,
  onSync,
  onOpenTournaments,
}: {
  matches: MatchSummary;
  syncing: boolean;
  onSync: () => void;
  onOpenTournaments: () => void;
}) {
  const overall = matches?.overall;
  const years: MatchYear[] = matches?.years || [];

  return (
    <div className="pb-12">
      <div className="flex items-center justify-between mb-6">
        <div className="flex gap-4">
          <Stat label="Matches" value={overall?.total ?? 0} />
          <Stat label="Wins" value={overall?.wins ?? 0} accent="text-green-400" />
          <Stat label="Losses" value={overall?.losses ?? 0} accent="text-red-400" />
          <Stat label="Win rate" value={`${overall?.win_rate ?? 0}%`} />
        </div>
        <button
          onClick={onSync}
          disabled={syncing}
          className="px-4 py-2.5 rounded-xl bg-[#1a1a1a] border border-[#333] text-white font-bold text-sm flex items-center gap-2 hover:border-[var(--rubber-red)] transition-colors disabled:opacity-70"
        >
          <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
          {syncing ? "Syncing your matches…" : "Sync my match data"}
        </button>
      </div>

      {years.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <Swords size={48} className="mx-auto mb-4 opacity-20" />
          <p className="mb-4">No match history stored yet.</p>
          <button onClick={onSync} className="text-[var(--rubber-red)] font-bold hover:underline">
            Pull my match data from OmniPong
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {years.map((y) => (
            <details key={y.year} className="rounded-2xl bg-[#1a1a1a] border border-[#333] overflow-hidden" open>
              <summary className="cursor-pointer list-none px-5 py-4 flex items-center justify-between">
                <span className="flex items-center gap-3 font-bold text-white">
                  <Trophy size={16} className="text-[var(--rubber-red)]" /> {y.year}
                </span>
                <span className="text-sm text-gray-400">
                  {y.wins}W – {y.losses}L · {y.win_rate}% · {y.tournaments} tournament
                  {y.tournaments === 1 ? "" : "s"}
                </span>
              </summary>
              <div className="border-t border-[#222] divide-y divide-[#222]">
                {y.matches.map((m: MatchRow, i: number) => (
                  <div key={i} className="px-5 py-3 flex items-center justify-between text-sm">
                    <div className="flex items-center gap-3">
                      <span
                        className={`w-6 h-6 rounded-md flex items-center justify-center text-[11px] font-bold ${
                          m.is_win ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                        }`}
                      >
                        {m.is_win ? "W" : "L"}
                      </span>
                      <span className="text-white">{m.opponent_name || "Unknown opponent"}</span>
                      {m.opponent_rating && (
                        <span className="text-gray-500 text-xs">({m.opponent_rating})</span>
                      )}
                    </div>
                    <div className="flex items-center gap-4 text-gray-400 text-xs">
                      <span>{m.score_summary || m.set_scores || ""}</span>
                      <span>{m.date ? String(m.date).slice(0, 10) : ""}</span>
                    </div>
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
      )}

      <button
        onClick={onOpenTournaments}
        className="mt-6 text-sm text-gray-400 hover:text-white flex items-center gap-2"
      >
        <ExternalLink size={14} /> Browse upcoming tournaments
      </button>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="px-5 py-3 rounded-2xl bg-[#1a1a1a] border border-[#333] min-w-[110px]">
      <div className="text-[10px] uppercase font-bold text-gray-500">{label}</div>
      <div className={`text-xl font-bold ${accent || "text-white"}`}>{value}</div>
    </div>
  );
}
