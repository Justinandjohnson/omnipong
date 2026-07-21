"use client";
import Sidebar from "@/components/Sidebar";
import StadiumSyncPanel from "@/components/StadiumSyncPanel";
import { useEffect, useState } from "react";
import { User, Shield, Download, Terminal } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface RubberrUser {
  full_name?: string;
  usatt_number?: string;
  rating?: number;
}

export default function SettingsPage() {
  const [user, setUser] = useState<RubberrUser | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/user`).then(r => r.json()).then(setUser).catch(() => {});
  }, []);

  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      <main className="flex-1 md:ml-64 pt-14 md:pt-0 p-8 overflow-y-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold">Settings</h1>
          <p className="text-gray-400">Manage your profile and integrations.</p>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl">
          {/* Profile Section */}
          <section className="bg-[var(--card)] p-6 rounded-2xl border border-[#333]">
            <div className="flex items-center gap-3 mb-6">
              <User className="text-[var(--rubber-red)]" size={24} />
              <h2 className="text-xl font-bold">Player Profile</h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-gray-500 uppercase font-bold tracking-wider">Full Name</label>
                <div className="p-3 bg-[#111] rounded-lg text-gray-200 mt-1 border border-[#333]">
                  {user?.full_name || "Guest"}
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase font-bold tracking-wider">USATT Number</label>
                <div className="p-3 bg-[#111] rounded-lg text-gray-200 mt-1 border border-[#333]">
                  {user?.usatt_number || "N/A"}
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase font-bold tracking-wider">Current Rating</label>
                <div className="p-3 bg-[#111] rounded-lg text-[var(--rubber-red)] font-bold mt-1 border border-[#333]">
                  {user?.rating || "N/A"}
                </div>
              </div>
            </div>
          </section>

          {/* Private data sync — no stored passwords */}
          <section className="bg-[var(--card)] p-6 rounded-2xl border border-[#333]">
            <div className="flex items-center gap-3 mb-6">
              <Shield className="text-[var(--rubber-red)]" size={24} />
              <h2 className="text-xl font-bold">Private Data Sync</h2>
            </div>
            <p className="text-xs text-gray-500 mb-4">
              We never ask for or store your Stadium/USATT password. You log in yourself,
              in your own browser &mdash; a small companion app on your machine lets our AI
              agent drive that already-logged-in tab to read your matches. Anything
              private stays on <span className="text-gray-300">this device</span>.
            </p>

            <div className="space-y-4">
              <div className="p-4 bg-[#111] rounded-xl border border-[#333] space-y-2">
                <div className="font-bold flex items-center gap-2 text-sm">
                  <Terminal size={14} className="text-[var(--rubber-red)]" />
                  1. Run the companion
                </div>
                <p className="text-xs text-gray-500">
                  The companion launches your own Chrome, opens one outbound connection
                  to our relay, and shows you a &ldquo;Log in / solve, then Continue&rdquo; prompt
                  whenever a login or verification step needs you. It never sends your
                  credentials anywhere.
                </p>
                <div className="inline-flex items-center gap-2 mt-1 text-xs font-mono text-gray-300 bg-[#0a0a0a] border border-[#333] rounded px-2 py-1.5">
                  <Download size={13} className="text-[var(--rubber-red)] shrink-0" />
                  cd companion &amp;&amp; ./run.sh — see companion/README.md
                </div>
              </div>

              <StadiumSyncPanel playerName={user?.full_name || ""} />
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
