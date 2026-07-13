/**
 * Presence örnek verisi (#21) — Ek B1: `GET /presence` S3 kontratı; o güne dek
 * şerit HER ZAMAN bu örnekle çizilir (VITE_MOCK'tan bağımsız) ve kendi
 * "(örnek)" etiketini taşır. Bilinçli olarak api client'tan geçmez — spec'te
 * olmayan yol taklit edilmez. radar.ts'ten ayrı dosya: bu modül bundle'a
 * bilerek girer, radar fixture'ı ise yalnız mock modunda yüklenir.
 */

export type MockPresence = { handle: string; module: string; branch: string | null };

export const mockPresence: MockPresence[] = [
  { handle: "asmarufoglu", module: "engine", branch: "T-17-cakisma-radari" },
  { handle: "EnesErdemT", module: "eval", branch: "T-28-eval-runner" },
  { handle: "fatih-claude", module: "frontend", branch: "T-21-radar-sayfasi" },
];
