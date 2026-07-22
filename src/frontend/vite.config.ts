/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, loadEnv } from "vite";

const ENV_DIR = "../..";

export default defineConfig(({ command, mode }) => {
  // #188 prod build hijyen guard: VITE_MOCK=1 ile prod build YASAK. `vite
  // build` varsayılan mode="production"dır (dev sunucusu "development" kullanır,
  // buradan etkilenmez) — yanlışlıkla mock'lu bir deploy (dist'e fixture/gerçek
  // isim sızıntısı, bkz. #188 "Neden") derleme anında engellenir; CI'daki
  // dist-tarama job'u (prod-build-guard.yml) buna GÜVENMEZ, ayrıca doğrular.
  if (command === "build" && mode === "production") {
    const env = loadEnv(mode, ENV_DIR, "");
    if (env.VITE_MOCK === "1") {
      throw new Error(
        "VITE_MOCK=1 iken prod build YASAK (#188) — mock fixture'ları (gerçek kişi handle'ları dahil) " +
          "dist'e sızdırır. Kapat (VITE_MOCK= ya da boş) ya da `vite build --mode development` kullan.",
      );
    }
  }
  return {
    // Env dosyaları REPO KÖKÜNDEN okunur (.env.example'ın belgelediği akış:
    // kökteki .env hem backend'i hem frontend'i besler; yalnız VITE_* öneklileri
    // client'a sızar). Bu satır olmadan kök .env SESSİZCE okunmuyordu (#21 bulgusu).
    envDir: ENV_DIR,
    plugins: [react(), tailwindcss()],
    test: {
      environment: "jsdom",
      setupFiles: ["./tests/setup.ts"],
    },
  };
});
