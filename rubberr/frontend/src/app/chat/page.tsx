"use client";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";

export default function ChatPage() {
  return (
    <div className="bg-[var(--background)] min-h-screen text-[var(--foreground)] flex">
      <Sidebar />
      <main className="flex-1 md:ml-64 pt-14 md:pt-0 p-8 h-screen flex flex-col">
        <header className="mb-6">
          <h1 className="text-3xl font-bold">AI Coach</h1>
          <p className="text-gray-400">Your personal table tennis assistant.</p>
        </header>

        <div className="flex-1 min-h-0">
             <ChatInterface />
        </div>
      </main>
    </div>
  );
}
