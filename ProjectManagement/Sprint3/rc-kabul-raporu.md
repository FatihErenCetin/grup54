# Sprint 3 · teslim öncesi dar RC kabul raporu

**Tarih:** 30 Temmuz 2026

**Issue:** [#363](https://github.com/FatihErenCetin/grup54/issues/363)

**Sonuç:** **PASS — teslim adayı kabul eşiklerinin tamamını geçti**

Bu koşum videoda gösterilecek Radar, Scope, Board, Activity ve Ask yüzeyleriyle
sınırlıdır. Yeni bir E2E çerçevesi kurulmadı; gerçek Edge tarayıcı motoru geçici
Chrome DevTools Protocol probuyla gözlendi. Süreler yerel geliştirme sunucusundaki
gözlemlerdir, performans eşiği değildir.

## Aday ve koşum ortamı

- Aday: `origin/main@2ed2617` üzerine PR
  [#238](https://github.com/FatihErenCetin/grup54/pull/238)
  `eac8ae2` ve PR
  [#322](https://github.com/FatihErenCetin/grup54/pull/322)
  `44ebe44` başlarının temiz yerel birleşimi.
- Koşumdan sonra iki PR da main'e birleşti (`61062af`, `4b96c5b`). Bu raporun
  dal tabanı `origin/main@dde027d` oldu; koşulan ağaçla aradaki tek fark
  `.gitignore` düzeltmesi ve onun birim testidir (#364), ürün çalışma zamanı
  kaynaklarında fark yoktur.
- Tarayıcı: Microsoft Edge `150.0.0.0`, Windows 10/11, headless gerçek Chromium
  motoru.
- Frontend: Vite geliştirme sunucusu, `http://127.0.0.1:5173`.
- Backend: FastAPI/Uvicorn, ayrı SQLite RC projeksiyonu,
  `http://127.0.0.1:8000`.
- Veri: `.harness/` + deterministik fake GitHub backfill; 22 görev, 3 olay,
  14 kapsam maddesi ve 11 karar kaydı.
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
| Radar | Sayfa açılır; boş deterministik aday kümesi dürüst “Radar temiz” durumuna gelir. | Başlık ve temiz durum çizildi; `/radar`, `/presence`, `/health` 200; console/network hatası yok. | 600,2 ms | PASS |
| Scope | Dondurulmuş amaç, kapsam içi/dışı maddeler ve karar paneli görünür. | 14 kapsam maddesi yüklendi; `/scope/current` ve `/scope/verdicts` 200; hata yok. | 485,4 ms | PASS |
| Board | Kanonik görevler beş kolona projekte edilir. | “22 kart · beş kolon” görünür; `/board` 200; hata yok. | 498,8 ms | PASS |
| Activity | Olay akışı ve aktör/görünüm filtreleri kullanılabilir. | 3 olay ve iki filtre grubu görünür; `/events` 200; hata yok. | 484,7 ms | PASS |
| Ask | Soru öncesi tarama makbuzu görünür; soru yerel zincirde kaynaklı cevaplanır. | Makbuz 14 kapsam · 22 görev · 11 karar gösterdi. “Hosted demo kararı nedir?” sorusu `/query` 200 ile iki kaynak alıntılı, orta güvenli cevap döndürdü. | 625,0 ms | PASS |

Süre, doğrudan route navigasyonundan akış koşulunun ve varsa etkileşimin
tamamlanmasına kadardır. Vite modül istekleri dâhildir; production performans
baseline'ı olarak kullanılmamalıdır.

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
metriklerini yeniden tanımlamadı; depodaki mevcut eval kapısının sonucunu
alıntıladı.

## Sıfır dış AI çağrısı kanıtı

Üç bağımsız iz aynı sonucu verdi:

1. `/health`: `gemini=missing`, `fallback=missing`, GitHub auth `missing`.
2. Backend başlangıç kaydı: `FakeJudgeAdapter` + `HashEmbeddings` +
   `FakeGitHubAdapter`.
3. Beş akışın tam tarayıcı Network kaydı: gözlenen host yalnız
   `127.0.0.1`; Gemini, Groq, Ollama veya başka bir dış host yok.

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

## Bulgular ve takip işleri

Ürün kabul akışlarında kusur çıkmadı; bu nedenle hata ekran görüntüsü veya
yeniden üretim izi gerektiren bir FAIL yok.

Koşum altyapısında iki bloklamayan takip işi açıldı:

- [#365](https://github.com/FatihErenCetin/grup54/issues/365) — Windows
  CP1252 konsolunda eval çıktısı `UnicodeEncodeError` ile çöküyor.
  `PYTHONUTF8=1` ile aynı reçete yeşil; kalıcı UTF-8 güvenliği ayrıca
  kapatılacak.
- [#366](https://github.com/FatihErenCetin/grup54/issues/366) —
  `npm audit --omit=dev`, `react-router-dom@7.18.1` ağacında GHSA-qwww-vcr4-c8h2
  için 2 yüksek uyarı bildiriyor. Uygulama RSC/action modu kullanmadığından
  ilk değerlendirmede RC akışını bloklamıyor; uygulanabilirlik ve güvenli
  sürüm ayrı issue'da kapatılacak.

Issue eklemeleri Sprint 3 bağımlılık haritasını bayatlatmış olabilir; harita
otomasyonunun #363, #365 ve #366'yı içerecek şekilde tazelenmesi gerekir.

## Karar

**GO.** Donmuş sekiz kapının tamamı geçti. Dar RC kapsamındaki ürün yüzeylerinde
teslimi bloklayan bir kusur yok; canlı AI kotası korunmuştur. #365 ve #366
teslim adayının işlevsel kabulünü bloklamayan, görünür takip borçlarıdır.
