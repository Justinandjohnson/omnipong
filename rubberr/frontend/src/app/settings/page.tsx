"use client";
import Sidebar from "@/components/Sidebar";
import { useEffect, useState } from "react";
import { RefreshCw, User, Shield, Video } from "lucide-react";

export default function SettingsPage() {
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
     fetch('http://localhost:8000/user')
        .then(r => r.json())
        .then(setUser)
        .catch(e => console.error(e));
  }, []);

  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      <main className="flex-1 ml-64 p-8 overflow-y-auto">
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

            {/* Integrations Section */}
            <section className="bg-[var(--card)] p-6 rounded-2xl border border-[#333]">
                <div className="flex items-center gap-3 mb-6">
                    <Shield className="text-[var(--rubber-red)]" size={24} />
                    <h2 className="text-xl font-bold">Integrations</h2>
                </div>
                
                <div className="space-y-4">
                     <IntegrationCard 
                        name="OmniPong" 
                        status="Connected" 
                        color="text-green-500" 
                        description="Source for USATT ratings and tournament registration."
                     />
                     <IntegrationCard 
                         name="Stadium Compete" 
                         status="Offline" 
                         color="text-red-500"
                         description="League tracking integration."
                     />
                     <IntegrationCard 
                         name="Live Stream" 
                         status="Beta" 
                         color="text-yellow-500"
                         description="AI video analysis link."
                     />
                </div>
            </section>
        </div>
      </main>
    </div>
  );
}

function IntegrationCard({ name, status, color, description }: any) {
    return (
        <div className="p-4 bg-[#111] rounded-xl border border-[#333] flex justify-between items-center group hover:border-gray-500 transition-colors">
            <div>
                <div className="font-bold flex items-center gap-2">
                    {name} 
                    <span className={`text-xs ${color} px-2 py-0.5 bg-white/5 rounded-full border border-white/10`}>{status}</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">{description}</p>
            </div>
            <button className="p-2 rounded-lg hover:bg-[#333] transition-colors">
                <RefreshCw size={16} className="text-gray-400 group-hover:text-white" />
            </button>
        </div>
    )
}
