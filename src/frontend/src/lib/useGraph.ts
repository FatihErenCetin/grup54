/** Dokunma grafı verisi (#104/#105) — polling konvansiyonu üstünde tipli tek satır.

    `GET /graph?window_days=<n>` → TouchGraph { window_days, nodes[], edges[] }.
    Parametre OPSİYONEL: verilmezse backend kendi varsayılanını uygular
    (bugün 14 gün, `engine/graph.DEFAULT_WINDOW_DAYS`). Bu yüzden burada
    varsayılan UYDURULMAZ — pencereyi gerçek değerinden okumak isteyen
    `data.window_days`'e bakar (cevabın kendisi taşır, sahte-canlılık yasak). */

import { api } from "./api";
import { usePolling } from "./usePolling";

export function useGraph(windowDays?: number) {
  // undefined query değerini openapi-fetch URL'e hiç yazmaz → parametresiz istek.
  // Anahtarda null: sorgu anahtarı "varsayılan pencere" ile "7 gün"ü karıştırmasın.
  return usePolling(["graph", windowDays ?? null], () =>
    api.GET("/graph", { params: { query: { window_days: windowDays } } }),
  );
}
