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
 */

import { useQuery } from "@tanstack/react-query";

export const POLL_INTERVAL_MS = 10_000;

type PollResult<T> = { data?: T; error?: unknown };

/** Konvansiyonun kendisi — saf ve test edilebilir (biri interval'i silerse test kırılır). */
export function pollingOptions<T>(
  key: readonly unknown[],
  fetcher: () => Promise<PollResult<T>>,
  intervalMs: number = POLL_INTERVAL_MS,
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
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false, // sekme arka plandayken polling durur (bilinçli)
  } as const;
}

export function usePolling<T>(
  key: readonly unknown[],
  fetcher: () => Promise<PollResult<T>>,
  intervalMs: number = POLL_INTERVAL_MS,
) {
  const query = useQuery(pollingOptions(key, fetcher, intervalMs));

  return {
    data: query.data,
    error: query.error,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    /** Son BAŞARILI verinin gerçek zamanı (ms epoch); 0 = henüz veri yok */
    dataUpdatedAt: query.dataUpdatedAt,
  };
}
