"use client";
import dynamic from 'next/dynamic';
import { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';

const VoiceAgent = dynamic(() => import('./VoiceAgent'), { 
  ssr: false,
  loading: () => null
});

const ChatAgent = dynamic(() => import('./ChatAgent'), { 
  ssr: false,
  loading: () => null
});

export default function VoiceAgentWrapper() {
  const pathname = usePathname();
  const [mode, setMode] = useState<'voice' | 'chat'>('chat');

  useEffect(() => {
    const saved = localStorage.getItem('aiAgentMode');
    if (saved === 'voice' || saved === 'chat') {
      setMode(saved);
    }
  }, []);

  const switchToVoice = () => {
    setMode('voice');
    localStorage.setItem('aiAgentMode', 'voice');
  };

  const switchToChat = () => {
    setMode('chat');
    localStorage.setItem('aiAgentMode', 'chat');
  };

  if (pathname === '/chat') return null;

  if (mode === 'voice') {
    return <VoiceAgent />;
  }

  return <ChatAgent onSwitchToVoice={switchToVoice} />;
}
