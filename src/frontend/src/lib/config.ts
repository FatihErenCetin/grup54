/**
 * Tipli env config — TEK GİRİŞ NOKTASI (#19).
 * Kural: bileşenler import.meta.env'i DOĞRUDAN okumaz; yalnız buradan geçer.
 * (Backend simetrisi: ensemble/config.py Settings — aynı ilke, #45'teki ders:
 * yanlış/eksik env sessizce boş sayfa değil, açılışta net hata üretmeli.)
 */

function readApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  try {
    return new URL(raw).origin;
  } catch {
    throw new Error(
      `VITE_API_BASE_URL geçerli bir URL değil: "${raw}" — .env dosyanı kontrol et (.env.example'a bak).`,
    );
  }
}

export const config = {
  apiBaseUrl: readApiBaseUrl(),
  mode: (import.meta.env.MODE === "production" ? "hosted" : "local") as
    | "local"
    | "hosted",
} as const;
