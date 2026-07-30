# Sprint 3 · teslim öncesi dar RC kabul raporu

**Tarih:** 30 Temmuz 2026

**Issue:** [#363](https://github.com/FatihErenCetin/grup54/issues/363)

**Sonuç:** **Dar yerel teknik RC PASS · genel teslim kararı KOŞULLU GO**

Bu koşum videoda gösterilecek Radar, Scope, Board, Activity ve Ask yüzeyleriyle
sınırlıdır. Yeni bir E2E çerçevesi kurulmadı; görünür gerçek Edge oturumu hem
makine-okunur Chrome DevTools Protocol probuyla hem de Semih tarafından ekranda
elle doğrulandı. Süreler yerel geliştirme sunucusundaki gözlemlerdir, performans
eşiği değildir.

## Aday ve koşum ortamı

- Son görünür koşum: `T-363-rc-kabul-kosumu@f18f213`. Dalın ürün çalışma
  zamanı ağacı `origin/main@dde027d` ile aynıdır; tek branch değişikliği bu
  rapordur.
- #238 ve #322 main'e sırasıyla `61062af` ve `4b96c5b` merge commit'leriyle
  birleşmiştir.
- Tarayıcı: Microsoft Edge `150.0.0.0`, Windows 10/11, **görünür** gerçek
  Chromium motoru.
- Frontend: Vite geliştirme sunucusu, `http://127.0.0.1:5173`.
- Backend: FastAPI/Uvicorn, ayrı SQLite RC projeksiyonu,
  `http://127.0.0.1:8000`.
- Veri: `.harness/` + deterministik fake GitHub backfill; Board'da 22 kart,
  Activity'de 3 olay; Ask korpusunda 14 kapsam maddesi, 23 görev belgesi ve
  11 karar kaydı.
- Dış sağlayıcı anahtarları boş: `GEMINI_API_KEY=` ve `GROQ_API_KEY=`.
  Başlangıç izi `FakeGitHubAdapter`, `FakeJudgeAdapter` ve `HashEmbeddings`
  seçildiğini doğruladı.
- Dış HTTP fail-closed tutuldu; tarayıcı Network kaydında görülen tek host
  `127.0.0.1` oldu.

## Donmuş kabul eşikleri

| Eşik | Hedef | Gerçek | Sonuç |
|---|---:|---:|---|
| Kritik video akışı başarısı | %100 | **5/5, %100** | PASS |
| Beklenmeyen uncaught console error | 0 | **0** | PASS |
| Beklenmeyen HTTP 4xx/5xx | 0 | **0** | PASS |
| Gemini/Groq dış HTTP çağrısı | 0 | **0** | PASS |
| Eval precision | ≥ 0,90 | **1,0000** | PASS |
| Eval F0.5 | ≥ 0,89 | **0,8929** | PASS |
| Eval korpus | ≥ 100 | **118** | PASS |
| Eval çağrı bütçesi | judge ≤ 6 · embed ≤ 6 · GitHub ≤ 12 | **5 · 5 · 11** | PASS |

## Tarayıcı kabul matrisi

| Akış | Beklenen | Gerçek | Gözlenen süre | Sonuç |
|---|---|---|---:|---|
| Radar | Gerçek backend zinciri deterministik bir çakışma üretir; kart ve detay paneli açılır. | 3 ortak dosyalı 1 yüksek tespit üretildi; iki aktör, iki branch, %50 confidence ve detay paneli görünür doğrulandı. | 1.015,2 ms | PASS |
| Scope | Dondurulmuş amaç ve kapsam içi/dışı maddeler görünür. | 14 kapsam maddesi yüklendi. `/scope/check` çağrılmadığı için “henüz kapsam kararı yok” dürüst boş durumu gösterildi. | 767,6 ms | PASS |
| Board | Kanonik görevler beş kolona projekte edilir. | “22 kart · beş kolon” görünür; hata yok. | 805,5 ms | PASS |
| Activity | Olay akışı ve aktör/görünüm filtreleri kullanılabilir. | 3 olay ve iki filtre grubu görünür; hata yok. | 780,6 ms | PASS |
| Ask | Soru öncesi tarama makbuzu görünür; soru yerel zincirde kaynaklı cevaplanır. | Makbuz 14 kapsam · 23 görev · 11 karar gösterdi. “Hosted demo kararı nedir?” sorusu iki kaynak alıntılı, orta güvenli cevap döndürdü. | 933,6 ms | PASS |

Süre, doğrudan route navigasyonundan akış koşulunun ve varsa etkileşimin
tamamlanmasına kadardır. Vite modül istekleri dâhildir; production performans
baseline'ı olarak kullanılmamalıdır.

### İnsan görsel kabulü

30 Temmuz 2026, 23:42–23:54 TSİ arasında aynı görünür Edge oturumu Semih
tarafından ekran ekran kontrol edildi:

| Ekran | İnsan kontrolü | Sonuç |
|---|---|---|
| Radar | Yüksek tespit kartı, iki aktör, üç dosya ve sağ detay paneli | PASS |
| Scope | DONMUŞ v1, kapsam içi/dışı; sıfır-AI nedeniyle dürüst boş karar paneli | PASS |
| Board | 22 kart ve beş kolon | PASS |
| Activity | 3 olay ve filtre kontrolleri | PASS |
| Ask | 14 kapsam · 23 görev · 11 karar makbuzu ve kaynak alıntılı cevap | PASS |

Kalıcı kanıt:

- [Makine-okunur tarayıcı/ağ sonucu](rc-kabul-tarayici-sonucu.json)
- [Radar tespit ve detay ekran görüntüsü](Screenshots/rc-radar-detay-2026-07-30.png)

## Eval ve çağrı bütçesi

Windows ortamında `make` kurulu olmadığı için Makefile'daki dört reçete değişmeden
tek tek çalıştırıldı:

```text
uv run python -m eval.eval_runner
uv run python -m eval.sweep
uv run python -m eval.gate
uv run python -m eval.butce_eval
```

`eval` sonucu:

```text
Precision 1.0000 · Recall 0.6250 · F1 0.7692 · F0.5 0.8929
TP=5 · FP=0 · FN=3 · TN=110 · toplam=118
```

`eval-gate` precision/F0.5/korpus eşiklerini geçti. `eval-butce` aynı sabit
korpusta bir radar koşumunu `5 judge · 5 embed · 11 GitHub çağrısı (10 olay)`
olarak ölçtü ve `6 · 6 · 12` bütçesinin altında kaldı. Bu RC koşumu eval
eşiklerini veya fixture'larını değiştirmedi. #363 mevcut sonucu alıntılamayı
istese de aynı issue `make eval` ve `make eval-butce` kapılarını yeşil şart
koştuğu için Makefile'daki deterministik, ağsız reçeteler yeniden çalıştırıldı;
değerler mevcut eval sonucuyla aynı kaldı. Canlı provider kalibrasyonu
çalıştırılmadı.

## Sıfır dış AI çağrısı kanıtı

Üç bağımsız iz aynı sonucu verdi:

1. `/health`: `gemini=missing`, `fallback=missing`, GitHub auth `missing`.
2. Backend başlangıç kaydı: `FakeJudgeAdapter` + `HashEmbeddings` +
   `FakeGitHubAdapter`.
3. Beş akışın tam tarayıcı Network kaydı: gözlenen host yalnız
   `127.0.0.1`; Gemini, Groq, Ollama veya başka bir dış host yok.

Kalıcı JSON izinde yalnız başarılı yanıtlar değil, `requestWillBeSent`,
`responseReceived`, `loadingFailed`, uncaught exception ve console error
olayları birlikte gözlendi. Böylece yanıt üretmeden başarısız olan bir dış
istek de sessizce host sayımından düşmez.

Dolayısıyla RC'nin dış AI çağrı sayısı **0** ve demo/video kotasından harcanan
generate isteği **0**'dır.

## Production smoke kanıtı

RC canlı ortamda `/query`, `/scope/check` veya soğuk `/radar` çağırmadı.
Production erişilebilirliği için #238'deki AI'sız smoke kanıtı alıntılandı:

- [Yeşil production koşumu](Screenshots/smoke-yesil.md):
  `api.recommend2me.com` + `recommend2me.com`, çıkış `0`; health, CORS ve
  altı SPA route'un doğrudan/refresh kontrolleri geçti.
- [Yeşil terminal ekran görüntüsü](Screenshots/smoke-yesil-terminal-2026-07-30.png).
- [Bilinçli kırmızı koşum](Screenshots/smoke-kirmizi.md):
  yanlış web hedefinde çıkış `2`, 14 hata; smoke'un hatayı gerçekten
  yakaladığı doğrulandı.
- [Kırmızı terminal ekran görüntüsü](Screenshots/smoke-kirmizi-terminal-2026-07-30.png).

Bu production kanıtının sınırı açıktır: health, CORS ve SPA kabuğunun
erişilebilirliğini kanıtlar; production ekranlarının gerçek veriyle uçtan uca
çalıştığını kanıtlamaz. Canlı AI kotasını koruma kararı nedeniyle bu turda
production `/query`, `/scope/check` ve soğuk `/radar` kabulü yapılmamıştır.

## Bulgular ve takip işleri

Ürün kabul akışlarında kusur çıkmadı; bu nedenle hata ekran görüntüsü veya
yeniden üretim izi gerektiren bir FAIL yok.

Koşum altyapısında iki takip işi açıldı:

- [#365](https://github.com/FatihErenCetin/grup54/issues/365) — Windows
  CP1252 konsolunda eval çıktısı `UnicodeEncodeError` ile çöküyor.
  `PYTHONUTF8=1` ile aynı reçete yeşil; kalıcı UTF-8 güvenliği ayrıca
  kapatılacak.
- [#366](https://github.com/FatihErenCetin/grup54/issues/366) —
  `npm audit --omit=dev`, `react-router-dom@7.18.1` ağacında GHSA-qwww-vcr4-c8h2
  için 2 yüksek uyarı bildiriyor. Uygulama RSC/action modu kullanmadığından
  ilk teknik değerlendirme dar işlevsel RC'yi bloklamıyor; ancak **genel
  teslim GO kararı**, uygulanabilirlik kapatılana veya PO süreli ve gerekçeli
  risk kabulü verene kadar koşulludur.

Issue eklemeleri Sprint 3 bağımlılık haritasını bayatlatmış olabilir; harita
otomasyonunun #363, #365 ve #366'yı içerecek şekilde tazelenmesi gerekir.

## Karar

**Dar yerel teknik RC: PASS.** Donmuş sekiz kapının tamamı geçti; görünür insan
kabulü ve dolu Radar detay akışı da doğrulandı. Canlı AI kotası korunmuştur.

**Genel teslim: KOŞULLU GO.** Production smoke veri-yüklü uçtan uca ürün
kabulü değildir. Ayrıca #366 için PO risk kararı veya teknik kapanış gerekir.
#365 yerel eval operatör deneyimi borcudur ve dar ürün kabulünü bloklamaz.
