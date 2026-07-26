/** Scope verisi — polling konvansiyonu üstünde tipli tek satır (useRadar kalıbı).

    İKİ ayrı uç, iki ayrı hook (sayfanın sol/sağ paneli):
    - `GET /scope/current`  → ScopeCurrent   (dondurulmuş kapsam: goal/in_scope/non_goals)
    - `GET /scope/verdicts` → ScopeVerdictsResponse (açık ref'lerin kararları + sayaçlar)

    `GET /scope/check?ref=` bilinçli olarak hook'lanmadı: tek ref'lik nokta-sorgu,
    liste sayfasının veri kaynağı değil (`/verdicts` zaten hepsini taşır). */

import { api } from "./api";
import { usePolling } from "./usePolling";

export function useScope() {
  return usePolling(["scope", "current"], () => api.GET("/scope/current"));
}

export function useScopeVerdicts() {
  return usePolling(["scope", "verdicts"], () => api.GET("/scope/verdicts"));
}
