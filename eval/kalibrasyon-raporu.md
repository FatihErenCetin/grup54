# Kalibrasyon Raporu (#18) — Radar eşikleri

> **Kontrat:** çıktı = kalibre eşikler (`config.py` `RADAR_MIN_JACCARD`/`RADAR_MIN_SIMILARITY`) + bu rapor (`docs/sprint2-kontratlar.md` #18 satırı). Kaynak: `eval/sweep_results.json` (60 kombinasyon, #29) + `eval/eval_runner.py` (#28). Tekrarlanabilir: `make eval-run` / `make eval-sweep` (veya `make eval`).

## Operasyon noktası

**`RADAR_MIN_JACCARD = 0.0`, `RADAR_MIN_SIMILARITY = 0.0`** — mevcut `config.py`/`.env.example` varsayılanlarıyla aynı. Bu bir placeholder değil, **kalibrasyon sonucu**: sweep grid'indeki 60 kombinasyonun **hiçbiri** 0.0/0.0'a göre precision'ı artırmıyor, yalnızca recall düşürüyor (aşağıda §3). Yani mevcut korpuste false-positive'i önleyen katman jaccard/similarity eşikleri değil, **gate (aynı-aktör/gürültü-dosyası) + judge**'dur.

## Sonuçlar (0.0/0.0, `make eval-run`)

| | Precision | Recall | F1 | F0.5 | TP | FP | FN | TN | n |
|---|---|---|---|---|---|---|---|---|---|
| **Genel (aynı-yazar DAHİL)** | 1.0000 | 0.7500 | 0.8571 | 0.9375 | 6 | 0 | 2 | 110 | 118 |
| Kuratörlü (#26) | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 5 | 0 | 0 | 7 | 12 |
| Backtest (#27) | 1.0000 | 0.3333 | 0.5000 | 0.7143 | 1 | 0 | 2 | 103 | 106 |
| **Genel (aynı-yazar HARİÇ)** | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 6 | 0 | 0 | 80 | 86 |
| Kuratörlü, hariç | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 5 | 0 | 0 | 6 | 11 |
| Backtest, hariç | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1 | 0 | 0 | 74 | 75 |

**Headline rakam = Genel (aynı-yazar HARİÇ), F0.5 = 1.0** — mevcut üretim davranışı (`gate.py`: `a.actor == b.actor` → otomatik geçit) zaten aynı-yazar çiftlerini eledigi için bu, canlıdaki gerçek performansı yansıtıyor.

## ⚠️ "HARİÇ = 1.0" ne anlama GELMİYOR

Aynı-yazar HARİÇ modundaki mükemmel skor bir **çözüm değil, ölçüm kapsamının daraltılması**. "DAHİL" modundaki 2 FN'nin ikisi de aynı-yazar çifti (`backtest-pr88-pr89-icmerge`, `backtest-pr135-pr137-icmerge` — Fatih'in kendi pr88↔pr89'u ve Esma'nın pr135↔pr137'si). HARİÇ modu bu iki zor vakayı **elemekle** mükemmel skora ulaşıyor, doğru sınıflandırarak değil. Bu tam olarak **D-38** kararının çıkış noktası: "tek kişi + çok branch" backtest'teki 3 gerçek çakışmanın 2'si — radar bunlara bilerek susuyor. İmplementasyon (#164, S3) bu boşluğu kapatana kadar bu rapor bu gerçeği gizlemez.

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
