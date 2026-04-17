"use client";
import Sidebar from "@/components/Sidebar";
import CalendarView from "@/components/CalendarView";
import PatternAnalysis from "@/components/PatternAnalysis";
import CareerGraph from "@/components/CareerGraph";
import TournamentCard from "@/components/TournamentCard";
import RubberrStats from "@/components/RubberrStats";
import PracticePartners from "@/components/PracticePartners";
import AIAlertPopup from "@/components/AIAlertPopup";
import { useEffect, useState } from "react";
import { AlertCircle } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

import { useArcade } from "@/context/ArcadeContext";
import ArcadeScoreInput from "@/components/ArcadeScoreInput";
import ArcadeMatchList from "@/components/ArcadeMatchList";
import DrillLab from "@/components/DrillLab";

// Skeleton Loading Components
const SkeletonCard = () => (
  <div className="min-h-[10rem] bg-[var(--card-background)] border border-[var(--border)] rounded-xl p-4 animate-pulse">
    <div className="h-4 bg-[var(--muted)] rounded w-3/4 mb-2"></div>
    <div className="h-3 bg-[var(--muted)] rounded w-1/2 mb-3"></div>
    <div className="h-3 bg-[var(--muted)] rounded w-2/3 mb-2"></div>
    <div className="flex gap-2 mt-4">
      <div className="h-8 bg-[var(--muted)] rounded w-1/3"></div>
      <div className="h-8 bg-[var(--muted)] rounded w-1/3"></div>
    </div>
  </div>
);

const SkeletonStats = () => (
  <div className="grid grid-cols-4 gap-4 animate-pulse">
    {[...Array(4)].map((_, i) => (
      <div key={i} className="bg-[var(--card-background)] border border-[var(--border)] rounded-lg p-4">
        <div className="h-6 bg-[var(--muted)] rounded w-1/2 mb-2"></div>
        <div className="h-4 bg-[var(--muted)] rounded w-3/4"></div>
      </div>
    ))}
  </div>
);

