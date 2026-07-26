/**
 * Presence örnek verisi — `GET /presence` (#60) fixture'ı.
 *
 * Eskiden PresenceStrip bunu DOĞRUDAN import ediyordu (uç yoktu, şerit hep
 * örnekti). Uç canlı olunca kural yerine oturdu: fixture yalnız MOCK ZİNCİRİNE
 * girer (`mocks/radar.ts` → `mockFetch`), bileşene değil. İki sonucu var:
 * - şerit gerçek veriyi çizer; örnek veri yalnız VITE_MOCK=1 iken görünür
 *   (ve o zaman AppLayout global "Örnek veri" rozetini basar — D-34),
 * - bu modül artık yalnız mock chunk'ında yüklenir → prod dist'e gerçek
 *   handle'lar sızmaz (#188 hijyen guard'ının derdi buydu).
 *
 * Tip zorunluluğu: fixture `PresenceResponse` şemasını DOLDURMAK ZORUNDA —
 * kontrat kayarsa burası derlemede kırılır.
 */

import type { components } from "../api/schema.d.ts";

type PresenceResponse = components["schemas"]["PresenceResponse"];

export function mockPresenceResponse(): PresenceResponse {
  // since/latest_ts her çağrıda taze — bayat-eleme (#60) ve "Son güncelleme"
  // akışı mock'ta da gerçek davranışıyla görünür.
  const now = Date.now();
  const dkOnce = (dk: number) => new Date(now - dk * 60_000).toISOString();
  return {
    entries: [
      {
        actor: { handle: "asmarufoglu", type: "human", responsible: null },
        module: "engine",
        task: "T-17",
        branch: "T-17-cakisma-radari",
        since: dkOnce(42),
      },
      {
        actor: { handle: "EnesErdemT", type: "human", responsible: null },
        module: "eval",
        task: "T-28",
        branch: "T-28-eval-runner",
        since: dkOnce(15),
      },
      {
        actor: { handle: "fatih-claude", type: "agent", responsible: "FatihErenCetin" },
        module: "frontend",
        task: "T-21",
        branch: "T-21-radar-sayfasi",
        since: dkOnce(3),
      },
    ],
    latest_ts: dkOnce(3),
  };
}
