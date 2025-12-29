"use client";
import Sidebar from "@/components/Sidebar";
import TournamentCard from "@/components/TournamentCard";
import { useEffect, useState } from "react";
import { Search, MapPin, Sparkles } from "lucide-react";

export default function TournamentsPage() {
  const [tournaments, setTournaments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("All"); 
  const [aiInsights, setAiInsights] = useState<any>(null);
  const [userState, setUserState] = useState<string>("TX"); // Default to TX until detected
  const [detectingLoc, setDetectingLoc] = useState(true);

  // Known Major Cities for the detected state (AI-lite: extendable map)
  // For now we keep the robust list for TX, but we can add others if needed or rely on string match
  const CITY_MAP: Record<string, string[]> = {
      "TX": ["plano", "austin", "houston", "san antonio", "dallas", "richardson", "irving", "katy", "allen", "colleyville", "round rock", "fort worth", "lubbock", "el paso", "arlington", "pearland", "sugar land", "frisco", "mckinney"],
      "CA": ["los angeles", "san francisco", "san diego", "sacramento", "san jose", "fremont", "irvine"],
      "NY": ["new york", "brooklyn", "queens", "manhattan", "bronx", "staten island", "flushing", "westchester"]
  };

  const isLocal = (location: string, targetState: string) => {
      if (!location) return false;
      const loc = location.toLowerCase();
      const stateCode = targetState.toLowerCase();
      
      // 1. Direct State Match
      if (loc.includes(` ${stateCode}`) || loc.includes(`, ${stateCode}`)) return true;
      
      // 2. Full State Name Match (Simple map)
      const stateNames: Record<string, string> = { "tx": "texas", "ca": "california", "ny": "new york" };
      if (stateNames[stateCode] && loc.includes(stateNames[stateCode])) return true;
      
      // 3. City Match (Smart Filter)
      const cities = CITY_MAP[targetState] || [];
      return cities.some(city => loc.includes(city));
  };

  useEffect(() => {
    // 1. Load Data
    fetch('http://localhost:8000/tournaments?region=all')
      .then(res => res.json())
      .then(data => {
        setTournaments(data);
        setLoading(false);
      })
      .catch(e => setLoading(false));

    // 2. Detect & Set AI Filter Location
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(async (pos) => {
            try {
                const { latitude, longitude } = pos.coords;
                const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`);
                const data = await res.json();
                
                // Smart parse state
                const addr = data.address;
                const state = addr.state; // "Texas"
                
                // Map full name to code if possible, or just use code
                // Heuristic: Use first 2 chars upper if unknown
                let code = "TX"; 
                if (state) {
                     if (state.toLowerCase() === "texas") code = "TX";
                     else if (state.toLowerCase() === "california") code = "CA";
                     else if (state.toLowerCase() === "new york") code = "NY";
                     else code = state.substring(0,2).toUpperCase();
                }
                
                setUserState(code);
                setFilter(code); // Auto-select local
            } catch (e) {
                console.log("Loc detection failed, defaulting to TX");
            } finally {
                setDetectingLoc(false);
            }
        }, () => setDetectingLoc(false));
    }

    // 3. Load AI Insights
    fetch('http://localhost:8000/tools/tournament_intelligence?limit=200')
      .then(res => res.json())
      .then(data => setAiInsights(data))
      .catch(e => console.error(e));
  }, []);

  // Get AI insights for a specific tournament
  const getInsightsForTournament = (tournamentTitle: string) => {
    if (!aiInsights?.recommendations) return null;
    return aiInsights.recommendations.find((rec: any) => rec.tournament === tournamentTitle);
  };

  const filtered = tournaments.filter(t => {
     const tLoc = t.location || ""; // Fix null crash
     const matchesSearch = t.title.toLowerCase().includes(search.toLowerCase()) || 
                           tLoc.toLowerCase().includes(search.toLowerCase());
     
     const isLoc = isLocal(tLoc, userState);
     
     const matchesFilter = filter === "All" ? true : 
                           filter === userState ? isLoc :
                           !isLoc; // National = Not Local
                           
     return matchesSearch && matchesFilter;
  });

  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      <main className="flex-1 ml-64 p-8 overflow-y-auto h-screen">
        <header className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Tournament Finder</h1>
          <p className="text-gray-400">Discover and register for upcoming events.</p>
        </header>

        {/* Controls */}
        <div className="flex gap-4 mb-8">
            <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={20} />
                <input
                    type="text"
                    placeholder="Search tournaments..."
                    className="w-full bg-[#1a1a1a] border border-[#333] rounded-xl pl-10 pr-4 py-3 text-white focus:outline-none focus:border-[var(--rubber-red)] transition-colors"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
            </div>
            <div className="flex bg-[#1a1a1a] rounded-xl p-1 border border-[#333]">
                <button onClick={() => setFilter("All")} className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${filter === "All" ? "bg-[#333] text-white" : "text-gray-400 hover:text-white"}`}>All</button>
                
                <button onClick={() => setFilter(userState)} className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${filter === userState ? "bg-[var(--rubber-red)] text-white shadow-lg" : "text-gray-400 hover:text-white"}`}>
                   {detectingLoc ? <Sparkles size={12} className="animate-spin" /> : null}
                   {userState === "TX" ? "Texas Only" : `${userState} Only`}
                </button>
                
                <button onClick={() => setFilter("Other")} className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${filter === "Other" ? "bg-[#333] text-white" : "text-gray-400 hover:text-white"}`}>National</button>
            </div>
        </div>

        {/* AI Status Indicator */}
        {aiInsights && (
          <div className="mb-6 text-sm text-gray-400 flex items-center gap-2">
            <Sparkles size={16} className="text-purple-400" />
            AI insights loaded for {aiInsights.tournaments_analyzed} tournaments based on your rating ({aiInsights.user_rating}) • Hover over cards for details
          </div>
        )}

        {/* Grid */}
        {loading ? (
             <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {[1,2,3,4,5,6].map(i => <div key={i} className="h-48 bg-[#1a1a1a] animate-pulse rounded-2xl"></div>)}
             </div>
        ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-12">
                {filtered.map((t, i) => (
                    <TournamentCard
                        key={i}
                        title={t.title}
                        location={t.location}
                        date={t.date_range}
                        status={t.status}
                        flyer_url={t.flyer_url}
                        aiInsights={getInsightsForTournament(t.title)}
                    />
                ))}
            </div>
        )}
        
        {!loading && filtered.length === 0 && (
            <div className="text-center py-20 text-gray-500">
                <MapPin size={48} className="mx-auto mb-4 opacity-20" />
                <p>No tournaments found matching your criteria.</p>
            </div>
        )}

      </main>
    </div>
  );
}
