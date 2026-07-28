# YZ Model Seçimi Raporu (#244)

> **Kanıt:** çıktı = ölçüm harness'i (`eval/model_secimi_eval.py`) + bu rapor. Amaç mevcut `config.py` varsayılanlarının ("neden bu model, neden bu boyut") **ölçülüp** kayda bağlanması — **değiştirilmesi DEĞİL**. Tekrarlanabilir: `make eval-model-secimi` (ağsız tahmin) / `uv run python -m eval.model_secimi_eval --run` (gerçek ölçüm, `GEMINI_API_KEY` gerektirir).

## 0. Bu raporun dürüst durumu

**Bu PR'da GERÇEK bir Gemini çağrısı YAPILMADI.** Ortamda da (`printenv`) `.env` dosyasında da (`.env` bu worktree'de yok) `GEMINI_API_KEY` **tanımlı değildi** — talimatın kati maliyet sınırı gereği ("YOKSA: hiçbir çağrı deneme") hiçbir ölçüm denenmedi. Aşağıdaki tüm sayısal sonuç tabloları bu yüzden **"ÖLÇÜLEMEDİ"** olarak işaretlidir; hiçbir rakam uydurulmadı. Kurulan şey: (a) harness'in kendisi — key eklendiğinde tek komutla gerçek ölçümü üretir, (b) key olmadan da hesaplanabilen kısım — **tahmini API çağrı sayısı** (aşağıda gerçek komut çıktısıyla birlikte) **ve** embedding boyutunun **depolama/indeks boyutu** (§4 — pgvector formülüyle ağsız hesaplanır).

> **#313 (bkz. #257 bulgu 1-4) harness'in KENDİSİNDE dört boşluğu kapattı** — Gemini judge/embedding rakamları hâlâ ÖLÇÜLEMEDİ (key yok) ama harness artık: (1) gecikmeyi retry/backoff beklemesinden **ARINDIRIYOR** (ayrı `avg_retry_wait_s` sütunu) ve gerçek modele ulaşıp başarısız olan çağrıları **görünür** kılıyor (`error_count`/`failed`) — eskiden tamamen başarısız bir model ya sahte-makul bir satır üretiyordu ya da tüm ölçümü çökertiyordu; (2) maliyet tahminine **en-kötü-durum HTTP istek** satırı ekledi (§2); (3) embedding boyutu için **depolama/indeks boyutunu** ağsız ölçtü (§4); (4) `--run` yolunda model/boyut başına hata yakalama + artımlı diske yazım ekledi — ödenmiş bir sonuç artık tek bir başarısızlıkta kaybolmuyor.

## 1. Yöntem — iki eksen

