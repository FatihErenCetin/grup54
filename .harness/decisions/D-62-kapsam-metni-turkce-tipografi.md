---
type: decision
id: D-62
title: "Donmuş `sprint-3.md` kapsam metni Türkçe karaktersizdi — tipografik düzeltme (#317)"
date: "2026-07-29"
status: accepted
---

## Bağlam

`.harness/scope/sprint-3.md` UTF-8 kodlu bir dosya ama front-matter'ı
(`title`/`owner`/`goals`/`non_goals`) ve gövdesi (`Amaç`/`Kaynak` paragrafları)
ASCII yazılmıştı ("Amac", "dondurulmus", "canliya alma", "Go-live mekanigi",
"Uc frontend sayfasi" vb.) — Türkçe karakter (ç/ğ/ı/ö/ş/ü) hiç kullanılmamış.
Bu metin `ScopePage.tsx`'te (`GET /scope/current` → `goal`/`in_scope`/
`non_goals`) birebir kullanıcıya basılıyor; canlıda doğrulandı
(`https://recommend2me.com/scope`). Sprint 3 teslim edilirken jüri bu sayfayı
okuyacak (#317).

Dosya front-matter'da `status: frozen` + `commit_sha` + `frozen_at` taşıyor —
PO tarafından dondurulmuş, ürünün kapsam-drift tespitinin dayandığı belge.
Frozen bir belgeye normalde dokunulmaz.

## Karar

**Yalnız tipografik düzeltme yapıldı** — ASCII harfler doğru Türkçe
karşılıklarına çevrildi (i→ı, g→ğ, s→ş, c→ç, o→ö, u→ü gerektiği yerde),
**hiçbir maddenin anlamı, sırası veya sayısı değişmedi**. Tek istisna:
"kontrat-once parallellesme" ifadesindeki fazladan `l` (İngilizce "parallel"
etkisiyle yazılmış bir yazım hatası) kaldırılıp repodaki kanonik yazımla
(`docs/sprint3-kontratlar.md` satır 3: "kontrat-önce paralelleşme") hizalandı
— bu da bir kelimenin İngilizce kalıntısını düzeltmektir, madde/anlam
değişikliği değil.

`goals` (6 madde) ve `non_goals` (6 madde) sayısı, sırası ve içeriği madde
madde karşılaştırıldı; **aynı** kaldı.

### Neyin BİLİNÇLİ olarak değişmediği

- **`commit_sha` (`18f846f...`) değiştirilmedi.** Kilit test
  (`test_commit_sha_dosyanin_VAR_OLDUGU_bir_commiti_gosterir`) yalnız
  permalink'in ÇÖZÜLDÜĞÜNÜ garanti eder (`git cat-file -e <sha>:<yol>`),
  byte-birebir içerik eşleşmesini değil — o commit'te dosya zaten vardı (blob
  varlığı, içerikten bağımsız bir kontrol). Sonuç: kanıt bağlantısı hâlâ
  çözülüyor, ama o tarihsel commit'teki metin bu PR'dan ÖNCEKİ ASCII hâli
  gösterecek. Bilinçli ödün: `commit_sha`'yı bu PR'ın kendi commit'ine
  yeniden pinlemek, issue #317'nin istemediği ayrı bir re-freeze işlemi
  olurdu (`version` + `frozen_at` + `commit_sha` birlikte bump edilmesi
  gerekirdi — PO kararı). Bu PR yalnız #317'nin dört kabul kriterini
  karşılıyor; re-pinleme istenirse ayrı bir karar/PR konusu.
- **`version` ve `frozen_at` değiştirilmedi** — dondurma OLAYININ kendisi
  (2026-07-25) aynı kaldı; değişen yalnız yazım, kapsam kararı değil.
- **Madde sayısı/sırası/anlamı değişmedi** — yeni bir test bunu kilitliyor
  (aşağıda).

## Koruyan testler

- `tests/unit/test_scope_kanit.py::test_commit_sha_dosyanin_VAR_OLDUGU_bir_commiti_gosterir`
  — kanıt bağlantısı kopmadı (bu PR'dan sonra da yeşil).
- `tests/unit/test_scope_kanit.py::test_sprint_3_madde_sayilari_sabit` — **yeni**:
  `goals`/`non_goals` sayısını (6/6) üretim okuyucusuyla (`FileHarnessPort.
  read_scope`) SAYAR, iddia edilen sayıya güvenmez. Mutasyon kanıtı: `goals`
  dizisinden son madde geçici silindi → `5 != 6` ile kırmızı görüldü → geri
  alındı → yeşil (testin docstring'inde de yazılı).
- `scripts/harness_validate.py` (`make test` / CI) — front-matter şeması
  (`scope.schema.json`) uyumu; front-matter alan sözleşmesi bozulmadı.

## Etkilenen belgeler

Yalnız `.harness/scope/sprint-3.md` (front-matter + gövde metni). Dizinde
başka `sprint-*.md` yok — aynı sorunun tekrarı için kontrol edildi, tek
dosya var.
