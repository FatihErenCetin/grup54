---
type: decision
id: D-58
title: "#79 tam yapılıyor — çok-kiracılı repo seçimi ürüne giriyor (D-23'ün son maddesi de değişti)"
date: "2026-07-28"
status: accepted
---

## Karar

**#79 düşürülmüyor, tam kapsamıyla yapılıyor.** Giriş yapan kullanıcı kendi
GitHub App kurulumuyla kendi repolarını seçip içe aktarabilecek. PO: *"bu
kesinlikle ürün içerisinde yer almalı."*

Reddedilen iki alternatif (SM Esma'nın sunduğu):

1. **#79'u düşürmek** — issue'nun kendi metnindeki çıkış maddesi (*"Video/cila
   riske girerse bu issue düşer"*) bunu meşru kılıyordu.
2. **Mevcut login'i #79'a saydırıp kapatmak** — kabul kriterleri kurulum
   seçimi ve kiracı izolasyonu hakkında, login hakkında değil; kriterleri
   karşılanmamış bir issue'yu "bitti" saymak yanlış beyan olurdu.

## D-23'ün son maddesi de değişti

D-23 (30 Haz, "KESİN") üç şey diyordu: *kullanıcı-DB yok · login yok · hosted
= tek no-login demo.* İlk ikisi **D-57** ile değişti. Bu kararla **üçüncüsü**
de değişiyor: hosted artık tek repo değil, çok kiracılı.

**Ama demo vaadi KORUNUYOR:** anonim ziyaretçi hiçbir şey yapmadan grup54'ün
kendi verisini görmeye devam eder. Login duvarı YOK. Çok-kiracılılık bunun
ÜSTÜNE gelir, yerine değil — dogfood demosu ürünün vitrini ve kaybedilmez.

## Ölçülen kapsam (tahmin değil)

| yüzey | veri kaynağı | kiracılaştırma |
|---|---|---|
| `radar` | **canlı GitHub** | adapter kiracı başına kurulmalı |
| `board` · `events` · `graph` | DB | 5 tabloya repo anahtarı + filtre |
| `scope` · `presence` | **`.harness/` yerel dosyalar** | kiracı reposunda o dosyalar bizde YOK |

Ek olarak: hiçbir projeksiyon tablosunda repo kolonu yok, servisler
uygulama seviyesinde tekil (`app.state.radar_service`), `GitHubAdapter`
repo'yu açılışta `settings`'ten alıyor.

## Mimari — "engine'e sıfır dokunuş" (#79 kriteri 4)

Engine sınıfları port'ları kurucudan aldığı için engine'e **hiç dokunmadan**
farklı port'lar verilebilir. `TenantRegistry`: `repo_full_name → memoize
edilmiş servis takımı` (LRU sınırlı). Engine dosyaları değişmez.

Kiracı **sunucuda** çözülür. `?repo=` parametresi kabul edilebilir ama
çağıranın izinli setine karşı doğrulanır; izinsizse 403. **İstemcinin
gönderdiği repoya körlemesine güvenilmez** — izolasyonun klasik kırılma yeri.

## Kabul edilen açık

`scope` ve `presence` kiracı repoları için **yapılandırılmamış** döner —
`.harness/` dosyaları yerel diskte ve başkasının reposunda bizde yok. Sahte
veri ya da demo reponun verisi DÖNDÜRÜLMEZ. GitHub'dan çekmek ayrı bir iş.

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

## Etkilenen belgeler

`internal/grup54_dizin_yapisi.md` §5'in "users/accounts/profiles tablosu
YOK" iddiası D-57 tarafından zaten kısmen geçersiz kılınmıştı;
`identities`/`installations`/`watched_repos` bu istisnayı GENİŞLETİR. Bu
kayıt o güncellemeyi tetikler, kendisi yapmaz.

## Neden bu risk alındı

PO'ya iki uyarı yapıldı: (a) kalan iş ~8 puanlık yeni mimari, donma
planına göre riskli (SM'in tespiti, ölçümle doğrulandı); (b) izolasyon
testlerini aceleye getirmenin bedeli geç teslimden ağır — hata, kullanıcıların
birbirinin verisini görmesi demek. PO ikisini de duyduktan sonra "bu gece
bitecek" dedi. Karar kayda geçiyor ki risk sessiz kalmasın.

**İzolasyon pazarlık konusu değil:** iki kiracıyla, birinin verisinin diğerine
hiçbir uçta sızmadığı test edilecek ve her filtre tek tek kaldırılıp testin
kırmızıya döndüğü görülecek.
