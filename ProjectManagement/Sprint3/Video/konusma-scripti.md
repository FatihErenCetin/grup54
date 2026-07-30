# 3 dakikalık tanıtım videosu — konuşma scripti

> **Bu dosya SESLENDİREN kişi içindir.** Çeken kişinin dosyası ayrı:
> [`cekim-rehberi.md`](cekim-rehberi.md). İkisi **aynı sahne numaralarını** (S1–S7)
> ve **aynı zaman kodlarını** kullanır — senkron oradan sağlanır.

**Kaynak:** akış #65'te dondurulmuş (yüzey listesi #363 dar RC ile aynı).
Bu script o dondurulmuş sürelere birebir uyar; yeni yüzey EKLEMEZ.

**Ölçülen:** 385 kelime. 150 kelime/dk'da **2:34** · 140'ta **2:45** ·
130'da (çok yavaş) **2:57** — üç uçta da 3:00 sınırının altında.

---

## Okuma kuralları (önce bunu oku)

1. **Yavaş oku.** Süre hesaplandı, acele etmene gerek yok.
2. **Sayıları ve model adlarını net söyle.** Ekranda görünen sayıyla ağzından
   çıkan sayı **aynı olmalı** — çeken kişi ön-uçuşta güncel sayıları teyit edip
   sana bildirecek (bkz. çekim rehberi §1.2).
3. **Arka planda müzik yok** (bootcamp kuralı). Sessiz oda, ağızdan 15–20 cm.
4. `«…»` = vurgula · `//` = kısa nefes durağı (kurguda kesim noktası) ·
   `>` ile başlayan satırlar **okunmaz**, ekranda ne olduğunu söyler.

### Telaffuz

| Yazılı | Söylenir |
|---|---|
| PR | "pi-ar" |
| pgvector | "pi-ci-vektör" |
| RAG | "reg" (tek hece) |
| MCP | "em-si-pi" |
| FastAPI | "fast-ey-pi-ay" |
| Gemini / Groq / Ollama | "cemini" / "grok" / "olama" |
| `gemini-2.5-flash` | "cemini iki nokta beş flaş" |
| `.harness/` | "harness klasörü" |
| port–adapter | "port adaptör" |
| 0.9 | "sıfır virgül dokuz" |

> **Model adlarını yutma.** Jüri "hangi modeli seçtiniz" sorusunun cevabını
> arıyor. Zorlanırsan `gemini-2.5-flash` yerine "cemini flaş" de — marka net
> kalsın yeter.

---

## S1 · AÇILIŞ — problem (00:00 → 00:20)

> Ekranda: Radar sayfası açık, tıklama yok.

Bir yazılım ekibinde dört kişi aynı anda çalışıyor — ve artık her birinin
yanında bir de yapay zeka aracı var. Kod üretimi hızlandı; koordinasyon
hızlanmadı. //

İki kişi farkında olmadan aynı dosyaya dokunuyor, iş kapsamdan sessizce
kayıyor, board gerçeği yansıtmıyor. //

Ensemble tam bu boşluk için var: ekibin «paylaşılan proje beyni».

---

## S2 · RADAR — çakışma tespiti + AI hattı (00:20 → 00:55)

> Ekranda: Radar listesi → yüksek şiddetli tespit → detay paneli
> (ortak dosyalar, güven skoru, Türkçe gerekçe).

Radar açık işleri birbirleriyle kıyaslıyor: «yüz dokuz» tespit, üçü yüksek. //

Burada iki geliştirici «otuz altı ortak dosyaya» dokunuyor. Aday olmak için
önce «ortak dosya» şartı var — bu deterministik, model harcamıyor. Sonra
«cemini embedding» modeliyle içerik benzerliği ölçülüyor. //

Kararı «cemini iki nokta beş flaş» veriyor ve «iki sinyali birlikte» görüyor:
hangi dosyalar kesişiyor, içerik ne kadar benzer. Çıktısı serbest metin değil,
şemaya bağlı — şiddet, güven, Türkçe gerekçe. Güven «sıfır virgül dokuz». //

Kod inceleme araçları tek bir pi-ar'ın **içine** bakar; Ensemble «iki ayrı işin
kesişimine» bakar.

---

## S3 · SCOPE — kapsam bekçisi (00:55 → 01:20)

> Ekranda: donmuş kapsam → kapsam içi/dışı → alıntılı karar satırı.

Kapsam bekçisi. Sprint kapsamı sprint başında donduruluyor; her iş bu metne
karşı değerlendiriliyor — aynı judge modeli, ayrı bir görev tanımıyla. //

Kararını «alıntıyla» gerekçelendiriyor: "kapsam dışı" demiyor, "şu maddeye
göre kapsam dışı" diyor. //

