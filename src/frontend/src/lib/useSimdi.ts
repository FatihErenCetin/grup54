/** Ticking "şimdi" — yalnız GÖRÜNTÜ amaçlı (#316/A4 canlılık nabzı).
 *
 * Hiçbir veri sorgusu TETİKLEMEZ, hiçbir sayı UYDURMAZ (D-34 sahte-canlılık
 * yasağı): tek işi, zaten var olan GERÇEK bir zaman damgasıyla (örn.
 * `useSaglik().dataUpdatedAt`) aradaki farkı render'dan render'a taze tutmak
 * — "12 sn önce" yazısı saniyede bir ilerlesin diye. Damganın kendisi hâlâ
 * son BAŞARILI `/health` yanıtının gerçek anıdır; burası yalnız "şimdi" ucunu
 * tazeler.
 */

import { useEffect, useState } from "react";

export function useSimdi(intervalMs = 1000): number {
  const [simdi, setSimdi] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setSimdi(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return simdi;
}
