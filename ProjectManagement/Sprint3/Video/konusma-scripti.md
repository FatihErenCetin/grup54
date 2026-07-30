# 3 dakikalık tanıtım videosu — konuşma scripti

> **Bu dosya SESLENDİREN kişi içindir.** Çeken kişinin dosyası ayrı:
> [`cekim-rehberi.md`](cekim-rehberi.md). İkisi **aynı sahne numaralarını** (S1–S7)
> ve **aynı zaman kodlarını** kullanır — senkron oradan sağlanır.

**Kaynak:** akış #65'te dondurulmuş (yüzey listesi #363 dar RC ile aynı).
Bu script o dondurulmuş sürelere birebir uyar; yeni yüzey EKLEMEZ.

**Toplam hedef:** 2:50–2:55 (üst sınır 3:00).
**Ölçülen:** 415 kelime · 145 kelime/dk temposunda ≈ **2 dakika 52 saniye**.

---

## Okuma kuralları (önce bunu oku)

1. **Yavaş oku.** Acele edip 2:20'de bitirmek, 3:05'te bitirmekten daha kötü
   değil ama gereksiz — süre zaten hesaplandı. Doğal konuşma temposu yeterli.
2. **Sayıları net söyle.** "yüz dokuz", "otuz altı", "sıfır virgül dokuz".
   Ekranda görünen sayıyla ağzından çıkan sayı **aynı olmalı** — çeken kişi
   ön-uçuşta güncel sayıları teyit edip sana bildirecek (bkz. çekim rehberi).
3. **Arka planda müzik yok** (bootcamp kuralı). Sessiz oda, ağızdan 15–20 cm
   mesafe, telefon mikrofonu bile yeterli — önemli olan netlik.
4. **Köşeli parantez içindekiler okunmaz.** `[…]` yönerge, `«…»` vurgu demek.
5. **Nefes yerleri** `//` ile işaretli. Orada kısa dur; kurguda kesim noktası olur.

### Telaffuz notları

| Yazılı | Söylenir |
|---|---|
| PR | "pi-ar" |
| pgvector | "pi-ci-vektör" |
| RAG | "reg" (tek hece) |
| MCP | "em-si-pi" |
| FastAPI | "fast-ey-pi-ay" |
| Gemini / Groq / Ollama | "cemini" / "grok" / "olama" |
| `.harness/` | "harness klasörü" |
| 0.9 | "sıfır virgül dokuz" |

---

## S1 · AÇILIŞ — problem (00:00 → 00:20)

> Ekranda: Radar sayfası açık, henüz tıklama yok.

Bir yazılım ekibinde dört kişi aynı anda çalışıyor — ve artık her birinin
yanında bir de yapay zeka aracı var. Kod üretimi hızlandı; koordinasyon
hızlanmadı. //

Sonuç tanıdık: iki kişi farkında olmadan aynı dosyaya dokunuyor, iş kapsamdan
sessizce kayıyor, board gerçeği yansıtmıyor. //

Ensemble tam bu boşluk için var: ekibin «paylaşılan proje beyni».

---

## S2 · RADAR — çakışma tespiti (00:20 → 00:55)

> Ekranda: Radar listesi → yüksek şiddetli tespite tıklanır → detay paneli açılır.

Radar, açık işleri birbirleriyle kıyaslıyor. Şu an «yüz dokuz» tespit var,
üçü yüksek şiddetli. //

Şuna bakalım: iki farklı geliştirici, «otuz altı ortak dosya».
Ama Ensemble bunu yalnızca dosya kesişimine bakarak söylemiyor — kesişimi bir
yapay zeka değerlendiricisine gönderiyor, ve gerekçesini Türkçe yazıyor:
aynı mantıksal birimler değişiyor, aralarında kritik dosyalar var.
Güven skoru: «sıfır virgül dokuz». //

Farkımız burada. Kod inceleme araçları tek bir pi-ar'ın **içine** bakar.
Ensemble «iki ayrı işin kesişimine» bakar — ve merge edilmeden önce uyarır.

---

## S3 · SCOPE — kapsam bekçisi (00:55 → 01:20)

> Ekranda: Scope sayfası, donmuş kapsam + bir karar satırı (alıntı görünür).

Kapsam bekçisi. Sprint kapsamı sprint başında donduruluyor; Ensemble her işi
bu donmuş metne karşı değerlendiriyor. //

Kararını «alıntıyla» gerekçelendiriyor: hangi maddeye dayandığını, hangi
cümleden çıkardığını gösteriyor. Yani "bu iş kapsam dışı" demiyor; "şu maddeye
göre kapsam dışı" diyor. //

Kapsam metni de git'te yaşıyor. Kapsam değişirse bu bir denetim kaydı oluyor —
kimse fark etmeden kayma olmuyor.

---

## S4 · BOARD — kendiliğinden dolan board (01:20 → 01:45)

> Ekranda: Board sayfası, beş kolon, kartlar görünür.

Board kendiliğinden doluyor. «Otuz dokuz kart, beş kolon» — kaynağı gerçek
pi-ar ve issue durumu. Kimse kart sürüklemedi. //

Kanonik kayıt git'te duruyor: `.harness/` klasörü. Veritabanı yalnızca bir
projeksiyon; ikisi çelişirse git kazanıyor. Board'un kendini güncellemesi
buradan geliyor. //

Ve bu klasör yalnız bizim ürünümüze açık değil. Bir em-si-pi sunucusu üzerinden
ekipteki «herkesin yapay zeka aracı aynı beyne bağlanıyor» — kimin nereye
dokunduğunu, işin kapsamda olup olmadığını sizin ajanınız da sorabiliyor.

