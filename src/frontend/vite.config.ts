/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  // Env dosyaları REPO KÖKÜNDEN okunur (.env.example'ın belgelediği akış:
  // kökteki .env hem backend'i hem frontend'i besler; yalnız VITE_* öneklileri
  // client'a sızar). Bu satır olmadan kök .env SESSİZCE okunmuyordu (#21 bulgusu).
  envDir: "../..",
  plugins: [react(), tailwindcss()],
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
  },
});
