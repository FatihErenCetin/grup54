---
type: decision
id: D-65
title: "Ask beş yerden kırıktı — karar kaydı korpusa girdi, radar Ask'ın vektörlerini silmeyi bıraktı, düşüş artık görünüyor"
date: "2026-07-30"
status: accepted
---

# D-65 — Ask'ın beş kusuru ve ortak kökleri

PO "Ask düzgün çalışıyor mu, test et" dedi. Mekanik olarak çalışıyordu:
`200`, atıflar arayüzde temiz `[1]` üst-simgesi, alıntı paneli, arama makbuzu,
boş soruda `422`. **Cevapları güvenilmezdi.** Beş kusur bulundu; ikisi
birbirini besliyordu, biri tamamen sessizdi.

## ① Karar günlüğü hiç aranmıyordu

`_CITATION_TYPES` `"decision"` ilan ediyor, arama makbuzu her seferinde
`decision: 0` basıyor, `AskPage`'in kendi metni *"…karar günlüğü ve PR
geçmişi üzerinde aranır"* diyordu. Ama `load_query_corpus()` yalnız
scope+task+event üretiyordu ve `HarnessPort`'ta **`read_decisions()` hiç
yoktu**.

Çevresindeki her şey hazırdı: `NON_DATA_FILENAMES["decisions"]`,
`decision.schema.json`, kontrattaki tip, arayüzdeki vaat. Yalnız ORTADAKİ
halka eksikti — o yüzden hiçbir şey hata vermedi.

## ② Sonuç: ürün KENDİ kararıyla çelişti

Canlı ölçüm: *"Hosted demo kararı neydi?"* → **"Fly backend + Vercel +
webhook"**. Fly.io 25–26 Tem'de tamamen terk edilmişti. Ürün eski bir görev
metnini (T-34) alıntılıyordu ve onu çürüten kaydı **okuyamıyordu**.

Bir kararı değiştiren tek şey başka bir karardır. Kurum hafızası diske
yazılıydı ama ürünün gözü ona kapalıydı.

## ③ Radar'ın rebuild'i Ask'ın vektörlerini siliyordu — SESSİZCE

En ağırı. Radar ile Ask **aynı `vector_index` tablosunu** paylaşıyordu.
Radar'ın rebuild'i `replace_all()` çağırır; sözleşmesi gereği tabloyu komple
silip yalnız kendi olay vektörlerini yazar. Ask'ın scope/task/decision
vektörleri her rebuild'de yok oluyordu.

Sessiz olmasının sebebi zinciri: `_indexed_hashes` **bellekte** → süreç
"zaten gömdüm" sanıyor → yeniden gömmüyor → vektör sorgusu yalnız olay
id'leri dönüyor → Ask korpusuna filtrelenince boş kalıyor → **istisna
fırlamadığı için `degraded` de dolmuyor**. Ürün tam yetenek iddia ederken
leksikal çalışıyordu.

Ölçüm: `vector_index` **661 satır** (378 commit + 149 pr + 134 issue), Ask
korpusundan (`task:`/`scope:`/`decision:`) **0 satır**. *"Sprint 3 kapsamında
neler var?"* sorusunun beş atfının da ham commit SHA'sı olmasının sebebi
buydu — semantik olarak yalnız olaylar vardı.

