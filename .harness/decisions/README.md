# `.harness/decisions/` — operasyonel karar günlüğü (append-only)

Git-native kurum hafızası: SM/PO/dev **önemli bir operasyonel karar** alınca
(mimari seçim, sözleşme değişikliği, kapsam kararı vb.) `D-NN-<kisa-slug>.md`
ekler. Geçmiş dosyalar **düzenlenmez** (yalnız `status` alanı, ör.
`superseded`, güncellenebilir) — audit, PR diff'inde görünür kalsın diye.

## Şema (`decision.schema.json`)

Zorunlu: `type: decision` · `id` (ör. `D-01`) · `title` · `date`. Opsiyonel:
`status`.

```markdown
---
type: decision
id: D-01
title: "Board aracı = GitHub Projects (Trello/Asana/Miro yerine)"
date: "2026-06-28"
status: accepted
---
Gerekçe: `T-<id>` branch + `Closes #<id>` PR ile entegre, kartları PR/issue
durumundan otomatik oynatır (dogfood).
```

## ⚠️ Bu klasör bugün BOŞ — bilinçli, migrasyon yapılmadı

Ekibin bugüne kadarki operasyonel karar kaydı `internal/grup54_karar_logu.md`
dosyasında yaşıyor (D-01…D-39+) — ama o dosya **gitignored** (özel strateji,
yalnızca `CLAUDE.local.md` @import zinciriyle ekip+AI'ya yüklenir, **push
edilmez**). Bu #242 kapsamında oradaki kararları buraya **kopyalamadık**,
çünkü:

1. **İki doğruluk kaynağı yaratır** — `internal/grup54_dizin_yapisi.md` §7
   zaten "karar kaydı" için iki ayrı irtifayı ayırıyor (stratejik →
   `grup54_vizyon_ve_karar_kaydi.md` · operasyonel → `.harness/decisions/`);
   ama mevcut operasyonel kararların **hepsi** `internal/`'de yazıldığı için
   hangisinin "yalnız ekip-içi strateji" hangisinin "public/audit'e açık
   operasyonel karar" olduğu ayrımı henüz yapılmadı.
2. **Sızma riski** — `internal/karar_logu.md` bazı kararların gerekçesinde
   ekip-içi/strateji bağlamı da taşıyabilir; körlemesine kopyalamak public
   repoya istenmeyen bağlam sızdırabilir.

**Migrasyon yolu (PO kararı bekliyor):** PO, `internal/grup54_karar_logu.md`
içindeki hangi D-NN'lerin "operasyonel + public-safe" olduğuna karar verip
onları burada `D-NN-*.md` olarak yeniden yazar (front-matter + kısa gövde).
Bu PR o kararı **almıyor** — yalnızca boş, şemaya uygun bir iskelet + bu
migrasyon notunu bırakıyor.