| Eksen | Aday değerler (varsayılan) | Ölçülen şey |
|---|---|---|
| **Judge yapılandırması** (`GEMINI_MODEL`) | `gemini-2.5-flash` (mevcut prod) vs `gemini-2.5-flash-lite` (ucuz/hızlı alternatif) | Aynı curated (#26, 12 vaka) + backtest (#27, 106 vaka) korpusu üzerinde `eval_runner` ile precision / recall / F1 / F0.5 + **ortalama gecikme** (yalnız gerçek modele ulaşan çağrılar zamanlanır — `cheap_prejudge` #24 önce elenenler hariç) |
| **Embedding boyutu** (`GEMINI_EMBEDDING_DIMENSIONS`) | `768` (mevcut prod) vs `1536` vs `3072` | Küçük, **sentetik** (elle yazılmış, `eval/datasets/`'e veya `tests/fixtures/`'a dokunulmadan) 8 "ilgili/ilgisiz metin çifti" örneklemi embed edilir; ilgili çiftlerin ortalama kosinüs benzerliği ile ilgisiz çiftlerinkinin farkı (**margin**) boyutlar arasında karşılaştırılır + **gecikme** |

**Neden sentetik embedding örneklemi?** `tests/fixtures/conflict_corpus.jsonl` ve `eval/datasets/backtest-grup54.jsonl` bilinçli olarak ham diff/commit metni TUTMAZ (veri sızıntısı önlemi — bkz. `eval/README.md`); yalnızca dosya listesi + insan notu var. Gerçek `radar.py::semantic_hunk_similarity` diff-hunk metnini embed eder, ama bu metin hiçbir fixture'da yoktur. Bu yüzden embedding-boyutu ayrım gücünü ölçmek için judge prompt'undaki dille aynı türden (kısa, Türkçe, değişiklik özeti) küçük bir temsili küme elle yazıldı — **bu bir üretim verisi değil, boyut-karşılaştırma mikro-benchmark'ıdır**, açıkça böyle işaretlenmiştir (§5).

## 2. Maliyet kontrolü — tahmini çağrı sayısı (GERÇEK, ağsız hesaplandı)

Komut ve **gerçek** çıktı (`2026-07-28`, bu worktree'de — #313 sonrası, EN KOTU DURUM satırı dahil):

```
$ uv run python -m eval.model_secimi_eval
============================================================
  YZ model secimi olcum harness'i (#244) — tahmini cagri sayisi
============================================================
  Judge aday(lar)i        : ['gemini-2.5-flash', 'gemini-2.5-flash-lite']
  Judge korpusu           : curated=12 + backtest=106 = 118 vaka (orneklemesiz — zaten ucuz)
  On-gecitten (cheap_prejudge + esik) gercek modele ULASAN vaka : 8
  Tahmini judge cagrisi   : 8 x 2 model = 16
  Embedding aday boyut(lar)i : [768, 1536, 3072]
  Embedding orneklemi     : 8 cift (12 essiz metin, sentetik — datasets/fixtures'a dokunulmadi)
  Tahmini embedding cagrisi : 3 boyut x 1 batch = 3
  Embedding depolama/indeks (agsiz, pgvector formulu) : 768=3080bayt, 1536=6152bayt, 3072=12296bayt
  TOPLAM tahmini cagri    : 19  (limit: 200)
  EN KOTU DURUM (retry dahil, #257 bulgu 2) : 19 x GEMINI_MAX_RETRIES=3 = 57 gercek HTTP istegi — 'TOPLAM tahmini cagri' MANTIKSAL sayidir, --max-calls
  bunu SINIRLAR ama 429/5xx retry'lari gercek istegi bu kata kadar cikarabilir (olculdu: 8 mantiksal -> 24 gercek, bkz. eval/model-secimi-raporu.md §2).

  GEMINI_API_KEY tanimli DEGIL (.env/ortam) — GERCEK CAGRI YAPILMAYACAK.
  Bu KABUL EDILEBILIR bir sonuctur (#244 maliyet siniri): harness hazir,
  key eklenince `--run` ile calistir. Rapor: eval/model-secimi-raporu.md
```

**Örnekleme gerekmedi:** hem judge hem embedding ekseni **tüm** aday/korpus üzerinde koşacak şekilde tasarlandı çünkü toplam (19) zaten `--max-calls` sınırının (200) çok altında — 118 vakalık tam korpus (curated+backtest) örneklemesiz kullanılabiliyor, çünkü `cheap_prejudge` (#24, aynı-aktör + gürültü-dosyası geçidi) + zorunlu dosya-kesişimi ön-koşulu (#162 pipeline parity) 118 vakanın yalnızca **8**'ini gerçek modele ulaştırıyor (kalan 110'u ağsız/ücretsiz eleniyor — bkz. `eval/kalibrasyon-raporu.md`). Bu sayı hard-code edilmedi; `estimate_real_judge_calls()` fonksiyonu `eval_runner.EvalRunner`'ı gerçek `FakeJudgeAdapter` ile koşturup gerçek modele ulaşan çağrıları SAYAR (`tests/unit/test_model_secimi_eval.py::test_estimate_real_judge_calls_matches_current_corpus` bunu kilitler) — korpus büyürse/değişirse sayı otomatik güncellenir, rapor elle senkron tutulmak zorunda değildir.

**EN KOTU DURUM satırı neden var (#257 bulgu 2 / #313):** "TOPLAM tahmini cagri" **MANTIKSAL** (judge/embedding) çağrıyı sayar, gerçek HTTP isteğini DEĞİL. `ResilientGeminiClient` 429/5xx'te `GEMINI_MAX_RETRIES`'a (varsayılan 3) kadar tekrar dener — yani gerçek istek sayısı mantıksal sayının `GEMINI_MAX_RETRIES` katına kadar çıkabilir (ölçüldü: 8 mantıksal çağrı → 24 gerçek istek, tam kat). `--max-calls` tavanı hâlâ mantıksal sayıya uygulanır (davranış DEĞİŞMEDİ) — yeni satır yalnızca kullanıcının **hangi sayıya imza attığını** açıkça göstermek için eklendi, sessiz bırakılmadı.

## 3. Ölçüm sonuçları — judge yapılandırması

| Model | Precision | Recall | F1 | F0.5 | Net gecikme (s)¹ | Retry bekleme (s)¹ | Hata sayısı¹ | Gerçek çağrı |
|---|---|---|---|---|---|---|---|---|
| `gemini-2.5-flash` (mevcut) | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | 8 (tahmini) |
| `gemini-2.5-flash-lite` (aday) | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | 8 (tahmini) |

¹ **#257 bulgu 1 / #313:** eskiden tek bir "Ort. gecikme" sütunu vardı ve tenacity'nin retry/backoff beklemesini de içeriyordu — 429/5xx sonrası saniyeler süren backoff'u "model hızı" gibi raporluyordu. Artık ikisi **AYRI**: "Net gecikme" yalnızca gerçek model işini, "Retry bekleme" yalnızca backoff'ta harcanan süreyi ölçer (`ResilientGeminiClient.last_call_retry_wait_s` — tenacity `idle_for` istatistiği). "Hata sayısı" gerçek modele ULAŞIP başarısız olan çağrıları sayar; bir model **tamamen** başarısız olursa (`JudgeUnavailableError` tüm denemelerde) satır ÖLÇÜLEMEDİ değil **BAŞARISIZ** olarak işaretlenir (`failed=True` + ham hata mesajı) — sessizce makul görünen bir P/R/F0.5 satırına dönüşmez, ne de ölçümün geri kalanını çökertir (bkz. `eval/model_secimi_eval.py::JudgeModelResult`, `tests/unit/test_model_secimi_eval.py::test_run_judge_model_probe_isolates_failing_model`).

## 4. Ölçüm sonuçları — embedding boyutu

| Boyut | İlgili çift ort. benzerlik | İlgisiz çift ort. benzerlik | Margin | Gecikme (s) | Depolama/indeks (bayt/vektör)² |
|---|---|---|---|---|---|
| `768` (mevcut prod) | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | **3080** (1x) |
| `1536` (aday) | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | **6152** (≈2x) |
| `3072` (aday, maksimum) | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | ÖLÇÜLEMEDİ | **12296** (≈4x) |

² **#257 bulgu 3 / #313 — ÖLÇÜLDÜ (API anahtarı gerekmiyordu):** #244'ün "embedding boyutu için indeks/depolama boyutu" kabul kriteri ne ölçülmüş ne de §5'e yazılmıştı; oysa pgvector'ın kendi depolama formülü (`4 * dimensions + 8 bytes` — `Vector` struct: 4B `vl_len_` + 2B `dim` + 2B `unused` header + boyut başına 4B `float4`) tamamen ağsız hesaplanabilir. Repo içinde ANN indeksi (hnsw/ivfflat) **YOK** — yalnız düz `vector(N)` kolonu (`migrations/versions/c4f1d6a2b8e9_vector_index_table.py`, boyut `settings.GEMINI_EMBEDDING_DIMENSIONS` ile parametrik) — yani bu sayı aynı zamanda "indeks boyutu"nun ta kendisi. Fonksiyon: `eval/model_secimi_eval.py::pgvector_storage_bytes()`, kilitleyen test: `tests/unit/test_model_secimi_eval.py::test_pgvector_storage_bytes_matches_documented_formula`. `uv run python -m eval.model_secimi_eval` çıktısında da (yukarıdaki §2 komut çıktısında) `GEMINI_API_KEY` OLMADAN görünür — "Embedding depolama/indeks (agsiz, pgvector formulu)" satırı.

## 5. ÖLÇÜLEMEYENLER (açık liste — sayı uydurulmadı)

- **Judge kalite farkı** (`gemini-2.5-flash` vs `gemini-2.5-flash-lite`): precision/recall/F0.5 gerçek ayrışması — `GEMINI_API_KEY` yok, hiçbir gerçek judge çağrısı yapılmadı.
- **Judge gecikme farkı**: iki model arası ortalama yanıt süresi — ölçülmedi.
- **Embedding boyutu ayrım gücü**: 768 vs 1536 vs 3072'nin gerçek Gemini `gemini-embedding-001` çıktısında margin farkı — ölçülmedi. (Not: `output_dimensionality` parametresinin bu üç değeri desteklediği model dokümantasyonundan biliniyor — kod zaten bunu `config.py::GEMINI_EMBEDDING_DIMENSIONS` ile destekliyor [`integrations/gemini/client.py`] — ama bu iddia bu oturumda **canlı API'ye karşı doğrulanmadı**.)
- **Embedding gecikme farkı**: boyut arttıkça gerçek Gemini API yanıt süresi değişimi — ölçülmedi.
- **Gerçek üretim korpusunda embedding-boyutu etkisi**: §1'de açıklanan sentetik örneklem gerçek diff-hunk metni değildir; gerçek etkiyi ölçmek üretim `radar.py` akışından örnekleme + ayrı bir (daha maliyetli) çalışma gerektirir — bu PR'ın kapsamı dışında bırakıldı.

## 6. Mevcut varsayılanların statik (ölçüme dayanmayan) gerekçesi

Ölçüm eksikliğinde bile mevcut seçimlerin **rastgele olmadığını** kayda geçirmek için:

- **`GEMINI_MODEL=gemini-2.5-flash`**: proje başından beri (bkz. `tests/unit/test_config.py::test_gemini_model_default`) tüm judge yolları (conflict/query/scope) için tek, tutarlı varsayılan; "flash" ailesi hızlı+ucuz olacak şekilde seçilmiş (gündelik radar pollingi için düşük gecikme önceliği — `docs/eval-metodoloji-devir.md` §1 F0.5/precision odağıyla tutarlı: ucuz model + sıkı rubrik + `cheap_prejudge` ön-geçidi, pahalı bir modeli her çifte çağırmak yerine).
- **`GEMINI_EMBEDDING_DIMENSIONS=768`**: **DEĞİŞTİRİLEMEZ bir mimari bağımlılık** — `config.py` §Radar eşikleri yorumunda ve DIKKAT notunda (#244 görev talimatı) açıkça belirtildiği gibi, pgvector kolon tipi `vector(768)` ve depoda duran **tüm mevcut gömülü embedding'ler** bu boyuta bağlı. Bu boyutu bugün değiştirmek şema migrasyonu + tüm geçmiş embedding'lerin yeniden hesaplanmasını gerektirir — bu PR'ın amacı **tam olarak bunu yapmamak**, yalnızca seçimi ölçüp gerekçelendirmektir (§5'teki ölçülemeyen kısım, ileride bir migrasyon kararı gerekirse referans olsun diye bilerek harness olarak bırakıldı).

## 7. Nasıl tekrar çalıştırılır (key eklenince)

```bash
# 1) .env'e GEMINI_API_KEY ekle (bkz. .env.example)
# 2) Tahmini tekrar doğrula (agsiz):
make eval-model-secimi
# 3) Gerçek ölçümü çalıştır (yalnızca tahmini <=200 VE key varsa ilerler):
uv run python -m eval.model_secimi_eval --run
# 4) eval/model-secimi-sonuclar.json üretilir; §3/§4 tablolarını ve §5'i
#    bu sayılarla GÜNCELLE (ÖLÇÜLEMEDİ satırlarını gerçek sayılarla değiştir).
```

## 8. Kaynaklar

- Harness: [`eval/model_secimi_eval.py`](model_secimi_eval.py) · testler: [`tests/unit/test_model_secimi_eval.py`](../tests/unit/test_model_secimi_eval.py)
- İlgili maliyet/gate mantığı: [`eval/gate.py`](gate.py), [`eval/provider_eval.py`](provider_eval.py) (aynı desen — provider yerine judge-model/embedding-boyutu ekseni)
- Kalibrasyon bağlamı (neden yalnızca 8/118 vaka gerçek modele ulaşıyor): [`eval/kalibrasyon-raporu.md`](kalibrasyon-raporu.md)
- Karar kaydı taslağı: bu PR'ın gövdesinde (PO `internal/grup54_karar_logu.md`'ye D-NN olarak işleyecek).
