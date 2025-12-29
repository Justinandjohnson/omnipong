import { useState, useEffect } from 'react';
import { Calendar, MapPin, DollarSign, Trophy, Star, Sparkles, Users, Loader2, Check, FileText } from 'lucide-react';

interface TournamentProps {
    title: string;
    location: string;
    date: string;
    status: string;
    cost?: string;
    events?: string;
    tier?: string;
    flyer_url?: string;
    aiInsights?: any;
}

export default function TournamentCard({ title, location, date, status, cost, events, tier, flyer_url, aiInsights }: TournamentProps) {
  const [loading, setLoading] = useState(false);
  const [signedUp, setSignedUp] = useState(false);

  const handleSignup = async () => {
      setLoading(true);
      try {
          // Extract event names from objects
          const recommendedEvents = aiInsights?.recommended_events?.map((e: any) => e.name) || [];
          const response = await fetch(`http://localhost:8000/tournaments/signup?tournament_title=${encodeURIComponent(title)}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(recommendedEvents)
          });
          const data = await response.json();
          if (data.status === 'success') {
              setSignedUp(true);
          } else {
              alert(`Signup failed: ${data.message || 'Unknown error'}`);
          }
      } catch (err) {
          console.error("Signup error:", err);
          alert("Failed to trigger AI signup. Is the backend running?");
      } finally {
          setLoading(false);
      }
  };

  return (
    <div className="p-5 rounded-2xl bg-[#1a1a1a] border border-[#333] hover:border-[var(--rubber-red)] transition-all cursor-pointer group grid grid-cols-1 overflow-hidden relative">
      
      {/* Decorative Gradient - Absolute is fine as it doesn't affect flow */}
      <div className="absolute top-0 right-0 w-32 h-32 bg-[var(--rubber-red)] opacity-5 blur-2xl rounded-full -translate-y-1/2 translate-x-1/2 group-hover:opacity-10 transition-opacity" />

      {/* Layer 1: AI Insights (Determines height if taller) */}
      <div className={`col-start-1 row-start-1 transition-opacity duration-300 ${aiInsights ? 'opacity-0 group-hover:opacity-100 z-10' : 'hidden'}`}>
        {aiInsights && (
          <div className="h-full bg-gradient-to-br from-purple-900/95 to-pink-900/95 backdrop-blur-sm rounded-xl p-1 -m-1"> 
             {/* Note: Added small negative margin/padding wrapper to mimic the inset overlay look while being in-flow */}
             <div className="flex items-center gap-2 mb-3">
                <Sparkles size={16} className="text-purple-400" />
                <h4 className="font-bold text-white text-sm">AI Insights</h4>
             </div>

             <div className={`inline-block px-2 py-1 rounded-full text-[10px] font-medium mb-3 ${
                aiInsights.difficulty_score <= 5 ? 'bg-green-500/30 text-green-300' :
                aiInsights.difficulty_score <= 7 ? 'bg-yellow-500/30 text-yellow-300' :
                'bg-red-500/30 text-red-300'
             }`}>
                {aiInsights.recommended_events?.[0]?.competitiveness || "Recommended Opportunity"}
             </div>

             <div className="space-y-4 text-sm pb-1">
                <div>
                  <div className="text-purple-200 font-bold mb-1">Recommended Events:</div>
                  {aiInsights.recommended_events?.map((evt: any, i: number) => (
                    <div key={i} className="text-white font-medium flex justify-between items-center text-xs bg-black/20 rounded p-1 mb-1">
                        <span>• {evt.name}</span>
                        {evt.fee && <span className="text-green-300">${evt.fee}</span>}
                    </div>
                  ))}
                </div>

                {/* Signup Button for AI Insights View */}
                <button 
                  onClick={(e) => {
                    e.stopPropagation();
                    handleSignup();
                  }}
                  disabled={loading || signedUp}
                  className={`
                    w-full py-2 rounded-lg font-bold text-xs flex items-center justify-center gap-2 transition-all
                    ${signedUp 
                      ? 'bg-green-500 text-white' 
                      : 'bg-white text-purple-900 hover:bg-purple-100'
                    }
                    ${loading ? 'opacity-70 cursor-not-allowed' : ''}
                  `}
                >
                  {loading ? <Loader2 size={14} className="animate-spin" /> : signedUp ? <Check size={14} /> : <Sparkles size={14} />}
                  {loading ? 'AI Signing Up...' : signedUp ? 'Signed Up!' : 'Sign Up with AI'}
                </button>

                {aiInsights.doubles_partner_suggestions?.length > 0 && (
                  <div>
                    <div className="text-pink-200 font-bold mb-1 flex items-center gap-1">
                      <Users size={14} /> Doubles Partners:
                    </div>
                    {aiInsights.doubles_partner_suggestions.slice(0, 3).map((p: any, i: number) => (
                      <div key={i} className="text-white font-medium">• {p.name} ({p.rating})</div>
                    ))}
                  </div>
                )}

                {aiInsights.known_players_likely_attending?.length > 0 && (
                   <div>
                     <div className="text-blue-200 font-bold mb-1">Known Players:</div>
                     {aiInsights.known_players_likely_attending.slice(0, 3).map((p: any, i: number) => (
                       <div key={i} className="text-white font-medium">• {p.name} ({p.your_record})</div>
                     ))}
                   </div>
                 )}
              </div>
           </div>
        )}
      </div>

      {/* Layer 2: Normal Content (Determines height if taller) */}
      <div className={`col-start-1 row-start-1 flex flex-col justify-between h-full transition-opacity duration-300 ${aiInsights ? 'group-hover:opacity-0 pointer-events-none group-hover:pointer-events-none' : ''}`}>
          <div>
              <div className="flex justify-between items-start mb-3">
                <div className="flex gap-2">
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-green-500/10 text-green-500 border border-green-500/20">
                      {status || "Open"}
                    </span>
                    {tier && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 flex items-center gap-1">
                          <Star size={8} /> {tier}
                        </span>
                    )}
                </div>
              </div>
        
              <h3 className="font-bold text-base mb-2 text-white group-hover:text-[var(--rubber-red)] transition-colors line-clamp-2">
                {title}
              </h3>
        
              <div className="space-y-2 mb-4">
                  <p className="text-sm text-gray-300 flex items-center gap-2">
                    <Calendar size={14} className="text-gray-500" /> 
                    {date}
                  </p>
                  <p className="text-sm text-gray-300 flex items-center gap-2">
                    <MapPin size={14} className="text-gray-500" /> 
                    {location}
                  </p>
              </div>
          </div>
          
          {/* Footer Info */}
          <div className="pt-4 border-t border-[#222] flex justify-between items-center mt-auto">
              <div className="flex flex-col">
                  <span className="text-[10px] text-gray-400 uppercase font-bold">Entry Fee</span>
                  <span className="text-sm font-bold text-white flex items-center gap-0.5">
                      {cost || "$--"}
                  </span>
              </div>
              <div className="flex flex-col items-end">
                   <span className="text-[10px] text-gray-400 uppercase font-bold">Events</span>
                   <span className="text-sm text-gray-200 max-w-[120px] truncate text-right mb-2">
                       {events || "Check Flyer"}
                   </span>
                   
                   <div className="flex items-center gap-2">
                      {flyer_url && (
                        <a 
                          href={flyer_url} 
                          target="_blank" 
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="p-1.5 rounded-lg bg-gray-800 text-blue-400 hover:bg-gray-700 transition-colors"
                          title="View PDF Flyer"
                        >
                          <FileText size={14} />
                        </a>
                      )}

                      {!aiInsights && (
                        <button 
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSignup();
                          }}
                          disabled={loading || signedUp}
                          className={`
                            px-3 py-1.5 rounded-lg font-bold text-[10px] flex items-center justify-center gap-1.5 transition-all
                            ${signedUp 
                              ? 'bg-green-500/20 text-green-400 border border-green-500/40' 
                              : 'bg-[var(--rubber-red)] text-white hover:bg-red-600'
                            }
                            ${loading ? 'opacity-70 cursor-not-allowed' : ''}
                          `}
                        >
                          {loading ? <Loader2 size={10} className="animate-spin" /> : signedUp ? <Check size={10} /> : <Sparkles size={10} />}
                          {loading ? 'Signing Up...' : signedUp ? 'Signed Up' : 'AI Sign Up'}
                        </button>
                      )}
                   </div>
              </div>
          </div>
      </div>
    </div>
  );
}
