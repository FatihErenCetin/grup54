/** "Projeye sor" verisi — polling konvansiyonu üstünde, ama TEK-ATIŞ ayarıyla.

    `GET /query?q=<soru>` → QueryResponse { answer, citations[], as_of, ... }.

    Diğer hook'lardan iki bilinçli farkı var (ikisi de kota/dürüstlük gerekçeli):
    - **Poll YOK** (`intervalMs=false`) + odakta tazeleme yok: bu bir projeksiyon
      değil, LLM'e sorulan bir soru. 10 sn'de bir yeniden sormak Gemini kotasını
      ve DEMO_MODE hız sınırını (429) boşa yakar; cevap `as_of` alanıyla zaten
      "hangi ana ait" olduğunu söyler.
    - **Soru boşken çağrılmaz** (`enabled`): boş `q` backend'de 422 üretir;
      kullanıcı daha hiçbir şey sormamışken hata basmak dürüst değil, gürültü.

    Sayfa için sözleşme: `soru` boşken hook `data=undefined, error=null,
    isLoading=false` döner → bu "hata" değil, "henüz sorulmadı" durumudur;
    sayfa o hâli davetkâr soru kutusu olarak çizer (tasarım paketi §2 /ask).
    Not: backend `q` için min 1 / max 500 karakter ister — kutuya maxLength koy,
    yoksa 500+ karakterde 422 gelir. */

import { api } from "./api";
import { usePolling } from "./usePolling";

export const ASK_MAX_LENGTH = 500;

export function useAsk(soru: string) {
  // Anahtar ve istek AYNI değeri kullanır (trim) — yoksa "auth" ile "auth "
  // iki ayrı cache girdisi olur, aynı soru iki kez sorulur.
  const q = soru.trim();
  return usePolling(
    ["ask", q],
    () => api.GET("/query", { params: { query: { q } } }),
    false,
    { enabled: q.length > 0, refetchOnWindowFocus: false },
  );
}
