"use client";
import { useState, useRef, useEffect } from 'react';
import { Send } from 'lucide-react';
import { getAIHeaders } from './DemoBar';

export default function ChatInterface() {
  const [messages, setMessages] = useState([
    { role: 'agent', content: "Hello! I'm Coach Rubberr. I've analyzed your latest match history. Ready to find your next tournament?" }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    // Optimistic update
    setMessages(prev => [...prev, { role: 'user', content: trimmed }]);
    setInput("");
    setError(null);
    setIsLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAIHeaders() },
        body: JSON.stringify({ message: trimmed }),
      });

      if (!res.ok) {
        throw new Error(`Server error ${res.status}`);
      }

      const data = await res.json();
      setMessages(prev => [...prev, { role: 'agent', content: data.response }]);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(`Failed to reach Coach Rubberr: ${errMsg}`);
      setMessages(prev => [...prev, {
        role: 'agent',
        content: 'Sorry, I could not connect to the backend right now. Make sure the server is running.'
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[var(--card)] rounded-2xl border border-[#333] overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-[#333] bg-[#0f0f0f]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--rubber-red)] to-[var(--rubber-accent)] flex items-center justify-center font-bold text-white text-xs">
            AI
          </div>
          <div>
            <h3 className="font-bold text-sm">Coach Rubberr</h3>
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"/>
              <span className="text-xs text-green-500">Online</span>
            </div>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] p-3 rounded-2xl text-sm ${
                m.role === 'user'
                  ? 'bg-[var(--rubber-red)] text-white rounded-br-none'
                  : 'bg-[#262626] text-gray-200 rounded-bl-none'
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-[#262626] text-gray-400 p-3 rounded-2xl rounded-bl-none text-sm flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="text-xs text-red-400 text-center px-4 py-1 bg-red-900/20 rounded-lg border border-red-800/40">
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-[#333] bg-[#0f0f0f] flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Ask about tournaments..."
          disabled={isLoading}
          className="flex-1 bg-[#1a1a1a] border border-[#333] rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-[var(--rubber-red)] transition-colors disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={isLoading}
          className="p-2 rounded-xl bg-[var(--rubber-red)] text-white hover:bg-[var(--rubber-dark)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
