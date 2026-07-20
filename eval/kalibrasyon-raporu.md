# Kalibrasyon Raporu (#18) — Radar eşikleri

> **Kanıt:** çıktı = kalibre eşikler (`config.py` `RADAR_MIN_JACCARD`/`RADAR_MIN_SIMILARITY`) + bu rapor (#18 kabul kriteri). Kaynak: `eval/sweep_results.json` (60 kombinasyon, #29) + `eval/eval_runner.py` (#28). Tekrarlanabilir: `make eval-run` / `make eval-sweep` (veya `make eval`).

## Operasyon noktası

**`RADAR_MIN_JACCARD = 0.0`, `RADAR_MIN_SIMILARITY = 0.0`** — mevcut `config.py`/`.env.example` varsayılanlarıyla aynı. Bu bir placeholder değil, **kalibrasyon sonucu**: sweep grid'indeki 60 kombinasyonun **hiçbiri** 0.0/0.0'a göre precision'ı artırmıyor, yalnızca recall düşürüyor (aşağıda §3). Yani mevcut korpuste false-positive'i önleyen katman jaccard/similarity eşikleri değil, **gate (aynı-aktör/gürültü-dosyası) + judge**'dur.

## Sonuçlar (0.0/0.0, `make eval-run`)

| | Precision | Recall | F1 | F0.5 | TP | FP | FN | TN | n |
|---|---|---|---|---|---|---|---|---|---|
| **Genel (aynı-yazar DAHİL)** | 1.0000 | 0.6250 | 0.7692 | 0.8929 | 5 | 0 | 3 | 110 | 118 |
| Kuratörlü (#26) | 1.0000 | 0.8000 | 0.8889 | 0.9524 | 4 | 0 | 1 | 7 | 12 |
| Backtest (#27) | 1.0000 | 0.3333 | 0.5000 | 0.7143 | 1 | 0 | 2 | 103 | 106 |
| **Genel (aynı-yazar HARİÇ)** | 1.0000 | 0.8333 | 0.9091 | 0.9615 | 5 | 0 | 1 | 80 | 86 |
| Kuratörlü, hariç | 1.0000 | 0.8000 | 0.8889 | 0.9524 | 4 | 0 | 1 | 6 | 11 |
| Backtest, hariç | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1 | 0 | 0 | 74 | 75 |

**Binary headline = Genel (aynı-yazar DAHİL), F0.5 = 0.8929.** #164 sonrası üretim farklı branch'lerdeki aynı-yazar çiftlerini aday bırakır; `gate.py` bunları Gemini'ye göndermeden `low` uyarıya çevirir. Binary eval yalnız `med/high` sonuçları conflict saydığı için bu uyarılar TP/FP sayılarını değiştirmez. Üretim aday akışını kullanan ayrı uyarı ölçümünde aynı-yazar gerçek çakışma coverage'ı **2/2**, negatif düşük uyarı sayısı **0**'dır.

`#162` öncesinde eval, `semantic-only-no-file-overlap` vakasını gerçek radarın zorunlu dosya-kesişimi kapısından geçirmeden doğrudan judge'a veriyordu. Pipeline paritesi sonrası bu vaka dürüstçe FN sayılıyor; genel TP `6→5`, FN `2→3` ve F0.5 `0.9375→0.8929`. Precision/FP değişmedi (`1.0/0`) ve sweep'in önerdiği operasyon noktası yine `0.0/0.0`.

## ⚠️ "HARİÇ = 1.0" ne anlama GELMİYOR

Aynı-yazar HARİÇ modundaki yüksek skor bir **çözüm değil, ölçüm kapsamının daraltılması**. "DAHİL" modundaki 3 FN'nin ikisi aynı-yazar çifti (`backtest-pr88-pr89-icmerge`, `backtest-pr135-pr137-icmerge` — Fatih'in kendi pr88↔pr89'u ve Esma'nın pr135↔pr137'si); üçüncüsü dosya-kesişimi olmayan kuratörlü vakadır. HARİÇ modu iki aynı-yazar vakasını **eleyerek** F0.5=0.9615'e ulaşıyor, doğru sınıflandırarak değil. D-38/#164 bu iki vakayı binary conflict'e yükseltmeden düşük-severity uyarı olarak görünür kılar; bu yüzden binary recall `0.6250` kalırken üretimdeki gerçek çakışma warning coverage'ı `0/2 → 2/2` olur.

## Metodoloji şerhleri (bkz. `docs/eval-metodoloji-devir.md` — MUTLAKA birlikte oku)

1. **In-sample:** eşikler aynı 118/86 vakada seçilip aynı vakalarla raporlandı — holdout yok. "Bu örneklemde" okunmalı, genelleme iddiası değil.
2. **n=1 tuzağı:** Backtest-only kırılımda (HARİÇ) pozitif sınıf **n=1** (yukarıdaki tablo) — istatistiksel gücü yok, tek başına kanıt sayılmaz. Kuratörlü (#26) n=5 ile bunu kısmen dengeliyor ama o da küçük ve elle seçilmiş.
3. **Eşikler FP silmiyor:** Sweep'in 60 noktasının **60'ında da** precision=1.0/FP=0 (`eval/sweep_results.json`) — jaccard/similarity'yi yükseltmenin tek etkisi recall'u düşürmek. Asıl FP bariyeri gate+judge katmanında.
4. **FakeJudge kalibrasyonu:** Ölçüm `FakeJudgeAdapter` (kural-tabanlı) ile yapıldı — gate+eşik katmanı üretimle birebir aynı, ama kapıyı geçip gerçek Gemini'ye düşen vakalarda judge ayrışabilir. Spot-check aşağıda.

## Gerçek Gemini judge spot-check

Kapsam dışı bırakıldı — `GEMINI_API_KEY` gerektirir, ayrı küçük bir takip notu olarak bırakılıyor (bu rapor FakeJudge'a dayandığını §4'te açıkça beyan ediyor).

## Gri-bölge etiketleme

`eval/datasets/backtest-grup54-gri.jsonl` (3 vaka) bu PR'ın kapsamı dışında — insan-yargısı + ekip görüşü gerektiriyor, ayrı küçük iş olarak bırakıldı (`eval/README.md` §"Gri bölge" ilkesine uygun).

## Sonuç

`RADAR_MIN_JACCARD=0.0` / `RADAR_MIN_SIMILARITY=0.0` kalibre edilmiş ve kanıtlanmış değerlerdir; DoD'nin "kabul edilebilir false-positive" şartı bu korpuste **precision=1.0** ile karşılanıyor (§2 uyarılarıyla birlikte okunmak kaydıyla). CI precision-gate (#30) bu rapordaki `make eval-run` çıktısını referans alabilir.
