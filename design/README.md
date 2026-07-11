# design/ — Ensemble ürün tasarımı

**Dosya:** `ensemble.pen` — [Pencil](https://pencil.dev) formatı. **Açmak için:** VS Code + Pencil eklentisi (`highagency.pencildev`) → dosyaya tıkla, kanvas açılır.

## İçindekiler (14 yüzey)

| Frame | Ne |
|---|---|
| `00-Foundations` | Design token'ları: renkler (dark+light temalı) · tipografi (Geist/Geist Mono) · spacing · ısı rampası |
| `03-Landing` | Pazarlama sayfası (hero + ürün penceresi + 3-adım + dogfood bandı + video) |
| `03-Radar` | S2 ana ekranı — **#21'in görsel şartnamesi** (feed + side-sheet + presence + dürüstlük haritası) |
| `03-Graph` ×4 | Isı matrisi (**#105 MVP**) · Git ağacı · Güç-yönlü (Obsidian) · Treemap (S3) |
| `03-Board` | Kendiliğinden dolan kanban (provenance + varış animasyonu karesi) |
| `03-Scope` | Kapsam bekçisi (donmuş kapsam paneli + verdict listesi + kanıt bloğu) |
| `03-Ask` | Cevap motoru (tipli citation'lar + tarama fişi + dürüst-red) |
| `03-Activity` | Olay akışı + Kendiliğinden Daily kartı |
| `03-Actors` | Aktör görünümü (ajan varyantı: pair zinciri + yapamaz listesi) |
| `04-Login` · `04-Settings` | Hosted vizyon ekranları (build #79 gate'li / evre-2 — D-28) |

## Altın kural: token senkronu (D-34)

Pencil değişken adları = `src/frontend/src/index.css` CSS token adları — **birebir**. Renk değişikliği iki adımda yaşar: Pencil'da `SetVariables` ↔ CSS'te `:root`/`.light`. Bileşenlere hex yazılmaz; iki taraf da yalnız token adı kullanır. (`get_variables` MCP aracı Pencil→CSS dökümünü verir.)

## Süreç

- Ekran tasarımları **karar kayıtlıdır**: her ekran deep-search + PO brainstorm ritüelinden geçti (kararlar AskUserQuestion kayıtlarında + `internal/grup54_ui_tasarim_paketi.md`).
- Değişiklik = normal akış (issue + branch + PR); .pen dosyası binary-benzeri olduğundan PR açıklamasına **ekran görüntüsü** eklenir (diff okunmaz).
- Kontrat bağımlılıkları: ekranların ihtiyaç duyduğu API ekleri `docs/sprint2-kontratlar.md` **Ek B**'dedir.
