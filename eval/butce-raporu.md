# Çağrı-Sayısı Bütçesi Raporu (#256) — precision-gate'in maliyet ikizi

> **Kanıt:** çıktı = `eval/butce_eval.py` (sabit fixture + sayaçlı sahte port'lar) + bu rapor. Tekrarlanabilir: `make eval-butce` (veya `make eval`). CI: `.github/workflows/ci.yml` → "Eval cagri-sayisi butcesi (#256)" adımı + `tests/unit/test_butce_eval.py` (`make test` içinde).

## Boşluk neydi

`eval/` **doğruluğu** (precision/recall) titizlikle ölçüyordu ama **kaynak tüketimini** hiçbir yerde ölçmüyordu. Bunun bedeli aynı gün üç kez ödendi:

| Ölçülmeyen soru | Canlıda çıkan sonuç | Issue |
|---|---|---|
| Judge kaç çağrı yapıyor? | 131 çağrı / soğuk `/radar` (kota 20/gün) | #255 |
| Judge ne kadar sürüyor? | 129 sn — sıralı döngü, CPU %1 | #254 |
| Judge tükenince ne oluyor? | 19 gerçek tespit → 131 sahte tespit | #252 |

## Sonuç (kabul kriteri #4)

**Bu korpuste bir `/radar` = 5 judge · 5 embed · 11 GitHub çağrısı** (10 olay, 5 dosya-kesişim çifti).

| Sayaç | Gözlenen | Bütçe (`eval/butce_eval.py`) |
|---|---|---|
| Judge çağrısı | 5 | `MAX_JUDGE_CALLS = 6` |
| Embed çağrısı | 5 | `MAX_EMBED_CALLS = 6` |
| GitHub çağrısı | 11 | `MAX_GITHUB_CALLS = 12` |

Bütçe payı bilinçli olarak **dar** tutuldu (gözlenenin +1'i) — asıl amaç güvenli bir tampon değil, sessiz bir regresyonun hemen kırmızı vermesi.

## Metodoloji

- **Fixture, canlı repo değil:** sayı deterministik olmalı — canlı GitHub'da olay sayısı her gün değişir, test flaky olurdu. Aynı girdi → aynı maliyet. Fixture 10 olaydan oluşur: 5 küme (`radar`/`judge`/`scope`/`board`/`query`), her kümede 2 olay, kümeye özgü **bir** dosyayı paylaşıyor. Kümeler arası dosya kesişimi yok → `file_overlap_candidates` tam olarak 5 aday üretiyor (C(10,2)=45 çiftin geri kalan 40'ı dosya-kesişimi filtresinde eleniyor).
- **`RadarService.collect()`'in gerçek yolu kullanılır** (#162'nin dersi — eval üretimin geçtiği kapılardan geçmeli, `file_overlap_candidates`/`semantic_hunk_candidates` gibi alt-fonksiyonları ayrı ayrı çağırıp kestirme yapmaz). Sayaçlar `GitHubPort`/`EmbeddingsPort`/`JudgePort`'a **sarmalayıcı** olarak enjekte edilir; `RadarService`'in kendisi hiç değişmez, yalnız gözlenir.
- **Operasyon noktası = kalibre üretim ayarları** (`config.py` ile birebir): `RADAR_MIN_JACCARD=0.0`, `RADAR_MIN_SIMILARITY=0.0`, `RADAR_WINDOW_DAYS=14` benzeri değerler; `judge_concurrency=1` yalnızca sayaç artırımını thread-race'ten arındırmak için (eşzamanlılığın kendisi zaten `tests/unit/test_radar.py`'deki #254 testlerinde ayrıca doğrulanıyor).

## Ölçeklenme (kabul kriteri #5) — kuadratik uyarısı

Aday sayısı **olay sayısında karesel**dir: `file_overlap_candidates` `itertools.combinations(events, 2)` üzerinden çalışır → C(n,2) çift. `RADAR_WINDOW_DAYS` ve `GITHUB_BACKFILL_LIMIT` ikisi de penceredeki olay sayısını (n) belirler:

