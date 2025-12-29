"use client";
import { useConversation } from '@elevenlabs/react';
import { motion } from 'framer-motion';
import { useCallback, useState, useEffect, useRef } from 'react';
import { Mic, X, Radio } from 'lucide-react';

// Define tools outside to prevent re-creation on render
const clientTools = {
    // === DATA RETRIEVAL ===
    getContext: async () => {
         try {
             const res = await fetch('http://localhost:8000/tools/context');
             if (!res.ok) throw new Error(`HTTP ${res.status}`);
             const data = await res.json();
             return JSON.stringify(data);
         } catch(e) {
             console.error("Tool Error (getContext):", e);
             return "Error fetching user context and recent match history.";
         }
    },
    
    getStats: async () => {
        try {
            const res = await fetch('http://localhost:8000/tools/stats');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            console.error("Tool Error (getStats):", e);
            return "Error fetching win/loss statistics.";
        }
    },

    getAnalysis: async () => {
        try {
            const res = await fetch('http://localhost:8000/tools/analysis');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            console.error("Tool Error (getAnalysis):", e);
            return "Error fetching match analysis and psychological patterns.";
        }
    },

    // === SYNC CONTROL ===
    syncOmnipong: async () => {
        try {
            const res = await fetch('http://localhost:8000/tools/sync/omnipong', { method: 'POST' });
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            return JSON.stringify({ status: "error", message: String(e) });
        }
    },
    
    syncStadium: async () => {
        try {
            const res = await fetch('http://localhost:8000/tools/sync/stadium', { method: 'POST' });
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            return JSON.stringify({ status: "error", message: String(e) });
        }
    },
    
    syncLeague: async () => {
        try {
            const res = await fetch('http://localhost:8000/tools/sync/league', { method: 'POST' });
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            return JSON.stringify({ status: "error", message: String(e) });
        }
    },
    
    syncLeaguePlayers: async () => {
        try {
            const res = await fetch('http://localhost:8000/tools/sync/league_players', { method: 'POST' });
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            return JSON.stringify({ status: "error", message: String(e) });
        }
    },

    syncTournaments: async (parameters: any) => {
        try {
            const { scope } = parameters || { scope: 'regional' };
            const res = await fetch(`http://localhost:8000/tools/sync/tournaments?scope=${scope}`, { method: 'POST' });
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            return JSON.stringify({ status: "error", message: String(e) });
        }
    },
    
    // === DATA QUERIES ===
    queryMatches: async (parameters: any) => {
        try {
            const { opponent_name, date_from, result } = parameters || {};
            const queryParams = new URLSearchParams();
            if (opponent_name) queryParams.append('opponent_name', opponent_name);
            if (date_from) queryParams.append('date_from', date_from);
            if (result) queryParams.append('result', result);
            
            const res = await fetch(`http://localhost:8000/tools/query/matches?${queryParams}`, { method: 'POST' });
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            return JSON.stringify({ error: String(e) });
        }
    },
    
    calculateStats: async (parameters: any) => {
        try {
            const { metric } = parameters || {};
            const res = await fetch(`http://localhost:8000/tools/stats/calculate?metric=${metric}`, { method: 'POST' });
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            return JSON.stringify({ error: String(e) });
        }
    },
    
    searchTournaments: async (parameters: any) => {
        try {
            const { location, date_from } = parameters || {};
            const queryParams = new URLSearchParams();
            if (location) queryParams.append('location', location);
            if (date_from) queryParams.append('date_from', date_from);

            const res = await fetch(`http://localhost:8000/tools/query/tournaments?${queryParams}`, { method: 'POST' });
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            return JSON.stringify({ error: String(e) });
        }
    },

    getPracticePartners: async (parameters: any) => {
        try {
            const { limit } = parameters || {};
            const res = await fetch(`http://localhost:8000/tools/practice_partners?limit=${limit || 5}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            console.error("Tool Error (getPracticePartners):", e);
            return JSON.stringify({ error: "Error fetching practice partner recommendations." });
        }
    },

    getTournamentIntelligence: async (parameters: any) => {
        try {
            const { tournament_title, limit } = parameters || {};
            const queryParams = new URLSearchParams();
            if (tournament_title) queryParams.append('tournament_title', tournament_title);
            if (limit) queryParams.append('limit', limit.toString());

            const res = await fetch(`http://localhost:8000/tools/tournament_intelligence?${queryParams}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            return JSON.stringify(data);
        } catch(e) {
            console.error("Tool Error (getTournamentIntelligence):", e);
            return JSON.stringify({ error: "Error fetching tournament intelligence." });
        }
    }
};

const agentCallbacks = {
    onConnect: () => console.log('✅ Connected to Agent'),
    onDisconnect: () => console.log('❌ Disconnected'),
    onMessage: (msg: any) => console.log('📩 Message from Agent:', msg),
    onError: (message: string, context?: any) => {
        console.error('⚠️ Voice Agent Error:', message, context);
    },
    onStatusChange: ({ status }: { status: string }) => {
        console.log('🔄 Connection Status Changed:', status);
    }
};

export default function VoiceAgent() {
  const [isOpen, setIsOpen] = useState(false);
  
  // NOTE: Removed clientTools temporarily to test if they're causing the disconnect.
  // The tools defined here MUST match exactly what's configured in the ElevenLabs dashboard.
  // If there's a mismatch, the server disconnects immediately.
  const conversation = useConversation({
    clientTools: clientTools,
    ...agentCallbacks
  });

  // Maintain a ref to the conversation instance for reliable cleanup on unmount
  const conversationRef = useRef(conversation);
  useEffect(() => {
      conversationRef.current = conversation;
  }, [conversation]);

  // FINAL SAFETY CLEANUP: Ensure any lingering session is ended when the component unmounts
  useEffect(() => {
      return () => {
          const current = conversationRef.current;
          if (current.status === 'connected' || current.status === 'connecting') {
              console.log("🧹 Cleaning up session on unmount...");
              current.endSession().catch(e => console.warn("Cleanup error:", e));
          }
      };
  }, []);

  const handleStart = useCallback(async () => {
      const agentId = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID || "mA8M9G5vMMdp6ibsraBq";
      
      try {
          // Explicitly request mic permission before starting
          await navigator.mediaDevices.getUserMedia({ audio: true });
          
          if (conversation.status === 'disconnected') {
              console.log("🚀 Starting Session (WebSocket)...");
              await conversation.startSession({
                  agentId: agentId,
                  connectionType: 'websocket' // Using WebSocket to avoid WebRTC DataChannel crash bug
              });
          } else {
              console.warn("⚠️ Cannot start session: already in state", conversation.status);
          }
      } catch (e) {
          console.error("❌ Failed to start conversation:", e);
          alert("Could not access microphone or start session.");
      }
  }, [conversation]);

  const handleStop = useCallback(async () => {
      console.log("🛑 Ending Session...");
      await conversation.endSession();
  }, [conversation]);

  const toggle = () => {
      if (conversation.status === 'connected' || conversation.status === 'connecting') {
          handleStop();
          setIsOpen(false);
      } else {
          setIsOpen(true);
          handleStart();
      }
  }

  // Visual State
  const status = conversation.status; // 'connected', 'connecting', 'disconnected'
  const isSpeaking = conversation.isSpeaking;

  return (
    <div className="fixed bottom-6 right-6 z-[9999]">
        {/* Expanded Window */}
        <motion.div 
            initial={false}
            animate={{ 
                width: isOpen ? 320 : 64, 
                height: isOpen ? 400 : 64,
                borderRadius: isOpen ? 24 : 32 
            }}
            className="bg-[#0a0a0a] border border-[#333] shadow-2xl overflow-hidden relative"
        >
            {/* Collapsed Button State */}
            {!isOpen && (
                <button 
                    onClick={toggle}
                    className="w-full h-full flex items-center justify-center bg-[var(--rubber-red)] text-white hover:scale-110 transition-transform"
                >
                    <Mic size={24} />
                </button>
            )}

            {/* Expanded Active State */}
            {isOpen && (
                <div className="flex flex-col h-full relative">
                    {/* Header */}
                    <div className="p-4 flex justify-between items-center border-b border-[#333]">
                        <div className="flex items-center gap-2">
                             <div className={`w-2 h-2 rounded-full ${status === 'connected' ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`} />
                             <span className="text-xs font-bold text-gray-400">
                                 {status === 'connected' ? 'Coach Listening' : 'Connecting...'}
                             </span>
                        </div>
                        <button onClick={toggle} className="p-2 hover:bg-[#222] rounded-full text-gray-400">
                            <X size={18} />
                        </button>
                    </div>

                    {/* Visualizer Area */}
                    <div className="flex-1 flex flex-col items-center justify-center p-8 relative">
                        {/* Orb Animation */}
                        <motion.div 
                            animate={{ 
                                scale: isSpeaking ? [1, 1.2, 1] : 1,
                                opacity: isSpeaking ? 1 : 0.5,
                            }}
                            transition={{ repeat: Infinity, duration: 1.5 }}
                            className="w-32 h-32 rounded-full bg-gradient-to-br from-[var(--rubber-red)] to-[var(--rubber-accent)] blur-2xl absolute opacity-20"
                        />
                        <div className="w-24 h-24 rounded-full bg-black border border-[#333] flex items-center justify-center relative z-10 shadow-2xl shadow-red-900/20">
                             <Radio size={32} className={isSpeaking ? "text-white animate-pulse" : "text-gray-600"} />
                        </div>
                        
                        <p className="mt-8 text-center text-sm text-gray-400">
                            {isSpeaking ? "Speaking..." : "Ask me about your matches..."}
                        </p>
                    </div>

                    {/* Controls */}
                    <div className="p-4 bg-[#111] border-t border-[#333]">
                         <div className="flex gap-2 justify-center">
                             <button onClick={() => conversation.setVolume({ volume: 0 })} className="px-4 py-2 text-xs bg-[#222] rounded-full text-gray-400">Mute</button>
                             <button onClick={toggle} className="px-4 py-2 text-xs bg-red-500/10 text-red-500 border border-red-500/20 rounded-full hover:bg-red-500/20">End Session</button>
                         </div>
                    </div>
                </div>
            )}
        </motion.div>
    </div>
  );
}
