/** Board verisi (#111) — polling konvansiyonu üstünde tipli tek satır (useRadar kalıbı).
    `GET /board` → { cards: BoardCard[] }; kart durumu yalnız ingest'ten gelir,
    UI sürüklemez (read-only board — özellik, eksiklik değil). */

import { api } from "./api";
import { usePolling } from "./usePolling";

export function useBoard() {
  return usePolling(["board"], () => api.GET("/board"));
}
