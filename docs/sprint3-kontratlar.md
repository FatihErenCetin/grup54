# Sprint-3 Kontratları (girdi → çıktı)

> **Amaç:** Sprint-3 = **go-live (canlıya alma) + web MVP'nin gerisi** — deploy mekaniği, kalan router'lar (/board · /events · /presence · /query · /scope · /graph), store/pgvector'ün canlı bağlanması, MCP okuma yüzü ve üç frontend sayfası **aynı anda, farklı kişilerde** ilerliyor. Kimse kimseyi beklemesin diye arayüzler **sprint başında donuyor** (retro aksiyonu **R2** · D-22: kontrat-önce paralelleşme). Kontrat değişirse buraya PR aç + daily'de duyur.

## İlke: kontrat-önce, paralel geliştirme (S3'te üç tür kontrat)

S2'deki iki tür kontrata (HTTP openapi + Python Protocol) S3'te **üçüncüsü** ekleniyor — go-live bunu zorunlu kılıyor:

1. **HTTP (FastAPI ↔ frontend):** endpoint'ler Pydantic modellerden **`src/shared/openapi.json`** üretir → frontend TS client *otomatik* (`npm run gen:api` → `src/api/schema.d.ts`). Frontend backend bitmeden client'ı üretip **mock veriyle** çalışır.
2. **Python Protocol (katmanlar arası):** her bağımlılık bir `Protocol` arkasında (`ensemble/ports.py`, `ensemble_shared/harness.py`) → **fake adapter** ile stub'lanır (PgVector gerçek Postgres olmadan, MCP gerçek harness olmadan test edilir).
3. **🆕 Deploy env eşlemesi (kod ↔ platform):** her env değişkeni **NEREDE** tutulur (sunucu env dosyası / Vercel env / CI secret / yalnız-local — D-46 self-host dönüşümü, bkz. Ek A değişiklik notu) ve hangi ikili **çift-yönlü kilitli** (CORS_ORIGINS ↔ VITE_API_BASE_URL). Bu donmadan iki kişi (infra + frontend) birbirinin URL'ini tahmin ederek çalışır → canlıda CORS/base-URL çakışması. Eşleme donunca ikisi de mock origin'le paralel gider.

```
Sunucu env dosyası ─env─> FastAPI (ENSEMBLE_MODE=hosted) ─Protocol─> engine ─Protocol─> PgVectorIndex ─> self-host PG
   (Ek A)                     (Ek B: router imzaları)      (Ek C store DI)     (Ek C)          (#182/#246)
                              │  ▲
              openapi.json ───┘  └─── MCP read tools (Ek D)
                    │
   Vercel env ─VITE_API_BASE_URL─> frontend TS client ─> Board · Ask · Activity · Heatmap · Actors (Ek E)
```

> **Not (TDK):** S2 Ek A–D'de donmuş **model** şekilleri (Detection, BoardCard.last_event, PresenceEntry, ScopeVerdict, Citation, TouchGraph, ErrorEnvelope…) burada **yeniden tanımlanmaz** — S3 yalnız o modelleri taşıyan **router/adapter/env imzalarını** dondurur ve S2'ye link verir. Kanonik model kaynağı: `ensemble/models.py` + `ensemble/api/schemas.py`; kanonik port kaynağı: `ensemble/ports.py`.

---

## Ek A (20 Tem) — Deploy env sözleşmesi (#181 · #186 · #190): her sır NEREDE yaşar

