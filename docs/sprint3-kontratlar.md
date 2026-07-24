# Sprint-3 Kontratları (girdi → çıktı)

> **Amaç:** Sprint-3 = **go-live (canlıya alma) + web MVP'nin gerisi** — deploy mekaniği, kalan router'lar (/board · /events · /presence · /query · /scope · /graph), store/pgvector'ün canlı bağlanması, MCP okuma yüzü ve üç frontend sayfası **aynı anda, farklı kişilerde** ilerliyor. Kimse kimseyi beklemesin diye arayüzler **sprint başında donuyor** (retro aksiyonu **R2** · D-22: kontrat-önce paralelleşme). Kontrat değişirse buraya PR aç + daily'de duyur.

## İlke: kontrat-önce, paralel geliştirme (S3'te üç tür kontrat)

S2'deki iki tür kontrata (HTTP openapi + Python Protocol) S3'te **üçüncüsü** ekleniyor — go-live bunu zorunlu kılıyor:

1. **HTTP (FastAPI ↔ frontend):** endpoint'ler Pydantic modellerden **`src/shared/openapi.json`** üretir → frontend TS client *otomatik* (`npm run gen:api` → `src/api/schema.d.ts`). Frontend backend bitmeden client'ı üretip **mock veriyle** çalışır.
2. **Python Protocol (katmanlar arası):** her bağımlılık bir `Protocol` arkasında (`ensemble/ports.py`, `ensemble_shared/harness.py`) → **fake adapter** ile stub'lanır (PgVector gerçek Postgres olmadan, MCP gerçek harness olmadan test edilir).
3. **🆕 Deploy env eşlemesi (kod ↔ platform):** her env değişkeni **NEREDE** tutulur (Fly secret / Vercel env / CI secret / yalnız-local) ve hangi ikili **çift-yönlü kilitli** (CORS_ORIGINS ↔ VITE_API_BASE_URL). Bu donmadan iki kişi (infra + frontend) birbirinin URL'ini tahmin ederek çalışır → canlıda CORS/base-URL çakışması. Eşleme donunca ikisi de mock origin'le paralel gider.

```
Fly secret ─env─> FastAPI (ENSEMBLE_MODE=hosted) ─Protocol─> engine ─Protocol─> PgVectorIndex ─> managed PG
   (Ek A)              (Ek B: router imzaları)      (Ek C store DI)     (Ek C)          (#182)
                              │  ▲
              openapi.json ───┘  └─── MCP read tools (Ek D)
                    │
   Vercel env ─VITE_API_BASE_URL─> frontend TS client ─> Board · Ask · Activity · Heatmap · Actors (Ek E)
```

> **Not (TDK):** S2 Ek A–D'de donmuş **model** şekilleri (Detection, BoardCard.last_event, PresenceEntry, ScopeVerdict, Citation, TouchGraph, ErrorEnvelope…) burada **yeniden tanımlanmaz** — S3 yalnız o modelleri taşıyan **router/adapter/env imzalarını** dondurur ve S2'ye link verir. Kanonik model kaynağı: `ensemble/models.py` + `ensemble/api/schemas.py`; kanonik port kaynağı: `ensemble/ports.py`.

---

## Ek A (20 Tem) — Deploy env sözleşmesi (#181 · #186 · #190): her sır NEREDE yaşar

> **Sahibi:** infra (deploy dilimi) · **Tüketicisi:** herkes (backend çalışma-zamanı, frontend build, CI). 🔒 **FROZEN** — bu tablo `docs/deploy-runbook.md`'nin (#190) tek kaynağıdır; `.env.example` anahtarı eklenince buraya da satır eklenir.

### A1 · Env → platform eşleme tablosu (#190 kabul kriteri)

