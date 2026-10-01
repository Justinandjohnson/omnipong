"use client";
import Sidebar from "@/components/Sidebar";
import AgentConsole from "@/components/AgentConsole";

export default function AgentPage() {
  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      <main className="flex-1 md:ml-64 pt-14 md:pt-0 p-8">
        <header className="mb-6">
          <h1 className="text-3xl font-bold">Agent</h1>
          <p className="text-gray-400">
            Scout, search, sync, or sign up — the same actions the MCP exposes.
          </p>
        </header>

        <AgentConsole />
      </main>
    </div>
  );
}