- Pencereyi **yarıya** indirmek (`RADAR_WINDOW_DAYS` veya etkin `n`) → aday sayısını **yaklaşık dörtte bire** düşürür (C(n/2,2) ≈ C(n,2)/4 büyük n için).
- Bu fixture'daki 5 çift/10 olay canlı `/radar`'ın küçük, kontrollü bir örneğidir. Gerçek `RADAR_WINDOW_DAYS=14` + `GITHUB_BACKFILL_LIMIT=50` penceresinde birikmiş onlarca olayda aynı büyüme kanunu #255'teki 131 çağrıya kadar çıkıyordu — 10 olaydan ~50 olaya çıkmak (5x), aday sayısını ~25x artırır (C(50,2)=1225 vs C(10,2)=45), bu da judge/embed çağrı sayısını orantılı büyütür.
- Pratik sonuç: kota/gecikme sorunu yaşandığında ilk çekilecek kol `RADAR_WINDOW_DAYS`/`GITHUB_BACKFILL_LIMIT`'i düşürmektir — dosya-kesişimi/benzerlik eşiklerini sıkılaştırmak (`RADAR_MIN_JACCARD`/`RADAR_MIN_SIMILARITY`) precision'ı riske atarken (`eval/kalibrasyon-raporu.md` §"HARİÇ" uyarısı), pencereyi daraltmak yalnız *hacmi* düşürür, *ölçütleri* değiştirmez.

## Mutasyon doğrulaması

`radar.py`'deki dosya-kesişimi filtresi (`if not overlap: continue`) geçici olarak kaldırılıp `make test`/`pytest tests/unit/test_butce_eval.py` koşuldu:

- **Öncesi (doğru kod):** judge=5, embed=5, github=11 — bütçe içinde, yeşil.
- **Mutasyon (filtre kaldırıldı):** judge=**45** (=C(10,2)), embed=5 (değişmedi — spurious çiftlerin dosya kesişimi boş, embed edilecek hunk yok), github=11 (değişmedi — `get_diff` benzersiz olay/branch başına önbelleklendiği için aday sayısından bağımsız). `test_real_fixture_passes_budget_gate` **kırmızı** verdi: `judge çağrısı 45 > bütçe 6`.
- Mutasyon geri alındı (`git diff` boş) — bu, kalıcı bir kod değişikliği değil, testin gerçekten yakaladığını kanıtlayan bir doğrulama adımıdır.

Bu, kabul kriterindeki senaryonun birebir doğrulanmasıdır: "aday sayısı C(n,2)'ye fırlar → bütçe testi KIRILMALI." Öncesinde böyle bir değişiklik tüm doğruluk testlerini yeşil bırakıp yalnızca faturayı patlatarak **sessizce** geçerdi; artık `make test` içinde kırmızı verir.

## Bilinen sınırlamalar

- Bütçe sabitleri (`MAX_JUDGE_CALLS` vb.) bu **sabit fixture'a** göre kalibre edildi — canlı `/radar`'ın 131 çağrılık gerçek olay hacmini birebir simüle etmez (determinizm için bilinçli tercih, yukarıdaki "Metodoloji" bölümüne bakın). Gerçek hacimdeki mutlak tavan için ayrı bir canlı/staging ölçümü (`eval/provider_eval.py`'nin `--run` bayrağına benzer, ağ gerektiren) takip konusu olarak bırakılıyor.
- `FakeJudgeAdapter`/`HashEmbeddings` kural-tabanlı ve offline'dır — gerçek Gemini/embedding sağlayıcısının çağrı-başına gecikmesini veya olası retry/backoff çağrılarını (ki bunlar da faturayı etkiler) ölçmez; yalnız **çağrı sayısını** ölçer (issue #256'nın odağı budur, süre #254'ün konusu).