**Çözüm:** ayrı tablo (`query_vector_index`, migration `e5b8d2c71a09`).
`replace_all`'ı daraltmak DEĞİL — sözleşmesi "hepsini değiştir" ve radar
için doğru olan da bu. İki korpusun yaşam döngüsü farklı (radar'ınki komple
yeniden kurulur, Ask'ınki artımlı tazelenir); farklı yaşam döngüsü, farklı
tablo.

## ④ Her yeniden başlatma tüm korpusu yeniden gömüyordu

`_indexed_hashes` constructor'da boş dict; **vektörler kalıcı, parmak izi
değil**. Restart → ~236 belge "değişmiş" sayılıyor → 236 embed çağrısı.
Gemini'nin ücretsiz günlük embed kotası **1000**. 30 Tem'de defalarca deploy
edildi → kota bitti → o günün geri kalanında **her cevap `degraded`**, üç
örnek sorunun ikisi `not_found`.

**Çözüm:** parmak izi `meta`'ya yazılır, açılışta indeksten okunur
(`VectorIndexPort.fingerprints()`).

## ⑤ `degraded` arayüze hiç düşmüyordu

`RadarPage`: 9 referans + özel `EksikSonucSeridi` bileşeni (yorumunda
"sessiz eksiltmenin panzehiri" yazıyor). `AskPage`: **0**. `ScopePage`: **0**.
API dürüstçe ilan ediyor, arayüz yutuyordu.

Sözleşme model katmanında **üç yerde** uygulanmış, arayüzde **bir yerde**
bağlanmıştı.

## ⑥ Yedek sağlayıcı Ask için bozuktu (deploy sonrası ölçüldü)

Düzeltmeler canlıya çıktıktan sonra `/query` **503** döndü. Log:

> `answer_query: iki sağlayıcı da üretemedi (birincil: 429 … · yedek: Groq Ask
> cevabı şemaya uymuyor: 2 validation errors)`

Yani Gemini'nin günlük **generate** kotası (flash için 20/gün) bitmiş, yedek
devreye girmiş, **Groq gerçekten cevap üretmiş** — ama `{"answer": "…"}`
döndürüp `citation_refs` ve `confidence` alanlarını atlamış.

Kök sebep: Gemini şemayı **sunucu tarafında zorluyor**, Groq'un
`response_format: json_object`'i yalnız "geçerli JSON" garanti ediyor —
şemayı zorlamıyor. Paylaşılan prompt alanları **adıyla istemiyordu**.

Yani kotanın bittiği an çalışan TEK yol, biçimsel bir eksik yüzünden çöpe
gidiyordu. Yedeğin varlık sebebi tam o andı.

**Çözüm iki katmanlı:**
1. Paylaşılan prompt üç alanı da **adıyla** istiyor (Gemini'ye zararsız, iki
   sağlayıcı aynı ölçütte kalıyor).
2. Groq adaptörü eksik alanları **muhafazakâr biçimde onarıyor** — ve sınırı
   net: `citation_refs` **uydurulmaz**, modelin cevabına KENDİ yazdığı
   `[cite:…]` işaretlerinden *okunur* (uydurma ref'i engine'in
   `_validated_citations`'ı zaten yakalar); hiç işaret yoksa onarım YAPILMAZ.
   `confidence` bir yargıdır ve model söylemediyse **en düşük kademe** verilir
   — bilinmeyen güveni "medium" saymak, olmayan bir kesinlik satmak olurdu.
   *Eksik yönde yanılmak serbest, fazla yönde değil.*

Not: Groq anahtarı **çalışıyordu**; sorun kimlik doğrulama ya da kota değil,
bizim ayrıştırmamızdı.

## Ortak kök: "son santim"

Beşinin de aynı şekli var — çevredeki her şey hazır, son bağlantı yok:
tip ilan edilmiş/okuyucu yok · alan üretilmiş/basılmayan arayüz · vektör
yazılmış/parmak izi kalıcı değil. Ve hiçbiri hata vermiyor, çünkü eksik olan
şey bir HATA değil bir **yokluk**.

Bu yüzden bu turda eklenen kurallardan biri şu: **`_decision_documents`
`AttributeError` yakalamaz.** Yakalasaydık, düzelttiğimiz bug'ı bilerek
yeniden inşa etmiş olurduk (kaynak sessizce boş kalır, makbuz `decision: 0`
basar, kimse fark etmez). Kural D-63/#330 ile aynı: **sağlayıcı arızasında
yumuşa, KENDİ sözleşme ihlalimizde patla.**

## Test boşluğu da kayda geçiyor

`AskPage`'in **hiç testi yoktu** (`pageTitles.test.tsx` yalnız başlığa
bakıyordu). Beş kusurun hiçbirini hiçbir test sormuyordu; eklediğim
düzeltmelerin ilk turunda da **1182 test yeşil kaldı** — bu iyi haber değil,
boşluğun kanıtıydı. `tests/ask.test.tsx` bu turda açıldı.

Ayrıca `test_migration_actor_verified` `downgrade -1` kullanıyordu, yani
kendi migration'ının HEAD olduğunu varsayıyordu; yeni migration eklenince
sessizce BAŞKA bir migration'ı sınamaya başladı. Hedef revizyon adıyla
sabitlendi.

## Groq yedeği (aynı gün, PO'dan)

`GROQ_API_KEY` zaten kuruluydu ve çalışıyordu (bkz. ⑥ — kırık olan ayrıştırma
tarafımızdı). **Embedding sorununu ÇÖZMEZ** — Groq yalnız
LLM judge sağlıyor (`judge` · `scope_judge` · `query_judge`), embedding
sunmuyor. Değeri şurada: Gemini'nin günlük *generate* kotası (flash için 20)
bitince cevap üretimi ayakta kalır. Semantik aramayı ayakta tutan şey ③ ve
④'ün kendisi.

## Kanıt

- **20 mutasyon kanıtı** (①4 · ③3 · ④4 · ⑤4 · ⑥5) — her kilit kodu bozunca kırılıyor
- 1197 backend + 356 frontend test yeşil · `ruff` temiz
- Migration `e5b8d2c71a09` · yeni port metodu `VectorIndexPort.fingerprints()`
- Yeni test dosyası: `src/frontend/tests/ask.test.tsx`

## İlgili

- İddia–ölçüm hizalaması: D-63 · Kapsam kaydı: D-64
- `#330` (degraded sözleşmesi) — model katmanı doğruydu, arayüz eksikti
