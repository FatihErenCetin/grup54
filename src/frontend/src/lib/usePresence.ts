/** Presence verisi (#60) — polling konvansiyonu üstünde tipli tek satır.

    `GET /presence` → { entries: PresenceEntry[], latest_ts }.
    Bayat beyanlar backend'de read-time'da elenir (#60) — istemci ayrıca
    süzmez; "kimse yok" cevabı GERÇEKTEN kimse yok demektir. */

import { api } from "./api";
import { usePolling } from "./usePolling";

export function usePresence() {
  return usePolling(["presence"], () => api.GET("/presence"));
}
