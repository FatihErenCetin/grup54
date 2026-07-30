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

## Bu klasörde dört kayıt var — toplu migrasyon HÂLÂ yapılmadı

`D-56` (27 Temmuz 2026) buraya, **toplu migrasyondan bağımsız** olarak yazıldı:
amacı Sprint 3 teslim edilirken jüriye görünür hesap verilebilirlik sağlamak ve
`internal/` gitignored olduğu için public repoda görünmüyor. Aşağıdaki gerekçe
D-01…D-55 için **aynen geçerli** — onlar hâlâ `internal/grup54_karar_logu.md`'de.

## ⚠️ D-01…D-55 buraya taşınmadı — bilinçli, migrasyon yapılmadı

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

## Mevcut kayıtlar

| id | tarih | konu |
|---|---|---|
| [D-56](D-56-review-beklemeden-merge.md) | 2026-07-27 | Sprint 3 son gününde review beklemeden merge — gerekçe, kapsam, bedel |
| [D-57](D-57-email-parola-uyeligi.md) | 2026-07-28 | Email + parola üyeliği S3'e alındı — D-23/D-28'in kapsamı değişti |
| [D-58](D-58-cok-kiracili-repo-secimi.md) | 2026-07-28 | #79 tam yapılıyor — çok-kiracılı repo seçimi; D-23'ün son maddesi de değişti |
| [D-59](D-59-events-presence-kontrat-sapmasi.md) | 2026-07-28 | `/events`+`/presence` kontrat sapması — dokümanı gerçeğe uydur (has_more/filtreler/presence-304 uygulanmıyor) |
| [D-60](D-60-board-kart-kumesi-github-issue.md) | 2026-07-30 | Board kart kümesi `.harness/tasks/` ile sınırlı değil — GitHub issue'ları da kart üretir (çakışmada `.harness` kazanır) |
| [D-62](D-62-kapsam-metni-turkce-tipografi.md) | 2026-07-29 | Donmuş `sprint-3.md` kapsam metni Türkçe karaktersizdi — tipografik düzeltme (#317) |
