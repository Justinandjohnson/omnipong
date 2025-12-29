"use client";
import { useState, useMemo, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, MapPin, Trophy, FileText } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface CalendarViewProps {
  tournaments: any[];
  userRating?: number;
  onToggleRegion?: (isInternational: boolean) => void;
}

export default function CalendarView({ tournaments, userRating = 1500, onToggleRegion }: CalendarViewProps) {
  const [isInternational, setIsInternational] = useState(false);
  const [currentDate, setCurrentDate] = useState(new Date());

  // Sync calendar when data changes
  useEffect(() => {
    if (tournaments.length > 0) {
        // Parse the very first valid date found
        const validTourney = tournaments.find(t => t.date_range && t.date_range.match(/(\d{1,2})\/(\d{1,2})\/(\d{2})/));
        if (validTourney) {
            const match = validTourney.date_range.match(/(\d{1,2})\/(\d{1,2})\/(\d{2})/);
            if (match) {
               const [_, m, d, y] = match;
               setCurrentDate(new Date(2000 + parseInt(y), parseInt(m) - 1, 1));
            }
        }
    } else {
        setCurrentDate(new Date());
    }
  }, [tournaments]);
  
  const handleToggle = () => {
      const newState = !isInternational;
      setIsInternational(newState);
      if (onToggleRegion) onToggleRegion(newState);
  };

  // Map dates to tournaments for lookup
  const tourneyMap = useMemo(() => {
     const map = new Map<string, any>();
     tournaments.forEach(t => {
         if (!t.date_range) return;
         const matches = [...t.date_range.matchAll(/(\d{1,2})\/(\d{1,2})\/(\d{2})/g)];
         matches.forEach(m => {
             const [_, mo, da, ye] = m;
             const fullYear = 2000 + parseInt(ye);
             const dateStr = `${fullYear}-${mo.padStart(2, '0')}-${da.padStart(2, '0')}`;
             
             // Keep the "best" tournament if multiple? Or just the first.
             if (!map.has(dateStr)) map.set(dateStr, t);
         });
     });
     return map;
  }, [tournaments]);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const getDaysArray = () => {
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const firstDay = new Date(year, month, 1).getDay();
      
      const slots = [];
      for (let i = 0; i < firstDay; i++) slots.push(null);
      for (let i = 1; i <= daysInMonth; i++) slots.push(new Date(year, month, i));
      
      return slots;
  };
  
  const days = getDaysArray();
  const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

  const handlePrev = () => setCurrentDate(new Date(year, month - 1, 1));
  const handleNext = () => setCurrentDate(new Date(year, month + 1, 1));
  const handleToday = () => setCurrentDate(new Date());

  // --- Recommendation Logic ---
  const getRecommendedEvent = (t: any) => {
      if (!t.events || !Array.isArray(t.events)) return "General Entry";
      
      // Filter for rating events (e.g. "U2000", "Under 1800")
      // Regex maps "U" or "Under" followed by digits
      const candidates = t.events.map((e: string) => {
          const match = e.match(/(?:U|Under)\s*(\d{4})/i);
          if (match) return { name: e, cap: parseInt(match[1]) };
          return null;
      }).filter(Boolean);

      if (candidates.length === 0) return "Open Singles"; // Default if no rated events found

      // Current Logic: Find smallest cap that is >= userRating
      // Sort candidates ascending
      candidates.sort((a: any, b: any) => a.cap - b.cap);
      
      const bestFit = candidates.find((c: any) => c.cap >= userRating);
      
      // If we found a fit (e.g. user 1500, found U1600), return it.
      // If no fit (user 2500, max U2400), return "Open Singles" or highest class?
      if (bestFit) return bestFit.name;
      
      // If user rating is higher than all caps, suggest Open
      return "Open Singles";
  };

  return (
    <div className="bg-[#1a1a1a] rounded-2xl border border-[#333] p-6 h-full flex flex-col relative z-0">
       {/* Header */}
       <div className="flex justify-between items-center mb-6">
            <div className="flex items-center gap-4">
                <h3 className="font-bold text-white flex items-center gap-2">
                    <CalendarIcon size={18} className="text-[var(--rubber-red)]" />
                    {monthNames[month]} {year}
                </h3>
                
                <button 
                   onClick={handleToggle}
                   className={`
                     px-2 py-1 text-[10px] font-bold uppercase tracking-wider rounded border transition-all
                     ${isInternational 
                         ? "bg-blue-600 border-blue-600 text-white" 
                         : "bg-transparent border-[#444] text-gray-400 hover:border-gray-200"
                     }
                   `}
                >
                    {isInternational ? "World" : "Local"}
                </button>
            </div>
            
            <div className="flex items-center gap-2">
                <button 
                    onClick={handleToday}
                    className="px-2 py-1 text-[10px] font-bold text-gray-500 hover:text-white hover:bg-[#333] rounded transition-colors"
                >
                    Today
                </button>
                <div className="flex gap-1">
                    <button onClick={handlePrev} className="p-1 hover:bg-[#333] rounded-lg text-gray-400"><ChevronLeft size={16} /></button>
                    <button onClick={handleNext} className="p-1 hover:bg-[#333] rounded-lg text-gray-400"><ChevronRight size={16} /></button>
                </div>
            </div>
       </div>

       {/* Days Grid */}
       <div className="grid grid-cols-7 gap-2 mb-2 text-center">
            {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => (
                <div key={i} className="text-[10px] font-bold text-gray-600 uppercase">{d}</div>
            ))}
       </div>
       
       <div className="grid grid-cols-7 gap-2 auto-rows-fr">
           {days.map((date, idx) => {
               if (!date) return <div key={`empty-${idx}`} className="aspect-square" />;
               
               const dateStr = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
               const tournament = tourneyMap.get(dateStr);
               const isToday = new Date().toDateString() === date.toDateString();

               return (
                   <div 
                       key={idx}
                       className={`
                           aspect-square rounded-lg flex flex-col items-center justify-center text-xs relative cursor-pointer group
                           ${tournament 
                               ? 'bg-[var(--rubber-red)] text-white font-bold shadow-lg shadow-red-900/50 hover:scale-105 transition-transform' 
                               : isToday 
                                   ? 'bg-[#333] text-white border border-[#444]' 
                                   : 'text-gray-400 hover:bg-[#222]'
                           }
                       `}
                   >
                       {date.getDate()}
                       {tournament && <div className="w-1 h-1 rounded-full bg-white absolute bottom-1.5" />}

                       {/* Tooltip Popup */}
                       {tournament && (
                           <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-3 w-64 opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none z-[100]">
                               <div className="bg-[#111] border border-[#444] rounded-xl p-4 shadow-2xl text-left">
                                   <h4 className="font-bold text-white text-sm mb-1 line-clamp-2">{tournament.title}</h4>
                                   
                                   <div className="flex items-center gap-1.5 text-[10px] text-gray-400 mb-3">
                                       <MapPin size={10} /> {tournament.location}
                                   </div>

                                   <div className="bg-[#222] rounded-lg p-2 border border-[#333]">
                                       <div className="text-[10px] text-[var(--rubber-red)] font-bold mb-1 flex items-center gap-1">
                                            <Trophy size={10} /> RECOMMENDED EVENT
                                       </div>
                                       <div className="text-xs text-white font-bold">
                                            {getRecommendedEvent(tournament)}
                                       </div>
                                   </div>
                               </div>
                               {/* Arrow */}
                               <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-[#444]" />
                           </div>
                       )}
                   </div>
               );
           })}
       </div>
       
       {/* Legend */}
       <div className="mt-auto pt-4 border-t border-[#222] flex gap-4 text-[10px] text-gray-500">
           <div className="flex items-center gap-1">
               <div className="w-2 h-2 rounded bg-[var(--rubber-red)]" /> Tournament
           </div>
           <div className="flex items-center gap-1">
               <div className="w-2 h-2 rounded bg-[#333] border border-[#444]" /> Today
           </div>
       </div>
    </div>
  );
}
