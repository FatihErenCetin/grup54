---
type: decision
id: D-64
title: "Graph ek görünüm modları (#130) S3 non-goal'undan kapsama alındı — ve treemap'in sessiz kayması kayda geçti"
date: "2026-07-30"
status: accepted
---

# D-64 — Graph'ın kalan iki modu kapsama alındı

## Karar

`.harness/scope/sprint-3.md` **non_goals** listesindeki

> Graph ek görünüm modları (git ağacı · güç-yönlü · treemap) — #130, ayrıca S3-stretch etiketli

maddesi **kaldırıldı**; #130'un dört modu da (ısı matrisi · treemap · güç-yönlü ·
git ağacı) Sprint 3 **goals**'una alındı. Karar sahibi: PO (Fatih Eren Çetin),
30 Temmuz 2026. Gerekçe: graf sayfası tanıtım videosunun kahraman karesi ve iki
boş sekme yerine dört çalışan mod isteniyor.

## Asıl bulgu: kayma zaten olmuştu, kaydı yoktu

Bu kaydı yazarken ortaya çıkan şey karardan daha önemli:

**Treemap, non-goal'da yazılı olduğu hâlde çoktan yapılmış ve sevk edilmişti.**
Yani donmuş kapsam ile sevk edilen ürün arasındaki fark bugün başlamadı; bir
kez **sessizce** oldu ve hiçbir yere yazılmadı. Kapsam metni "yapılmayacak"
derken ürün onu çoktan yapmıştı.

Bu tam olarak Ensemble'ın yakalamak için var olduğu şeydir (scope-drift), ve
kendi deponuzda olması iddianın zayıflığı değil **testi**dir: kayma her ekipte
olur, fark edilip **kaydedilmesi** olmaz. Bugünkü fark — kayma yine oldu ama
bu sefer kararın kendisi, gerekçesi ve daraltılmış kabul kriterleri yazılı.

Ders (D-63 ile aynı kök): *söylediğimiz ile ölçtüğümüz arasındaki fark, bir
belge güncellenmediği için değil, güncellenmesi kimsenin işi olmadığı için
büyür.* Kapsam dosyasını düzenlemek **audit olayıdır** — bu commit o olaydır.

## Gate'in iki gerekçesi neydi, nasıl aşıldı

`GraphPage.tsx` iki modu bilinçli gate'lemişti ve gerekçeleri kodda yazılıydı.
İkisi de **delinmeden**, gerekçenin kendisi çözülerek aşıldı:

| Gate gerekçesi | Ne yapıldı |
|---|---|
| **Güç-yönlü** "layout için yeni kütüphane (d3-force) gerektirir; bu depoda bağımlılık ekleme yasağı var" | Kütüphane **eklenmedi**. Fruchterman-Reingold (1991) `src/frontend/src/lib/grafYerlesimi.ts` içine ~70 satır olarak yazıldı. Bağımlılık yasağı **korundu**; `package.json` değişmedi. |
| **Git ağacı** "şerit/dirsek çizimi gerçek commit DAG'ı (`parent_sha`) ister; kontrat taşımıyor → uydurma ağaç çizmektense gate'li bırakıyoruz" | Bu gerekçe **hâlâ geçerli ve kabul edildi**: gerçek DAG **çizilmiyor**. Çizilen, kontratın taşıdığı bilgi: dal başına şerit + zaman sıralı olaylar. Ebeveyn–çocuk oku yok. |

## Daraltılan kabul kriteri (#130'un orijinaline göre)

#130 "4 mod tek sekme ailesinde" diyordu; korundu. Ama şu **düşürüldü**:

- ❌ "Git ağacı: **merge dirsekleri**" — `parent_sha` olmadan çizilemez, çizilmiyor.
- ✅ Yerine: dal şeritleri + zaman sıralı olay noktaları + PR olaylarında ayrı şekil.
- ✅ Sınır **ekranda yazılı**: *"Bu bir commit ağacı (DAG) değil… ok/dirsek çizilmiyor — uydurulmuyor."* Yalnız kod yorumuna yazmak, kullanıcı için hiç yazmamakla aynı şeydir; kullanıcı çizilen her oka inanır.
- ✅ "Çakışma noktası → Radar çapraz-linki" korundu, ama etiketi **"çakışma" değil "çakışma adayı"**: iki dalın aynı dosyaya dokunması bir *sinyaldir*, tespit değil. Gerçek karar (kesişim + judge + eşik) Radar'da; link oraya götürür. Radar bugün derin-link (seçili tespit) desteklemiyor → sahte bir sorgu parametresi uydurulmadı, link sayfanın kendisine gidiyor.

