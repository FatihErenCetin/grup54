<!-- PUBLIC README — canlı reponun (FatihErenCetin/grup54) köküne koy, mevcut ŞABLON README'nin yerine. -->

<div align="center">

# 🧭 Ensemble — Paylaşılan Proje Beyni

**AI çağı yazılım ekipleri için koordinasyon aracı:** kim neye dokunuyor, kimler çakışmak üzere, nerede plandan sapıldı — ve panoya **doğal dille sor**. Hepsi tek canlı ekranda, gerçek GitHub verisinden.

[**▶ İlk prototipi çalıştır**](harness-dashboard/README.md#çalıştırma) · YZTA Bootcamp 2026 · **grup54**

![Ensemble — ilk prototip panosu](harness-dashboard/docs/dashboard.png)

> **İlk prototip:** [`harness-dashboard/`](harness-dashboard/) — vizyonun çalışan bir kesiti. Ensemble'ın tam mimarisi (FastAPI engine · Gemini "judge" · MCP · `.harness/`) geliştiriliyor.

</div>

---

## 👥 Takım

| | İsim | Rol | GitHub | LinkedIn |
|:---:|---|---|:---:|:---:|
| <img src="https://github.com/FatihErenCetin.png" width="56" height="56"> | **Fatih Eren Çetin** | Product Owner · Developer | [@FatihErenCetin](https://github.com/FatihErenCetin) | [in/fatih-eren-cetin](https://www.linkedin.com/in/fatih-eren-cetin/) |
| <img src="https://github.com/esma6.png" width="56" height="56"> | **Esma Fazilet Karagülle** | Scrum Master · Developer | [@esma6](https://github.com/esma6) | [in/esma-karagulle](https://www.linkedin.com/in/esma-karagulle/) |
| <img src="https://github.com/EnesErdemT.png" width="56" height="56"> | **Enes Talha Erdem** | Developer | [@EnesErdemT](https://github.com/EnesErdemT) | [in/enesterdem](https://www.linkedin.com/in/enesterdem/) |
| <img src="https://github.com/asmarufoglu.png" width="56" height="56"> | **Semih Marufoğlu** | Developer | [@asmarufoglu](https://github.com/asmarufoglu) | [in/asmarufoglu](https://www.linkedin.com/in/asmarufoglu/) |

> Roller bootcamp boyunca sabittir; **PO ve SM dahil herkes kod yazar.** Ekip içi iletişim kuralı: birincil **SM (Esma)**, yedek **PO (Fatih)**.

---

## 🧩 Ürün

Bir ekip hızlandıkça — özellikle herkes kendi AI asistanıyla kod yazarken — kimin ne yaptığını takip etmek zorlaşır: aynı iş tekrarlanır, insanlar birbirinin koduna dokunup çakışır, iş kapsamın dışına taşar. **Ensemble**, ekibin GitHub'daki **canlı** çalışmasını izleyip bunları tek ortak panoda gösterir. *(Sahte/mock veri yok — gerçek branch, PR ve issue'lar okunur.)*

- **🎯 Çakışma radarı** — aynı dosyaya dokunan birden fazla branch'i, merge çakışması yaşanmadan **önce** yakalar.
- **👀 Kim neye dokunuyor** — her branch'in son commit'i, yazarı, mesajı canlı.
- **📋 Kendiliğinden dolan sprint board** — issue/PR'lar otomatik Backlog → Devam → İncelemede → Bitti.
- **🛡️ Kapsam bekçisi** — issue'ya bağlı olmayan PR'ları işaretler (plan dışı işi görünür kılar).
- **💬 Beyne sor** — doğal dille soru, repo'nun gerçek verisinden yanıt.

![Kapsam bekçisi ve Beyne sor](harness-dashboard/docs/scope-and-ask.png)

▶ Çalıştırma (tek dosyalık HTML, kurulum yok) ve tüm detaylar: **[`harness-dashboard/README.md`](harness-dashboard/README.md)**

---

## 🧠 Mimari & Yapay Zeka

Ensemble, **insanların** (web pano) ve **her üyenin AI aracının** aynı paylaşılan bağlamı görmesi için tasarlandı. Yapay zekâ, bir süs değil ürünün karar katmanı:

| Yetenek | Durum |
|---|---|
| **Beyne sor** — kurallı mod (anahtarsız, gerçek repo verisinden) | 🟢 çalışıyor |
| **Beyne sor** — AI modu (LLM ile serbest doğal dil yanıtı) | 🟢 çalışıyor (opsiyonel anahtar) |
| Çakışma radarı — dosya-kesişimi tespiti | 🟢 çalışıyor |
| **Semantik çakışma + scope-drift** — embeddings + Gemini **"judge"** karar katmanı + eşik kalibrasyonu | 🟡 tasarlandı (sonraki sürüm) |
| **MCP arayüzü** — AI araçları (Cursor/Claude Code) ortak bağlamı okur/yazar | 🟡 tasarlandı |
| **`.harness/`** — git-senkron, kanonik ortak bağlam (repoya yazma) | 🟡 tasarlandı |

Hedeflenen motor: **Python + FastAPI** (engine) · **Gemini** (embeddings + judge) · **MCP server** · **GitHub App** (webhook). Çalışma modu local-first; demo için tek hosted örnek.

---

## 💼 İş Modeli

Tam **Yalın Kanvas** (9 blok) — vizyon + rakip araştırmasından damıtıldı:

[![Ensemble Yalın Kanvas](ProjectManagement/General/yalin-kanvas.png)](ProjectManagement/General/yalin-kanvas.md)

> **Özet:** **Source-available çekirdek** (kaynak görünür, kullanım kısıtlı — OSI open source *değil*; PolyForm Strict) + hosted Team ≈ $8–12/geliştirici/ay · **open-core = doğrulama sonrası gelecek opsiyonu 💡** (relicense yolu açık) · hedef = AI-destekli küçük ekipler (öğrenci/bootcamp = dogfood köprübaşı) · **rekabet avantajı** = 4 koordinasyon parçasının (proaktif çakışma + canlı scope-drift + insan & ajan ortak farkındalık + git-yazılabilir `.harness/`) birleşimi — birebir rakip yok. Detay: [`yalin-kanvas.md`](ProjectManagement/General/yalin-kanvas.md).

---

## 📋 Proje Yönetimi

<!-- TAKIM: board kurulunca gerçek URL'yi yapıştır. GitHub Projects önerilir (issue/PR ile otomatik senkron — ürünün kendi "kendiliğinden dolan board" hikâyesini dogfood eder). -->
**Backlog board:** _GitHub Projects (kurulup linklenecek)_

### Sprint 1  *(19 Haz – 5 Tem 2026)*

<!--
TAKIM — bu 6 başlığı GERÇEK veriyle doldurun (graded "proje yönetimi" puanının tek kaynağı):
1. Backlog Dağıtma Mantığı: toplam puan + S1/S2/S3 split (gerekçe) + Hedef-vs-Gerçekleşen tablosu.
2. Daily Scrum: platformu ADIYLA (ör. "Discord, hafta içi 21:00") + tarihli not görselleri.
3. Sprint Board: gerçek GitHub Projects screenshot'ı + renk kodu (mavi=story, kırmızı=task).
4. Sprint Review: katılımcı listesi + alınan kararlar.
5. Sprint Retrospective: 2-3 somut aksiyon.
Burndown (bonus): basit bir grafik veya tablo (Gün | İdeal kalan | Gerçek kalan).
ProjectManagement/Sprint1Documents/ içindeki ŞABLON dosyalarını (Movie App/Spider-Man) SİLİN; yerine gerçek kanıt koyun.
-->

- **Backlog Dağıtma Mantığı:** _bu sprint dolduruluyor — toplam puan, S1/S2/S3 dağılımı (gerekçe), hedef vs gerçekleşen._
- **Daily Scrum Notları:** _platform + tarihli kanıt._
- **Sprint Board Updates:** _GitHub Projects board görüntüsü + renk kodu (mavi=story, kırmızı=task)._
- **Ürün Durumu:** Çalışan **harness** panosu — yukarıdaki ekran görüntüleri (`harness-dashboard/docs/`). İlk sürüm canlı GitHub verisiyle çalışıyor; **PR #1 (Esma · frontend) merge edildi**, ekip aktif geliştiriyor (Fatih · Esma · Enes commit'ledi).
- **Sprint Review:** _kararlar + katılımcılar._
- **Sprint Retrospective:** _bir sonraki sprint için somut aksiyonlar._

### Sprint 2 · Sprint 3
_Aynı 6 başlıkla, sprint ilerledikçe._

---

## 🛠️ Teknoloji

Bu sürüm: tek-dosya **HTML + JS** (build yok) · **GitHub REST API** (canlı veri). Çalıştırma, "nasıl çalışıyor", yol haritası ve dürüst bilinen sınırlar → **[`harness-dashboard/README.md`](harness-dashboard/README.md)**. Hedeflenen tam mimari için yukarıdaki *Mimari & Yapay Zeka* bölümüne bakın.