export default function Home() {
  const { isArcadeMode } = useArcade();
  const [tournaments, setTournaments] = useState<any[]>([]);
  const [allTournaments, setAllTournaments] = useState<any[]>([]);
  const [user, setUser] = useState<{ full_name: string, rating: number } | null>(null);
  const [location, setLocation] = useState<{ lat: number, lng: number, state?: string } | null>(null);
  const [loadingLoc, setLoadingLoc] = useState(false);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<"usatt" | "league" | "arcade">("league");
  const [arcadeRefresh, setArcadeRefresh] = useState(0);
  const [hasUpdates, setHasUpdates] = useState(false);

  // Sync viewMode with global Arcade state
  useEffect(() => {
    if (isArcadeMode) {
        setViewMode("arcade");
    } else {
        setViewMode("league"); // Default back to league or keep user preference? Resetting for simplicity
    }
  }, [isArcadeMode]);

  // Cache utilities
  const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
  
  const getCachedData = (key: string) => {
    if (typeof window === 'undefined') return null;
    try {
      const cached = localStorage.getItem(key);
      if (!cached) return null;
      const { data, timestamp } = JSON.parse(cached);
      if (Date.now() - timestamp > CACHE_DURATION) {
        localStorage.removeItem(key);
        return null;
      }
      return data;
    } catch {
      return null;
    }
  };

  const setCachedData = (key: string, data: any) => {
    if (typeof window === 'undefined') return;
    try {
      localStorage.setItem(key, JSON.stringify({ data, timestamp: Date.now() }));
    } catch (e) {
      console.warn('Cache write failed:', e);
    }
  };

  // Simple hash function to detect data changes
  const hashData = (data: any): string => {
    try {
      const str = JSON.stringify(data);
      let hash = 0;
      for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32-bit integer
      }
      return hash.toString();
    } catch {
      return '';
    }
  };

  // Smart fetch that only updates if data changed (unless force=true)
  const smartFetchUser = async (force: boolean = false): Promise<boolean> => {
    if (force) {
      // Force refresh - bypass hash check
      const data = await fetchUser();
      if (data) {
        const newHash = hashData(data);
        localStorage.setItem('user_hash', newHash);
        setUser(data);
      }
      return true;
    }
    
    const currentHash = localStorage.getItem('user_hash');
    const data = await fetchUser();
    if (data) {
      const newHash = hashData(data);
      if (newHash !== currentHash) {
        localStorage.setItem('user_hash', newHash);
        setUser(data);
        return true;
      }
    }
    return false;
  };

  const smartFetchTournaments = async (stateFilter?: string, force: boolean = false): Promise<boolean> => {
    if (force) {
      // Force refresh - bypass hash check
      const data = await fetchTournaments(stateFilter);
      if (data && data.length > 0) {
        const newHash = hashData(data);
        localStorage.setItem('tournaments_hash', newHash);
        setAllTournaments(data);
        setTournaments(data.slice(0, 3));
        return true;
      }
      return false;
    }
    
    const currentHash = localStorage.getItem('tournaments_hash');
    const data = await fetchTournaments(stateFilter);
    if (data && data.length > 0) {
      const newHash = hashData(data);
      if (newHash !== currentHash) {
        localStorage.setItem('tournaments_hash', newHash);
        setAllTournaments(data);
        setTournaments(data.slice(0, 3));
        return true; // Data changed
      }
    }
    return false; // No change
  };

  // 1. Fetch User (with cache)
  const fetchUser = async () => {
    try {
      const res = await fetch(`${API_URL}/user`);
      if (!res.ok) throw new Error("No user found");
      const data = await res.json();
      setUser(data);
      setCachedData('user', data);
      return data;
    } catch (e) {
      console.log("User fetch error:", e);
      return null;
    }
  };

  // 2. Fetch Tournaments (with cache, Filtered by State if available)
  const fetchTournaments = async (stateFilter?: string) => {
    try {
      let url = `${API_URL}/tournaments`;
      if (stateFilter) url += `?state=${stateFilter}`;
      
      const res = await fetch(url);
      const data = await res.json();
      setAllTournaments(data);
      setTournaments(data.slice(0, 3));
      setCachedData('tournaments', data);
      return data;
    } catch (e) {
      console.error("Tournament fetch error:", e);
      return [];
    }
  };

  // 3. Optimized Initial Load Logic with Smart Background Refresh
  useEffect(() => {
    // Load from cache immediately for instant UI
    const cachedUser = getCachedData('user');
    const cachedTournaments = getCachedData('tournaments');
    
    if (cachedUser) setUser(cachedUser);
    if (cachedTournaments) {
      setAllTournaments(cachedTournaments);
      setTournaments(cachedTournaments.slice(0, 3));
    }

    // If we have cached data, consider page loaded
    if (cachedUser && cachedTournaments && cachedTournaments.length > 0) {
      setLoading(false);
    }

    // Initial fetch - use smart fetch to only update if data changed
    Promise.all([
      smartFetchUser(),
      smartFetchTournaments()
    ]).then(() => setLoading(false))
      .catch(err => {
        console.error("Initial data fetch error:", err);
        setLoading(false);
      });

    // Background: Get location and refine tournament filter (non-blocking)
    if (navigator.geolocation) {
      setLoadingLoc(true);
      navigator.geolocation.getCurrentPosition(async (position) => {
        const { latitude, longitude } = position.coords;
        
        // Reverse Geocode to get State (non-blocking)
        try {
          const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`);
          const data = await res.json();
          const stateName = data.address?.state;
          
          setLocation({ lat: latitude, lng: longitude, state: stateName });
          
          // Refetch tournaments with state filter if we got a state
          if (stateName) {
            smartFetchTournaments(stateName);
          }
        } catch (err) {
          console.error("Reverse geocode failed", err);
          setLocation({ lat: latitude, lng: longitude });
        } finally {
          setLoadingLoc(false);
        }
      }, (err) => {
        console.error("Location permission denied", err);
        setLoadingLoc(false);
      });
    }

    // Background refresh: Poll every 30 seconds for updates, but only update UI on changes
    const refreshInterval = setInterval(async () => {
      const userChanged = await smartFetchUser();
      const tournamentsChanged = await smartFetchTournaments(location?.state);
      
      // Show update indicator if new data found (but not on initial load)
      if ((userChanged || tournamentsChanged) && !loading) {
        setHasUpdates(true);
        // Auto-hide indicator after 5 seconds
        setTimeout(() => setHasUpdates(false), 5000);
      }
    }, 30000);

    return () => clearInterval(refreshInterval);
  }, []);

  const handleSyncOmni = async () => {
      try {
          await fetch(`${API_URL}/sync/omnipong`, { method: 'POST' });
          // Force fresh fetch after sync to ensure we get the new data
          await smartFetchTournaments(location?.state, true); 
          await smartFetchUser(true);
          alert("Quick Sync (OmniPong) executed!");
      } catch (e) {
          alert("Sync failed: " + e);
      }
  };

  const handleSyncLeaguePlayers = async () => {
      try {
          const res = await fetch(`${API_URL}/tools/sync/league_players`, { method: 'POST' });
          const data = await res.json();
          if (data.status === "success") {
              // Force refresh to show updated player data
              await smartFetchUser(true);
              alert("League Players synced with official USATT ratings!");
          } else {
              alert("Sync failed: " + data.message);
          }
      } catch (e) {
          alert("Sync failed: " + e);
      }
  };

  const handleSyncTournaments = async () => {
      try {
          // Trigger 'all' to cover both history and regional as requested
          const res = await fetch(`${API_URL}/tools/sync/tournaments?scope=all`, { method: 'POST' });
          const data = await res.json();
          if (data.status === "success") {
              // Force fresh fetch to immediately show new tournaments
              await smartFetchTournaments(location?.state, true);
              alert("Tournament Sync Complete!");
          } else {
              alert("Sync failed: " + data.message);
          }
      } catch (e) {
          alert("Sync failed: " + e);
      }
  };

  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      
      {hasUpdates && (
        <div className="fixed top-4 left-1/2 transform -translate-x-1/2 z-50">
          <div className="bg-green-600 text-white px-4 py-2 rounded-full shadow-lg animate-pulse">
            New data available!
          </div>
        </div>
      )}
      
      <main className="flex-1 ml-64 overflow-y-auto">
        
        {/* Hero Section (Full Width, No Padding) */}
        <div className="w-full h-[400px] relative">
           <CareerGraph
             onSyncOmni={handleSyncOmni}
             onSyncLeague={handleSyncLeaguePlayers}
             onSyncTournaments={handleSyncTournaments}
             source={viewMode}
             onSourceChange={isArcadeMode ? undefined : setViewMode}
             hideToggle={isArcadeMode}
           />
        </div>

        {/* Actionable Content (With Padding) */}
        <div className="p-8 grid grid-cols-12 gap-8">
          
          {/* Row 1: Key Stats */}
          <div className="col-span-12">
             {loading ? <SkeletonStats /> : <RubberrStats rating={user?.rating || 0} source={viewMode} />}
          </div>

          {/* Row 2: Actionable Items */}
          <div className="col-span-7">
             <section>
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider">
                     {location?.state ? `Opportunities in ${location.state}` : 'Upcoming Opportunities'}
                  </h2>
                  {loadingLoc && <span className="text-xs animate-pulse text-[var(--rubber-accent)]">Locating...</span>}
                </div>
                
                {isArcadeMode && (
                    <div className="space-y-6 mb-8">
                        <ArcadeScoreInput onScoreSubmit={() => {
                            fetchUser();
                            setArcadeRefresh(prev => prev + 1);
                        }} />
                        <ArcadeMatchList refreshTrigger={arcadeRefresh} />
                    </div>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Left: Cards List */}
                    <div className="space-y-3">
                      {loading ? (
                        <SkeletonCard />
                      ) : tournaments.length === 0 ? (
                        <div className="p-8 text-center border dashed border-[#333] rounded-xl text-gray-500">
                          <AlertCircle className="mx-auto mb-2 opacity-50" />
                          No tournaments found. <br/> Try running a Sync.
                        </div>
                      ) : (
                         tournaments.map((t, i) => (
                           <div key={i} className="min-h-[10rem]">
                               <TournamentCard
                                  title={t.title}
                                  location={t.location}
                                  date={t.date_range}
                                  status={t.status || "Open"}
                                  cost={t.estimated_cost}
                                  events={t.events}
                                  tier={t.tier}
                                  flyer_url={t.flyer_url}
                                />
                           </div>
                        ))
                      )}
                    </div>

                    {/* Right: Calendar View */}
                     <div className="h-full min-h-[400px]">
                         <CalendarView
                             tournaments={allTournaments}
                             userRating={user?.rating || 1500}
                             onToggleRegion={async (isInternational) => {
                                 try {
                                     const res = await fetch(`${API_URL}/tournaments?region=${isInternational ? 'international' : 'local'}`);
                                     const data = await res.json();
                                     setAllTournaments(data);
                                     setTournaments(data.slice(0, 3));
                                     setCachedData('tournaments', data);
                                 } catch (err) {
                                     console.error("Region toggle fetch error:", err);
                                 }
                             }}
                         />
                     </div>
                </div>
             </section>
          </div>

          {/* Row 2b: Right Column (Partners & Patterns) */}
          <div className="col-span-5 flex flex-col gap-6">
            <div>
                <PracticePartners limit={2} />
            </div>

            <div>
                <DrillLab />
            </div>
            
            <div className="flex-1">
                <PatternAnalysis source={viewMode} />
            </div>
          </div>
          
        </div>
      </main>
      <AIAlertPopup />
    </div>
  );
}