Kapsam metni de git'te yaşıyor; değişirse bu bir denetim kaydı oluyor.

---

## S4 · BOARD — mimari + MCP (01:20 → 01:45)

> Ekranda: Board, beş kolon, kartlar.

Board kendiliğinden doluyor: «otuz dokuz kart, beş kolon» — kaynağı gerçek
pi-ar ve issue durumu, GitHub App ve webhook üzerinden. //

Kanonik kayıt git'te: `.harness/` klasörü; veritabanı yalnız projeksiyon,
çelişirse git kazanıyor. //

Tek motor iki arayüz: aynı çekirdek hem web'i hem bir «em-si-pi» sunucusunu
besliyor — herkesin yapay zeka aracı aynı beyne sorabiliyor.

---

## S5 · ACTIVITY — orkestrasyon + kalibrasyon (01:45 → 02:05)

> Ekranda: olay akışı, bir filtreye tıklanır.

Activity ortak zaman çizelgesi: commit, pi-ar ve issue olayları tek akışta. //

Arka planda judge dört katmanla sarılı — «kalıcı hafıza, devre kesici, önbellek
ve yedek sağlayıcı». Aynı çift ikinci kez sorulmuyor; birincil sağlayıcı
düşerse zincir ayakta kalıyor. //

Eşikler de uydurma değil: etiketli bir veri kümesinde ölçülüp kalibre edildi.

---

## S6 · ASK — RAG hattı (02:05 → 02:45)

> Ekranda: "Tarandı" şeridi → örnek soru → makbuz → kaynaklı cevap.
> **Bu sahne tek çekimde alınır** (çekim rehberi §1.4, kota kuralı).

En sevdiğimiz kısım. Projeye Türkçe soruyoruz:
«Hosted demo kararı neydi?» //

Önce neyi taradığını söylüyor: kapsam, görevler, karar günlüğü, olaylar. //

Altında bir «reg» hattı var: belgeler embedding'lenip «pi-ci-vektör»de
tutuluyor, anlamsal arama kelime eşleşmesiyle birlikte çalışıyor. Cevabı üreten
model «yalnız bulunan kanıtı» görüyor, ve her atıf kanıt kümesine karşı
doğrulanıyor — eşleşmeyen atıf varsa o cevap gösterilmiyor. //

Sonuç: ürün kendi karar kaydından cevap veriyor, ve bu karardan önceki
cevabının artık geçersiz olduğunu da söylüyor. Kaynağı olmayan tek bir cümle
göstermiyoruz.

---

## S7 · KAPANIŞ — mimari + yığın (02:45 → 03:00)

> Ekranda: Ask cevabı kalır ya da Radar'a dönülür. Tıklama yok.

Mimari «port adaptör»: çekirdekte framework ya da sağlayıcı importu yok —
cemini'yi grok'la veya tam-yerel olama ile değiştirmek tek satır; o modda veri
makineden çıkmıyor. //

Yığın fast-ey-pi-ay, React, «pi-ci-vektör»; kendi sunucumuzda.

Ensemble — ekip koordinasyonunu «görünür» kılar.

---

## Yedek cümleler — ekranda uyarı şeridi çıkarsa

Ürün, elindeki zemin daraldığında bunu **söyler** (sessizce eksik cevap
vermez). Kayıt anında sağlayıcı kotası dolmuşsa ekranda turuncu bir uyarı
şeridi görünebilir. Çeken kişi ön-uçuşta kontrol edip sana **hangi varyantı
okuyacağını** bildirecek.

**A) Şerit YOK (tercih edilen):** script'i olduğu gibi oku.

**B) Radar'da "sonuç eksik" şeridi VAR** — S2'nin sonuna ekle:

> Bir uyarı da görüyorsunuz: bu turda bazı çiftler değerlendirilemedi ve ürün
> bunu «söylüyor». Liste kısa çünkü sonuç eksik — çakışma olmadığı için değil.

**C) Ask'ta "zemin dar" şeridi VAR** — S6'nın sonuna ekle:

> Buradaki uyarı da aynı ilkeden: bu cevap dar bir zeminde üretildi ve ürün
> bunu saklamıyor. Yanlış olmayabilir ama eksik olabilir — ve bunu size o
> söylüyor.

> **Not:** B ya da C okunursa ~8 saniye uzar. O durumda S5'in son cümlesini
> ("Eşikler de uydurma değil…") çıkar; teknoloji kapsaması S2 ve S7'de zaten
> duruyor.

---

## Süre kontrolü

