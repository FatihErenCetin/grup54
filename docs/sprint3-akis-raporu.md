# Sprint 3 Akış Raporu — planlanan vs gerçekleşen

> **Dönem:** 20 Temmuz–2 Ağustos 2026  
> **Plan kaynağı:** [`sprint3-bagimlilik.md`](sprint3-bagimlilik.md)  
> **Gerçekleşen kaynak:** GitHub `Sprint 3` milestone issue kapanışları + 20 Temmuz–2 Ağustos merge kayıtları. Kapanış anında milestone **52 issue: 51 kapalı, 1 açık (#64)**; aynı dönemde repoda **122 PR** merge edildi. PR sayısı yalnız milestone issue'larını değil, sprint içinde açılan review/fix/kanıt takiplerini de içerir.

## 1. Zaman çizelgesi

Dalga sınıfları sprint başındaki insan-kürasyonlu plana göre verilmiştir. `Takip` sprint içinde review/ölçümle doğan ve ilk dalga tablosunda bulunmayan işi gösterir.

| Tarih | Kapanan milestone işleri | Planla karşılaştırma |
|---|---|---|
| **20 Tem** | D0: #186, #32, #57, #162, #163, #164 | MCP/onboarding/AI kalite şeritleri planlandığı gibi bağımsız başladı ve aynı gün sonuç verdi. |
| **21 Tem** | D0: #61, #180, #31 · Takip: #207 | Deploy kökü Dockerfile ile, scope-drift çekirdeği erken kapandı. |
| **22 Tem** | D1: #181 · D0: #55, #188, #59, #58, #53, #62, #104, #152, #78 | Paralel backend/AI şeritleri planla uyumlu; ilk platform manifesti bu tarihte kapandı. |
| **23 Tem** | D0: #51, #60, #179 | Veri zincirinin kökü #179 ancak gün 4'te kapandı; aşağı akış D2/D3 bu noktaya kadar bekledi. |
| **24 Tem** | D0: #206, #177 | Build/Windows bağlantı dokusu kapandı. |
| **25 Tem** | D0: #56, #63 | Hosted sertleştirme tamamlanırken Fly→VDS kararı (D-46) planı değiştirdi. |
| **26 Tem** | Milestone kapanışı yok | Platform geçişi, judge fail-open ve maliyet/perf takipleri üzerinde 6 PR merge edildi. |
| **27 Tem** | D0: #192, #34, #184, #52, #170, #158, #48, #33, #66, #129, #105 · D1: #182, #185 · D2: #183, #187 · D3: #191, #190 · Takip: #268, #266 | Ana entegrasyon yığınının büyük bölümü tek günde kapandı: **19 milestone issue**. Teknik bağımlılıklar tamamlanmış olsa da issue kapanış sırası planı yansıtmadı. |
| **28 Tem** | Stretch: #79 | Başta gate'li stretch olan üyelik/çok-kiracılık D-57/D-58 ile tam kapsama alındı. |
| **29 Tem** | Milestone kapanışı yok | Tasarım-parite review turu; kapanışlar ertesi güne aktı. |
| **30 Tem** | D1/stretch: #130 · D3: #189, #65 | Canlı smoke, dört modlu graf ve video kapanışı teslimin son iş gününe kaldı. |
| **31 Tem–1 Ağu** | Milestone kapanışı yok | Kanıt toplama ve teslim hazırlığı; GitHub'da yeni milestone kapanışı yok. |
| **2 Ağu** | Takip: #363 | Sıfır dış AI çağrılı dar RC kabul koşumu kapandı. #64 açık kaldı ve bu rapor/README işiyle tamamlanıyor. |

## 2. Sapma tablosu

| İş / zincir | Plan | Gerçekleşen | Sapma nedeni |
|---|---|---|---|
| **Deploy platformu** | Fly.io manifesti üzerinden devam | 25 Tem'de self-host VDS'e geçildi (D-46) | Fly seçiminin ekip kararı olmadığı fark edildi; platform değişirken çevre değişkeni kontratı korundu. |
| **Veri kritik yolu** | #179 → #182 → #183 → #191 | #179 23 Tem; kalan üçü 27 Tem'de kapandı ve kapanış damgaları aşağı akışı önce gösterdi | Stacked PR/rebase/review akışı nedeniyle GitHub issue kapanış sırası teknik teslim sırasını yansıtmadı. |
| **Deploy kritik yolu** | #61 → #181 → #184 → #185 → #189 | 21 → 22 → 27 → 27 → 30 Tem | En uzun takvim beklemesi #181 ile #184 arasında; veri zinciri, review düzeltmeleri ve platform değişimi aynı aralığa girdi. |
| **#79 üyelik** | Eval gate'i sonrası düşürülebilir stretch | 28 Tem'de tam kapsamıyla kapandı | PO kararı D-57/D-58 ile kapsam genişledi. |
| **#130 graf modları** | Stretch/non-goal | D-64 ile kapsama alındı, 30 Tem'de kapandı | Treemap'in kayıtsız sevk edildiği fark edilince kapsam değişikliği görünür karara dönüştürüldü. |
| **#64/#65 teslim işleri** | D1'de sahiplen, D3'ten önce hazırla | #65 30 Tem'de; #64 sprint kapanışında hâlâ açık | Haritanın “son güne sıkışmasın” uyarısı gerçekleşti; PM/video üründen sonra ele alındı. |

## 3. Kritik yol gerçekleşmesi

**Planlanan veri zinciri:** `#179 → #182 → #183 → #191`  
**Fiilî takvim:** `#179 (23 Tem) → #191/#183/#182 kapanış kümesi (27 Tem)`.

Teknik entegrasyon dört gün içinde tamamlandı; ancak stacked branch ve tekrar review'lar nedeniyle issue kapanışlarının sırası bağımlılık sırasını ters gösterdi. Bu, durum takibinde yalnız “issue closed” damgasının yeterli olmadığını; PR head, CI ve gerçek tüketim kablosunun birlikte doğrulanması gerektiğini gösterdi.

**Planlanan deploy zinciri:** `#61 → #181 → #184 → #185 → #189`  
**Fiilî takvim:** `#61 (21 Tem) → #181 (22 Tem) → #184/#185 (27 Tem) → #189 (30 Tem)`.

Kökten canlı smoke'a **9 takvim günü** geçti. En uzun görünür bekleme 22–27 Temmuz arasındaki manifest→wiring geçişiydi. Bu aralıkta platform Fly'dan VDS'e taşındı, veri zinciri tamamlandı ve bağımsız review'lar düzeltme üretti.

## 4. Bekleme analizi

- **22–27 Tem · entegrasyon platosu:** veri/deploy PR'ları stacked ilerledi; “lokalde birlikte yeşil” sonuçları izole branch CI'ında aynı anlama gelmedi. Bekleme kişi değil, branch bağımlılığı ve tekrar review kaynaklıydı.
- **25–26 Tem · platform değişimi:** Fly kanıtı beklenirken hedef platformun ekip kararı olmadığı fark edildi. D-46 ile VDS'e geçiş, yanlış kanıt üretmeyi durdurdu fakat deploy zincirine yeniden kablolama ekledi.
- **27 Tem · kapanış yığılması:** 19 milestone issue aynı gün kapandı. Bu hız, önceki günlerde birikmiş entegrasyonun toplu inişiydi; düzenli akış değil.
- **30 Tem–2 Ağu · teslim kanıtı:** smoke, video, PM raporu ve RC ürün geliştirmesinden sonra toplandı. #64'ün son açık milestone kalemi kalması, başlangıç haritasındaki teslim-riski uyarısını doğruladı.

## 5. Retro girdileri

1. **Kritik yol PR'larını stacked bırakmazdık:** her dal kendi CI gerçeğini koruyacak biçimde daha erken, küçük ve bağımsız PR'lara ayrılırdı.
2. **Platform kararını koddan önce public karar kaydına yazardık:** sağlayıcı adı issue/kontrata girmeden önce PO kararı aranırdı.
3. **Teslim kanıtını sprint işi sayardık:** board/daily/review görselleri ve video script'i D1'de sahiplenilir, son üç güne bırakılmazdı.
4. **“Bitti” sinyalini üçlü doğrulardık:** issue durumu + izole CI + gerçek tüketici davranışı birlikte görülmeden kapanış beyan edilmezdi.
5. **Scope değişikliklerini aynı gün dondurulmuş kayda işlerdik:** D-57/D-58/D-64 gibi kararlar görünür; sessiz sevk edilen stretch kabul edilmezdi.

---

Bu rapor retro için **girdidir**; kararların kanonik kaydı `.harness/decisions/`, iş durumunun kanonik kaydı GitHub'dır.
