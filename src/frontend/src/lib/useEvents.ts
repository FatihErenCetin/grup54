/** Olay akışı (#52 · #265 · #273) — polling konvansiyonu üstünde tipli tek satır.
 *
 * `GET /events` → `{ events: NormalizedEvent[], latest_ts }`
 *
 * Veri kaynağı DB projeksiyonu (`EventRow`), GitHub portu DEĞİL (#265): port
 * `_seen_ids` ile "bu process'te görülmüş" olayları filtreler — ingest için
 * doğru, HTTP okuma için felaket (ikinci istemci boş feed alırdı). `/board`
 * ile aynı desen: `.harness` kanonik, DB projeksiyon, HTTP projeksiyondan okur.
 *
 * ── ARTIMLI ÇEKİM (#273) ────────────────────────────────────────────────
 * Uç `since` destekliyordu ama UI her poll'de TÜM akışı okuyordu. Ölçüldü
 * (canlı, 2026-07-27, 663 olay):
 *
 *     since YOK  -> 223 KB
 *     since VAR  -> 26 KB     (~8.5x)
 *
 * ETag zaten çalışıyor (değişiklik yoksa 304 + 0 bayt), ama ETag TÜM akıştan
 * hesaplandığı için **tek bir yeni olay** 223 KB'ın tamamını yeniden
 * getirtiyordu. Olay sayısı arttıkça kötüleşir: bugün 663, sprint sonunda
 * daha fazla.
 *
 * Backend `since`'i ALT SINIR olarak DAHİL ediyor (`>=`, `engine/events.py`)
 * — yani sınırdaki olay tekrar gelir, KAYBOLMAZ. Doğru tarafa yanılmış:
 * tekrarı `id` ile eliyoruz, kayıp veriyi elemek mümkün olmazdı.
 */

import { api } from "./api";
import type { components } from "../api/schema.d.ts";
import { usePolling } from "./usePolling";

type NormalizedEvent = components["schemas"]["NormalizedEvent"];
type EventsResponse = { events: NormalizedEvent[]; latest_ts?: string | null };

/** Birikim React DIŞINDA tutulur — bilinçli.
 *
 * `useEvents()` birden çok bileşende çağrılıyor (ActivityPage, ısı matrisi
 * hücre listesi, aktör sayfası). React Query aynı `queryKey` için TEK
 * `queryFn` koşturur; birikim `useRef`'te olsaydı hangi bileşenin ref'inin
 * kullanıldığı MOUNT SIRASINA bağlı olurdu ve o bileşen unmount olunca
 * birikim sessizce sıfırlanırdı. Modül seviyesi bu belirsizliği kaldırıyor.
 */
let birikim = new Map<string, NormalizedEvent>();
let imlec: string | null = null;

/** Testler için — modül durumu testler arasında sızmasın. */
export function _birikimiSifirla(): void {
  birikim = new Map();
  imlec = null;
}

/** Yalnız test/teşhis: kaç olay birikti. */
export function _birikimSayisi(): number {
  return birikim.size;
}

export function useEvents() {
  return usePolling<EventsResponse>(["events"], async () => {
    const { data, error } = await api.GET("/events", {
      params: { query: imlec ? { since: imlec } : {} },
    });

    // HATA DALINDA BİRİKİMİ BOZMA: `usePolling` hatayı fırlatıp react-query'nin
    // "veri var, hata geçici" davranışına bırakıyor. İmleci ilerletirsek
    // başarısız bir istekte aradaki olayları BİR DAHA hiç istemeyiz.
    if (error !== undefined || data === undefined) return { data, error };

    const gelen = (data as EventsResponse).events ?? [];
    for (const e of gelen) birikim.set(e.id, e);

    // İmleci yalnız İLERİ taşı. Sunucu daha eski bir `latest_ts` dönerse
    // (yeniden kurulum, saat kayması) geri sarmak, aradaki olayları
    // birikimde tutup yenilerini kaçırmaya yol açardı.
    const yeniImlec = (data as EventsResponse).latest_ts ?? null;
    if (yeniImlec && (imlec === null || yeniImlec >= imlec)) imlec = yeniImlec;

    return {
      data: {
        events: [...birikim.values()],
        latest_ts: imlec,
      },
    };
  });
}
