"use client";
import Sidebar from "@/components/Sidebar";
import { useEffect, useState } from "react";
import { RefreshCw, User, Shield, Save, Trash2, Eye, EyeOff } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ServiceCreds {
  configured: boolean;
  username: string;
}

export default function SettingsPage() {
  const [user, setUser] = useState<any>(null);
  const [creds, setCreds] = useState<Record<string, ServiceCreds>>({});
  const [omnipongUser, setOmnipongUser] = useState("");
  const [omnipongPass, setOmnipongPass] = useState("");
  const [stadiumUser, setStadiumUser] = useState("");
  const [stadiumPass, setStadiumPass] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [showPass, setShowPass] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetch(`${API_URL}/user`).then(r => r.json()).then(setUser).catch(() => {});
    fetch(`${API_URL}/credentials`).then(r => r.json()).then((data) => {
      setCreds(data);
      if (data.omnipong?.username) setOmnipongUser(data.omnipong.username);
      if (data.stadium?.username) setStadiumUser(data.stadium.username);
    }).catch(() => {});
  }, []);

  async function saveCreds(service: string) {
    const username = service === "omnipong" ? omnipongUser : stadiumUser;
    const password = service === "omnipong" ? omnipongPass : stadiumPass;
    if (!username || !password) return;
    setSaving(service);
    try {
      await fetch(`${API_URL}/credentials`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service, username, password }),
      });
      setCreds(prev => ({ ...prev, [service]: { configured: true, username } }));
      if (service === "omnipong") setOmnipongPass("");
      else setStadiumPass("");
    } finally {
      setSaving(null);
    }
  }

  async function removeCreds(service: string) {
    await fetch(`${API_URL}/credentials/${service}`, { method: "DELETE" });
    setCreds(prev => ({ ...prev, [service]: { configured: false, username: "" } }));
    if (service === "omnipong") { setOmnipongUser(""); setOmnipongPass(""); }
    else { setStadiumUser(""); setStadiumPass(""); }
  }

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

          {/* Integrations Section */}
          <section className="bg-[var(--card)] p-6 rounded-2xl border border-[#333]">
            <div className="flex items-center gap-3 mb-6">
              <Shield className="text-[var(--rubber-red)]" size={24} />
              <h2 className="text-xl font-bold">Integrations</h2>
            </div>
            <p className="text-xs text-gray-500 mb-4">
              Your credentials are stored locally on this machine only — never sent to any server.
              The agent uses them to log in and sync your data.
            </p>

            <div className="space-y-6">
              <CredentialCard
                name="OmniPong"
                description="USATT ratings and tournament registration"
                configured={creds.omnipong?.configured}
                username={omnipongUser}
                password={omnipongPass}
                showPassword={showPass.omnipong}
                saving={saving === "omnipong"}
                onUsernameChange={setOmnipongUser}
                onPasswordChange={setOmnipongPass}
                onTogglePassword={() => setShowPass(p => ({ ...p, omnipong: !p.omnipong }))}
                onSave={() => saveCreds("omnipong")}
                onRemove={() => removeCreds("omnipong")}
                usernamePlaceholder="OmniPong username"
              />
              <CredentialCard
                name="Stadium Compete"
                description="League tracking and match history"
                configured={creds.stadium?.configured}
                username={stadiumUser}
                password={stadiumPass}
                showPassword={showPass.stadium}
                saving={saving === "stadium"}
                onUsernameChange={setStadiumUser}
                onPasswordChange={setStadiumPass}
                onTogglePassword={() => setShowPass(p => ({ ...p, stadium: !p.stadium }))}
                onSave={() => saveCreds("stadium")}
                onRemove={() => removeCreds("stadium")}
                usernamePlaceholder="Email address"
              />
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

function CredentialCard({
  name, description, configured, username, password, showPassword, saving,
  onUsernameChange, onPasswordChange, onTogglePassword, onSave, onRemove, usernamePlaceholder,
}: {
  name: string; description: string; configured?: boolean;
  username: string; password: string; showPassword?: boolean; saving: boolean;
  onUsernameChange: (v: string) => void; onPasswordChange: (v: string) => void;
  onTogglePassword: () => void; onSave: () => void; onRemove: () => void;
  usernamePlaceholder: string;
}) {
  return (
    <div className="p-4 bg-[#111] rounded-xl border border-[#333] space-y-3">
      <div className="flex justify-between items-center">
        <div>
          <div className="font-bold flex items-center gap-2">
            {name}
            <span className={`text-xs px-2 py-0.5 rounded-full border border-white/10 ${
              configured ? "text-green-500 bg-green-500/10" : "text-gray-500 bg-white/5"
            }`}>
              {configured ? "Connected" : "Not configured"}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-1">{description}</p>
        </div>
        {configured && (
          <button onClick={onRemove} className="p-2 rounded-lg hover:bg-red-500/20 transition-colors" title="Remove credentials">
            <Trash2 size={14} className="text-red-400" />
          </button>
        )}
      </div>
      <div className="space-y-2">
        <input
          type="text"
          value={username}
          onChange={e => onUsernameChange(e.target.value)}
          placeholder={usernamePlaceholder}
          className="w-full p-2.5 bg-[#0a0a0a] rounded-lg border border-[#333] text-sm text-gray-200 placeholder:text-gray-600 focus:border-[var(--rubber-red)] focus:outline-none transition-colors"
        />
        <div className="relative">
          <input
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={e => onPasswordChange(e.target.value)}
            placeholder={configured ? "••••••••  (saved)" : "Password"}
            className="w-full p-2.5 pr-10 bg-[#0a0a0a] rounded-lg border border-[#333] text-sm text-gray-200 placeholder:text-gray-600 focus:border-[var(--rubber-red)] focus:outline-none transition-colors"
          />
          <button onClick={onTogglePassword} className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-300">
            {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
        <button
          onClick={onSave}
          disabled={!username || !password || saving}
          className="w-full flex items-center justify-center gap-2 p-2.5 rounded-lg bg-[var(--rubber-red)] text-white text-sm font-bold disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-110 transition-all"
        >
          {saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
          {saving ? "Saving..." : configured ? "Update" : "Save & Connect"}
        </button>
      </div>
    </div>
  );
}
