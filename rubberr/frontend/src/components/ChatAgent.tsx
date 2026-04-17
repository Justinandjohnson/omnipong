"use client";
import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MessageSquare, X, Send, Loader2, Mic } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Message {
  role: 'user' | 'agent';
  content: string;
}
interface ChatAgentProps {
  onSwitchToVoice?: () => void;
}

export default function ChatAgent({ onSwitchToVoice }: ChatAgentProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    { role: 'agent', content: "Hey! I'm Coach Rubberr. Ask me anything about your matches, stats, or upcoming tournaments!" }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    
    const userMessage = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    try {
      // Call the backend chat endpoint with full tool access
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage })
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const data = await response.json();
      setMessages(prev => [...prev, { role: 'agent', content: data.response }]);
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => [...prev, { 
        role: 'agent', 
        content: "Sorry, I couldn't connect to the backend. Please make sure the server is running on port 8000." 
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-[9999]">
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className="absolute bottom-16 right-0 w-[360px] h-[500px] bg-[#0a0a0a] border border-[#333] rounded-2xl shadow-2xl overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="p-4 border-b border-[#333] bg-[#111] flex justify-between items-center">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[var(--rubber-red)] to-[var(--rubber-accent)] flex items-center justify-center">
                  <MessageSquare size={18} className="text-white" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-white">Coach Rubberr</h3>
                  <div className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"/>
                    <span className="text-xs text-green-500">Chat Mode</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {/* Voice Mode Toggle */}
                <button 
                  onClick={onSwitchToVoice}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#222] border border-[#444] text-gray-400 hover:text-white hover:border-[var(--rubber-red)] transition-all text-xs"
                  title="Switch to Voice Mode"
                >
                  <Mic size={14} />
                  <span>Voice</span>
                </button>
                <button 
                  onClick={() => setIsOpen(false)} 
                  className="p-2 hover:bg-[#222] rounded-full text-gray-400 hover:text-white transition-colors"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div 
                    className={`max-w-[85%] p-3 rounded-2xl text-sm whitespace-pre-line ${
                      m.role === 'user' 
                        ? 'bg-[var(--rubber-red)] text-white rounded-br-sm' 
                        : 'bg-[#1a1a1a] text-gray-200 rounded-bl-sm border border-[#333]'
                    }`}
                  >
                    {m.content}
                  </div>
                </div>
              ))}
              
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-[#1a1a1a] border border-[#333] rounded-2xl rounded-bl-sm p-3 flex items-center gap-2">
                    <Loader2 size={16} className="animate-spin text-gray-500" />
                    <span className="text-sm text-gray-500">Thinking...</span>
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-3 border-t border-[#333] bg-[#111]">
              <div className="flex gap-2">
                <input 
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
                  placeholder="Ask about your matches..." 
                  className="flex-1 bg-[#1a1a1a] border border-[#333] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--rubber-red)] transition-colors placeholder-gray-600"
                  disabled={isLoading}
                />
                <button 
                  onClick={handleSend}
                  disabled={isLoading || !input.trim()}
                  className="p-3 rounded-xl bg-[var(--rubber-red)] text-white hover:bg-[var(--rubber-dark)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send size={18} />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main FAB Button */}
      <motion.button
        onClick={() => setIsOpen(!isOpen)}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.95 }}
        className={`w-14 h-14 rounded-full flex items-center justify-center shadow-lg transition-colors ${
          isOpen 
            ? 'bg-[#333] text-white' 
            : 'bg-[var(--rubber-red)] text-white hover:bg-[var(--rubber-dark)]'
        }`}
      >
        {isOpen ? <X size={24} /> : <MessageSquare size={24} />}
      </motion.button>
    </div>
  );
}