| Env anahtarı | Nerede tutulur | Not |
|---|---|---|
| `ENSEMBLE_MODE` | **Fly secret** = `hosted` · local `.env` = `local` | hosted'da store+pgvector devreye girer (Ek C) |
| `CORS_ORIGINS` | **Fly secret** | = Vercel prod origin (**A2 çift-yön**); asla `*` (config açılışta reddeder) |
| `DATABASE_URL` | **Fly secret** | managed PG DSN `postgresql+psycopg://…` (#182) — local'de SQLite dosya yolu |
| `GEMINI_API_KEY` | **Fly secret** + **CI secret** (eval hattı) | yoksa engine Fake/Hash'e düşer (canlıda İSTENMEZ) |
| `GEMINI_MODEL` · `GEMINI_EMBEDDING_MODEL` · `GEMINI_EMBEDDING_DIMENSIONS` · `GEMINI_TIMEOUT_S` · `GEMINI_MAX_RETRIES` | **Fly secret (opsiyonel)** | kod'da varsayılan var; yalnız override gerekince set |
| `GITHUB_APP_ID` · `GITHUB_APP_INSTALLATION_ID` | **Fly secret** | makine-auth kimliği |
| `GITHUB_APP_PRIVATE_KEY` | **Fly secret (PEM İÇERİĞİ)** | 🆕 #186 — **dosya yolu DEĞİL, ham PEM metni** (A3) |
| `GITHUB_APP_PRIVATE_KEY_PATH` | **yalnız-local** | geliştiricinin diskindeki `.pem`; Fly'da **boş** (mount yok) |
| `GITHUB_REPO_OWNER` · `GITHUB_REPO_NAME` | **Fly secret** | izlenen repo |
| `GITHUB_DEFAULT_BRANCH` | **Fly secret (opsiyonel)** | varsayılan `main` |
| `GITHUB_WEBHOOK_SECRET` | **Fly secret** | webhook imza doğrulaması (D-35) |
| `GITHUB_WEBHOOK_PROXY_URL` | **yalnız-local** (smee kanalı) | hosted'da webhook doğrudan Fly URL'ine gelir → boş |
| `RADAR_WINDOW_DAYS` · `RADAR_MIN_JACCARD` · `RADAR_MIN_SIMILARITY` | **Fly secret (opsiyonel)** | kalibrasyon çıktısı (#18); kod default'u kanonik |
| `DEMO_MODE` | **Fly secret** = `true` (`fly.toml [env]`, sır değil ama tek-satırlık açma/kapama bayrağı burada yaşar) | 🆕 #63 — açılışta fail-closed: `true` iken `GITHUB_REPO_OWNER`/`NAME` zorunlu (bkz. Ek F) |
| `DEMO_RATE_WINDOW_S` · `DEMO_AI_RATE_LIMIT` · `DEMO_AI_GLOBAL_LIMIT` · `DEMO_RATE_LIMIT` · `DEMO_CACHE_TTL_S` · `DEMO_CACHE_MAX_ENTRIES` | **Fly secret (opsiyonel)** | 🆕 #63 — kod default'u kanonik; yalnız override gerekince set (bkz. Ek F) |
| `VITE_API_BASE_URL` | **Vercel env (build-time)** | = Fly backend public URL (**A2 çift-yön**); origin-only, query/hash yasak |
| `VITE_MOCK` | **yalnız-local** · Vercel'de **BOŞ** | prod'da fixture chunk'ı sızmasın (yalnız `"1"` mock açar) |
| `FLY_API_TOKEN` | **CI secret** | deploy pipeline (GitHub Actions → `fly deploy`) |

> **yalnız-local** = platforma **hiç** girilmez; **Fly secret** = backend çalışma-zamanı; **Vercel env** = frontend build-time; **CI secret** = pipeline. Aynı anahtar iki sütunda olamaz (tek doğruluk); istisna = local ile hosted'ın FARKLI değeri (ENSEMBLE_MODE, DATABASE_URL, PRIVATE_KEY yolu-vs-içeriği).

### A2 · Çift-yönlü kilit: `CORS_ORIGINS` ↔ `VITE_API_BASE_URL` (🔒 birlikte değişir)

İki ayrı platformda yaşayan **tek** kontrat — biri değişince diğeri **zorunlu** değişir:

```
Fly:    CORS_ORIGINS      = https://<vercel-app>.vercel.app     # backend KİMİ kabul eder
Vercel: VITE_API_BASE_URL = https://<fly-app>.fly.dev           # frontend KİME gider
```

- **Kural:** biri güncellenince diğeri aynı PR/deploy penceresinde güncellenir; tek taraflı değişiklik = tarayıcıda "CORS error" (gerçek hatayı gizler — S2 #45/#150 dersi). Hata cevapları bile `Access-Control-Allow-Origin` taşır (Ek D, S2).
- **Paralel çalışma:** infra mock Vercel origin'iyle, frontend mock Fly URL'iyle başlar; entegrasyonda ikisi gerçek değerle **aynı anda** set edilir.

### A3 · `GITHUB_APP_PRIVATE_KEY` imza eklemesi (#186 — 🔒 config + auth)

Fly/Render secret'ları env-**string**; mount'lu dosya değil → hosted'a PEM dosya-yoluyla verilemez. Yeni alan + çözümleme sırası donuyor:

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

Mevcut router'lar: `/health` · `/radar` · `/scope/check` · `/board` · `/query` (openapi'de var). S3 bunları **zenginleştirir** + `/events` · `/presence` · `/graph` **ekler**.

### B1 · `GET /board` (#51) — 🔒

```
GET /board  →  BoardResponse { cards: BoardCard[] }
```
- `BoardCard` = S2 Ek B2 (mevcut alanlar + `last_event: LastEvent | None`). Model AYNEN; route donuyor.
- Kaynak: `#41` projeksiyonu üzerinde **ince okuma** — `BoardService(session_factory).get_cards()` (mevcut imza, `engine/board.py`). Durum geçişini yalnız ingest yazar (TDK).
- **Sahibi:** backend (Enes) · **Tüketicisi:** Board sayfası (#33).

### B2 · `GET /events` + `GET /presence` (#52) — artımlı polling cursor 🔒

```
GET /events?since=<ISO>&before=<ISO|id>&limit=<n>&actor=<handle>&branch=<ad>
  →  { events: NormalizedEvent[], has_more: bool }              # S2 Ek B5 imzası, AYNEN

GET /presence   [If-None-Match: "<etag>"]
  →  200 { entries: PresenceEntry[], updated_at }  +  ETag: "<hash>"      # S2 Ek B1
  →  304 (gövdesiz)  eğer If-None-Match eşleşirse                          # artımlı: boşuna byte çekme
```
- **Cursor sözleşmesi (frozen):** `/events` = `since=` (bu andan sonrası, artımlı) + `before=` sayfalama (aynı-saniye tie-break: `id`). `/presence` = **ETag** (küçük ve tümü döner; değişmediyse `304`). Polling her tick tüm feed'i çekmez.
- `NormalizedEvent` (S2 §1) + `PresenceEntry` (S2 Ek B1) AYNEN. `type=` filtresi v1'de YOK (client-side, Ek B5 notu).
- **Sahibi:** backend (Esma) · **Tüketicisi:** Activity feed (#33) + MCP `who_is_touching` (Ek D).

### B3 · `GET /query` (#58, Ask) — RAG + gerekçeli cevap 🔒

```
GET /query?q=<nl>  →  QueryResponse                             # S2 Ek B4 zenginleştirilmiş şekil
#   { answer (içinde [cite:…] placeholder), citations: (str | Citation)[],
#     as_of, last_commit, window?, confidence, status, searched[], nearest[] }
```
- Akış: NL → vektör retrieval (`.harness` + events, Ek C VectorIndexPort.query) → Gemini `JudgePort`-benzeri gerekçeli yanıt. Yanıt modeli S2 Ek B4'te kilitli; #58 `api/schemas.py` `QueryResponse`'u B4'e **yükseltir** (imza S2'de donuk, route burada donuyor).
- Tek-atım (SSE streaming S3'te YOK — S2 Ek B6, sahte-canlılık yasak D-34). `status="not_found"` = dürüst red (`searched`/`nearest` fişleri).
- **Sahibi:** AI (Semih) · **Tüketicisi:** Ask sayfası (#33).

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

---

## Ek C (20 Tem) — Store / pgvector portu (#183 · #182): app-boot DI + DDL tek-kaynak

> **Sahibi:** store (Enes) · **Tüketicisi:** RadarService / QueryService (retrieval). 🔒 **FROZEN** port imzaları — `VectorIndexPort` S2 §2'de donuk; burada **hosted adapter ctor + fabrika + boot DI + DDL sahipliği** kilitlenir.

### C1 · Port + hosted adapter imzası (mevcut kod — `store/vector_store.py`) 🔒

```python
class VectorIndexPort(Protocol):                                # S2 §2, AYNEN
    def upsert(self, id: str, vec: list[float], meta: dict) -> None: ...
    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]: ...

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
- **Sağlayıcı kararı (#182 → yeni D-NN, karar_logu):** Neon/Supabase (pgvector hazır) vs Fly PG (manuel) — gerekçeli seç. Kontrat çıktısı: `DATABASE_URL=postgresql+psycopg://…` (Ek A) · `available_extensions`'da `vector` · prod rolüyle `CREATE EXTENSION vector` + `alembic upgrade head` temiz koşar. Bir semantik query gerçek PG'de döner (Fake/SQLite değil).

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
DEMO_CACHE_MAX_ENTRIES: int = 256
```

İkinci bir `DEMO_REPO` anahtarı **eklenmedi** — `GITHUB_REPO_OWNER`/`NAME` (Ek A) zaten reponun kanonik pin'i; demo modda bu ikisi zorunlu hâle gelir (ikinci doğruluk kaynağı yaratmamak için, bkz. `internal` TDK ilkesi).

### F2 · IP/rate cap (`api/rate_limit.py`) — 🔒 429 sözleşmesi

- Yalnız `DEMO_MODE=true` iken `create_app`'e **CORSMiddleware'DEN ÖNCE** eklenir (Starlette: son eklenen en dışta koşar — CORS dışta kalmalı ki 429 de `Access-Control-Allow-Origin` taşısın, #45/#150 dersi).
- **Muaf:** GET-dışı metodlar (webhook POST) ve `/health` (Fly health-check).
- **AI kovası** = yalnız `/query` + `/scope/check` (gerçekten Gemini çağıran, kullanıcı-girdili yollar). `/radar` bilerek **genel kovada** — frontend'i 10 sn'de bir poll'layan kendi Radar sayfasını kesmesin; onun maliyetini F3 sıfırlıyor.
- AI kovasında **iki sayaç**: IP anahtarı (`DEMO_AI_RATE_LIMIT`) + `"*"` global anahtarı (`DEMO_AI_GLOBAL_LIMIT`) — IP rotasyonuna karşı.
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

## Pratik: S3 paralel çalışma reçetesi

- **Sprint başı (bugün):** bu dosya (Ek A–E) donar → herkes kendi diliminde mock/fixture ile başlar.
- **Infra (#181/#182/#186/#190):** Ek A tablosuyla Fly/Vercel/managed-PG kurar; frontend'i beklemez (mock origin).
- **Backend router (#51/#52/#59/#104):** Ek B imzalarını implement eder; fake harness/store fixture'ıyla test.
- **AI (#58):** `GET /query` RAG'ını `VectorIndexPort` + fake retrieval ile yazar; gerçek PG'yi sonra bağlar (Ek C).
- **Store (#183):** app-boot DI + DDL tek-kaynak; local davranışı bozmadan hosted'ı ekler.
- **MCP (#32):** engine'e delege eden read tool'lar; HTTP ile aynı motoru paylaşır (Ek D).
- **Frontend (#33/#105/#129):** üretilen client + mock ile 5 sayfayı yapar; entegrasyonda `VITE_API_BASE_URL`'i gerçek Fly URL'ine çevirir (Ek A2).

> **Kural (S2'den devam):** kontrat değişikliği = bu dosyaya PR + daily'de duyuru. Sessizce imza/env-yeri değiştirme — birinin stub'ını ya da deploy'unu kırarsın.
