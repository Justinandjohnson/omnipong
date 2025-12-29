"use client";
import React, { createContext, useContext, useState, useEffect } from 'react';

interface ArcadeContextType {
  isArcadeMode: boolean;
  toggleArcadeMode: () => void;
}

const ArcadeContext = createContext<ArcadeContextType | undefined>(undefined);

export function ArcadeProvider({ children }: { children: React.ReactNode }) {
  const [isArcadeMode, setIsArcadeMode] = useState(false);

  // Load preference from local storage on mount
  useEffect(() => {
    const stored = localStorage.getItem('rubberr_arcade_mode');
    if (stored === 'true') {
      setIsArcadeMode(true);
    }
  }, []);

  // Sync with document body class for global theming
  useEffect(() => {
    if (isArcadeMode) {
      document.body.classList.add('theme-arcade');
    } else {
      document.body.classList.remove('theme-arcade');
    }
  }, [isArcadeMode]);

  const toggleArcadeMode = () => {
    setIsArcadeMode(prev => {
      const newState = !prev;
      localStorage.setItem('rubberr_arcade_mode', String(newState));
      return newState;
    });
  };

  return (
    <ArcadeContext.Provider value={{ isArcadeMode, toggleArcadeMode }}>
      {children}
    </ArcadeContext.Provider>
  );
}

export function useArcade() {
  const context = useContext(ArcadeContext);
  if (context === undefined) {
    throw new Error('useArcade must be used within an ArcadeProvider');
  }
  return context;
}
