# Issue Brifing Rehberi — işe başlamadan bağlamı yükle (insan + AI ortak)

> **Ne zaman:** Bir issue'ya başlamadan ÖNCE. AI aracına şunu de: *"`docs/issue-brifing-rehberi.md`'yi oku ve #N için brifing ver."* (Claude Code: `/issue-brifing N`.)
> **Neden:** Issue gövdesi "ne yapılacak"ı söyler; bu brifing "projedeki yeri, nedeni ve nasılı"nı yükler. Konu kaybına karşı ilk savunma hattı (F-04).

## AI'ın okuyacağı kaynaklar (sırayla)

1. `gh issue view <N>` — gövde + kabul kriterleri + label/milestone
2. `docs/sprint2-kontratlar.md` *(ya da güncel sprintin kontrat dosyası)* — bu işin girdi/çıktı sözleşmesi
3. `docs/<milestone-slug>-bagimlilik.md` (örnek: `docs/sprint2-bagimlilik.md` — #119 yayın konvansiyonu) — haritadaki konumu (neye bağlı, neyi kilitliyor)
4. `README.md` "Mimari & Yapay Zeka" bölümü + `ROADMAP.md` — büyük resimdeki yeri
5. Gerekirse: ilgili modülün mevcut kodu (`src/...`)

## Çıktı formatı — 5 bölüm, sabit sıra

1. **Hikâye (projedeki yeri):** Bu iş hangi ürün vaadini taşıyor? Sprint hedefine ve (biliniyorsa) jüri puan kalemine bağı ne? Bir kullanım sahnesiyle anlat — mekanizmayla değil, ihtiyaçla başla. *(3-6 cümle)*
2. **Girdi → Çıktı:** Bu iş ne alır, ne verir? Kontrattaki ilgili model/port/endpoint imzasını göster. Girdi kimden geliyor, çıktıyı kim tüketiyor?
3. **Haritadaki konumun:** ← neye bağımlı (başlamadan ne bitmiş olmalı / mock'la nasıl başlanır) · → çıktını kim bekliyor (kritik yoldaysa söyle).
4. **Adım planı:** issue'ya özel 4-7 somut adım (dosya/fonksiyon düzeyinde) + hangi testin neyi kanıtlayacağı.
5. **Sokratik kontrol soruları (2-3):** Geliştiriciye yönelt — kenar durumlar, hata yolları, tasarım gerekçeleri üzerine. *Amaç sınav değil, kodlamaya başlamadan düşündürmek.* Cevapları bekle; yanlışsa anlat, doğruysa onayla.

## Kurallar

- **Issue'ya yorum olarak YAZILMAZ** — brifing kişinin kendi AI oturumunda üretilir/tüketilir (issue'lar gürültüsüz kalır). Issue'da kalıcı olan tek şey şablondaki "Bağlam" bölümüdür.
- **Uydurma yok:** Kontratta/haritada olmayan şeyi "var" deme; boşluk görürsen "bu kontratta eksik — PO'ya sor" de (kontrat borcu erken yakalanır).
- **Kapsam bekçiliği:** Brifing sırasında issue'nun kapsam dışına taşan fikirler çıkarsa → yeni issue önerisi olarak listele, plana katma (`docs/kapsam-sinirlari.md` ruhu).
- Türkçe, sade dil; ürün terimleri (radar, ingest, judge…) İngilizce kalır (D-34 hibrit dil kuralı).

> **`gh` yoksa / yalnız web:** issue sayfasını + kontrat dosyasını + bu rehberi AI'a yapıştır — aynı 5 bölümü iste (Gemini AI Studio dahil).

> Kaynak: 8 Tem 2026 brainstorm (F-04) — #45'te birebir uygulanan brifing deneyiminin damıtılmış standardı. Rehber değişirse: PR + daily'de duyuru.