| Sahne | Ekran aralığı | Ekran | Kelime | Konuşma ≈ |
|---|---|---:|---:|---:|
| S1 Açılış | 00:00–00:20 | 20 sn | 48 | 21 sn |
| S2 Radar | 00:20–00:55 | 35 sn | 84 | 36 sn |
| S3 Scope | 00:55–01:20 | 25 sn | 43 | 18 sn |
| S4 Board | 01:20–01:45 | 25 sn | 50 | 21 sn |
| S5 Activity | 01:45–02:05 | 20 sn | 47 | 20 sn |
| S6 Ask | 02:05–02:45 | 40 sn | 78 | 33 sn |
| S7 Kapanış | 02:45–03:00 | 15 sn | 35 | 15 sn |
| **Toplam** | | **3:00** | **385** | **~2:45** |

> Kelime sayıları **sayıldı**, tahmin değil. İki uçta da hesaplandı:
> 140 kelime/dk → **2:45** · 130 kelime/dk (çok yavaş) → **2:57**.
>
> **PROVA KAPISI:** kronometreyle bir kez baştan sona oku.
> **2:50'yi geçiyorsan** şu üç cümleyi çıkar (bu sırayla):
>
> 1. S5 son cümlesi — *"Eşikler de uydurma değil…"*
> 2. S3 son cümlesi — *"Kapsam metni de git'te yaşıyor…"*
> 3. S1 ikinci paragrafı — *"İki kişi farkında olmadan…"*
>
> Üçü birden ~25 kelime; kalan süre 2:30 civarına iner.
> **S2 ve S6 kısaltılmaz** — final değerlendirmede "yapay zeka öğeleri" 35 puan
> ve o iki sahne tam olarak onun cevabı.

---

## Ek: teknoloji kapsaması — nerede ne söyleniyor

> **Okunmaz.** Bootcamp rehberi §5.1'in yedi sorusunun script'te *gerçekten*
> karşılandığını doğrulamak için. Bir cümle çıkarılacaksa önce buraya bakılır:
> hangi sorunun cevabı kayboluyor?

| Bootcamp §5.1 sorusu | Nerede | Ne söyleniyor |
|---|---|---|
| Hangi AI model / servis? | S2 · S7 | `gemini-embedding` · `gemini-2.5-flash` · Groq yedeği · Ollama yerel |
| AI ürün içinde hangi görevi üstleniyor? | S2 | iki ayrı iş: **embedding** (anlamsal benzerlik) + **judge** (karar) |
| Agent / workflow / prompt yapısı | S2 · S5 | deterministik aday elemesi → embedding sinyali → judge'a **iki sinyal birlikte** · şemaya bağlı yapılandırılmış çıktı · judge'ın **dört katmanı** |
| Bilgi tabanı / RAG / vektör DB | S4 · S6 | `.harness/` git-native bilgi tabanı · pgvector · RAG + **atıf doğrulama** |
| AI kullanıcıya hangi değeri sağlıyor? | S2 · S3 · S6 | çakışmayı merge öncesi yakalama · kapsam kararını alıntıyla · kaynaklı cevap |
| Servisler ve entegrasyonlar | S4 · S7 | GitHub App + webhook · MCP sunucusu · kendi sunucu + Vercel |
| Teknik mimari özeti | S4 · S7 | tek motor iki arayüz · `.harness` kanonik / DB projeksiyon · **port–adapter** |

### Ölçülmüş iddialar (uydurma yok — kaynak: kod + canlı ürün, 31 Tem 2026)

| İddia | Kaynak |
|---|---|
| `gemini-2.5-flash` · `gemini-embedding-001` (768 boyut) · Groq `llama-3.3-70b-versatile` · Ollama `llama3.2` + `nomic-embed-text` | `src/backend/ensemble/config.py` |
| Judge dört katman: `PersistentJudge` · `DevreKesiciJudge` · `CachedConflictJudge` · `FallbackJudge` | `src/backend/ensemble/engine/` |
| "Çekirdekte framework/sağlayıcı importu yok" | `engine/` altında **0** fastapi, **0** sağlayıcı SDK importu (ölçüldü) |
| Aday şartı **ortak dosya** (`if not overlap: continue`); Jaccard eleme DEĞİL **sıralama** için (varsayılan eşik 0.0). Benzerlik judge'a **girdi** olarak gidiyor: `judge_conflict(a, b, overlap, sim)` | `engine/radar.py` · `ports.py:105` |
| MCP'de **iki okuma aracı**: `who_is_touching`, `check_scope` | `src/mcp/ensemble_mcp/server.py` — `declare_work` bilinçli kapsam dışı, script'te de iddia EDİLMİYOR |
| Eşikler: precision ≥ 0.90 · F0.5 ≥ 0.89 · korpus ≥ 100 | `eval/gate.py` |
| 109 tespit · 3 yüksek · 36 ortak dosya · güven 0.9 · 39 kart | canlı `api.recommend2me.com` (çekim günü ön-uçuşta tazelenecek) |