> **Sahibi:** infra (deploy dilimi) · **Tüketicisi:** herkes (backend çalışma-zamanı, frontend build, CI). 🔒 **FROZEN** — bu tablo `docs/deploy-runbook.md`'nin (#190) tek kaynağıdır; `.env.example` anahtarı eklenince buraya da satır eklenir.
>
> **Değişiklik notu (25 Tem, D-46 — self-host dönüşümü):** bu ek ilk donduğunda (20 Tem) hedef platform Fly.io idi (#181, `fly.toml`). #192 review'ünde (Semih) go-live topolojisi **self-host VDS + Docker Compose + self-hosted GitHub Actions runner**'a çevrildi — issue #192'nin kabul kriterleri PO tarafından buna göre güncellendi (D-46, `internal/grup54_karar_logu.md`). Aşağıdaki A1/A2/A3 **sessizce değil, bu notla** güncellendi: donmuş SATIRLAR (hangi env anahtarının hangi ortama ait olduğu) **AYNEN** kalıyor — değişen yalnızca "nerede tutulur" sütunundaki **platform adı** (Fly secret → sunucudaki env dosyası) ve `FLY_API_TOKEN` satırının **kaldırılması** (self-host CD'nin hiçbir CI secret'ına ihtiyacı yok — bkz. `.github/workflows/deploy.yml`). Vercel tarafı (frontend) **DEĞİŞMEDİ**.
>
> **Ek not (25 Tem, ikinci geçiş — main merge sonrası tarama):** ilk geçişte yalnız A1/A2/A3 satırları tarandı; main'den gelen #239'un (T-63) eklediği `DEMO_MODE`/`DEMO_RATE_*` satırları — ve bu dosyanın Ek C (`Sağlayıcı kararı`) ile sonundaki "Pratik" bölümünde kalan `Fly` referansları — gözden kaçmıştı. Hepsi aynı ilkeyle (donmuş satır AYNEN, yalnız platform adı self-host'a) güncellendi. **Bilinçli olarak dokunulmayanlar:** Ek F'teki `Fly-Client-IP` başlık önceliği, `/health` için "Fly health-check" notu ve `512 MB Fly VM`/`fly.toml auto_stop_machines` referansları — bunlar Ek A'nın env-yeri kararını tekrar etmiyor, hâlâ repoda duran gerçek `fly.toml` + `rate_limit.py` kodunun davranışını birebir anlatıyor (bu ikisi bu görev kapsamında self-host'a taşınmadı; ayrı bir temizlik konusu).

### A1 · Env → platform eşleme tablosu (#190 kabul kriteri)

| Env anahtarı | Nerede tutulur | Not |
|---|---|---|
| `ENSEMBLE_MODE` | **Sunucu env dosyası** (`/etc/ensemble/ensemble.env`) = `hosted` · local `.env` = `local` | hosted'da store+pgvector devreye girer (Ek C) |
| `CORS_ORIGINS` | **Sunucu env dosyası** | = Vercel prod origin (**A2 çift-yön**); asla `*` (config açılışta reddeder) |
| `DATABASE_URL` | **Sunucu env dosyası** | self-host Postgres+pgvector DSN `postgresql+psycopg://…` (#182/#246, aynı VDS'te docker compose servisi) — local'de SQLite dosya yolu |
| `GEMINI_API_KEY` | **Sunucu env dosyası** + **CI secret** (eval hattı) | yoksa engine Fake/Hash'e düşer (canlıda İSTENMEZ) |
| `GEMINI_MODEL` · `GEMINI_EMBEDDING_MODEL` · `GEMINI_EMBEDDING_DIMENSIONS` · `GEMINI_TIMEOUT_S` · `GEMINI_MAX_RETRIES` | **Sunucu env dosyası (opsiyonel)** | kod'da varsayılan var; yalnız override gerekince set |
| `GITHUB_APP_ID` · `GITHUB_APP_INSTALLATION_ID` | **Sunucu env dosyası** | makine-auth kimliği |
| `GITHUB_APP_PRIVATE_KEY` | **Sunucu env dosyası (PEM İÇERİĞİ)** | 🆕 #186 — **dosya yolu DEĞİL, ham PEM metni** (A3) |
| `GITHUB_APP_PRIVATE_KEY_PATH` | **yalnız-local** | geliştiricinin diskindeki `.pem`; sunucuda **boş** (mount yok) |
| `GITHUB_REPO_OWNER` · `GITHUB_REPO_NAME` | **Sunucu env dosyası** | izlenen repo |
| `GITHUB_DEFAULT_BRANCH` | **Sunucu env dosyası (opsiyonel)** | varsayılan `main` |
| `GITHUB_WEBHOOK_SECRET` | **Sunucu env dosyası** | webhook imza doğrulaması (D-35) |
| `GITHUB_WEBHOOK_PROXY_URL` | **yalnız-local** (smee kanalı) | hosted'da webhook doğrudan sunucunun genel URL'ine (Caddy/DNS) gelir → boş |
| `RADAR_WINDOW_DAYS` · `RADAR_MIN_JACCARD` · `RADAR_MIN_SIMILARITY` | **Sunucu env dosyası (opsiyonel)** | kalibrasyon çıktısı (#18); kod default'u kanonik |
| `DEMO_MODE` | **Sunucu env dosyası** = `true` (`/etc/ensemble/ensemble.env`, sır değil ama tek-satırlık açma/kapama bayrağı burada yaşar) | 🆕 #63 — açılışta fail-closed: `true` iken `GITHUB_REPO_OWNER`/`NAME` zorunlu (bkz. Ek F) |
| `DEMO_RATE_WINDOW_S` · `DEMO_AI_RATE_LIMIT` · `DEMO_AI_GLOBAL_LIMIT` · `DEMO_RATE_LIMIT` · `DEMO_CACHE_TTL_S` · `DEMO_CACHE_MAX_ENTRIES` | **Sunucu env dosyası (opsiyonel)** | 🆕 #63 — kod default'u kanonik; yalnız override gerekince set (bkz. Ek F) |
| `CORS_PREVIEW_ORIGIN_REGEX` | **Sunucu env dosyası (opsiyonel)** | 🆕 #343 — Vercel **preview** origin ailesi (`grup54-git-<dal>-<proje>.vercel.app`); her dalda değiştiği için sabit allowlist'e yazılamaz. Desen **çapalı** (`^…$`) olmak ZORUNDA ve serbest `.*` içeremez — açılışta reddedilir. Boş = KAPALI (fail-closed). `*` hiçbir koşulda geçmez (#45 aynen geçerli) |
| `VITE_API_BASE_URL` | **Vercel env (build-time)** | = self-host backend public URL (Caddy/DNS domain, **A2 çift-yön**); origin-only, query/hash yasak |
| `VITE_MOCK` | **yalnız-local** · Vercel'de **BOŞ** | prod'da fixture chunk'ı sızmasın (yalnız `"1"` mock açar) |

> **yalnız-local** = platforma **hiç** girilmez; **Sunucu env dosyası** (`/etc/ensemble/ensemble.env`, docker compose `env_file:` ile okunur) = backend çalışma-zamanı; **Vercel env** = frontend build-time; **CI secret** = pipeline. Aynı anahtar iki sütunda olamaz (tek doğruluk); istisna = local ile hosted'ın FARKLI değeri (ENSEMBLE_MODE, DATABASE_URL, PRIVATE_KEY yolu-vs-içeriği). **`FLY_API_TOKEN` satırı D-46 ile kaldırıldı** — self-host CD'nin (`.github/workflows/deploy.yml`) hiçbir CI secret'ına ihtiyacı yok; deploy kapısı bir CI **secret** değil bir repo **VARIABLE**'ıdır (`vars.DEPLOY_ENABLED`, kill-switch: `gh variable set DEPLOY_ENABLED --body false`).

### A2 · Çift-yönlü kilit: `CORS_ORIGINS` ↔ `VITE_API_BASE_URL` (🔒 birlikte değişir)

İki ayrı platformda yaşayan **tek** kontrat — biri değişince diğeri **zorunlu** değişir:

```
Sunucu (ensemble.env): CORS_ORIGINS      = https://<vercel-app>.vercel.app     # backend KİMİ kabul eder
Vercel:                VITE_API_BASE_URL = https://<self-host-domain>         # frontend KİME gider
```

> **🆕 Üçüncü taraf (30 Tem, #343):** A2 kilidi ilk kurulduğunda yalnız **production** çifti düşünülmüştü. Preview build'leri de aynı `VITE_API_BASE_URL`'i taşır ama origin'leri farklıdır — bu aile sözleşmede yoktu. Ölçülen sonuç: preview sayfası açılıyor, **veri çekemiyor**; frontend PR'ları görsel doğrulanamıyor ve review hattı tıkanıyor (#322 ikinci kez changes-requested). `CORS_PREVIEW_ORIGIN_REGEX` bu üçüncü tarafı kapatır.

- **Kural:** biri güncellenince diğeri aynı PR/deploy penceresinde güncellenir; tek taraflı değişiklik = tarayıcıda "CORS error" (gerçek hatayı gizler — S2 #45/#150 dersi). Hata cevapları bile `Access-Control-Allow-Origin` taşır (Ek D, S2).
- **Paralel çalışma:** infra mock Vercel origin'iyle, frontend mock self-host URL'iyle başlar; entegrasyonda ikisi gerçek değerle **aynı anda** set edilir.

### A3 · `GITHUB_APP_PRIVATE_KEY` imza eklemesi (#186 — 🔒 config + auth)

Sunucu env dosyası da (eski Fly/Render gibi) env-**string** tutar; mount'lu dosya değil → hosted'a PEM dosya-yoluyla verilemez. Yeni alan + çözümleme sırası donuyor:

```python
# ensemble/config.py — Settings'e EKLENEN alan (mevcut PATH alanı AYNEN kalır)
GITHUB_APP_PRIVATE_KEY: str | None = None      # PEM İÇERİĞİ (hosted); PATH'in alternatifi

# ensemble/integrations/github/auth.py — PEM çözümleme önceliği (frozen):
#   1) GITHUB_APP_PRIVATE_KEY_PATH varsa → Path(...).read_text()   (mevcut yol, local)
#   2) yoksa GITHUB_APP_PRIVATE_KEY (içerik) → doğrudan kullan     (hosted)
#   3) ikisi de yoksa → GitHubConfigError → FakeGitHubAdapter'a graceful degradasyon (app.py mevcut davranışı)
```

- **Sahibi:** backend/infra (Esma/Enes) · **Tüketicisi:** `GitHubAdapter` / `InstallationTokenCache`.
- Readiness sözleşmesi: yalnız env-secret'larla (diskte `.pem` YOK) hosted engine **gerçek** `GitHubAdapter`'ı kurar; `/health` auth=ok. `.env.example`'a `GITHUB_APP_PRIVATE_KEY=` (hosted alternatifi) açıklamayla eklenir.
- **Sınır:** #79 (kullanıcı "GitHub ile gir") FARKLI katman + GATE'li stretch — bu makine-auth ondan bağımsız (D-28).

---

## Ek B (20 Tem) — API router imzaları (#51 · #52 · #58 · #59 · #104)

> **Sahibi:** backend/AI (router başına) · **Tüketicisi:** frontend TS client (Ek E) + MCP (Ek D). 🔒 **FROZEN path + query + response**. Taşınan **model** şekilleri S2 Ek A/B'de donuk — burada yalnız **route imzası** (path, query param, cursor, zarf) kilitlenir. `openapi.json` bu route'larla yeniden üretilir; frontend `npm run gen:api`.

Mevcut router'lar: `/health` · `/radar` · `/scope/check` · `/board` · `/query` (openapi'de var). S3 bunları **zenginleştirir** + `/events` · `/presence` · `/graph` · `/auth/*` **ekler**.

### B1 · `GET /board` (#51) — 🔒

```
GET /board  →  BoardResponse { cards: BoardCard[], last_transition_at: datetime | None, source: "seed" | "ingest" }
```
- `BoardCard` = S2 Ek B2 (mevcut alanlar + `last_event: LastEvent | None`). Model AYNEN; route donuyor.
- Kaynak: `#41` projeksiyonu üzerinde **ince okuma** — `BoardService(session_factory).get_cards()` (mevcut imza, `engine/board.py`). Durum geçişini yalnız ingest yazar (TDK).
- **Sahibi:** backend (Enes) · **Tüketicisi:** Board sayfası (#33).
- 🆕 **Şema DEĞİŞMEDİ, davranış genişledi (#331 · D-60, 30 Tem):** `openapi.json` bit-bit aynı (`make contracts` çıktısı boş diff) — ama `cards` artık `.harness/tasks/` ile SINIRLI DEĞİL: `.harness`'te dosyası olmayan gerçek GitHub issue'ları da kart üretir (çakışmada `.harness` kazanır). İki görünür sonuç: (1) `BoardCard.ref` GitHub kaynaklı kartlarda `#<numara>` taşır (`.harness` kaynaklılarda genelde `null`) — tüketici `ref`'i "yalnız `.harness` alanı" varsayMAMALI; (2) kart sayısı repo issue sayısı mertebesine çıkar (ölçüm: 22 → 155). Geçmiş de artık backfill'den kurtarılıyor, yani `last_transition_at` webhook öncesine de gidebilir. Kaynak: `store/rebuild.py` + `Projector.upsert_issue_cards`; karar: `.harness/decisions/D-60-*.md`.
- 🆕 **Kontrat değişti (İş 4, D-55 rebuild-fold planı):** `BoardResponse`'a `last_transition_at`/`source` alanları eklendi — `BoardCard` (yukarıdaki satır) DEĞİŞMEDİ, ek alan yalnız yanıt zarfında. Amaç: fold hiç uygulanmamışsa (`source="seed"`) board'un tamamen `.harness` tohumundan geldiğini, webhook kesintisinde bile SESSİZCE değil GÖRÜNÜR şekilde işaretlemek. Kaynak: `BoardService.get_board()` (yeni metod, `get_cards()` AYNEN korunuyor) → `engine/board.py::compute_board_provenance()`.

### B2 · `GET /events` + `GET /presence` (#52) — artımlı polling cursor 🔒

> **🆕 Kontrat sapması kayıt altına alındı (#265 madde 3 → D-59, 28 Tem):** aşağıdaki imza S2 Ek B5'in orijinal donuşundan **BİLEREK** sapıyor — `has_more` + `before/limit/actor/branch` sayfalaması **uygulanmadı**, `/presence` **ETag/304 uygulamadı**. Gerekçe + kabul edilen açık: `.harness/decisions/D-59-events-presence-kontrat-sapmasi.md`. Bu blok artık **gerçek davranışı** anlatır (kontrat kodun peşinden sessizce sürüklenmedi — doküman koda uyduruldu, karar kaydıyla).

```
GET /events?since=<ISO> [If-None-Match: "<etag>"]
  →  200 { events: NormalizedEvent[], latest_ts: datetime }  +  ETag: "<hash>"
  →  304 (gövdesiz) eğer If-None-Match eşleşirse (cache hit)
  →  200 (since'ten BAĞIMSIZ, tam feed döner) eğer ETag uyumsuzsa (geç gelen eski olay durumu)

GET /presence
  →  200 { entries: PresenceEntry[], latest_ts: datetime }        # ETag/304 YOK — her poll tam gövde
```
- **Cursor sözleşmesi (uygulanan hâl):** `/events` = `since=` (bu andan sonrası, artımlı, `>=` DAHİL) + **ETag** (tüm DB snapshot'ından — `since` yalnız DÖNEN GÖVDEYİ daraltır, ETag'i değil). `before=`/`limit=`/`actor=`/`branch=` filtreleri ve `has_more` sayfalama **YOK**; bugünkü olay hacminde (~763) tam feed + `since` daraltması yeterli (`/events` madde 2 kod yorumunda ölçüm var). `/presence` küçük ve TTL'li (`get_presence`, #60) olduğu için ETag'siz her poll'de tam gövde döner — sözleşmenin önerdiği "büyürse pahalanır" riski `/presence`'ta henüz gerçekleşmedi.
- `NormalizedEvent` (S2 §1) + `PresenceEntry` (S2 Ek B1) AYNEN. `type=` filtresi v1'de YOK (client-side, Ek B5 notu).
- **Sahibi:** backend (Esma) · **Tüketicisi:** Activity feed (#33) + MCP `who_is_touching` (Ek D) — ikisi de bugün yalnız `since` kullanıyor, `If-None-Match` GÖNDERMİYOR (bkz. `src/frontend/src/lib/useEvents.ts`, `usePresence.ts`); ETag mekanizması bugün istemcisiz ama sözleşmede kalıyor (gelecekte istemci eklenirse davranışı doğru — #265 madde 2).

### B3 · `GET /query` (#58, Ask) — RAG + gerekçeli cevap 🔒

```
GET /query?q=<nl>  →  QueryResponse                             # S2 Ek B4 zenginleştirilmiş şekil
#   { answer (içinde [cite:…] placeholder), citations: (str | Citation)[],
#     as_of, last_commit, window?, confidence, status, searched[], nearest[] }
```
- Akış: NL → vektör retrieval (`.harness` + events, Ek C VectorIndexPort.query) → Gemini `JudgePort`-benzeri gerekçeli yanıt. Yanıt modeli S2 Ek B4'te kilitli; #58 `api/schemas.py` `QueryResponse`'u B4'e **yükseltir** (imza S2'de donuk, route burada donuyor).
- Tek-atım (SSE streaming S3'te YOK — S2 Ek B6, sahte-canlılık yasak D-34). `status="not_found"` = dürüst red (`searched`/`nearest` fişleri).
- **Sahibi:** AI (Semih) · **Tüketicisi:** Ask sayfası (#33).

> **🆕 Kontrat değişti (30 Tem, #330 — additive):** `QueryResponse`'a ve `ScopeVerdict`'e `degraded: str | None = null` eklendi. Donmuş alanların hiçbiri **değişmedi**; ek alan varsayılanlı ve geriye-uyumlu (S2 Ek B4/B3 şekilleri korunuyor).
> **Neden:** 29 Tem canlı ölçümünde `/query`'nin üç örnek sorusu da `503 query_retrieval_unavailable`, `/scope/check` ise `503 gemini_unavailable` dönüyordu — Gemini ücretsiz kotası (ölçüldü: **20 istek/gün**) bitince embeddings çağrısı tüm isteği iptal ediyordu. Oysa her iki motorda da **leksikal yol her koşulda hesaplanıyor** ve skorlama onu tek başına taşıyabiliyor.
> **Sözleşme:** `degraded == null` → sonuç TAM yetenekle üretildi. Dolu ise semantik retrieval kullanılamadı, seçim yalnız leksikal eşleşmeyle yapıldı; sonuç gerçek ama zemini dar. İstemci bunu **göstermek zorundadır** — `RadarResponse.degraded` ile aynı ilke (*"temiz" ile "temiz diyemiyoruz" karıştırılmaz*, D-53).
> **Sınır:** düşüş yalnız **sağlayıcı arızasında** olur. Adapter sözleşme ihlali (vektör adedi yanlış) ve corpus'un hiç okunamaması **hâlâ hata fırlatır** — onları `degraded` notuna çevirmek gerçek bir bug'ı yumuşak bir dipnota gömerdi.

### B4 · `GET /scope/*` (#59 → #31 wiring) — 🔒 scope-drift verdict

```
GET /scope/check?ref=<pr>  →  ScopeVerdict                      # mevcut route; #31 dedektörüne bağlanır
GET /scope/current         →  { goal, in_scope[], non_goals[], version, frozen_at, ref, commit_sha }   # S2 Ek B3
GET /scope/verdicts        →  { verdicts: ScopeVerdict[], counts, judged_at }                          # S2 Ek B3
```
- `ScopeVerdict` = S2 Ek B3 (`evidence: str | ScopeItemRef` union · `match_none` · `signals`). Model AYNEN; route donuyor.
- `check_scope(ref)` motoru **MCP ile paylaşılır** (Ek D ikiz) — `ScopeService(harness_port, judge_port).check_scope(ref) -> ScopeVerdict` (mevcut iki zorunlu parametre AYNEN). #31 dedektörü bu imzayı doldurur.
- #31'in geriye-uyumlu DI dikişleri keyword-only'dir: `embeddings_port=None` (yoksa lexical retrieval), `subject_port=None` (yoksa `.harness/tasks` + `active` ref çözümleme), `sprint="3"`, `top_k=4`. #59 canlı PR başlık/diff özetini `ScopeSubjectPort.resolve_scope_subject(ref) -> ScopeSubject` ile verir; engine GitHub adapter'ına doğrudan bağlanmaz.
- Scope judge, çakışma judge'ından ayrı `ScopeJudgePort.judge_scope(ref, subject, candidates) -> ScopeJudgement` sözleşmesidir. Ucuz kesin-eşleşme geçidi engine'de; belirsiz karar fake/Gemini adapter'da tek kez yaşar. Eksik/taslak scope, çözülemeyen ref ve bozuk judge cevabı verdict'e çevrilmez; açık hata verir.
- **Sahibi:** backend (Esma) · **Tüketicisi:** Scope sayfası + MCP `check_scope`.

### B5 · `GET /graph` (#104, S2 çekme adayı) — 🔒 aktör×modül dokunma grafı

```
GET /graph?window_days=14  →  TouchGraph { window_days, nodes: GraphNode[], edges: GraphEdge[] }
```
- Model = S2 **Ek A** (D-33'te #106 ile dondurulmuştu) — AYNEN. Sıfır LLM: saf `NormalizedEvent` + `active/` aggregation. Modül = path'in ilk 2 segmenti (**hesaplanır**, şemaya yazılmaz).
- **Sahibi:** backend · **Tüketicisi:** Radar ısı matrisi (#105) + Actors sayfası (#129, client-side filtre).

### B6 · `/auth/*` (#79 — kullanıcı girişi) — 🔒 GitHub OAuth-user oturumu

> S2 Ek B6'da "gate'li, kapsam dışı" olarak ertelenmişti (D-28) — çekirdek eval (#17+#18) yeşile döndükten sonra gate açıldı, imza burada donuyor. `#16`'nın **makine** App-auth'ından (`GITHUB_APP_*`, Ek A) tamamen ayrı katman; radar/board/scope/query gibi hiçbir mevcut uç buna bağımlı DEĞİL.

```
GET  /auth/config   →  200 { enabled: bool }                       # sır yoksa da HER ZAMAN 200
GET  /auth/login    →  302 GitHub yetkilendirme adresine            # enabled=false → 503
GET  /auth/callback →  302 frontend'e (AUTH_POST_LOGIN_URL) + Set-Cookie(oturum)
GET  /auth/me       →  200 { handle: str, avatar_url: str | None } | 401
POST /auth/logout   →  204 + çerezi siler                           # oturum yoksa da idempotent 204
```
- Çerez: imzalı (stdlib `hmac`, `webhook.py::verify_signature` ile aynı disiplin), `HttpOnly` + `Secure` + `SameSite=Lax`; `Domain` = `AUTH_COOKIE_DOMAIN` (paylaşılan üst alan adı — Fly alt-domaini kendi cookie'sini yazmasın diye); yerelde `Domain` set edilmez.
- `access_token` hiçbir yerde saklanmaz — yalnız `callback` içinde `/user` çağrısı için bellekte tutulur, sonra atılır (#79 kuralı). Kullanıcı/identity tablosu, installation picker, çok-kiracılık = #79'un kalan/ayrı dilimi (kapsam dışı).
- **Sahibi:** backend (Esma) · **Tüketicisi:** Login/profil sayfası (frontend `useAuth`).

---

## Ek C (20 Tem) — Store / pgvector portu (#183 · #182): app-boot DI + DDL tek-kaynak

> **Sahibi:** store (Enes) · **Tüketicisi:** RadarService / QueryService (retrieval). 🔒 **FROZEN** port imzaları — `VectorIndexPort` S2 §2'de donuk; burada **hosted adapter ctor + fabrika + boot DI + DDL sahipliği** kilitlenir.

### C1 · Port + hosted adapter imzası (mevcut kod — `store/vector_store.py`) 🔒

```python
class VectorIndexPort(Protocol):                                # S2 §2 + #191
    def upsert(self, id: str, vec: list[float], meta: dict) -> None: ...
    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]: ...
    def clear(self) -> None: ...                                # #191: idempotent rebuild için indeksi sıfırla
    def replace_all(self, vectors, *, session=None) -> None: ...# #191/#218: idempotent replace + hosted'da caller DB-transaction'ına atomik yaz (session verilirse commit çağırana)

class PgVectorIndex:                                            # hosted impl (#182'nin PG'sine yazar)
    def __init__(self, session_factory: Callable[[], Session], *,
                 dimensions: int, table_name: str = "vector_index"): ...

def build_vector_index(settings, *, session_factory=None) -> VectorIndexPort:
    #   hosted → PgVectorIndex(session_factory, dimensions=GEMINI_EMBEDDING_DIMENSIONS)   (session_factory ZORUNLU)
    #   local  → LocalVectorIndex()   (in-memory; davranışı S3'te DEĞİŞMEZ)
```

### C2 · App-boot DI sözleşmesi (#183 — lifespan wiring) 🔒

```python
# ensemble/app.py lifespan — hosted dalı (donuyor):
if settings.ENSEMBLE_MODE == "hosted":
    engine = get_engine(settings)                              # store/engine.py (mevcut)
    app.state.session_factory = get_session_factory(engine)   # -> Callable[[], Session]
    vector_index = build_vector_index(settings, session_factory=app.state.session_factory)
    # vector_index → RadarService / QueryService'e enjekte (retrieval bağı)
# local dalı: session_factory yok, LocalVectorIndex — mevcut davranış korunur
```
- **Sözleşme:** `app.state.session_factory: Callable[[], Session]` (yalnız hosted); `build_vector_index` hosted'da `PgVectorIndex` döndürür ve servise enjekte edilir. `deps.py`'deki geçici stub'lar (`BoardService(lambda: None)` · `ScopeService(None, None)`) bu boot ile gerçek DI'ya bağlanır.

### C3 · DDL tek-kaynak (#183 — TDK ihlali kapanışı) 🔒

- **Kanonik = migration** (`store/migrations/versions/c4f1d6a2b8e9_vector_index_table.py`). `PgVectorIndex.create_schema()` **kaldırılır / test-yardımcısına indirilir** (iki DDL kaynağı yasak).
- `vector(768)` hardcode'u → `settings.GEMINI_EMBEDDING_DIMENSIONS` ile hizalanır (dims drift önlenir).
- **Sağlayıcı kararı (#182 → D-NN, karar_logu):** ilk donduğunda (20 Tem) iki açık seçenek vardı — Neon/Supabase (pgvector hazır) vs Fly PG (manuel); **25 Tem D-46 ile self-host'a çözüldü** — aynı VDS'te docker compose Postgres+pgvector servisi (#246, bkz. Ek A `DATABASE_URL`). Kontrat çıktısı değişmedi: `DATABASE_URL=postgresql+psycopg://…` (Ek A) · `available_extensions`'da `vector` · prod rolüyle `CREATE EXTENSION vector` + `alembic upgrade head` temiz koşar. Bir semantik query gerçek PG'de döner (Fake/SQLite değil).

---

## Ek D (20 Tem) — MCP tool sözleşmesi (#32): who_is_touching + check_scope (read)

> **Sahibi:** backend (MCP dilimi, `src/mcp/ensemble_mcp/`) · **Tüketicisi:** AI araçları (Claude Code / Cursor / …, `.mcp.json` ile bağlanan). 🔒 **FROZEN tool imzaları** — mantık engine'e delege eder, yeniden yazılmaz (dizin_yapisi §5).

```python
# FastMCP server (transport: local stdio / hosted HTTP-SSE) — READ-ONLY tool'lar:

who_is_touching(module: str | None = None) -> list[PresenceEntry]
#   → HarnessPort.read_active() (ensemble_shared.harness) projeksiyonu; module verilirse o modüle filtre.
#   PresenceEntry = S2 Ek B1 (ActorRef + module + task + branch + since). HTTP /presence (Ek B2) ile aynı veri.

check_scope(ref: str) -> ScopeVerdict
#   → ScopeService.check_scope(ref) (engine/scope.py) delegasyonu — HTTP /scope/check (Ek B4) ikizi,
#     TEK motor iki yüz (drift mantığı #31'de bir kez yazılır).
```

- **Kapsam sınırı:** `declare_work` (yazma, ajanın kendi `active/<handle>-claude.md`'si) = **S3 write-back / stretch** — #32 yalnız **read**. Read tool'lar aynı Protocol'leri (HarnessPort read tarafı + ScopeService) tüketir → HTTP ile bit-bit tutarlı, mock harness fixture'ıyla test edilir.
- **Tazelik:** MCP okuması da projeksiyon üzerinden; çelişkide `.harness` kazanır (dizin_yapisi §7).

**ADDITIVE NOT (30 Tem, #332 — `GET /settings/mcp`):** tool imzaları DEĞİŞMEDİ; değişen yalnız *bağlanma reçetesini dağıtan* uç. `{config_json, yol}` alanları **aynen duruyor** (eski istemci kırılmaz), yanlarına eklendi:

```
GET /settings/mcp -> 200 {config_json, yol,            # T-307, DEĞİŞMEDİ (= Claude Code kaydı)
                          mod: "local"|"hosted",
                          araclar: [{arac, ad, bicim: "json"|"toml", yol,
                                     config_metni, paylasimli_dosya, aciklama, kaynak}],
                          hosted_notu: str|null}
```

- **Davranış değişikliği (bilinçli):** bu uç hosted'da artık **404 değil**. Gerekçe: anahtar okumaz/yazmaz, dolayısıyla `_require_local_mode`'un koruduğu riski taşımaz; hosted'da 404 kullanıcıya *sessiz bir duvardı*. Şimdi 200 + `hosted_notu` (MCP'nin neden yalnız yerel bir stdio süreci olduğu). **Anahtar uçlarının (`/saglayici`, `/test`) 404'ü YERİNDE** ve testle kilitli.
- Araç→yol/biçim tablosunun kanonik kaynağı: `src/backend/ensemble/mcp_clients.py` (her satırın yanında doğrulandığı resmî belge). İnsan özeti: `AGENTS.md` §"MCP: kendi aracını bağla".

---

## Ek E (20 Tem) — Frontend ↔ backend tüketim haritası (#33 · #105 · #129)

> **Sahibi:** frontend (Fatih) · **Tüketicisi:** yok (uç tüketici). 🔒 **Kural:** sayfalar backend'e **YALNIZ üretilmiş `src/api/` client'ı** üzerinden erişir (`api.GET(...)`, elle `fetch`/axios YOK — `lib/api.ts` tek giriş). Tümü `usePolling` konvansiyonundan geçer (~10 sn, arka planda durur; D-34 sahte-canlılık yasak).

| Sayfa | Tükettiği endpoint(ler) | Kaynak issue | Not |
|---|---|---|---|
| **Board** | `GET /board` (Ek B1) | #33 | kendiliğinden dolan board; `last_event` provenance satırı |
| **Ask** | `GET /query?q=` (Ek B3) | #33 | NL "beyne sor" + `[cite:…]` alıntı side-sheet'i |
| **Activity** | `GET /events?since=/before=/…` + `GET /presence` (Ek B2) | #33 | artımlı feed (since=) + presence şeridi (ETag) |
| **Radar ısı matrisi** | `GET /graph?window_days=` (Ek B5) | #105 | radarın "nedeni"; hücre → event/PR listesi; renk `Detection.actors` ile tutarlı |
| **Actors `/:handle`** | **YENİ endpoint YOK** — client-side filtre | #129 | `/graph` (TouchGraph) + `/board` (BoardCard) + `/radar` (Detection) filtreleri + derin-link query-param'ları: `/board?assignee=` · `/radar?actor=` · `/graph` filtreli |

- **Codegen zinciri (frozen):** `openapi.json` → `npm run gen:api` → `src/api/schema.d.ts` → `lib/api.ts` (`openapi-fetch`, tip-güvenli). Kontrat kayarsa derleme kırılır (CI drift-check). Backend bitmeden **mock** (`VITE_MOCK=1`, yalnız local) ile paralel.
- **#129 çift-yön kanıtı:** sıfır yeni endpoint = Ek B modellerinin ikinci tüketicisi → kontrat boşluklarını erken yakalar (S2 Ek A'daki `NormalizedEvent` ikinci-tüketici mantığının aynısı).

---

## Ek F (23 Tem) — Hosted demo sertleştirme (#63): tek-repo pin + rate cap + cached verdict

> **Sahibi:** backend (rate cap + cache + repo-pin) · **Tüketicisi:** hosted demo'nun kendisi (fatura kapağı). 🔒 **FROZEN** — `DEMO_MODE` bayrağı VARSAYILAN KAPALI; local/dev davranışı bu bayrak açılmadan HİÇ değişmez. Amaç: *"Public no-login demo paid AI çağırıyor → Gemini faturası patlamasın."*

**Kapsam:** issue'nun 4 parçasından **3'ü** burada (tek-repo pin · IP/rate cap · cached verdict); **seed** #48+#191'e devredildi (gerekçe: PR gövdesi + #191 yorumu — ön-koşulu #183 hâlâ açık, ayrıca repoda `.harness/` hiç yok).

### F1 · `DEMO_MODE` tek bayrak (`config.py`) — 🔒

```python
DEMO_MODE: bool = False   # acilista fail-closed: True iken GITHUB_REPO_OWNER/NAME ZORUNLU
DEMO_RATE_WINDOW_S: int = 60
DEMO_AI_RATE_LIMIT: int = 10        # IP basina, /query + /scope/check (kullanici-girdili AI)
DEMO_AI_GLOBAL_LIMIT: int = 60      # tum IP'ler toplami — IP-rotasyonuna karsi asil tavan
DEMO_RATE_LIMIT: int = 120          # IP basina, diger (poll'lanan) GET yollari
DEMO_CACHE_TTL_S: int = 900
DEMO_CACHE_MAX_ENTRIES: int = 1024
```

İkinci bir `DEMO_REPO` anahtarı **eklenmedi** — `GITHUB_REPO_OWNER`/`NAME` (Ek A) zaten reponun kanonik pin'i; demo modda bu ikisi zorunlu hâle gelir (ikinci doğruluk kaynağı yaratmamak için, bkz. `internal` TDK ilkesi).

### F2 · IP/rate cap (`api/rate_limit.py`) — 🔒 429 sözleşmesi

- Yalnız `DEMO_MODE=true` iken `create_app`'e **CORSMiddleware'DEN ÖNCE** eklenir (Starlette: son eklenen en dışta koşar — CORS dışta kalmalı ki 429 de `Access-Control-Allow-Origin` taşısın, #45/#150 dersi).
- **Muaf:** GET-dışı metodlar (webhook POST) ve `/health` (Fly health-check).
- **AI kovası** = yalnız `/query` + `/scope/check` (gerçekten Gemini çağıran, kullanıcı-girdili yollar). `/radar` bilerek **genel kovada** — frontend'i 10 sn'de bir poll'layan kendi Radar sayfasını kesmesin; onun maliyetini F3 sıfırlıyor.
- AI kovasında **iki sayaç**: IP anahtarı (`DEMO_AI_RATE_LIMIT`) + `"*"` global anahtarı (`DEMO_AI_GLOBAL_LIMIT`) — IP rotasyonuna karşı.
- 🆕 #63 (G6) — **genel kova da global tavan taşır:** `/radar` bilerek genel kovada olduğu için eskiden yalnız IP-başına (`DEMO_RATE_LIMIT`) sınırlıydı; sahte `Fly-Client-IP` rotasyonuyla bu sınır sonsuz kez atlatılabiliyordu (ölçüm: 2000 istek/2000 uydurma IP → 200=2000, 429=0 — fatura kapağı fiilen yoktu). Düzeltme: **yeni bir `.env` anahtarı eklenmeden**, AI kovasının zaten donmuş per-IP:global oranı (`DEMO_AI_RATE_LIMIT`:`DEMO_AI_GLOBAL_LIMIT`, varsayılan 10:60 = 6x) genel kovaya da uygulanan **türetilmiş** bir global sayaçla (`_general_global_limit = round(DEMO_RATE_LIMIT * DEMO_AI_GLOBAL_LIMIT / DEMO_AI_RATE_LIMIT)`) genişletildi. Varsayılan ayarlarla: aynı 2000-sahte-IP senaryosu düzeltmeden sonra 200=720, 429=1280 döner (türetilen tavan 120·60/10=720 ile birebir).
- `client_ip()` önceliği: `Fly-Client-IP` > `X-Forwarded-For` ilk kayıt > `request.client.host` > `"unknown"`.
- Aşımda **429** + `Retry-After: <saniye>` + kanonik `ErrorEnvelope`: `{"error": "demo_rate_limited", "message": "...", "status": 429}` — Ek D zarfının bir üyesi, `errors.py::ERROR_RESPONSES`'a koşulsuz eklendi (openapi drift-check kararsızlaşmasın).
- **Kabul edilen risk:** IP başlığı istemci tarafından uydurulabilir — bu bir MALİYET KAPAĞI, güvenlik sınırı değil; uydurmaya karşı asıl koruma global tavandır.

### F3 · Cached verdict (`engine/cache.py`) — 🔒 mevcut Protocol'ler AYNEN

- `TtlLruCache` (TTL + LRU boyut sınırı) + üç ince sarmalayıcı — **hiçbir port imzası değişmez**: `CachedConflictJudge(JudgePort)` · `CachedQueryJudge(QueryJudgePort)` · `CachedScopeJudge(ScopeJudgePort)`. Anahtar = girdinin içerik-hash'i (`sha256`, `content_hash()` ile aynı felsefe) — kimlik değil içerik keyed.
- Wiring yalnız `DEMO_MODE=true` iken, `app.py`'de mevcut fabrikaların (`build_query_judge`, `build_scope_judge`, `_build_judge_port`) çıktısının ÜSTÜNE sarılır; `integrations/gemini/*` hiç değişmez.
- **Asıl hedef:** `RadarService.get_detections()` her istekte her aday çifti yeniden yargılıyordu; frontend `usePolling` ~10 sn'de bir tüm Radar sayfasını yeniliyor — tek açık sekme dakikada 6 kez aynı çiftleri Gemini'ye yeniden sorduruyordu. Cache bunu HIT'e çevirir.
- `CachedEmbeddings` (mevcut, embeddings.py) demo modda `max_entries=DEMO_CACHE_MAX_ENTRIES` alır (serbest metin `q` sınırsız büyümesin — 512 MB Fly VM); local/dev'de `max_entries=None` (bugünkü sınırsız davranış, sıfır regresyon).

### F4 · Tek read-only repo'ya sabitleme (`api/routers/webhook.py`) — 🔒

- İmza doğrulaması + JSON parse'tan **sonra**, event işlemeden **önce**: `DEMO_MODE=true` ve gelen `repository.full_name` yapılandırılan `GITHUB_REPO_OWNER/NAME` ile eşleşmiyorsa event **202 `{"status":"ignored","reason":"repo_not_pinned"}`** ile yok sayılır — DB'ye tek satır yazılmaz. 4xx DEĞİL (GitHub'ın webhook'u devre dışı bırakmasını önlemek için `ping` ile aynı desen).
- Pin kontrolü imza doğrulamasının **ardından** çalışır (sıra bozulursa güvenlik gerilemesi — testle kilitli).

### F5 · Bilinçli sınırlar (kayıt için)

- **In-memory + tek instance:** sayaç/cache Fly makinesi durup kalkınca sıfırlanır (`fly.toml`: `auto_stop_machines=stop`, `min_machines_running=1`). Dağıtık sayaç (Redis) **bilerek kapsam dışı** (`kapsam-sinirlari.md` queue/worker yasağı).
- **Bayatlık:** TTL 900 sn → demo taze bir push'u en fazla ~15 dk geç gösterebilir; verdict içerik-anahtarlı olduğu için YANLIŞ cevap üretmez, yalnız gecikir.
- **Seed** (#48/#191) bu ekin kapsamında DEĞİL — ön-koşulu #183 açık kaldığı sürece hosted store boş projeksiyon döner.

---

## Ek G (28 Tem) — Aktör doğrulama (#296, T-296): `NormalizedEvent.actor_verified`

> **Yalnız EKLEME** — S2 §1'in donmuş `NormalizedEvent` imzasına dokunulmadı (aynı "Ek D"/"Ek F" desenindeki additive genişletme). Teşhis: ingest, commit yazarını GitHub hesabıyla (`author.login` / webhook `author.username`) eşleştiremediğinde ham git commit adına DÜŞER (`commit.author.name`); bu düşüş bugüne kadar arayüzde görünmezdi ("Merge Simulation" vakası — dogfood bulgusu, #296).

```python
class NormalizedEvent(BaseModel):
    ...                          # S2 §1 AYNEN — hiçbir alan değişmedi/silinmedi
    actor_verified: bool = True  # 🆕 YALNIZ EKLEME, varsayılan True ("doğrulanmış")

class GraphNode(BaseModel):      # S2 Ek A (#106 ile donmuş)
    ...                          # id/type/weight AYNEN — hiçbir alan değişmedi/silinmedi
    actor_verified: bool = True  # 🆕 YALNIZ EKLEME (28 Tem, PO talebi) — yalnız type="actor" anlamlı
```

- **Üretici:** `integrations/github/normalize.py::commit_to_event` (REST) + `webhook_push_to_events` (webhook `push`). Tercih sırası KİLİTLİ: `login`/`username` VARSA ham ad ASLA kullanılmaz; düşüldüğünde `logger.warning` ile (hangi commit/sha, hangi ham ad) GÖRÜNÜR kılınır.
- **Projeksiyon:** `store/models.py::EventRow.actor_verified` (`server_default=true`) — migration `3a2ba7afdced`. Mevcut satırlar (PO kararı: olası eşleşmeyen eski satırlar dahil, #296 "kısa vadeli temizlik" notu) güvenli varsayılana düşer, geçmiş yeniden yorumlanmaz.
- **Tüketici 1 — Activity sayfası** (`GET /events` → `NormalizedEvent[]`, Ek B5 AYNEN): aktör grubunun ÇİPİ `ActorChip`'in `verified` prop'unu doğrudan `NormalizedEvent.actor_verified`'ten alır (bir grupta HERHANGİ BİR olay eşleşmediyse grup işaretlenir).
- **Tüketici 2 — `GET /graph`** (`TouchGraph` → `GraphNode`, S2 Ek A): PO bu hatayı İLK burada gördü ("Merge Simulation" grafta 5. takım üyesi gibi göründü, issue buradan çıktı) — o yüzden işaretleme yalnız Activity'de bırakılmadı. `engine/graph.py::build_touch_graph` her aktör düğümü için pencheredeki TÜM olaylarını tarar; **toplama kuralı BİLEREK "en az bir olay doğrulandıysa aktör doğrulanmış sayılır"** (OR) — tersi (tek eşleşmeyen olay komple işaretlesin, AND) DEĞİL, çünkü aynı kişi bazı commit'lerini doğru `git config` ile bazılarını yanlışla atmış olabilir; login/username eşleşen TEK bir olay bile o kişinin gerçek bir GitHub kullanıcısı olduğunun güçlü kanıtıdır, komple "eşleşmedi" göstermek yanlış alarm üretir. Yalnız aktörün TÜM olayları eşleşmediyse ("Merge Simulation" vakası — ham ad hiçbir zaman login/username OLAMAZ) düğüm işaretlenir. Gerekçe kod yorumunda da var (`engine/graph.py` ilgili satır). `GraphPage.tsx` (Isı matrisi + Treemap, her ikisi de aynı `TouchGraph`'tan türer) ve `IsiMatrisi.tsx` (Radar'a gömülü panel, AYNI grafiği çizer) hepsi `nodes`'tan bir `aktör -> doğrulandı mı` haritası kurup `ActorChip`'e geçirir.
- **KAPSAM DIŞI (bilinçli, "neden" kaydı):** `Detection.actors` (Radar, `GET /radar`) ve `BoardCard.assignee` (Board, `GET /board`) BU EKİN KAPSAMINDA DEĞİL. `BoardCard.assignee` `.harness/tasks/*.md`'den gelen insan-editable bir alan — bir GitHub commit/PR/issue event'i DEĞİL, dolayısıyla `actor_verified` sinyali kavramsal olarak orada YOK (kim atandığını insan yazar, ingest türetmez). `Detection.actors` ise judge'ın çakışma bulduğu çift — event'lerin kendisi zaten `GET /events`/`GET /graph` üzerinden işaretli, aynı bilgiyi üçüncü bir yüzeyde tekrar taşımak (ve üç yerin birbirinden kayması riski) bu görevin kapsamına alınmadı. İkisine de taşımak AYRI bir kontrat genişletmesi ister (yeni issue) — "graf işaretliyor, board/radar neden işaretlemiyor" sorusunun cevabı burada kayıtlı.
- **`ActorChip` (`components/ui.tsx`):** yeni opsiyonel `verified?: boolean` prop'u (varsayılan `true`). `false` iken renk TEK BAŞINA değil (D-34) — avatar kesikli çerçeve + köşe rozeti (ikinci kanal) + `title`'da açık metin ("... eşleşmedi") eklenir. "Sahte kişi" DENMEZ.

---

## Ek H (30 Tem) — Agentic aksiyon (#339, D-61): `GitHubPort`'un YAZMA yüzeyi

> **Additive.** Donmuş hiçbir imza değişmedi; `GET /radar` şeması dahil **hiçbir HTTP sözleşmesi dokunulmadı** (`make openapi` çıktısı bit-bit aynı — bu yüzden `schema.d.ts` regen'i de gerekmedi). Bu ek, `GitHubPort` protokolüne **eklenen** üç metodu ve üç yeni env anahtarını kayda geçirir.

`GitHubPort` bu ekten önce **%100 salt-okunurdu** (ölçüldü 29 Tem: adapter'da tek POST/PATCH yok). Eklenen yüzey:

```python
class GitHubPort(Protocol):
    ...                                                    # mevcut dört metod AYNEN
    def pull_request_open(self, number: int) -> bool: ...              # 🆕 #339
    def list_pull_request_comment_bodies(self, number: int) -> list[str]: ...  # 🆕
    def create_pull_request_comment(self, number: int, body: str) -> str: ...  # 🆕
```

- **Üç ayrı metod, tek "yorum at" değil:** "yazabilir miyim" ve "zaten yazdım mı" kararları yazmanın KENDİSİNDEN önce ve ondan bağımsız alınır — tek metod olsaydı guard'lar adapter'ın içine gömülür ve engine'den test edilemezdi.
- **Hiçbiri "bilemedim"i bir değere çökertmez.** PR durumu okunamıyorsa `False` (=kapalı) değil **istisna** beklenir (`JudgeUnavailableError` ile aynı ders, #252): "kapalı" bir olgu, "bilmiyorum" olgunun yokluğu.
- **Uygulamalar:** gerçek → `integrations/github/write.py::GitHubWriteMixin` (`GitHubAdapter` miras alır) · fake → `integrations/github/fake.py::FakeGitHubAdapter` (ağa çıkmayan, bellekte biriken ikiz).
- **GitHub ucu KİLİTLİ:** yorum `POST /repos/{o}/{r}/**issues**/{n}/comments`'a gider. `/pulls/{n}/comments` başka bir şeydir (satır-içi review yorumu; `commit_id`+`path`+`line` ister) — yanlış uç, testler yeşilken canlıda 422 demek olurdu. Kilit: `tests/unit/test_agentic_action.py::test_adapter_yorumu_ISSUES_ucuna_POSTlar`.

**Tüketici (bugün tek):** `engine/agentic.py::AgenticActionService` — `RadarResult.pairs`'teki `severity=high` tespitler için ilgili açık PR'lara gerekçeli uyarı yorumu bırakır. Çalıştırma: `python -m ensemble.agentic_cli` (üretimde `docker compose exec api ...`; `docs/deploy-runbook.md` §10).

**`RadarResult` (engine-içi, HTTP şeması DEĞİL) additive alan:** `pairs: list[DetectionPair]` — `detections` ile aynı sıra/aynı küme, ek olarak tespiti üreten iki `NormalizedEvent` + kesişen dosyalar. Varsayılanı boş liste; `RadarResult()`i elle kuran mevcut çağıranlar etkilenmez. `RadarResponse` (API) **değişmedi**.

**Yeni env anahtarları** (tam tablo: `docs/deploy-runbook.md` §2, satır 44a–44c):

| anahtar | default | anlamı |
|---|---|---|
| `AGENTIC_ACTIONS_ENABLED` | `false` | ana şalter; kapalıyken tek bir GitHub çağrısı bile yok |
| `AGENTIC_ACTIONS_DRY_RUN` | `true` | ne yazacağını loglar, yazmaz |
| `AGENTIC_ACTIONS_MAX_PER_RUN` | `3` (min 1) | tur başına yazma tavanı; aşan kısım loglanır + rapora girer |

Gerçek yazma = `ENABLED=true` **ve** `DRY_RUN=false` **ve** App'in `Pull requests: write` izni. Gerekçe, kapsam ayrımı ("MCP write-back" non-goal'undan farkı) ve kabul edilen riskler: `.harness/decisions/D-61-agentic-github-yazma-yolu.md`.
## Ek I (30 Tem) — Onboarding sihirbazı uçları (#340, vizyon §8.5)

> **Yalnız EKLEME.** Hiçbir donmuş imzaya (Ek B router'ları, S2 modelleri) dokunulmadı; yeni bir router (`/onboarding/*`) ve yalnız ona ait yeni modeller eklendi. `openapi.json` + `src/frontend/src/api/schema.d.ts` `make contracts` ile BİRLİKTE üretildi.

### I1 · Uç imzaları

| Uç | Girdi | Çıktı | LLM? |
|---|---|---|---|
| `GET /onboarding/durum` | — | `OnboardingDurum` | hayır |
| `POST /onboarding/sorular` | `SorularIstegi{mod,tur,brief}` | `SorularYaniti{sorular,tur,tur_bitti,eksikler}` | **hayır** |
| `POST /onboarding/brief` | `BriefIstegi{mod,serbest_metin,cevaplar,brief,varsayimlarla_doldur}` | `BriefYaniti{brief,eksikler,uyarilar,ai_kullanildi,degraded?}` | yalnız `mod="anlat"` ya da `varsayimlarla_doldur` |
| `POST /onboarding/taslak` | `TaslakIstegi{brief}` | `TaslakYaniti{taslak,degraded?}` | **evet** (1 çağrı) |
| `POST /onboarding/plan` | `PlanIstegi{storyler,kapasite}` | `SprintPlani` · 400 | **hayır** (deterministik) |
| `POST /onboarding/uygula` | `UygulaIstegi{onay,brief,taslak,plan?}` | `YazmaSonucu` · 403 · 404 · 409 | hayır |

### I2 · Donan kurallar (imza kadar bağlayıcı)

- **Durum sunucuda TUTULMAZ.** Her uç taslağın tamamını alır ve döner; "şu anki taslak"ın sahibi istemcidir. Oturum tablosu/temizleyicisi YOK.
- **K6 (kilitli):** `POST /onboarding/uygula` `onay.onaylandi is true` DEĞİLSE **403** döner ve *hiçbir dosyaya dokunmaz* (`.harness/` dizini bile oluşmaz). Kapı `onboarding/apply.py::harness_yaz`'ın ilk satırıdır; mutasyonla kilitli (`tests/unit/test_onboarding_onay_kapisi.py`).
- **Yazma yalnız local:** `ENSEMBLE_MODE != "local"` → `uygula` **404** (`settings.py` KURAL 1'in aynısı, aynı gerekçe). Diğer beş uç her modda çalışır (jüri hosted demoda sihirbazı görebilsin).
- **Yazma kökü = `Path.cwd()`** — ürünün geri kalanı `.harness/`'i `FileHarnessPort()` (varsayılan kök `"."`) ile cwd'den okuyor; masaüstü paketi (`packaging/launcher.py`) açılışta `os.chdir(data_dir)` yapıyor. Dosya konumundan türetilen bir kök orada .app paketinin içini gösterirdi.
- **Üzerine YAZMA yok:** hedef `scope/sprint-N.md` (ya da task dosyası) zaten varsa **409**, dosya adları listelenir; PO'nun dondurduğu kapsam ezilmez.
- **`degraded` (yeni model `OnboardingDegraded{asama,saglayici,neden}`):** `RadarResponse.degraded` deseninin aynısı (#252). LLM aşaması düşerse 200 + BOŞ taslak + DOLU `degraded`. Uydurma taslak ÜRETİLMEZ; `build_drafter` sağlayıcı yoksa `None` döner (bilinçli olarak `Fake*Drafter` YOK).
- **Sağlayıcı zinciri:** Gemini → Groq yedeği (`FallbackOnboardingDrafter`, `engine/fallback.FallbackJudge` deseni). `LLM_PROVIDER=ollama` iken bulut yedeği **devreye girmez** (README "tam-yerel gizlilik modu" taahhüdü, #255 kararının aynısı).

### I3 · Ek F ekleme: demo rate-limit artık POST da ölçer

`api/rate_limit.py`'ye `AI_METERED_POST_PATHS = {"/onboarding/brief", "/onboarding/taslak"}` eklendi. Ek F'deki GET kovaları ve limitleri **DEĞİŞMEDİ**; yalnız bu iki POST yolu AI kovasına dahil edildi. Gerekçe: middleware `request.method != "GET"` ile başlıyordu, dolayısıyla kullanıcı-girdili serbest metin + Gemini çağrısı taşıyan bu iki uç hosted demoda **kapaksız** kalırdı. Sihirbazın deterministik uçları (`/sorular`, `/plan`, `/durum`) bilerek DIŞARIDA — ağsız ve ücretsizler.

---

## Pratik: S3 paralel çalışma reçetesi

- **Sprint başı (bugün):** bu dosya (Ek A–E) donar → herkes kendi diliminde mock/fixture ile başlar.
- **Infra (#181/#182/#186/#190):** Ek A tablosuyla self-host VDS/Vercel/Postgres+pgvector kurar (D-46); frontend'i beklemez (mock origin).
- **Backend router (#51/#52/#59/#104):** Ek B imzalarını implement eder; fake harness/store fixture'ıyla test.
- **AI (#58):** `GET /query` RAG'ını `VectorIndexPort` + fake retrieval ile yazar; gerçek PG'yi sonra bağlar (Ek C).
- **Store (#183):** app-boot DI + DDL tek-kaynak; local davranışı bozmadan hosted'ı ekler.
- **MCP (#32):** engine'e delege eden read tool'lar; HTTP ile aynı motoru paylaşır (Ek D).
- **Frontend (#33/#105/#129):** üretilen client + mock ile 5 sayfayı yapar; entegrasyonda `VITE_API_BASE_URL`'i gerçek self-host backend URL'ine çevirir (Ek A2, D-46).

> **Kural (S2'den devam):** kontrat değişikliği = bu dosyaya PR + daily'de duyuru. Sessizce imza/env-yeri değiştirme — birinin stub'ını ya da deploy'unu kırarsın.
