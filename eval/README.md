# eval/ — kalibrasyon & backtest verisi

> **Neden var:** 1 numaralı teknik risk = false-positive radar (gürültülüyse ekip kapatır). Eşikler tahminle değil **ölçümle** ayarlanır (A4 kararı); bir dedektör, eval kabul edilebilir FP gösterene dek "bitmiş" sayılmaz (`docs/gelistirme-dongusu.md` DONE kapısı). Veri sözleşmesi: `docs/sprint2-kontratlar.md` **Ek C**.

## İki dataset, tek şema (`ConflictCase`)

| Dataset | Kaynak | Ne test eder |
|---|---|---|
| `tests/fixtures/conflict_corpus.jsonl` (#26) | kuratörlü / el yapımı | **bilinen kenar durumlar** — recall'un alt sınırı; `sim` elle atanır (embeddings'siz geçit testi) |
| `eval/datasets/backtest-grup54.jsonl` (#27) | grup54'ün **gerçek git tarihi** | **gerçekçi dağılım** — precision'a gerçekçi taban; `sim=None` (dedektör hesaplar — veri sızıntısı yok) |

`eval/datasets/backtest-grup54-gri.jsonl` = **gri bölge**: git'e göre temiz merge ama ortak dosyalara dokunulmuş → potansiyel *semantik* çakışma. Otomatik etiket verilmez (`label_beklemede`), **#28 v1 tüketmez**; insan etiketledikçe ana dosyaya taşınır.

## Üretim & determinizm (iki aşama)

```
make eval-dataset          # = python3 eval/backtest/build_dataset.py
```

1. **Snapshot** (insan, ara sıra): `gh pr list --state merged` metadata'sı → `eval/backtest/pr-snapshot.json`, **commit'lenir**. Dataset'in zaman pini budur.
2. **Build** (script, tekrar üretilebilir): yalnız snapshot + yerel git objeleri; ağ yok, rastgelelik yok, `LC_ALL=C` → aynı snapshot = **bit-bit aynı çıktı** (test: `test_builder_deterministik_*`).

Etiketleme mantığı ve iç-merge madenciliği (çözülüp gömülmüş conflict'lerin geri kazanımı) `build_dataset.py` docstring'inde.

## Bilinen sınırlamalar (dürüst mod)

- **Ground truth = git'in metinsel conflict'i.** Metinsel olarak temiz ama *mantıksal* çakışan işleri pozitif sayamayız → bu dataset'e karşı ölçülen **recall iyimserdir** (dedektörün hedefi git'ten geniş). Gri dosya + #26 korpusu bu boşluğu kapatmak içindir.
- **Pozitif örnek az** (~4): 3 haftalık genç repo; ekip büyüdükçe/`pr-snapshot.json` tazelendikçe artar. Recall ölçümünde #26 ile birlikte değerlendirin.
- **Negatifler kolay ağırlıklı:** ayrık-dosya çiftleri dosya-kesişim geçidiyle bedavaya doğrulanır; asıl ayrıştırıcı metrik gri bölge + judge aşamasındadır (#29 sweep'te katmanlayın — `note` alanındaki `[ayni-yazar]`/`[ic-merge]` etiketleri filtre içindir).
- Aynı-yazar çiftleri **dahildir** (çakışma fiziği yazar tanımaz); ürün semantiği (aktörler-arası uyarı) runner katmanında filtrelenebilir.
