/**
 * Tipli env config — TEK GİRİŞ NOKTASI (#19).
 * Kural: bileşenler import.meta.env'i DOĞRUDAN okumaz; yalnız buradan geçer.
 * (Backend simetrisi: ensemble/config.py Settings — aynı ilke, #45'teki ders:
 * yanlış/eksik env sessizce boş sayfa değil, açılışta net hata üretmeli.)
 */

function readApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(
      `VITE_API_BASE_URL geçerli bir URL değil: "${raw}" — .env dosyanı kontrol et (.env.example'a bak).`,
    );
  }
  // Path öneki KORUNUR (hosted backend /api gibi bir önek arkasında olabilir);
  // eskiden .origin sessizce düşürüyordu — bu dosyanın kendi ilkesine aykırıydı.
  // Query/hash ise base URL'de anlamsız → sessizce taşımak yerine açık hata.
  if (url.search || url.hash) {
    throw new Error(
      `VITE_API_BASE_URL query/hash içeremez: "${raw}" — yalnız origin (+ opsiyonel path öneki).`,
    );
  }
  return url.href.replace(/\/+$/, "");
}

export const config = {
  apiBaseUrl: readApiBaseUrl(),
  mode: (import.meta.env.MODE === "production" ? "hosted" : "local") as
    | "local"
    | "hosted",
  // Mock modu (#21): VITE_MOCK=1 → tipli client fixture'lardan beslenir
  // (dedektör #17 gelene dek zengin görsel durum). Açıkken UI'da global
  // "ÖRNEK VERİ" rozeti ZORUNLU — sahte-canlılık yasak (D-34).
  mock: import.meta.env.VITE_MOCK === "1",
} as const;
