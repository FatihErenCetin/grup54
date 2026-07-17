# Eval Metodolojisi ve Kalibrasyon Şerhi (Esma'ya Devir)

> **Bağlam:** Enes'in hazırladığı `eval_runner` (#28) ve `sweep` (#29) altyapısı **PR #161 ile geliyor**. Kalibrasyon süreci, ürün vizyonunu doğrudan etkileyen metodolojik kararlar gerektiriyor. Bu belgedeki şerhler, eval/kalibrasyon süreçlerini (#18) devralacak olan **Esma** için kılavuz niteliğindedir. *(Rev: F0.5 bu PR'da koda eklendi + D-38 uyumu + metodoloji şerhleri — Fatih, review-fix.)*

## 1. F0.5 Metriği Neden Şart?

Çakışma radarının 1 numaralı teknik riski **"False Positive" (Yanlış Alarm) yorgunluğudur**. Eğer radar çok fazla gürültü yaparsa, geliştirici ekibi ürünü kapatır veya uyarıları görmezden gelmeye başlar.

Bu nedenle standart **F1 Skoru** (Precision ve Recall'a eşit ağırlık veren metrik) bizim kullanım senaryomuz için yeterli değildir. Radarımızda **Precision (Doğruluk)**, Recall'dan (Kapsayıcılıktan) katbekat daha değerlidir. Olası bir çakışmayı kaçırmak (False Negative), olmayan bir çakışma yüzünden geliştiriciyi rahatsız etmekten (False Positive) çok daha kabul edilebilirdir.

**Durum:** ✅ Bu PR'da uygulandı — `_compute_metrics` artık `f05` hesaplıyor
(formül: `1.25·P·R / (0.25·P + R)`), sweep "best" seçimi **F0.5-birincil**
(`eval/sweep.py`), `sweep_results.json` yeniden üretildi.
**Görev (Esma):** operasyon noktasını `sweep_results.json`'daki **F0.5 tablosundan** seç ve seçimini aşağıdaki §5 şerhleriyle birlikte raporla.

## 2. Jaccard ve Similarity Eşiklerinin Yorumlanması

- **Backtest Verisi (sim=None):** Backtest corpus'u gerçek git tarihinden çekilir. Bu veride `sim` metriği başta hesaplanmamıştır. `sweep.py` bu verileri test ederken `sim=None` olduğu için kural tabanlı judge (FakeJudgeAdapter) üzerinden "dosya kesişimi (overlap)" ağırlıklı karar verir.
- Gerçek NLP tabanlı `EmbeddingsPort` entegre olduğunda, semantic similarity değerleri dolacak ve `min_similarity` eşiğinin sweep'teki önemi artacaktır. Threshold sweep yaparken, kuratörlü corpus'taki yüksek `sim` skorlarının gerçekçi olup olmadığını izlemelisin.

## 3. Aynı-Yazar (Same Author) Filtrelemesi — ⚠️ D-38 ile revize

"Geliştiricinin kendi işiyle çakışması uyarıya değer değildir" **eski varsayımdı** ve
backtest verisi bunu çürüttü: repo tarihimizdeki 3 gerçek çakışmanın **2'si aynı
kişinin iki branch'i arasında** (pr88↔pr89, pr135↔pr137) — tek kişi + çok branch/ajan
tam hedef senaryomuz. **PO kararı D-38 (16 Tem):** aynı-yazar çiftleri tamamen
susturulmak yerine **low-severity uyarıya** dönecek; implementasyon **#164** (S3).

Kalibrasyon için pratik sonuç:
- **S2 operasyon noktası:** mevcut üretim davranışı hâlâ aynı-yazar-eleme olduğundan
  eşikler **aynı-yazar HARİÇ** tablosundan seçilebilir — ama rapora "D-38/#164 sonrası
  yeniden değerlendirilecek" şerhi düşülmeli.
- `sweep.py` her iki ekseni de koşuyor (`include_same_author_axis=True`) — #164
  geldiğinde DAHİL tablosu doğrudan kullanılabilir olacak.

## 4. Gri Bölge Etiketlemesi

- `eval/datasets/backtest-grup54-gri.jsonl` dosyasında, git seviyesinde çakışmayan ama ortak dosyalara dokunulan *potansiyel semantik çakışmalar* var.
- Bu dosya otomatik tüketilmez. Bunlar "label_beklemede"dir.
- İnsan gözüyle (senin ve ekibin kalanıyla) incelenip `conflict` veya `no_conflict` olarak manuel etiketlendikten sonra `backtest-grup54-el-etiketli.jsonl` dosyasına taşınmalıdır. Bu sayede recall'u artıracak gerçek vakalar kazanmış oluruz.

## 5. Metodoloji Şerhleri (rakamları raporlarken MUTLAKA birlikte ver)

Kaynak: PR #161 review doğrulaması (ölçümler tekrarlanabilir: `make eval-run` / `make eval-sweep`).

1. **In-sample:** Eşikler aynı 118 vakada seçilip aynı vakalarla raporlanıyor —
   holdout/doğrulama seti yok. Skorlar "bu örneklemde" okunmalı, genelleme iddiası değil.
2. **n=1 tuzağı:** Aynı-yazar HARİÇ modda backtest'in pozitif sınıfı **tek vakaya**
   düşüyor (3 conflict'in 2'si aynı-yazar) — o moddaki F1/F0.5=1.0'ın istatistiksel
   gücü yok denecek kadar az; **başlık rakamı olarak kullanılamaz**.
3. **Eşikler FP silmiyor:** 60 grid noktasının 60'ında da precision=1.0/FP=0 —
   sweep'in asıl bulgusu, mevcut korpustaki FP işini eşiklerin değil gate'lerin
   (aynı-aktör + gürültü-dosyası) yaptığı; eşik artışı yalnız recall düşürüyor.
4. **FakeJudge kalibrasyonu:** Ölçüm `FakeJudgeAdapter` ile — gate+eşik katmanı
   üretimle birebir aynı, ama kapıyı geçip LLM'e düşen vakalarda gerçek Gemini
   judge ayrışabilir. Canlı judge'la spot-check önerilir (#18 kapsamında).
