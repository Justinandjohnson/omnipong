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
import { RefreshCw, MapPin, AlertCircle } from "lucide-react"; 

import { useArcade } from "@/context/ArcadeContext";
import ArcadeScoreInput from "@/components/ArcadeScoreInput";

export default function Home() {
  const { isArcadeMode } = useArcade();
  const [tournaments, setTournaments] = useState<any[]>([]);
  const [user, setUser] = useState<{ full_name: string, rating: number } | null>(null);
  const [location, setLocation] = useState<{ lat: number, lng: number, state?: string } | null>(null);
  const [loadingLoc, setLoadingLoc] = useState(false);
  const [viewMode, setViewMode] = useState<"usatt" | "league" | "arcade">("league");

  // Sync viewMode with global Arcade state
  useEffect(() => {
    if (isArcadeMode) {
        setViewMode("arcade");
    } else {
        setViewMode("league"); // Default back to league or keep user preference? Resetting for simplicity
    }
  }, [isArcadeMode]);

  // 1. Fetch User
  const fetchUser = () => {
      fetch('http://localhost:8000/user')
      .then(res => {
        if (!res.ok) throw new Error("No user found");
        return res.json();
      })
      .then(d => setUser(d))
      .catch(e => console.log("User fetch error:", e));
  }

  // 2. Fetch Tournaments (Filtered by State if available)
  const fetchTournaments = (stateFilter?: string) => {
      let url = 'http://localhost:8000/tournaments';
      if (stateFilter) url += `?state=${stateFilter}`;
      
      fetch(url)
      .then(res => res.json())
      .then(d => setTournaments(d.slice(0, 3))) 
      .catch(e => console.error(e));
  }

  // 3. Geolocation Logic
  useEffect(() => {
    fetchUser();
    // ask for location immediately
    if (navigator.geolocation) {
      setLoadingLoc(true);
      navigator.geolocation.getCurrentPosition(async (position) => {
        const { latitude, longitude } = position.coords;
        
        // Reverse Geocode to get State
        try {
          const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`);
          const data = await res.json();
          // Extract state code if possible, or name
          // OSM returns "address": { "state": "Arizona", ... }
          const stateName = data.address?.state;
          const stateCode = stateName ? stateName.substring(0,2).toUpperCase() : null; // Simple heuristic for now
          
          setLocation({ lat: latitude, lng: longitude, state: stateName });
          fetchTournaments(stateName); // Filter by detected state
        } catch (err) {
          console.error("Reverse geocode failed", err);
          fetchTournaments(); // Fallback to all
        } finally {
          setLocation({ lat: latitude, lng: longitude }); // Fallback even if reverse fails
          setLoadingLoc(false);
        }
      }, (err) => {
        console.error("Loc permission denied", err);
        fetchTournaments();
        setLoadingLoc(false);
      });
    } else {
      fetchTournaments();
    }
  }, []);

  const handleSyncOmni = async () => {
      try {
          await fetch('http://localhost:8000/sync/omnipong', { method: 'POST' });
          fetchTournaments(location?.state); 
          fetchUser();
          alert("Quick Sync (OmniPong) executed!");
      } catch (e) {
          alert("Sync failed: " + e);
      }
  };

  const handleSyncStadium = async () => {
      try {
          await fetch('http://localhost:8000/sync/stadium', { method: 'POST' });
          fetchUser(); 
          alert("Full History Sync (Stadium) executed!");
      } catch (e) {
          alert("Sync failed: " + e);
      }
  };

  const handleSyncLeaguePlayers = async () => {
      try {
          const res = await fetch('http://localhost:8000/tools/sync/league_players', { method: 'POST' });
          const data = await res.json();
          if (data.status === "success") {
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
          const res = await fetch('http://localhost:8000/tools/sync/tournaments?scope=all', { method: 'POST' });
          const data = await res.json();
          if (data.status === "success") {
              fetchTournaments(location?.state);
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
      
      <main className="flex-1 ml-64 overflow-y-auto">
        
        {/* Hero Section (Full Width, No Padding) */}
        <div className="w-full h-[400px] relative">
           <CareerGraph 
             onSyncOmni={handleSyncOmni} 
             onSyncStadium={handleSyncStadium} 
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
             <RubberrStats rating={user?.rating || 0} source={viewMode} />
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
                
                {/* Arcade Mode Input Injection */}
                {isArcadeMode && (
                    <ArcadeScoreInput onScoreSubmit={fetchUser} />
                )}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Left: Cards List */}
                    <div className="space-y-3">
                      {tournaments.length === 0 ? (
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
                            tournaments={tournaments}
                            userRating={user?.rating || 1500}
                            onToggleRegion={(isInternational) => {
                                fetch(`http://localhost:8000/tournaments?region=${isInternational ? 'international' : 'local'}`)
                                    .then(res => res.json())
                                    .then(data => setTournaments(data));
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
