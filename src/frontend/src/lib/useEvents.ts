/** Olay akışı (#52 · #265) — polling konvansiyonu üstünde tipli tek satır.
 *
 * `GET /events` → `{ events: NormalizedEvent[], latest_ts }`
 *
 * Veri kaynağı DB projeksiyonu (`EventRow`), GitHub portu DEĞİL (#265): port
 * `_seen_ids` ile "bu process'te görülmüş" olayları filtreler — ingest için
 * doğru, HTTP okuma için felaket (ikinci istemci boş feed alırdı). `/board`
 * ile aynı desen: `.harness` kanonik, DB projeksiyon, HTTP projeksiyondan okur.
 */

import { api } from "./api";
import { usePolling } from "./usePolling";

export function useEvents() {
  return usePolling(["events"], () => api.GET("/events"));
}
