"use client";
import { useState } from 'react';
import { Send } from 'lucide-react';

export default function ChatInterface() {
  const [messages, setMessages] = useState([
    { role: 'agent', content: "Hello! I'm Coach Rubberr. I've analyzed your latest match history. Ready to find your next tournament?" }
  ]);
  const [input, setInput] = useState("");

  const handleSend = () => {
    if (!input.trim()) return;
    
    // Optimistic Update
    setMessages(prev => [...prev, { role: 'user', content: input }]);
    const currentInput = input;
    setInput("");

    // Simulate Agent Response (Mock for now, can connect to backend /chat later)
    setTimeout(() => {
      setMessages(prev => [...prev, { role: 'agent', content: `I found 3 tournaments eligible for your rating (1177). Would you like me to auto-enter you in the 'U1400' event at the Phoenix Open?` }]);
    }, 1000);
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
      </div>

      {/* Input */}
      <div className="p-3 border-t border-[#333] bg-[#0f0f0f] flex gap-2">
        <input 
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Ask about tournaments..." 
          className="flex-1 bg-[#1a1a1a] border border-[#333] rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-[var(--rubber-red)] transition-colors"
        />
        <button 
          onClick={handleSend}
          className="p-2 rounded-xl bg-[var(--rubber-red)] text-white hover:bg-[var(--rubber-dark)] transition-colors"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
