# macOS Masaüstü Paketi — Kurulum + Yapım Notları (T-305)

> **Ne:** Ensemble'ı geliştirici ortamı olmadan (uv/Node kurmadan) çalıştırabilen bir **sürükle-bırak macOS paketi** — "Obsidian'ı kurar gibi" (PO isteği). **Kim:** kurulumu yapan herkes bu dosyayı okur; paketi yeniden üreten kişi (release) `packaging/` dizinini de okur. **Ne zaman:** `.dmg` indirip kurarken ya da `make paket-macos` ile yeni bir paket üretirken.
>
> **Bu doküman ölçülerek yazıldı** — her iddia bu daldaki gerçek bir `make paket-macos` çalıştırması + üretilen `.dmg`'yi açıp `.app`'i çalıştırarak, `/board` gibi uçların 200 döndüğü doğrulanarak yazıldı (bkz. §4). Varsayım yazılmadı.

---

## 1. Kullanıcı için — kurulum

1. `packaging/dist-macos/Ensemble.dmg`'yi indir/aç (çift tıkla).
2. Açılan pencerede **Ensemble.app**'i **Applications** kısayoluna sürükle.
3. **İlk açılışta ÖNEMLİ:** bu paket **imzasız**dır (bkz. §3 — Apple Developer hesabı gerektirir, bu proje almadı). macOS Gatekeeper bunu bildiği için ilk açılışta normal çift tıklama **ÇALIŞMAZ** ("Ensemble.app" bozuk ya da güvenilmez görünecek). Şunu yap:
   - Applications'ta **Ensemble.app**'e **sağ tıkla → Aç**.
   - Çıkan uyarı penceresinde tekrar **Aç**'a tıkla.
   - Bu yalnızca **ilk açılışta** gerekir; sonraki açılışlar normal çift tıklamayla çalışır.
4. Birkaç saniye içinde varsayılan tarayıcın otomatik açılır ve Ensemble arayüzünü gösterir (`http://127.0.0.1:8756/`). İlk açılışta migration çalıştığı için 1-2 saniye gecikme normaldir.
5. Kapatmak için: Dock'tan sağ tık → Çık, ya da uygulama penceresindeyken **Cmd+Q**.

**Veri nerede saklanıyor?** `~/Library/Application Support/Ensemble/` — SQLite veritabanı (`ensemble.db`), kopyalanmış `.harness/` iskeleti, log dosyası (`ensemble.log`). Uygulamayı silmek bu klasörü SİLMEZ (veri kalır) — tamamen kaldırmak için bu klasörü de elle sil.

**Bir şey ters giderse:** `~/Library/Application Support/Ensemble/ensemble.log`'a bak (windowed uygulama — konsol penceresi açmaz, tüm çıktı bu log dosyasına yazılır).

---

## 2. Neden imzasız (dürüstlük notu)

