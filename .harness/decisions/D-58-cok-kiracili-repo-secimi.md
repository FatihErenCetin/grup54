---
type: decision
id: D-58
title: "Çok-kiracılı repo seçimi (#79'un kalan dilimi) — TenantRegistry + kiracıya göre PK genişletmesi"
date: "2026-07-28"
status: accepted
---

## Karar

#79'un ikinci yarısı (Installation picker + gerçek çok-kiracılık) T-79'da
teslim edildi. Beş temel mimari karar:

1. **`repo_full_name` beş projeksiyon tablosunun (`events`, `task_projection`,
   `presence`, `task_status_events`, `vector_index`) birincil anahtarının
   PARÇASI** — yalnızca ek bir kolon DEĞİL. Gerekçe: PR/issue/task numaraları
   repo başına sıfırlanır (`pr:1:...`, `T-51` her repoda ayrı bir şey
   olabilir); yalnız kolon eklemek iki kiracının aynı `id`'yi paylaşmasına
   (sessiz üzerine-yazma, izolasyon ihlali) yol açardı.
2. **`TenantRegistry`** (`ensemble/tenancy.py`) — `repo_full_name ->
   memoize edilmiş ServiceTeam`, LRU sınırlı. Demo kiracı (bugünkü tek-repo
   kurulum) İSTİSNA: onun takımı `lifespan`de (app.py) zaten kurulan
   singleton'ların KENDİSİDİR, yeniden kurulmaz (D-23'ün "bugünkü public demo
   aynen çalışmaya devam etmeli" vaadi korunur).
3. **Engine sınıflarına (RadarService/ScopeService/QueryService) SIFIR
   DOKUNUŞ** — her kiracı, `GitHubAdapter`'ın owner/repo/installation_id'yi
   YALNIZCA kendisine verilen `Settings`'ten okuduğu gerçeğinden yararlanılıp,
   `Settings.model_copy(update={...})` ile klonlanmış bir ayar nesnesiyle
   kuruldu — `integrations/github/adapter.py`/`auth.py` HİÇ değişmedi.
   `BoardService`/`EventService`/`GraphService` (port almayan, DB'yi doğrudan
   sorgulayan üç servis) `repo_full_name` kurucu parametresi kazandı — bu,
   "sıfır dokunuş" ilkesinin DIŞINDA bilinçli bir istisna (bu üçü zaten port
   soyutlaması kullanmıyordu).
4. **`NullHarnessPort`** — `.harness/` yalnız demo reponun yerel diskinde
   yaşar; gerçek kiracılar için scope "unavailable" (503), presence/tasks boş
   döner. Demo reponun gerçek verisi hiçbir zaman başka bir kiracıya sızmaz.
5. **GitHub OAuth callback artık get-or-create bir `UserRow` açıyor**
   (`identities` tablosu üzerinden) — Installation picker bir `user_id`'ye
   ihtiyaç duyduğu için. D-57'nin "GitHub OAuth `users`'a yazmaz" iddiasını
   BURADA GEÇERSİZ KILAR (D-57'nin kendisi email+parola dilimine özgüydü;
   hesap BİRLEŞTİRME hâlâ kapsam dışı — yalnızca GitHub kimliğinin KENDİ satırı
   açılıyor, email hesabıyla otomatik birleşme YOK).

## Neden kayda geçiyor

Üç önceki karar (D-23, D-57, `internal/grup54_dizin_yapisi.md` §5) "users
tablosu yok" / "GitHub OAuth kullanıcıları users'a yazmaz" gibi iddialar
taşıyordu; T-79 bunları GENİŞLETTİ (iptal etmedi). Kayıt olmadan bu genişleme
yapılırsa, ileride biri "D-57 GitHub OAuth users'a yazmaz diyordu, şimdi neden
yazıyor?" diye sorduğunda cevap bulunamaz — `docs/karar-drifti-rehberi.md`'nin
tarif ettiği drift tam budur.

## Kapsam — ne yapılıyor, ne yapılmıyor

