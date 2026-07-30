---
inclusion: always
---

# grup54 / Ensemble — yönlendirme (Kiro steering)

Kanonik çalışma sözleşmesi `AGENTS.md`'dedir (kurallar orada — **burada tekrar YOK**, tek-doğruluk-kaynağı). Aşağıdaki dosyaları her oturumda bağlamına dahil et:

#[[file:../../AGENTS.md]]
#[[file:../../CONTRIBUTING.md]]
#[[file:../../docs/gelistirme-dongusu.md]]

- Ortak sözleşme = `AGENTS.md` · git akışı = `CONTRIBUTING.md` · issue→done = `docs/gelistirme-dongusu.md`.
- Kontratlar = `docs/sprint2-kontratlar.md` · kapsam (YAPMA listesi) = `docs/kapsam-sinirlari.md`.
- Özel strateji (gitignored `internal/`, bundle ile) → ilgili işte elle `Read` et.

**MCP (isteğe bağlı ama tavsiye edilir):** `.harness/` döngüsünü elle okumak yerine `who_is_touching` / `check_scope` tool'larını kullan. Kiro için hedef dosya **`.kiro/settings/mcp.json`** (workspace) ya da `~/.kiro/settings/mcp.json` (ikisi varsa workspace kazanır):

```json
{ "mcpServers": { "ensemble": { "command": "uv",
  "args": ["run", "--directory", "<repo-koku>", "python", "-m", "ensemble_mcp.server"] } } }
```

`<repo-koku>` = reponun MUTLAK yolu. Sunucunun tek başına kalktığını görmek için `make mcp`. Diğer araçların yolları + gerekçe → `AGENTS.md` §"MCP: kendi aracını bağla".
