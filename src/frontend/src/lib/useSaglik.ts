/** `GET /health` — çalışma modunun TEK doğruluk kaynağı.
 *
 * NEDEN VAR (ölçüldü, 2026-07-28): topbar'daki mod rozeti `config.mode`'dan
 * besleniyordu ve o değer **Vite'ın BUILD modundan** türüyor:
 *
 *     mode: import.meta.env.MODE === "production" ? "hosted" : "local"
 *
 * Yani "üretim derlemesi = hosted" varsayımı. Bu, masaüstü paketi (#305)
 * çıkana kadar doğruydu — ama o paket de **üretim derlemesi taşıyor ve
 * YERELDE çalışıyor.** Kullanıcı kendi bilgisayarına kurduğu uygulamada
 * "hosted" yazısını görürdü: rozet, bilmediği bir şeyi iddia ediyordu.
 *
 * Backend gerçek modu zaten `/health`'te dönüyor (`{status, mode, ...}`).
 * Rozet artık ORADAN besleniyor; `config.mode` yalnız derleme-zamanı
 * varsayılanı olarak, cevap gelene kadar kullanılır.
 *
 * `useSettings.ts` aynı dersi ayarlar kapısı için zaten uygulamıştı —
 * bu, o disiplinin rozete taşınması.
 */

import { api } from "./api";
import { usePolling } from "./usePolling";

type SaglikYaniti = { status?: string; mode?: string };

export function useSaglik() {
  return usePolling<SaglikYaniti>(["health"], () => api.GET("/health"));
}
