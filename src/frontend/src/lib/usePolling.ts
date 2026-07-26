/**
 * Polling konvansiyonu (#20) — tüm veri sayfaları bu hook'tan geçer.
 *
 * Kararlar (gerekçeli, brifing sorusu 1):
 * - Aralık ~10 sn (Ek B2 önerisi); sekme ARKA PLANDAYKEN durur
 *   (`refetchIntervalInBackground` varsayılanı false) — radar sayfası
 *   projeksiyondur, kimse bakmıyorken tazelemenin kullanıcı değeri yok.
 * - Odağa dönüşte ANINDA tazelenir (`refetchOnWindowFocus`) — kullanıcı
 *   kısa süreliğine dürüst-eski saati görür, hemen ardından taze veri gelir
 *   (sahte-canlılık yasak, D-34).
 * - `dataUpdatedAt` dışarı verilir → "Son güncelleme" göstergesi GERÇEK
 *   zamanı basar, uydurma değil.
 *
 * İki bilinçli ayar (`PollingAyari`) — projeksiyon ucu ile TEK-ATIŞ ucu farkı:
 * - `/radar`, `/board`, `/scope`, `/graph`, `/presence` PROJEKSİYONdur → poll'lanır.
 * - `/query` (LLM) tek-atıştır: `intervalMs=false` + `refetchOnWindowFocus:false`
 *   ile 10 sn'de bir yeniden SORULMAZ (kota + DEMO_MODE 429 riski), `enabled`
 *   ile de soru boşken hiç istek atılmaz.
 */

import { useQuery } from "@tanstack/react-query";

export const POLL_INTERVAL_MS = 10_000;

type PollResult<T> = { data?: T; error?: unknown };

export type PollingAyari = {
  /** false → sorgu HİÇ çalışmaz (boş soruyla /query'e gitmek gibi). Varsayılan: true */
  enabled?: boolean;
  /** Odağa dönüşte tazele. Tek-atış (LLM) uçlarında bilinçli kapatılır. Varsayılan: true */
  refetchOnWindowFocus?: boolean;
};

/** Konvansiyonun kendisi — saf ve test edilebilir (biri interval'i silerse test kırılır). */
export function pollingOptions<T>(
  key: readonly unknown[],
  fetcher: () => Promise<PollResult<T>>,
  /** false = otomatik tazeleme yok (tek-atış uç) */
  intervalMs: number | false = POLL_INTERVAL_MS,
  { enabled = true, refetchOnWindowFocus = true }: PollingAyari = {},
) {
  return {
    queryKey: key,
    queryFn: async () => {
      const { data, error } = await fetcher();
      // openapi-fetch hata döndürür, fırlatmaz — react-query'nin retry/error
      // makinesine girmesi için burada fırlatıyoruz. Boş-gövdeli non-ok cevapta
      // (örn. 204/Content-Length:0) error da data da undefined kalabilir —
      // sessizce "veri var" sayılmaz, o da hatadır.
      if (error !== undefined) throw error;
      if (data === undefined) throw new Error("Boş cevap: sunucu veri döndürmedi");
      return data;
    },
    refetchInterval: intervalMs,
    refetchOnWindowFocus,
    refetchIntervalInBackground: false, // sekme arka plandayken polling durur (bilinçli)
    enabled,
  } as const;
}

export function usePolling<T>(
  key: readonly unknown[],
  fetcher: () => Promise<PollResult<T>>,
  intervalMs: number | false = POLL_INTERVAL_MS,
  ayar: PollingAyari = {},
) {
  const query = useQuery(pollingOptions(key, fetcher, intervalMs, ayar));

  return {
    data: query.data,
    error: query.error,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    /** Son BAŞARILI verinin gerçek zamanı (ms epoch); 0 = henüz veri yok */
    dataUpdatedAt: query.dataUpdatedAt,
  };
}