Apple, macOS'ta çalışan her `.app`'in **notarize edilmiş** (Apple'ın kötü amaçlı yazılım taraması) ve bir **Apple Developer Program** üyeliğiyle (yıllık $99) imzalanmış olmasını Gatekeeper üzerinden fiilen zorunlu kılar. Bu projenin böyle bir hesabı **yok** — bu yüzden paket `codesign`'ın "ad-hoc" (kimliksiz, yalnızca arm64 çalıştırma zorunluluğunu karşılayan) imzasıyla dağıtılıyor, gerçek bir geliştirici kimliği taşımıyor.

Ölçülen sonuç (`spctl --assess --type execute -v Ensemble.app`): **`rejected`** — hem imzasız hem quarantine bayraklı (indirilmiş) durumda Gatekeeper bunu doğrudan reddediyor. Sağ tık → Aç akışı, kullanıcının kendi rızasıyla bu kararı ezmesine izin veren **tek** meşru yol; bunun dışında "güvenli, endişelenme" demiyoruz — gerçekten imzasız bir ikili çalıştırıyorsun, bunu bilerek yap.

---

## 3. Paketi yeniden üretmek (release / bakım)

```
make paket-macos
```

(`packaging/build_macos.sh`'ı çağırır.) Adımlar:

1. **Frontend production build** — `src/frontend`'de `VITE_API_BASE_URL=http://127.0.0.1:8756` ile `npm run build`. **Kritik kısıt:** Vite ortam değişkenlerini **derleme anında** JS'e gömer (`src/frontend/src/lib/config.ts`), runtime'da değiştirilemez. Bu yüzden backend'in dinleyeceği port **sabit** (`8756`, hem `packaging/launcher.py::PREFERRED_PORT` hem bu script'te tanımlı — ikisini SENKRON tut).
2. **PyInstaller** (`packaging/ensemble.spec`) — `uv run --with-requirements packaging/requirements-build.txt pyinstaller ...` ile, kök `pyproject.toml`/`uv.lock`'a dokunmadan (geçici üst-katman ortamı). Backend kodu + alembic migration dosyaları + `.harness/` iskeleti + frontend `dist/`'i tek `.app`'e gömer.
3. **`.dmg`** — `hdiutil` ile `.app` + `Applications` kısayolu + "İlk açılışta" notu içeren sürükle-bırak imajı.

Çıktı: `packaging/dist-macos/Ensemble.app` + `packaging/dist-macos/Ensemble.dmg` (gitignored — büyük ikili, repo'ya girmez; her release elle/CI'da yeniden üretilir).

**Sadece macOS'ta çalışır** (`hdiutil`, `.app`/`.dmg` formatı macOS'a özgü). Node/npm + uv'nin geliştirme ortamında zaten kurulu olduğu varsayılır (bkz. `AGENTS.md` §Build/test).

### Port neden sabit, "boş port bul" değil?

Görev tanımı "boş bir port bul" diyordu; gerçek kısıt (yukarıdaki Vite kısıtı) rastgele port seçimini imkansız kılıyor — frontend derlemesi hangi porta konuşacağını ÖNCEDEN bilmek zorunda. Bunun yerine `launcher.py::_resolve_port()` şunu yapar:
- Port (`8756`) boşsa → kullan.
- Port zaten **bizim** bir Ensemble instance'ımız tarafından tutuluyorsa (health-check ile doğrulanır) → yeni süreç **başlatma**, yalnızca tarayıcıyı aç (tek-instance davranışı — çift tıklama ikinci bir backend süreci doğurmaz).
- Port **başka** bir uygulama tarafından tutuluyorsa → açık bir hata ver ("Port 8756 kullanımda... o uygulamayı kapatıp tekrar dene"), sessizce başka bir porta KAYMAZ (kayarsa frontend'in gömülü API adresinden kopardı).

"Hazır olana kadar bekle" kısmı gerçekten **port yoklamasıyla** yapılıyor (`/health`'i 0.2 sn aralıkla, 30 sn'ye kadar sorar), sabit bir `sleep` YOK.

### Tek port mu, iki port mu?

Bu iş yazıldığı sırada backend `dist/`'i kendi başına servis ETMİYORDU (paralel çalışan başka bir dilim bunu ekleyebilir — bkz. görev notu). `launcher.py::_mount_frontend_if_needed` şunu yapar: `create_app()`'in döndürdüğü `FastAPI` nesnesinde `/` için zaten bir route/mount VARSA (paralel iş inmiş) **hiçbir şey eklemez**; YOKSA paketlenmiş frontend `dist/`'ini `StaticFiles(html=True)` ile **aynı porta** (`8756`) kendisi ekler. Sonuç: hangi senaryo gerçekleşirse gerçekleşsin **tek port** — `launcher.py` bu iki durumu ayırt edip doğru olanı yapıyor, elle senkron gerekmiyor.

---

## 4. Gerçekten test edildi mi? (kanıt)

Bu dalda (T-305) gerçekten çalıştırıldı, uydurulmadı:

| Adım | Sonuç |
|---|---|
| `make paket-macos` | ✅ `Ensemble.app` (72M) + `Ensemble.dmg` (36M) üretti |
| `.dmg`'yi `hdiutil attach` ile aç, içeriği kontrol et | ✅ `Ensemble.app` + `Applications` kısayolu + not dosyası görüldü |
| `.app`'i DMG'den **başka bir klasöre kopyala** (gerçek "kur" simülasyonu) ve çalıştır | ✅ `/health`, `/board`, `/events`, `/graph`, `/radar`, `/auth/config` → hepsi **200** |
| Tarayıcı gerçekten açıldı mı? | ✅ Log'da `GET /` + ardından `/assets/*.js`, `/assets/*.css`, `/auth/config` istekleri — yalnızca gerçek bir tarayıcının HTML'i render edip React uygulamasını çalıştırması bu deseni üretir (çıplak `curl` tek bir istek yapar) |
| Veri dizini + `.harness/` kopyası + SQLite migration | ✅ `~/Library/Application Support/Ensemble/` altında `.harness/`, `ensemble.db` (migration sonrası ~164K, 8 migration da koştu), `ensemble.log` oluştu |
| İkinci kopyayı (aynı port) çalışırkenken başlat | ✅ Yeni süreç başlatmadı, `exit 0` ile çıktı, ilk instance etkilenmedi |
| Portu **yabancı** bir sürece işgal ettirip başlat | ✅ Açık hata mesajı + `exit 1`, sessiz bozulma yok |
| Gatekeeper (`spctl --assess --type execute`) | ✅ `rejected` — dokümandaki uyarı gerçek davranışla eşleşiyor |
| `codesign -dv` | `Signature=adhoc`, `TeamIdentifier=not set` — imzasız olduğu doğrulandı |

**Test edilmedi / bilinmiyor:** başka bir Mac'te (bu makinenin dışında), gerçekten internetten indirilmiş (tam quarantine + Safari "hangi siteden indirildi" meta verisiyle) bir `.dmg` ile sağ-tık-Aç akışının UI adımları — yalnızca `spctl`'in verdiği karar (`rejected`) doğrulandı, tıklama akışının kendisi görsel olarak izlenmedi.

---

## 5. Bilinen riskler / sınırlar

- **Boyut:** `.app` ~72M, `.dmg` ~36M (sıkıştırılmış). Büyük kısmı `libpython3.12.dylib` (17M) + `cryptography` (11M, gömülü OpenSSL) + `pydantic_core` (4M) — bunlar gerçek çalışma zamanı bağımlılıkları, kolayca küçültülemez. `google-genai`/`jsonschema`/`alembic`'in test/benchmark alt paketleri `packaging/ensemble.spec::_is_test_noise` ile elendi (ilk denemede 75M idi).
- **`.harness/` tohumu:** paket, bu REPONUN bugünkü `.harness/` içeriğinin (gerçek sprint/scope/task verisi) bir kopyasını taşır — kullanıcının kendi projesine özel bir `.harness/` DEĞİL, grup54'ün kendi board'unun statik bir anlık görüntüsü. Bu, Ensemble'ın "kendi projesini izleme" ürün vizyonuyla TAM örtüşmüyor (bu masaüstü paketi GitHub App/webhook kurulumu yapmıyor) — kapsam bilerek dar tutuldu: yalnızca "uygulama açılıp çalışıyor" kanıtı, gerçek bir GitHub reposunu izleme kurulumu DEĞİL.
- **Sürüm yükseltmesi:** yeni bir `.dmg` kurulduğunda `launcher.py::_seed_harness` `.harness/` zaten varsa DOKUNMAZ (veri kaybı riskine karşı) — yeni sprint/scope içeriği otomatik gelmez, elle güncellenmesi gerekir.
- **GEMINI_API_KEY / GitHub App:** paket varsayılan olarak hiçbirini içermez — backend zaten bunlar eksikken FakeJudgeAdapter/FakeGitHubAdapter/HashEmbeddings'e düşecek şekilde tasarlanmış (bkz. `ensemble/app.py::_build_judge_port` vb.); masaüstü paketi bunu DEĞİŞTİRMEZ, yalnızca aynı zarif düşüşten faydalanır. Gerçek anahtarlarla çalıştırmak isteyen kullanıcı için bir ayar arayüzü YOK (stretch — bu görevin kapsamı dışında).
- **Windows/Linux:** bu paket yalnızca macOS içindir (`hdiutil`, `.app` bundle formatı). Diğer platformlar için ayrı bir iş gerekir.

---

## 6. İlgili dosyalar

- `packaging/launcher.py` — çalışma zamanı başlatıcı (veri dizini · migration · port çözümü · tarayıcı açma).
- `packaging/ensemble.spec` — PyInstaller derleme tarifi (neyin neden dahil edildiği yorumlarda).
- `packaging/build_macos.sh` — uçtan uca derleme scripti (`make paket-macos` bunu çağırır).
- `packaging/requirements-build.txt` — yalnızca paketleme için gereken araçlar (kök `uv.lock`'a eklenmedi).
