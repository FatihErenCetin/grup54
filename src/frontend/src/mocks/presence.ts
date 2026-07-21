/**
 * Presence örnek verisi (#21) — Ek B1: `GET /presence` S3 kontratı; o güne dek
 * şerit HER ZAMAN bu örnekle çizilir (VITE_MOCK'tan bağımsız) ve kendi
 * "(örnek)" etiketini taşır. Bilinçli olarak api client'tan geçmez — spec'te
 * olmayan yol taklit edilmez. radar.ts'ten ayrı dosya: bu modül bundle'a
 * bilerek girer, radar fixture'ı ise yalnız mock modunda yüklenir.
 *
 * #188 — handle'lar ANONİM (dev-a/b/c): bu dosya VITE_MOCK'tan bağımsız HER
 * prod build'e girdiği için gerçek GitHub kullanıcı adı burada YASAK (aksi
 * halde public no-login demo'ya gerçek kişi bilgisi sızar — bkz. #188 "Neden").
 * `.github/workflows/prod-build-guard.yml` bu isimlerin dist'e dönüşünü CI'da
 * doğrular; gerçek handle eklenirse kırmızı verir.
 */

export type MockPresence = { handle: string; module: string; branch: string | null };

export const mockPresence: MockPresence[] = [
  { handle: "dev-a", module: "engine", branch: "T-17-cakisma-radari" },
  { handle: "dev-b", module: "eval", branch: "T-28-eval-runner" },
  { handle: "dev-c-claude", module: "frontend", branch: "T-21-radar-sayfasi" },
];
