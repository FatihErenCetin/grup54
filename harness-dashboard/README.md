# harness — proje beyni

> Bir yazılım ekibi hızlandıkça — özellikle herkes kendi yapay zekâ asistanıyla kod yazarken — kimin ne yaptığını takip etmek zorlaşır. **harness**, ekibin GitHub'daki çalışmasını izleyip herkese tek bir ortak tabloda *"kim neye dokunuyor, kimler çakışmak üzere, nerede plandan sapıldı"* bilgisini gösteren paylaşılan bir **proje beynidir**.

Pano, repo'nun **canlı GitHub verisine** bağlanır — sahte/mock veri yoktur. Branch'leri, açık PR'ları ve issue'ları okuyup ekibin o anki gerçek durumunu tek ekranda gösterir.

---

## Ekran görüntüleri

### Genel pano — radar, sprint board, kim neye dokunuyor

![harness panosu](docs/dashboard.png)

Üst şeritte canlı metrikler (aktif branch, açık çakışma, kapsam dışı PR, açık PR). Solda çakışma radarı ve dosya temasları, sağda GitHub hareketinden kendiliğinden dolan sprint board.

### Kapsam bekçisi + Beyne sor

![Kapsam bekçisi ve beyne sor](docs/scope-and-ask.png)

Bir issue'ya bağlı olmayan PR'lar amber ile işaretlenir. Altta doğal dille soru sorulan "Beyne sor" paneli — repo'nun gerçek durumundan yanıt verir.

---

## Özellikler

**Çakışma radarı.** Her branch'i ana branch ile karşılaştırıp hangi dosyalara dokunduğunu çıkarır. Aynı dosyaya birden fazla branch dokunuyorsa, merge çakışması yaşanmadan önce uyarır.

**Kim neye dokunuyor.** Her branch'in son commit'ini, yazarını ve mesajını canlı gösterir — ekip birbirinin ayağına basmadan ilerler.

**Kendiliğinden dolan sprint board.** Açık/kapalı issue'lar ve açık PR'lar otomatik olarak Backlog / Devam ediyor / İncelemede / Bitti sütunlarına yerleşir. Elle kart sürükleme yok.

**Kapsam bekçisi.** Başlığında veya açıklamasında bir issue referansı (`#123`, `Fixes #123`) olmayan açık PR'ları işaretler — plan dışına çıkan işi görünür kılar.

**Beyne sor.** Doğal dille soru sorulur, repo'nun o anki gerçek verisinden yanıt gelir. İki modda çalışır:
- **Kurallı mod (varsayılan, anahtarsız):** Sorular panodaki gerçek sayılardan yanıtlanır. Demo için en sağlam yol budur.
- **AI modu (opsiyonel):** Bir LLM API anahtarı girilirse, aynı gerçek repo durumu bağlam olarak verilip serbest doğal dil cevabı üretilir.

---

## Çalıştırma

Kurulum gerekmez. Tek dosyalık bir HTML uygulamasıdır.

> Bu pano repo içinde `harness-dashboard/` klasöründe yaşar; repo kökündeki diğer dosyalara dokunmaz.

1. `harness-dashboard/index.html` dosyasını indirin (veya repoyu klonlayın).
2. Dosyayı bir tarayıcıda açın.
3. Pano otomatik olarak `FatihErenCetin/grup54` reposunu izlemeye başlar.

Başka bir repoyu izlemek için sağ üstteki kutuya `kullanıcı/repo` yazıp **Yenile**'ye basmanız yeterli.

### Beyne sor — AI modu (opsiyonel)

"Beyne sor" panelindeki **LLM anahtarı** kutusuna kendi Anthropic API anahtarınızı yapıştırırsanız, sorular gerçek bir dil modeline gider. Anahtar yalnızca tarayıcınızda kalır, koda gömülü değildir.

> **Uyarı:** API anahtarınızı asla dosyaya yazıp commit'lemeyin. Kutuya elle girin. Public repoda anahtar paylaşmak onun çalınmasına yol açar.

---

## Nasıl çalışıyor

Pano, GitHub'ın herkese açık REST API'sini kullanır:

| Veri | Kaynak |
|------|--------|
| Aktif branch'ler | `GET /repos/{repo}/branches` |
| Branch'in değiştirdiği dosyalar | `GET /repos/{repo}/compare/{base}...{branch}` |
| Son commit bilgisi | `GET /repos/{repo}/commits/{sha}` |
| Açık PR'lar | `GET /repos/{repo}/pulls?state=open` |
| Issue'lar | `GET /repos/{repo}/issues?state=all` |

Çakışma radarı, `compare` sonuçlarındaki dosya listelerini kesiştirerek aynı dosyaya dokunan birden fazla branch'i bulur. Kapsam bekçisi, PR metninde issue referansı olup olmadığını kontrol eder.

---

## Bilinen sınırlar

Bu, bootcamp sprint'i kapsamında geliştirilen ilk sürümdür. Dürüst olmak gerekirse şunlar henüz yoktur veya kısıtlıdır:

- **GitHub API sınırı:** Token'sız çalışırken GitHub saatte 60 istek izin verir. Çok branch'li repolarda birkaç yenilemede sınıra takılabilirsiniz. Panonun altında kalan istek sayısı gösterilir. Bir Personal Access Token eklenirse sınır 5000/saate çıkar.
- **`.harness/` senkronu yok:** Ürün vizyonundaki "ortak bağlam projenin içinde yaşar" kısmı (repoya yazma) bir backend / CI adımı gerektirir; bu sürüm yalnızca okur.
- **AI çağrısı tarayıcıdan:** Beyne sor'un AI modu şu an tarayıcıdan doğrudan API'ye gider. Üretim sürümünde bu çağrı bir backend'e taşınmalıdır.
- **Gerçek zamanlı uyarı yok:** Çakışmalar yenilemede hesaplanır; canlı webhook tabanlı anlık uyarı sonraki aşamadır.

---

## Yol haritası

- [ ] Kullanıcı token'ı ile yüksek API limiti
- [ ] `.harness/` dosyalarına yazma (git ile senkron ortak bağlam)
- [ ] AI çağrıları için backend
- [ ] Webhook tabanlı anlık çakışma uyarısı
- [ ] AI araçları (Cursor / Claude Code) için ortak bağlam okuma/yazma arayüzü

---

## Takım

grup54 — YZTA bootcamp ekibi. Her üye kendi branch'inde çalışır; beğenilen branch ana hatta birleştirilir.
