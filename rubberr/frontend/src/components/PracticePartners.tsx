"use client";
import React, { useState, useEffect } from 'react';
import { Users, MessageCircle, Settings, X, Shield } from 'lucide-react';
import ScoutingReport from './ScoutingReport';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function PracticePartners({ limit }: { limit?: number }) {
  const [partners, setPartners] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState("");
  const [scoutingPlayer, setScoutingPlayer] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/user`)
      .then(res => res.json())
      .then(data => {
        if (data.phone_number) setPhoneNumber(data.phone_number);
      })
      .catch(() => {});

    // Mock partner data for now as strictly not in DB yet
    const mockPartners = [
      { player_name: "Steve Smith", rating: 1180, reason: "Close match, good practice for pressure." },
      { player_name: "Alex Wong", rating: 1250, reason: "Plays aggressive, helps your defense." },
      { player_name: "Maria Garcia", rating: 1120, reason: "Excellent placement, improves your footwork." }
    ];
    setPartners(limit ? mockPartners.slice(0, limit) : mockPartners);
    setLoading(false);
  }, [limit]);

  const handleRemind = async (partner: any, index: number) => {
    setSendingId(index);
    try {
      const res = await fetch(`${API_URL}/tools/remind_practice_partner`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          partner_name: partner.player_name,
          reason: partner.reason
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        alert("Reminder sent!");
      } else {
        alert("Failed: " + data.message);
      }
    } catch (e) {
      alert("Error sending reminder");
    } finally {
      setSendingId(null);
    }
  };

  const savePhone = async () => {
    try {
      const res = await fetch(`${API_URL}/settings/update_phone`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneNumber })
      });
      const data = await res.json();
      if (data.status === 'success') {
        setShowSettings(false);
        alert("Phone number updated!");
      } else {
        alert("Failed: " + data.message);
      }
    } catch (e) {
      alert("Error updating phone");
    }
  };

  return (
    <div className="bg-[#1a1a1a] rounded-2xl border border-[#333] p-6 h-full relative overflow-hidden group">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Users size={20} className="text-[var(--rubber-red)]" />
          <h2 className="text-lg font-bold">Practice Partners</h2>
        </div>
        <button 
          onClick={() => setShowSettings(true)}
          className="text-gray-500 hover:text-white transition-colors"
        >
          <Settings size={18} />
        </button>
      </div>

      <div className="space-y-4">
        {partners.map((p, i) => (
          <div key={i} className="bg-[#222] border border-[#333] rounded-xl p-4 hover:border-[var(--rubber-red)] transition-all">
            <div className="flex justify-between items-start mb-2">
              <div>
                <h3 className="font-bold text-white">{p.player_name}</h3>
                <p className="text-xs text-gray-500">Rating: {p.rating}</p>
              </div>
              <div className="flex items-center gap-2">
                <button 
                  onClick={() => setScoutingPlayer(p.player_name)}
                  className="p-2 bg-[#111] hover:bg-[#333] rounded-lg text-gray-400 hover:text-[var(--rubber-red)] transition-all"
                  title="Scouting Report"
                >
                  <Shield size={16} />
                </button>
                <button 
                  onClick={() => handleRemind(p, i)}
                  disabled={sendingId === i}
                  className="p-2 bg-[#111] hover:bg-[#333] rounded-lg text-gray-400 hover:text-white transition-all disabled:opacity-50"
                  title="Send Reminder"
                >
                  <MessageCircle size={16} className={sendingId === i ? "animate-pulse" : ""} />
                </button>
              </div>
            </div>
            <p className="text-xs text-gray-400 leading-relaxed italic">
              "{p.reason}"
            </p>
          </div>
        ))}
      </div>

      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#1a1a1a] border border-[#333] rounded-2xl p-6 max-w-sm w-full relative">
            <button onClick={() => setShowSettings(false)} className="absolute top-4 right-4 text-gray-500 hover:text-white"><X size={20}/></button>
            <h3 className="text-lg font-bold mb-4">Reminder Settings</h3>
            <div className="space-y-4">
              <div>
                <label className="text-xs font-bold text-gray-500 uppercase mb-1 block tracking-widest">Phone Number</label>
                <input 
                  type="text" 
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder="+18041234567"
                  className="w-full bg-[#111] border border-[#333] rounded-lg px-4 py-2 text-white outline-none focus:border-[var(--rubber-red)]"
                />
              </div>
              <button 
                onClick={savePhone}
                className="w-full bg-[var(--rubber-red)] text-white py-2 rounded-lg font-bold hover:brightness-110 transition-all"
              >
                Save Number
              </button>
            </div>
          </div>
        </div>
      )}

      {scoutingPlayer && (
        <ScoutingReport 
            playerName={scoutingPlayer} 
            onClose={() => setScoutingPlayer(null)} 
        />
      )}
    </div>
  );
}
