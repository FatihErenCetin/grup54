# Eval Metodolojisi ve Kalibrasyon Şerhi (Esma'ya Devir)

> **Bağlam:** Enes'in hazırladığı `eval_runner` (#28) ve `sweep` (#29) altyapısı merge edilerek devreye alındı. Ancak kalibrasyon süreci, ürün vizyonunu doğrudan etkileyen metodolojik kararlar gerektiriyor. Bu belgedeki şerhler, eval/kalibrasyon süreçlerini devralacak olan **Esma** için kılavuz niteliğindedir.

## 1. F0.5 Metriği Neden Şart?

Çakışma radarının 1 numaralı teknik riski **"False Positive" (Yanlış Alarm) yorgunluğudur**. Eğer radar çok fazla gürültü yaparsa, geliştirici ekibi ürünü kapatır veya uyarıları görmezden gelmeye başlar.

Bu nedenle standart **F1 Skoru** (Precision ve Recall'a eşit ağırlık veren metrik) bizim kullanım senaryomuz için yeterli değildir. Radarımızda **Precision (Doğruluk)**, Recall'dan (Kapsayıcılıktan) katbekat daha değerlidir. Olası bir çakışmayı kaçırmak (False Negative), olmayan bir çakışma yüzünden geliştiriciyi rahatsız etmekten (False Positive) çok daha kabul edilebilirdir.

**Görev (Esma):**
- `eval/eval_runner.py` içindeki `_compute_metrics` fonksiyonuna **F0.5 skoru** eklenmeli.
- Formül: `(1 + 0.5^2) * (precision * recall) / ((0.5^2 * precision) + recall)`
- Eşik (Threshold) sweep aramalarında "En iyi F1" yerine **"En iyi F0.5"** optimize edilmelidir.

## 2. Jaccard ve Similarity Eşiklerinin Yorumlanması

- **Backtest Verisi (sim=None):** Backtest corpus'u gerçek git tarihinden çekilir. Bu veride `sim` metriği başta hesaplanmamıştır. `sweep.py` bu verileri test ederken `sim=None` olduğu için kural tabanlı judge (FakeJudgeAdapter) üzerinden "dosya kesişimi (overlap)" ağırlıklı karar verir.
- Gerçek NLP tabanlı `EmbeddingsPort` entegre olduğunda, semantic similarity değerleri dolacak ve `min_similarity` eşiğinin sweep'teki önemi artacaktır. Threshold sweep yaparken, kuratörlü corpus'taki yüksek `sim` skorlarının gerçekçi olup olmadığını izlemelisin.

## 3. Aynı-Yazar (Same Author) Filtrelemesi

Ürün semantiği açısından bir geliştiricinin "kendi işiyle çakışması" uyarıya değer bir durum değildir. Çakışma fiziği yazar tanımasa da, radarın amacı **başkalarının** paralel eylemlerinden haberdar etmektir.
- `sweep.py`'de `include_same_author_axis=True` olarak koşuyoruz.
- Kalibrasyon sonucu seçilecek nihai config parametrelerinde, `RADAR_MIN_JACCARD` ve `RADAR_MIN_SIMILARITY` değerleri **aynı-yazar HARIÇ (exclude_same_author=True)** tablosuna göre seçilmelidir.

## 4. Gri Bölge Etiketlemesi

- `eval/datasets/backtest-grup54-gri.jsonl` dosyasında, git seviyesinde çakışmayan ama ortak dosyalara dokunulan *potansiyel semantik çakışmalar* var.
- Bu dosya otomatik tüketilmez. Bunlar "label_beklemede"dir.
- İnsan gözüyle (senin ve ekibin kalanıyla) incelenip `conflict` veya `no_conflict` olarak manuel etiketlendikten sonra `backtest-grup54-el-etiketli.jsonl` dosyasına taşınmalıdır. Bu sayede recall'u artıracak gerçek vakalar kazanmış oluruz.
