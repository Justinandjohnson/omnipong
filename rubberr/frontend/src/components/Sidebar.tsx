"use client";
import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, BarChart2, Settings, Trophy, Map as MapIcon, MessageCircle, Gamepad2, Menu, X } from 'lucide-react';
import { useArcade } from "@/context/ArcadeContext";

function NavItem({ icon, label, href, active }: { icon: React.ReactNode, label: string, href: string, active?: boolean }) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200
        ${active
          ? 'bg-[var(--rubber-red)] text-white shadow-lg shadow-red-900/20'
          : 'text-gray-400 hover:bg-[#1f1f1f] hover:text-white'
        }`}
    >
      {icon}
      <span className="font-medium">{label}</span>
    </Link>
  );
}

function ArcadeToggle() {
  const { isArcadeMode, toggleArcadeMode } = useArcade();

  return (
    <div
      onClick={toggleArcadeMode}
      className={`mt-4 flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 cursor-pointer border border-transparent
        ${isArcadeMode
          ? 'bg-[var(--rubber-dark)]/20 border-[var(--rubber-red)] shadow-[0_0_15px_rgba(217,70,239,0.3)]'
          : 'hover:bg-[#1f1f1f] text-gray-400'
        }`}
    >
      <Gamepad2 size={20} className={isArcadeMode ? "text-[var(--rubber-red)] animate-pulse" : ""} />
      <div className="flex-1">
        <span className={`font-medium block ${isArcadeMode ? 'text-white' : ''}`}>Arcade Mode</span>
        <span className="text-[10px] text-gray-500 uppercase tracking-wider">{isArcadeMode ? 'Active' : 'Off'}</span>
      </div>

      {/* Toggle Switch UI */}
      <div className={`w-8 h-4 rounded-full relative transition-colors ${isArcadeMode ? 'bg-[var(--rubber-red)]' : 'bg-[#333]'}`}>
        <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all duration-300 ${isArcadeMode ? 'left-[18px]' : 'left-0.5'}`} />
      </div>
    </div>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  const close = () => setIsOpen(false);

  return (
    <>
      {/* Mobile hamburger button */}
      <button
        className="md:hidden fixed top-3 left-3 z-50 p-2 bg-[var(--sidebar)] rounded-lg border border-[#333] text-gray-300"
        onClick={() => setIsOpen(o => !o)}
        aria-label="Toggle menu"
      >
        {isOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/60 z-40"
          onClick={close}
        />
      )}

      {/* Sidebar panel */}
      <div className={`
        h-screen w-64 bg-[var(--sidebar)] border-r border-[#333] flex flex-col fixed left-0 top-0 z-50
        transition-transform duration-300 ease-in-out
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        md:translate-x-0
      `}>
        <div className="p-6 pt-5">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-[var(--rubber-red)] to-[var(--rubber-accent)] bg-clip-text text-transparent">
            Rubberr.
          </h1>
          <p className="text-xs text-gray-500 mt-1">AI Table Tennis Coach</p>
        </div>

        <nav className="flex-1 px-4 space-y-2">
          <NavItem icon={<Home size={20} />} label="Dashboard" href="/" active={pathname === '/'} />
          <NavItem icon={<MapIcon size={20} />} label="Map" href="/map" active={pathname === '/map'} />
          <NavItem icon={<Trophy size={20} />} label="Tournaments" href="/tournaments" active={pathname === '/tournaments'} />
          <NavItem icon={<BarChart2 size={20} />} label="Analytics" href="/analytics" active={pathname === '/analytics'} />
          <NavItem icon={<MessageCircle size={20} />} label="AI Coach" href="/chat" active={pathname === '/chat'} />
        </nav>

        <div className="p-4 border-t border-[#333]">
          <NavItem icon={<Settings size={20} />} label="Settings" href="/settings" active={pathname === '/settings'} />
          <ArcadeToggle />
        </div>
      </div>
    </>
  );
}
