/** #21 — Radar verisi: polling konvansiyonu üstünde tipli tek satır. */

import { api } from "./api";
import { usePolling } from "./usePolling";

export function useRadar() {
  return usePolling(["radar"], () => api.GET("/radar"));
}
