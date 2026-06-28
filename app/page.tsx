"use client";

import { useState, useEffect } from "react";
import Navbar from "./components/Navbar";
import Sidebar from "./components/Sidebar";
import CommandPalette from "./components/CommandPalette";
import AlertPanel from "./components/AlertPanel";
import TimeMachine from "./components/TimeMachine";
import ZenCenter from "./components/ZenCenter";

export default function Home() {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);

  // Cmd+K / Ctrl+K shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsCommandPaletteOpen((prev) => !prev);
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="relative w-full h-screen overflow-hidden grid-bg">
      {/* Navbar */}
      <Navbar />

      {/* Sidebar */}
      <Sidebar
        isCollapsed={isSidebarCollapsed}
        onToggle={() => setIsSidebarCollapsed((prev) => !prev)}
      />

      {/* Main Content Area */}
      <main
        className="absolute top-[52px] bottom-[56px] right-0 overflow-hidden transition-all duration-300 ease-in-out"
        style={{
          left: isSidebarCollapsed ? "48px" : "272px",
        }}
      >
        {/* Zen Center */}
        <ZenCenter />

        {/* Alert Panel - Floating Right */}
        <AlertPanel />
      </main>

      {/* Time Machine - Bottom Bar */}
      <TimeMachine />

      {/* Command Palette - Overlay */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
      />

      {/* Ambient background decorations */}
      <div
        className="fixed pointer-events-none z-0"
        style={{
          top: "20%",
          right: "10%",
          width: "400px",
          height: "400px",
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(248, 81, 73, 0.02) 0%, transparent 70%)",
          filter: "blur(60px)",
        }}
      />
      <div
        className="fixed pointer-events-none z-0"
        style={{
          bottom: "30%",
          left: "20%",
          width: "300px",
          height: "300px",
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(88, 166, 255, 0.02) 0%, transparent 70%)",
          filter: "blur(60px)",
        }}
      />
    </div>
  );
}