**Yapılan:** `identities`/`installations`/`watched_repos` tabloları · tek
migration'da backfill + composite PK genişletmesi (SQLite + gerçek Postgres/
pgvector'da doğrulandı) · `TenantDep` (sunucu-taraflı kiracı çözümü, `?repo=`
izinli sete karşı doğrulanır, izinsizse 403) · dört yeni uç (`/auth/
install-url`, `/auth/install-callback`, `/auth/installations`, `GET`/`PUT
/auth/repos`) · yedi okuma ucunun (`/radar`, `/board`, `/events`, `/presence`,
`/graph`, `/scope`, `/query`) hepsi için mutasyon-doğrulanmış izolasyon
testleri (`tests/unit/test_tenant_isolation.py`).

**Bilerek YAPILMAYAN — ve dürüstçe ilan edilen:**

- **GitHub App installation callback CSRF koruması dar kapsamlı.**
  `/auth/install-callback` bir token DEĞİŞTİRMEZ (yalnızca `installation_id`'yi
  oturuma bağlar) — en kötü senaryo bir saldırganın KENDİ kurulumunu kurbanın
  hesabına bağlatması (kurbanın verisi sızmaz, yalnızca saldırganın reposu
  kurbanın "izlenebilir" setine girer, `PUT /auth/repos`'a kadar hiçbir şey
  görünmez). Tam OAuth `state` çerezi kadar sıkı değil — kabul edilen, düşük-
  önem bir sınır.
- **GitHub App'in "Setup URL" ayarı bu kod tabanından YÖNETİLEMEZ** —
  operatörün GitHub App panelinden `/auth/install-callback`'i Setup URL
  olarak kaydetmesi GEREKİR (kod bunu doğrulayamaz/zorlayamaz).
- **LLM port'ları (`judge_port`/`embeddings_port`/`query_judge_port`/
  `scope_judge_port`) kiracılar arasında PAYLAŞILIR** — içerik-adresli
  cache'ler, kiracıdan habersiz; iki kiracıda BİREBİR aynı metin varsa
  (nadir) cache isabeti paylaşılabilir. Veri sızıntısı DEĞİL (yargının
  kendisi içerikten türer), ama bilinçli bir basitleştirme.
- **Radar'ın `default_base` (GITHUB_DEFAULT_BRANCH) kiracı başına
  YAPILANDIRILAMAZ** — tüm kiracılar `settings.GITHUB_DEFAULT_BRANCH`
  ("main") kullanır. Bir kiracının varsayılan dalı "main" değilse
  branch-diff temelli özellikler daha az doğru olabilir; PR/issue tabanlı
  tespit etkilenmez.
- **`GitHubAdapter`'ın kendi içi durumu (`_seen_ids`, ETag cache) `TenantRegistry`
  LRU tahliyesinde kaybolur** — bir kiracı LRU'dan atılıp yeniden kurulursa
  bir sonraki `/radar` çağrısı o kiracı için "ilk backfill" gibi davranır.
  Zararsız (idempotent, yalnızca bir sonraki pollün maliyeti artar) ama not
  edilmeye değer.

## Reddedilen seçenekler

- **Her kiracı için ayrı Postgres şeması/veritabanı** — gerçek izolasyon
  garantisi daha güçlü olurdu ama S3 zaman bütçesinde migration/ops
  karmaşıklığı orantısız; tek şema + `repo_full_name` filtresi + mutasyon-
  doğrulanmış testler yeterli güven veriyor.
- **`VectorIndexPort` imzasına `repo_full_name` parametresi eklemek** —
  QueryService/RadarService'in (engine) çağrı sitesini değiştirmeyi
  gerektirirdi ("sıfır dokunuş" ilkesini ihlal). Bunun yerine `PgVectorIndex`
  kiracıyı CONSTRUCTOR'da bağlıyor (`GitHubAdapter`'ın owner/repo'yu
  bağlamasıyla AYNI desen).

## Etkilenen belgeler

`internal/grup54_dizin_yapisi.md` §5'in "users/accounts/profiles tablosu
YOK" iddiası D-57 tarafından zaten kısmen geçersiz kılınmıştı;
`identities`/`installations`/`watched_repos` bu istisnayı GENİŞLETİR. Bu
kayıt o güncellemeyi tetikler, kendisi yapmaz.
