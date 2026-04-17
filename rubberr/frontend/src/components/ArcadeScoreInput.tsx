"use client";
import React, { useState } from 'react';
import { Gamepad2, Mic, Send, Trophy, Skull, Search, Square } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function ArcadeScoreInput({ onScoreSubmit }: { onScoreSubmit: () => void }) {
  // ... (State declarations remain same)
  const [input, setInput] = useState("");
  const [opponent, setOpponent] = useState("");
  const [loading, setLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [lastResult, setLastResult] = useState<{ summary: string, match_id: number } | null>(null);
  
  // State for parsed preview
  const [parsedIntent, setParsedIntent] = useState<{
      player1_name?: string,
      player2_name?: string,
      player1_score?: number,
      player2_score?: number,
      summary?: string
  } | null>(null);

  const mediaRecorderRef = React.useRef<MediaRecorder | null>(null);
  const chunksRef = React.useRef<Blob[]>([]);
  const mimeTypeRef = React.useRef<string>("");

  // Future: Player Lookup State
  const [searchResult, setSearchResult] = useState<any>(null);

  const handleSubmit = async () => {
    if (!input || !opponent) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/arcade/submit_score`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player1_name: "Justin",  // Current user
          player2_name: opponent,
          manual_score: input
        })
      });
      const data = await res.json();
      
      if (data.status === "success") {
        setLastResult(data);
        setInput("");
        onScoreSubmit(); // Refresh parent stats
      } else {
        alert("Error: " + data.message);
      }
    } catch (e) {
      alert("Submission failed");
    } finally {
      setLoading(false);
    }
  };

  const handlePlayerSearch = async (name: string) => {
      setOpponent(name);
      if (name.length > 2) {
          try {
              const res = await fetch(`${API_URL}/arcade/lookup_player`, {
                  method: 'POST',  
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({ name })
              });
              const data = await res.json();
              if (data.status === 'not_found') {
                  setSearchResult({ status: 'not_found' });
              } else {
                  setSearchResult(data.player);
              }
          } catch(e) {}
      } else {
          setSearchResult(null);
      }
  }

  const getSupportedMimeType = () => {
      const types = [
          'audio/webm;codecs=opus', 
          'audio/webm', 
          'audio/mp4', 
          'audio/ogg', 
          'audio/wav'
      ];
      for (const t of types) {
          if (MediaRecorder.isTypeSupported(t)) return t;
      }
      return ''; // Fallback to browser default
  };

  const getExtension = (mime: string) => {
      if (mime.includes('mp4')) return 'mp4';
      if (mime.includes('ogg')) return 'ogg';
      if (mime.includes('wav')) return 'wav';
      return 'webm'; // Default
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      const mimeType = getSupportedMimeType();
      mimeTypeRef.current = mimeType;
      
      const options = mimeType ? { mimeType } : undefined;
      const mediaRecorder = new MediaRecorder(stream, options);
      
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        const type = mimeTypeRef.current || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type });
        const ext = getExtension(type);
        await processAudio(blob, `recording.${ext}`);
        stream.getTracks().forEach(track => track.stop()); // Cleanup
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Mic Error:", err);
      alert("Microphone access denied or error occurred.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const processAudio = async (audioBlob: Blob, filename = "recording.webm") => {
      setLoading(true);
      const formData = new FormData();
      formData.append("file", audioBlob, filename);

      try {
          const res = await fetch(`${API_URL}/arcade/transcribe`, {
              method: 'POST',
              body: formData
          });
          const data = await res.json();
          
          if (data.status === "success" && data.intent) {
              // Auto-fill from AI Intent
              if (data.intent) {
                  const { player1_name, player2_name, player1_score, player2_score } = data.intent;

                  if (player2_name) {
                      setOpponent(player2_name);
                      handlePlayerSearch(player2_name);
                  }

                  // Set Preview
                  if (player1_score !== undefined && player2_score !== undefined) {
                      setParsedIntent({
                          player1_name: player1_name || "Justin",
                          player2_name: player2_name || "Opponent",
                          player1_score,
                          player2_score,
                          summary: `${player1_score} - ${player2_score}`
                      });
                  }
              }
              
              // Set the text box to the confirmation or transcript
              if (data.confirmation) {
                 setInput(data.transcript); // Keep transcript in box for editing
              } else {
                 setInput(data.transcript);
              }
          } else {
              console.error("Transcription Error:", data);
              alert("Transcription failed or unclear. Check console.");
          }
      } catch (e) {
          console.error(e);
          alert("Audio processing failed.");
      } finally {
          setLoading(false);
      }
  };

  const handleDragOver = (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
  };
  const handleDrop = async (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      
      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
          const file = files[0];
          if (file.type.startsWith('audio/') || file.type.startsWith('video/')) {
              await processAudio(file, file.name);
          } else {
              alert("Please drop an audio file.");
          }
      }
  };

  return (
    <div className="mb-8">
        <div 
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`bg-gradient-to-r from-[#1a0524] to-[#0f0214] border rounded-2xl p-6 relative overflow-hidden group transition-all duration-300
                ${isDragging ? 'border-[var(--rubber-red)] shadow-[0_0_30px_rgba(239,68,68,0.3)] scale-[1.02]' : 'border-[var(--rubber-red)]/30'}`}
        >
            {isDragging && (
                <div className="absolute inset-0 bg-[var(--rubber-red)]/20 z-50 flex items-center justify-center backdrop-blur-sm">
                    <p className="text-xl font-bold text-white animate-bounce">Drop Voice Memo Here</p>
                </div>
            )}
            
            {/* Background Glow */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--rubber-red)]/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 group-hover:bg-[var(--rubber-red)]/10 transition-all duration-700" />

            <div className="relative z-10">
                <div className="flex items-center gap-3 mb-6">
                    <div className="p-2 bg-[var(--rubber-red)]/20 rounded-lg text-[var(--rubber-red)] border border-[var(--rubber-red)]/50">
                        <Gamepad2 size={24} />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-white tracking-tight">New Arcade Match</h2>
                        <p className="text-xs text-[var(--foreground)] opacity-70">Log a recreational game instantly</p>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Opponent Input */}
                    <div className="space-y-2">
                        <label className="text-xs font-bold text-[var(--foreground)] uppercase ml-1">Vs Opponent</label>
                        <div className="relative">
                            <input 
                                type="text"
                                value={opponent}
                                onChange={(e) => handlePlayerSearch(e.target.value)}
                                placeholder="Friend's Name..."
                                className="w-full bg-[#05010a] border border-[#333] rounded-xl px-4 py-3 text-white focus:outline-none focus:border-[var(--rubber-red)] transition-all placeholder:text-gray-700"
                            />
                            <Search className="absolute right-3 top-3.5 text-gray-600" size={16} />
                            
                            {/* Player Hint */}
                            {searchResult && (
                                <div className={`absolute top-full left-0 mt-2 w-full border rounded-lg p-2 z-20 text-xs flex justify-between
                                    ${searchResult.status === 'not_found' ? 'bg-red-900/20 border-red-500/30 text-red-400' : 'bg-[#111] border-[#333] text-gray-400'}`}>
                                    
                                    {searchResult.status === 'not_found' ? (
                                        <span>User Not Found (Strict Mode)</span>
                                    ) : (
                                        <>
                                            <span>{searchResult.name}</span>
                                            <span className="font-bold text-[var(--rubber-accent)]">Rating: {searchResult.rating}</span>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Score Input */}
                    <div className="space-y-2">
                        <label className="text-xs font-bold text-[var(--foreground)] uppercase ml-1">Result / Score</label>
                        
                        {/* AI Match Preview Card */}
                        {parsedIntent && (
                            <div className="mb-2 p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg flex justify-between items-center animate-in fade-in slide-in-from-top-2">
                                <div className="flex flex-col">
                                    <span className="text-xs text-purple-400 font-bold uppercase">Match Preview</span>
                                    <span className="text-sm text-white font-mono">
                                        {parsedIntent.player1_name} vs {parsedIntent.player2_name} ({parsedIntent.summary})
                                    </span>
                                </div>
                                <button 
                                    onClick={() => setParsedIntent(null)}
                                    className="text-xs text-gray-500 hover:text-white"
                                >
                                    Clear
                                </button>
                            </div>
                        )}

                        <div className="flex gap-2 items-start">
                            <textarea
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder='"I won 3-1" or "11-9, 11-8"'
                                className="flex-1 bg-[#05010a] border border-[#333] rounded-xl px-4 py-3 text-white focus:outline-none focus:border-[var(--rubber-red)] transition-all placeholder:text-gray-700 font-mono min-h-[50px] resize-y"
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && !e.shiftKey) {
                                        e.preventDefault();
                                        handleSubmit();
                                    }
                                }}
                            />
                            
                            <div className="flex flex-col gap-2">
                                <button 
                                    onClick={handleSubmit}
                                disabled={loading || !opponent || !input}
                                className="bg-[var(--rubber-red)] hover:bg-[var(--rubber-dark)] text-white px-4 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center shadow-[0_0_15px_rgba(239,68,68,0.4)]"
                            >
                                {loading ? <div className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full" /> : <Send size={18} />}
                            </button>
                            
                            {/* Voice Button */}
                             <button 
                                onClick={isRecording ? stopRecording : startRecording}
                                className={`px-4 rounded-xl transition-all border flex items-center justify-center
                                    ${isRecording 
                                        ? 'bg-red-500/20 text-red-500 border-red-500 animate-pulse' 
                                        : 'bg-[#222] hover:bg-[#333] text-gray-400 border-[#333]'
                                    }`}
                             >
                                {isRecording ? <Square size={18} fill="currentColor" /> : <Mic size={18} />}
                            </button>
                        </div>
                    </div>
                </div>
                </div>

                {/* Success Feedback */}
                {lastResult && (
                    <div className="mt-4 p-3 bg-green-500/10 border border-green-500/30 rounded-xl flex items-center gap-3 text-green-400 text-sm animate-in fade-in slide-in-from-top-2">
                        <Trophy size={16} />
                        <span>Match Saved: <strong>{lastResult.summary}</strong></span>
                    </div>
                )}
            </div>
        </div>
    </div>
  );
}
