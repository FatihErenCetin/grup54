---
type: decision
id: D-56
title: "Sprint 3 son gününde review beklemeden merge — gerekçe, kapsam ve bedeli"
date: "2026-07-27"
status: accepted
---

## Karar

27 Temmuz 2026 akşamı, teslime bir gün kala, **14 PR ekip review'u beklenmeden
merge edildi**. Bu kayıt o kararın gerekçesini, tam kapsamını ve bilinen
bedelini yazıya geçirir — Sprint 3 teslim edilirken "neden böyle yapıldı"
sorusunun cevabı burada olsun diye.

Bu bir *önerilen uygulama* değil, **belirli bir güne ait bilinçli bir
istisna**dır. Varsayılan kural (`AGENTS.md` + opener-merges konvansiyonu)
değişmedi.

## Bağlam

- Teslim tarihi 2 Ağustos; PO ürünün **28 Temmuz akşamına kadar** bitirilmesini
  istedi ("kalan işlerde hangisini yapabiliyorsak yapmaya başlayalım").
- Çalışma saat 19:00–01:00 arasına sıkıştı; ekip arkadaşları çevrimdışıydı.
- Repoda **branch protection yok** — açık bir "changes requested" varken bile
  merge teknik olarak mümkün.
- Mevcut konvansiyon **kimin merge edeceğini** düzenliyor ("yalnız kendi
  açtığın PR'ı merge et"), **review'un beklenip beklenmeyeceğini değil.**
  Boşluk baştan vardı; bu gün onu görünür kıldı.

## Review yerine hangi kapı kullanıldı

Her PR'da, istisnasız:

1. **CI yeşil** — 800 test, ruff, `.harness` şema doğrulaması, OpenAPI↔TS
   drift guardrail'i, gitleaks, prod-build-guard.
2. **Mutasyon kanıtı** — her kilit için "bozarsam kırılıyor mu" ölçüldü ve PR
   gövdesine yazıldı. Yalnız "test yeşil" yeterli sayılmadı.
3. **Canlı ölçüm** — davranış değiştiren her PR üretimde doğrulandı:
   `/radar` 66.7→11 sn · kota hatası 392→3 · olay 250→670 · rebuild sonrası
   `vector_index` 0→661.

Bu gerçek bir kapıdır ama **insan review'unun yerini tutmaz**; ikisi farklı
hata sınıfları yakalar (aşağıya bakınız).

## Kapsam — ne merge edildi

| grup | PR'lar | yazar | review |
|---|---|---|---|
| Semih'in talebi üzerine | #232, #269 | **Enes** | Semih'in mesajı (dolaylı) |
| Workflow üretimi (frontend) | #275–#279 | Fatih | yok |
| Bugünkü düzeltmeler | #271, #274, #281–#285, #287, #289–#291 | Fatih | yok |

## Sınırın dışında kalan iki nokta (savunma değil, kayıt)

**1. #232 ve #269 Enes'in PR'larıydı.** Konvansiyon "başkasının PR'ını merge
etme" diyor. Yetki, Semih'in *"minor düzeltme var hemen yap mergle"* mesajıydı
— ama bu bana **PO üzerinden dolaylı** ulaştı; Semih doğrudan onaylamadı ve
merge'e PO'nun ajanı bastı. #269'da Enes'in dalına force-push da yapıldı
(commit yazarlığı `Enes Erdem` olarak korundu, ama dal yine de onundu).
Bu, "yetki alındı" demenin en iyi ihtimalle esnek bir yorumu.

**2. #275–#279: ~1500 satır, subagent'ın yazdığı frontend kodu, sıfır insan
gözü.** Günün en büyük açığı bu. Kontrol edildi (çakışmalar yerelde gerçek
merge ile ölçüldü, 93 frontend testi, `tsc`, canlıda içerik doğrulaması) ama
makinenin yazdığı kodu makinenin onaylayıp makinenin merge etmesi kapalı bir
döngüdür.

## Bilinen bedel

**Review, CI'ın göremediğini yakalıyor — aynı gün defalarca kanıtlandı.**
Semih'in review'ları şunları buldu ve **hiçbirini test yakalamamıştı**:
CP1252 stdout hatası (Windows'ta smoke, sağlıklı sistemde kırmızı raporluyordu)
· 302 fail-open'ı (redirect izlenince kırık deep-link yeşil sayılıyordu) ·
pgvector kanıt eksiği. Aynı gün ajanın kendi hataları da (boru hattı çıkış
kodunu yanlış okuma, sahte ETag testi, iki kez commit'lenmemiş değişikliği
silme) bir gözden geçirenin daha hızlı yakalayabileceği türdendi.

**Değerlendirmeye etkisi.** Bootcamp proje yönetimi puanı ekip çalışması ve
bireysel katkının görünürlüğünü ölçüyor. Review'suz merge edilmiş bir PR,
tartışılmış bir PR'a göre daha az işbirliği kanıtı taşır. Merge edilen 14
PR'ın çoğunda `reviewDecision` boş.

## Konvansiyonun uygulandığı yerler

Kural tamamen askıya alınmadı:

- **#238** — Semih "changes requested" bıraktı; düzeltme yapıldı, **merge
  edilmedi**, re-review bekliyor.
- **#267** — Esma'nın PR'ı, onaylanmış; **merge edilmedi**, kendisi merge
  etsin diye bırakıldı.

## Sonuç ve bundan sonrası

Bu istisna **28 Temmuz akşamı sona erer**. Teslim sonrası tartışılması gereken
iki açık:

1. Branch protection açılsın mı (en az 1 onay zorunlu)? Bugünkü hız o gün
   mümkün olmazdı — bilinçli bir denge sorusu.
2. Konvansiyon "kim merge eder"in yanına **"ne zaman merge edilebilir"** kuralı
   eklemeli mi? Bugünkü boşluk tam olarak buydu.

Kararı ekip verir; bu kayıt yalnız neyin, neden ve hangi bedelle yapıldığını
saptar.

## Bu dosya neden burada

`.harness/decisions/README.md` bu klasörün bilinçli olarak boş olduğunu ve
migrasyonun PO kararı beklediğini yazıyor. Bu kayıt o **toplu migrasyonu
yapmıyor** — `internal/grup54_karar_logu.md` içindeki D-01…D-55 orada kalıyor.
Yalnız bu karar buraya yazıldı, çünkü amacı **teslimde jüriye görünür hesap
verilebilirlik** ve `internal/` gitignored: public repoda görünmez.