---

## S5 · ACTIVITY — ortak zaman çizelgesi (01:45 → 02:05)

> Ekranda: Activity sayfası, olay akışı + filtreler.

Activity, ekibin ortak zaman çizelgesi. Commit, pi-ar ve issue olayları tek
akışta; aktöre ve türe göre filtreleniyor. //

Günlük özet de buradan çıkıyor — kimin neye dokunduğunu görmek için kimseye
sormak gerekmiyor. //

Bir not: radar'ın şiddet eşikleri uydurma değil. Etiketli bir veri kümesi
üzerinde ölçülüp kalibre edildi; yanlış alarm oranını görmeden bir eşiği
"tamam" saymıyoruz.

---

## S6 · ASK — projeye doğal dille sor (02:05 → 02:45)

> Ekranda: Ask sayfası → örnek soru tıklanır → makbuz → kaynaklı cevap.
> **Bu sahne tek çekimde alınır** (bkz. çekim rehberi, kota kuralı).

En sevdiğimiz kısım. Projeye Türkçe soruyoruz:
«Hosted demo kararı neydi?» //

Önce neyi taradığını söylüyor: kapsam, görevler, karar günlüğü, olaylar. //

Cevap projenin «kendi karar kaydından» geliyor ve kaynağını gösteriyor.
Dikkat edin — ürün, bu karardan önce verdiği eski cevabın artık geçersiz
olduğunu da söylüyor. Kurum hafızası kod tabanında yaşıyor, ve ürün onu
okuyabiliyor. //

Altında bir «reg» hattı var: belgeler embedding'lenip pi-ci-vektör'de
tutuluyor, cevap yalnız bulunan kanıta dayanıyor.
Kaynağı olmayan tek bir cümle göstermiyoruz.

---

## S7 · KAPANIŞ — teknoloji + değer (02:45 → 03:00)

> Ekranda: Ask cevabı kalır ya da Radar'a dönülür. Yeni tıklama yok.

Altyapı: fast-ey-pi-ay çekirdek, React arayüz, PostgreSQL üstünde
pi-ci-vektör. Yapay zeka tarafında birincil model cemini; kotası dolduğunda
grok yedeğe geçiyor, tam-yerel modda ise olama ile hiçbir veri makineden
çıkmıyor. //

Ensemble — yapay zeka çağında ekip koordinasyonunu «görünür» kılar.
Kaynaklı, ölçülü, ve eksik olduğunda bunu söyleyen bir şekilde.

---

## Yedek cümleler — ekranda uyarı şeridi çıkarsa

Ürün, elindeki zemin daraldığında bunu **söyler** (sessizce eksik cevap
vermez). Kayıt anında sağlayıcı kotası dolmuşsa ekranda turuncu bir uyarı
şeridi görünebilir. Çeken kişi ön-uçuşta bunu kontrol edip sana **hangi
varyantı okuyacağını** bildirecek.

**A) Şerit YOK (tercih edilen):** yukarıdaki script'i olduğu gibi oku.

**B) Radar'da "sonuç eksik" şeridi VAR** — S2'nin sonuna ekle:

> Şu an bir uyarı da görüyorsunuz: bu turda bazı çiftler değerlendirilemedi ve
> ürün bunu «söylüyor». Liste kısa çünkü sonuç eksik — çakışma olmadığı için
> değil. Sessizce eksik sonuç göstermiyoruz.

**C) Ask'ta "zemin dar" şeridi VAR** — S6'nın sonuna ekle:

> Buradaki uyarı da aynı ilkeden: bu cevap dar bir zeminde üretildi ve ürün
> bunu saklamıyor. Yanlış olmayabilir ama eksik olabilir — ve bunu size o
> söylüyor.

> **Not:** B ya da C okunursa toplam süre ~8 saniye uzar. O durumda S5'in ikinci
> cümlesini ("Günlük özet de buradan çıkıyor…") çıkar — süre yine sınırın
> altında kalır.

---

## Süre kontrolü

| Sahne | Ekran aralığı | Ekran süresi | Kelime | Konuşma ≈ |
|---|---|---:|---:|---:|
| S1 Açılış | 00:00–00:20 | 20 sn | 50 | 21 sn |
| S2 Radar | 00:20–00:55 | 35 sn | 75 | 31 sn |
| S3 Scope | 00:55–01:20 | 25 sn | 54 | 22 sn |
| S4 Board | 01:20–01:45 | 25 sn | 67 | 28 sn |
| S5 Activity | 01:45–02:05 | 20 sn | 53 | 22 sn |
| S6 Ask | 02:05–02:45 | 40 sn | 71 | 29 sn |
| S7 Kapanış | 02:45–03:00 | 15 sn | 45 | 19 sn |
| **Toplam** | | **3:00** | **415** | **~2:52** |

> Kelime sayıları **sayıldı**, tahmin değil. Konuşma süresi 145 kelime/dakika
> kabulüyle; her sahnede birkaç saniyelik pay var (`//` duraklarının yeri).
> Sen S6'da cevabı beklerken oluşan boşluk kurguda kısaltılacak — o yüzden
> ekran süresi ile konuşma süresi arasındaki fark normal.

Provada telefon kronometresiyle bir kez baştan sona oku. **3:00'ı geçiyorsa**
sırasıyla şunları kısalt: S5'in ikinci cümlesi → S4'ün ikinci paragrafı →
S3'ün ikinci cümlesi. S2 ve S6 **kısaltılmaz** (jürinin en çok puanladığı iki
yer: çekirdek yetenek ve yapay zeka kullanımı).
