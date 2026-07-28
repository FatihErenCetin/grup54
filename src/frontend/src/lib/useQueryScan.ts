/** "Tarandı" şeridi (#319 — tasarım paketi /ask) — `GET /query/scan`.
 *
 * `useAsk`'tan (aynı dosyanın yanı, `/query`) BİLİNÇLİ FARKI: bu uç LLM'e
 * HİÇ gitmez (`QueryService.scan()` yalnız corpus'u sayar — bkz. backend
 * docstring'i), bu yüzden `/radar`/`/board` gibi PROJEKSİYON sayılıp
 * POLL'LANIR (varsayılan 10 sn, `useAsk`'ın aksine `intervalMs=false` YOK).
 * Soru sorulmadan önce de çağrılır — kutunun altındaki şerit sayfa
 * açılır açılmaz gerçek sayılarla dolsun diye.
 */

import { api } from "./api";
import { usePolling } from "./usePolling";

export function useQueryScan() {
  return usePolling(["query-scan"], () => api.GET("/query/scan"));
}
