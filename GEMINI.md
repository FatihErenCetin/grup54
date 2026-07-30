# GEMINI.md — grup54 / Ensemble

> Gemini CLI bu dosyayı **otomatik yükler**. **Kurallar burada DEĞİL** — kanonik sözleşme `AGENTS.md`'de. Bu dosya yalnızca oraya yönlendirir (tek-doğruluk-kaynağı korunur, drift yok, içerik kopyalanmaz).

@AGENTS.md
@CONTRIBUTING.md
@docs/gelistirme-dongusu.md

**Her oturum başında bunları yüklemiş ol:**
- **`AGENTS.md`** — ortak çalışma sözleşmesi (branch/commit/PR · mimari ilkeler · kapsam disiplini · `.harness` döngüsü · "ne nereye" haritası).
- **`CONTRIBUTING.md`** — git akışı detayı (issue → branch → commit → PR → merge).
- **`docs/gelistirme-dongusu.md`** — atanmış issue'yu bitirmenin tek rehberi (+ DONE kapısı).
- İş kontratları → `docs/sprint2-kontratlar.md` · kapsam sınırları (YAPMA listesi) → `docs/kapsam-sinirlari.md`.

**MCP (isteğe bağlı ama tavsiye edilir):** `.harness/` döngüsünü elle okumak yerine `who_is_touching` / `check_scope` tool'larını kullan. Gemini CLI için hedef dosya **`.gemini/settings.json`** (proje) ya da `~/.gemini/settings.json`; bu **genel ayar dosyasıdır** — üzerine yazma, yalnız `mcpServers` anahtarını ekle:

```json
{ "mcpServers": { "ensemble": { "command": "uv",
  "args": ["run", "--directory", "<repo-koku>", "python", "-m", "ensemble_mcp.server"] } } }
```

Sunucunun kalktığını görmek için `make mcp`, oturumda doğrulamak için `/mcp`. Diğer araçların yolları + gerekçe → `AGENTS.md` §"MCP: kendi aracını bağla".

> Özel strateji/bağlam (gitignored `internal/`, bundle ile gelir) → ilgili işe başlarken `@internal/<dosya>.md` ile ekle.
