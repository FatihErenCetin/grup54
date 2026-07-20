# Scope-drift kalibrasyon raporu (#31)

## Operasyon amacı

Scope bekçisi ekipte gereksiz alarm üretirse kısa sürede görmezden gelinir. Bu
yüzden birincil metrik **alert precision**: gerçek `in_scope` işe
`drift/non_goal_violation` demek false-positive (FP) sayılır. Üç sınıfın doğru
ayrımını ayrıca accuracy ile izliyoruz.

Kanonik komut:

```text
make scope-eval
```

## Korpus ve sonuç (20 Temmuz 2026)

`eval/datasets/scope-corpus.json` toplam 18 elle etiketli vaka taşır:

- 8 `in_scope`
- 5 `non_goal_violation`
- 5 `drift`

Kalibre offline sonuç:

| Metrik | Sonuç | Kapı |
|---|---:|---:|
| Üç-sınıf accuracy | 1.0000 | ≥ 0.80 |
| Alert precision | 1.0000 | ≥ 0.95 |
| Alert recall | 1.0000 | raporlanır |
| False-positive | 0 | tek FP precision kapısını kırar |

İlk koşum Jaccard retrieval ile `accuracy=0.5556`, `precision=0.6250`, `FP=6`
verdi. Uzun task metni kısa scope maddesini gereksiz cezalandırdığı için lexical
retrieval overlap katsayısına çevrildi. Path'lerin `GitHub App` gibi metinlerle
yalancı eşleşmesi görülünce dosyalar karar metninden ayrılıp yalnız
`Signals.files` olarak tutuldu. Son skor dağılımında en düşük doğru kapsam
eşleşmesi `0.1667`, en yüksek gerçek drift eşleşmesi `0.1429`; fake judge eşiği
bu ölçülen boşluk içinde `0.16` olarak sabitlendi.

## Dürüst sınırlar

- Bu korpus küçük ve in-sample'dır; eşik genellenebilirlik iddiası değildir.
- CI/fake yol lexical retrieval kullanır. Gerçek wiring embeddings enjekte
  ettiğinde aday sıralaması semantic skoru da hesaba katar.
- Gerçek Gemini yapılandırılmış cevap yolu unit-testte stub client ile
  doğrulandı; canlı Gemini spot-check henüz yapılmadı.
- Korpus büyürken özellikle benzer kelime kullanan ama kapsam dışı işler
  (IDE/mobile/çok-repo) eklenmeli; precision kapısı aşağı çekilmemeli.