## Canlı veri ölçümü — tasarımı iki yerde değiştirdi

Kod yazıldıktan **sonra** üretim verisine bakıldı (`GET /events`, 30 Tem 2026,
1036 olay). İki şey çıktı ve ikisi de tasarımı değiştirdi:

**1. 130 şerit (14 günlük pencerede), 82'si tek olaylı.** 130 satır çizmek
sayfayı kullanılamaz yapardı. Sessizce ilk N'i almak ise kendi kuralımızı
("gizli üst sınır yok — neyin düştüğünü söyle") çiğnerdi. Yapılan: en hareketli
12 şerit + **kaç şerit/olayın gizlendiğini yazan bir satır** + "Tümünü göster".
Kırpma bir duvar değil, bir varsayılan.

İnce ama kritik ayrıntı: **çakışma hesabı kırpmadan ÖNCE yapılır.** Sonra
yapsaydık bir şeridi gizlemek, o dosyayı "tek dalda geçiyor" hâline getirip
**gerçek bir çakışma adayını sessizce yok ederdi**. Görünürlük kararı,
doğruluk kararını asla değiştirmemeli — bu ayrıca teste bağlandı.

**2. 378 commit + 193 issue dalsız (toplam olayların %55'i).** Issue'ların dalı
doğal olarak yok; commit'lerinki ise **D-63'ün ölçtüğü aynı kök**: commit'ler
`sha=main` ile çekiliyor, dal atfı gelmiyor. Kullanıcı 312 olaylık "dal bilgisi
yok" şeridini bir **hata** sanabilirdi → şeridin etiketi sebebi açıkça yazıyor
("issue'ların dalı yoktur, commit'ler varsayılan daldan çekildiği için dal atfı
gelmez — bir hata değil, kaynağın sınırı").

Yöntem notu: ikisi de **kod yazılmadan önce tahmin edilemezdi**, ölçülünce
çıktı. "Önce yaz, sonra gerçek veriye bak" adımı atlanmış olsaydı, iki mod da
testlerde yeşil ama üründe kullanılamaz olurdu.

## Yan bulgu: determinizm açığı testle yakalandı

Kuvvet simülasyonunda düğümler id'ye göre sıralanıyordu ama **kenarlar
sıralanmıyordu**. Kayan nokta toplaması birleşme özelliği taşımadığı için
(`a+b+c ≠ a+c+b`, son bitlerde) aynı graf farklı sırada geldiğinde 300 adımlık
doğrusal-olmayan simülasyon bu görünmez farkı **gözle görülür konum farkına**
büyütüyordu. "Girdi sırası değişse de aynı resim" testi bunu yakaladı; kenarlar
da sıralandı.

Kayıt sebebi: "deterministik" demek tohumu sabitlemek DEĞİLDİR — birikimli
kayan nokta işlemlerinde **iterasyon sırası da girdidir**.

## Kanıt

- `src/frontend/src/lib/grafYerlesimi.ts` — saf yerleşim (React'siz, DOM'suz)
- `src/frontend/src/components/GucYonluGraf.tsx` · `GitAgaci.tsx` — çizim
- `src/frontend/tests/grafYerlesimi.test.ts` (25 test) + `graph.test.tsx` (40 test)
- **18 mutasyon kanıtı**: her kilit, kodu bozunca **gerçekten** kırılıyor (totoloji yok)
- 344 frontend + 1182 backend test yeşil · `ruff` temiz
- Sıfır yeni endpoint · sıfır yeni bağımlılık (`package.json` değişmedi)

## İlgili

- Kapsam: `.harness/scope/sprint-3.md` (bu commit'te düzenlendi — düzenleme = audit)
- İddia–ölçüm hizalaması: D-63
- Issue: #130 (yeniden açıldı, kabul kriterleri güncellendi)
