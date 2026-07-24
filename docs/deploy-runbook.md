# Deploy Runbook — Ensemble (Fly.io + Vercel)

> **Ne:** Ensemble backend'ini Fly.io'ya, frontend'ini Vercel'e canlıya almanın **operatör** rehberi — env→platform eşlemesi, ilk deploy sırası, doğrulama, rollback. **Kim:** infra dilimini yürüten kişi (bugün: Fatih); ekip içinde herkes okuyabilir. **Ne zaman:** go-live'da ve her rollback/rotasyon gerektiğinde.
>
> **Sır hijyeni (baştan, tekrar tekrar):** bu dosyada hiçbir yerde **gerçek** bir secret DEĞERİ yazılmaz — yalnız `<placeholder>`. Bir değeri kopyalayıp buraya yapıştırmak yasak.
>
> **Kanonik kaynak zinciri** (çelişki olursa bu sıra kazanır):
> 1. [`docs/sprint3-kontratlar.md`](sprint3-kontratlar.md) **Ek A** — 🔒 FROZEN env→platform eşleme tablosu; bu runbook onun **operasyonel uygulamasıdır** (kod/komut seviyesi). Ek A'da satırı olmayan ama `.env.example`'da olan anahtarlar bu dosyada **§2 sonunda ayrıca not edilir** (bkz. "Ek A'nın kapsamadığı anahtarlar") — kontrat metnine dokunulmadı.
> 2. [`docs/github-app-kurulum.md`](github-app-kurulum.md) — GitHub App kimliği + PEM elde etme.
> 3. [`docs/gelistirme-dongusu.md`](gelistirme-dongusu.md) — DONE kapısı (bu iş bittiğinde neyin kanıtlanması gerektiği).
>
> **Bu doküman bir uygulama günlüğü değildir** — komutları verir, gerçek deploy'u yapan kişi kendi terminalinde koşturur. Placeholder'lar `<bu-şekilde>` yazılır.

---

## 0. Önce oku, sonra koş

Aşağıdaki adımlar **sıralıdır** — atlarsan bir sonraki adım anlamsız bir hatayla patlar (örn. secret'ı app'ten önce eklemek). İlk kez deploy ediyorsan §3'ü baştan sona, tek oturumda takip et. Yalnızca bir secret'ı rotate ediyorsan §9'a, yalnızca geri alıyorsan §5'e atla.

Bu doküman `T-190-deploy-runbook` dalının kendisi — bu dal, altındaki bağımlı işlerin (aşağıdaki tablo) **en son** merge edileceği varsayımıyla yazılıyor: `#189`/`#192`/`#63` bu dal `main`'e inene kadar zaten inmiş olur, o yüzden onlara ait bölümler **bugünkü davranış** olarak yazıldı (hedge yok). `#187` ve `#182`/`#183` için böyle bir sıralama garantisi **yok** — onlar hâlâ **"hedef durum"** olarak işaretli (bkz. §8 ve ilgili notlar):

| Bağımlı iş | Durum (bu dal `main`'e inerken) | Bu runbook'taki karşılığı |
|---|---|---|
| **#189** — `scripts/smoke.py` + `make smoke` | `main`'de (bu dal en son merge edildiği için önden gelmiş varsayılır) | §4 — komut doğrudan kullanılır |
| **#192** — `.github/workflows/deploy.yml` (CD) | `main`'de (yukarıdaki gerekçeyle) | §3 adım 10 |
| **#63** — `DEMO_MODE` hosted sertleştirme | `main`'de (yukarıdaki gerekçeyle) | §6 |
| **#187** — `release_command` (alembic-on-deploy) | **hedef durum** — henüz yok, `fly.toml` başlığı bunu açıkça diğer bir işe devretmiş | §3 adım 6 |
| **#182/#183** — self-host pgvector app + hosted DI | **hedef durum** — D-39 kararı Ek C3'te donuk; sağlayıcı kurulumu ayrı iş | §3 adım 2–3 |

> ⚠️ Bu varsayım yanlış çıkarsa (örn. `#189`/`#192`/`#63` bu dal merge olurken hâlâ `main`'de değilse) §4 ve §6'daki ilgili bölümler geçici olarak yine "henüz `main`'de değil" hedge'iyle okunmalı — operatör deploy anında `git log main -- <ilgili dosya>` ile gerçek durumu doğrulasın.

---

## 1. Topoloji

```
                         ┌────────────────────────────┐
                         │  GitHub (FatihErenCetin/    │
                         │  grup54) — webhook: push,   │
                         │  pull_request, issues       │
                         └──────────────┬───────────────┘
                                        │ webhook (D-35)
                                        ▼
┌───────────────┐   build-time    ┌────────────────────────┐   .internal:5432   ┌──────────────────┐
│  Vercel (SPA)  │◄───────────────┤  Fly: ensemble-backend  ├────────────────────►│ Fly: grup54-db    │
│  vite build    │  VITE_API_     │  ENSEMBLE_MODE=hosted   │  (yalnız Fly özel   │ pgvector/pgvector │
│  Root Dir:     │  BASE_URL      │  FastAPI + uvicorn      │   ağı — public port │ :pg16 + kalıcı    │
│  src/frontend  │                │  /health /radar /board  │   YOK)               │ volume            │
│                │  CORS_ORIGINS  │  /query /scope /events  │                      │                  │
│  ─────────────►│◄───────────────┤  /presence /graph       │                      │                  │
└───────────────┘   (A2 çift-yön) └────────────┬────────────┘                      └──────────────────┘
                                               │
                          GitHub Actions ──────┘  (workflow_run: CI TAMAMI yeşil → flyctl deploy, #192)
                          CI (lint-test + gitleaks + frontend) → Deploy (Fly)
```

- **Frontend (Vercel):** statik SPA, `vite build`; `VITE_API_BASE_URL` **build-time** gömülür (rewrite kuralları `src/frontend/vercel.json`'da).
- **Backend (Fly `ensemble-backend`):** tek `fly.toml`, tek Dockerfile imajı; `/health` public health-check.
- **DB (Fly `grup54-db`):** **ayrı app**, yalnız Fly'ın özel ağı (`*.internal`) üzerinden erişilir — public port yok (D-39). DB kanonik değil, **projeksiyon** (`.harness/` + GitHub kanonik → bozulursa `make rebuild` / #191 seed).
- **CD (GitHub Actions → `deploy.yml`, #192):** yalnız `main`'e **push** + CI workflow'unun (`ci.yml`, `name: CI`) **TAMAMI** yeşil olunca `flyctl deploy` koşar — `workflow_run`'ın `conclusion == 'success'`ü tek bir job'a değil, CI'in **üçünün de** (`lint-test` + `gitleaks` + `frontend`) yeşil olduğu anlamına gelir (`eval-gate` ayrı bir job değil, `lint-test`'in içinde bir adım). Bu kapı, main'in required-check listesinden (`lint-test` + `check-single-issue` + `frontend`) **bağımsız ikinci bir katman** — biri PR aşamasında, diğeri deploy tetiklemesinde aynı "CI'in tamamı yeşil" kuralını uygular. PR/fork çalıştırmaz (fail-safe token kapısı, §3 adım 10).

---

## 2. Env → platform eşleme tablosu

`.env.example`'daki **38 anahtarın tamamı** aşağıda — bu sayı `#63` (`DEMO_MODE` + 6× `DEMO_*`, §6) `.env.example`'a eklediği 7 anahtarı da içeriyor (bu dal en son merge edildiği için §0'daki gerekçeyle `#63`'ün zaten `main`'de olduğu varsayılıyor). *(37'si düz `ANAHTAR=` satırı, 1'i — `CORS_ORIGINS` — yalnız yorum-satırı örneği; ikisi de sayılır, bkz. dosyanın kendisi.)* Dört sınıf: **Fly secret** (şifreli, `fly secrets set`) · **Vercel env** (build-time, Vercel dashboard) · **yalnız-local** (hiçbir platforma girilmez) · **CI secret** (`gh secret set`, pipeline).

> **Mekanizma kolonu neden ayrı:** aynı "Fly" sütununda iki farklı gerçek yaşıyor — `fly.toml`'ın `[env]` bloğu (**sır değil, repoda commit'li düz metin**) ile `fly secrets set` (**şifreli, repoda hiç görünmez**). İkisi de "Fly'da yaşıyor" ama biri git'te okunabilir, diğeri değil. Bu ayrım olmadan "ENSEMBLE_MODE Fly secret" cümlesi yanlış izlenim bırakır (aslında `fly.toml`'da çıplak yazıyor).

| # | Anahtar | Nerede | Mekanizma | Not |
|---|---|---|---|---|
| 1 | `ENSEMBLE_MODE` | Fly | `fly.toml` `[env]` (commit'li) | hosted'da `"hosted"` sabit; local `.env` = `local` |
| 2 | `LLM_PROVIDER` | Fly (opsiyonel) | `fly secrets set` | hosted'da `gemini` kalır — Fly VM'de Ollama **yok**; kod default'u zaten `gemini` |
| 3 | `GEMINI_API_KEY` | Fly secret **+** CI secret (ileride) | `fly secrets set` · `gh secret set` | yoksa engine `FakeJudgeAdapter`'a düşer (canlıda **istenmez**); CI bugün `eval-gate`'i `FakeJudgeAdapter` ile offline koşuyor → **bugün CI'da gerekmiyor**, eval canlı provider'a bağlanınca eklenir |
| 4 | `GEMINI_MODEL` | Fly (opsiyonel) | `fly secrets set` | kod default `gemini-2.5-flash`; yalnız override gerekince set |
| 5 | `GEMINI_EMBEDDING_MODEL` | Fly (opsiyonel) | `fly secrets set` | kod default `gemini-embedding-001` |
| 6 | `GEMINI_EMBEDDING_DIMENSIONS` | Fly (opsiyonel) | `fly secrets set` | kod default `768`; `vector(N)` migration'ıyla **hizalı** olmalı (Ek C3) |
| 7 | `GEMINI_TIMEOUT_S` | Fly (opsiyonel) | `fly secrets set` | kod default `10` |
| 8 | `GEMINI_MAX_RETRIES` | Fly (opsiyonel) | `fly secrets set` | kod default `3` |
| 9 | `OLLAMA_BASE_URL` | yalnız-local | — | Fly VM'de Ollama çalıştırılmıyor; kod zaten yalnız `127.0.0.1`/`localhost` kabul ediyor (loopback zorunluluğu) |
| 10 | `OLLAMA_MODEL` | yalnız-local | — | tam-yerel gizlilik modu (#78) |
| 11 | `OLLAMA_EMBEDDING_MODEL` | yalnız-local | — | " |
| 12 | `OLLAMA_EMBEDDING_DIMENSIONS` | yalnız-local | — | " |
| 13 | `OLLAMA_TIMEOUT_S` | yalnız-local | — | " |
| 14 | `OLLAMA_MAX_RETRIES` | yalnız-local | — | " |
| 15 | `GITHUB_APP_ID` | Fly secret | `fly secrets set` | `4257285` (sır değil ama zaten Fly secret olarak set edilir — Ek A'nın sınıflaması) |
| 16 | `GITHUB_APP_PRIVATE_KEY_PATH` | yalnız-local | — | Fly'da **boş bırak** (mount yok — imajda `.pem` dosyası yok) |
| 17 | `GITHUB_APP_PRIVATE_KEY` | Fly secret (**PEM İÇERİĞİ**) | `fly secrets set` — bkz. §3 adım 4, ayrı kutu | **path DEĞİL**, ham PEM metni; `config.py` çözümleme sırası: PATH varsa PATH kazanır (yerel), yoksa bu alan (hosted) |
| 18 | `GITHUB_APP_INSTALLATION_ID` | Fly secret | `fly secrets set` | `145474476` |
| 19 | `GITHUB_REPO_OWNER` | Fly secret | `fly secrets set` | izlenen repo sahibi |
| 20 | `GITHUB_REPO_NAME` | Fly secret | `fly secrets set` | izlenen repo adı — **`#63` ile**: `DEMO_MODE=true` iken bu ikisi eksikse uygulama **hiç açılmaz** (fail-closed, §6) |
| 21 | `GITHUB_DEFAULT_BRANCH` | Fly (opsiyonel) | `fly secrets set` | kod default `main` |
| 22 | `GITHUB_BACKFILL_LIMIT` | Fly (opsiyonel) | `fly secrets set` | kod default `50` |
| 23 | `GITHUB_WEBHOOK_SECRET` | Fly secret | `fly secrets set` | webhook imza doğrulaması (D-35); **rotate** prosedürü §9 |
| 24 | `GITHUB_WEBHOOK_PROXY_URL` | yalnız-local | — | hosted'da webhook doğrudan Fly URL'ine gelir (smee kanalı yalnız local geliştirme) |
| 25 | `RADAR_WINDOW_DAYS` | Fly (opsiyonel) | `fly secrets set` | kalibrasyon çıktısı (#18); kod default `14` |
| 26 | `RADAR_MIN_JACCARD` | Fly (opsiyonel) | `fly secrets set` | kod default `0.0` (kalibrasyon sonucu, placeholder değil — bkz. `.env.example` yorumu) |
| 27 | `RADAR_MIN_SIMILARITY` | Fly (opsiyonel) | `fly secrets set` | kod default `0.0` |
| 28 | `DATABASE_URL` | Fly secret | `fly secrets set` | `postgresql+psycopg://ensemble:<pw>@grup54-db.internal:5432/ensemble` (D-39, Ek C3) — ⚠️ **tuzak**: aşağıdaki kutuya bak |
| 29 | `VITE_API_BASE_URL` | **Vercel env** (build-time) | Vercel dashboard → *Environment Variables* → Production | = Fly backend public URL (A2 çift-yön); **yalnız origin (+ opsiyonel path öneki)** — query/hash `lib/config.ts` tarafından reddedilir, path öneki ise **korunur** (bkz. `config.ts::readApiBaseUrl` — eskiden `.origin` sessizce path'i düşürüyordu, artık düşürmüyor); değişince **redeploy şart** (build-time gömülür, "Save" yetmez) |
| 30 | `VITE_MOCK` | yalnız-local; Vercel'de **BOŞ** | — | yalnız `"1"` mock açar; prod'da tanımlarsan `vite.config.ts` build'i **kendi kırar** (#188 guard) — bu bilerek: sızıntıyı derleme aşamasında yakalar |
| 31 | `CORS_ORIGINS` | Fly secret | `fly secrets set` | = Vercel prod origin, **A2 çift-yön** (aşağıda ayrı bölüm); asla `*` — config açılışta reddeder (`config.py::_decode_cors_origins`) |

> **yalnız-local** = platforma hiç girilmez · **Fly secret** = backend çalışma-zamanı (`fly secrets set`) · **Fly `[env]`** = backend çalışma-zamanı ama sır değil, `fly.toml`'da commit'li · **Vercel env** = frontend build-time · **CI secret** = pipeline (`gh secret set`). Aynı anahtar iki sütunda **olamaz** — istisna: local ile hosted'ın **farklı** değeri (`ENSEMBLE_MODE`, `DATABASE_URL`, PEM yolu-vs-içeriği).

### Ek A'nın kapsamadığı anahtarlar (bulgu — kod/kontrat DEĞİŞTİRİLMEDİ)

`docs/sprint3-kontratlar.md` Ek A "bu tablo runbook'un tek kaynağıdır" diyor ama `.env.example`'da olup Ek A'nın satırında **olmayan** 8 anahtar var: `LLM_PROVIDER`, 6× `OLLAMA_*`, `GITHUB_BACKFILL_LIMIT`. Yukarıdaki tablo bu yüzden Ek A'nın **üst kümesi** — kabul kriteri "her `.env.example` anahtarı" olduğu için hepsini kapsamak zorunlu. Ek A'ya satır eklemek bu PR'ın işi **değil** (aynı tabloyu düzenleyen `T-63-hosted-demo-hardening` dalıyla çakışır) — ayrı bir takip issue'da (sahibi: infra) kapatılmalı.

### Platform-only ekstra anahtarlar (`.env.example`'da YOK, yine de gerekli)

| Anahtar | Nerede | Not |
|---|---|---|
| `PORT` | Fly `[env]` (commit'li) | `fly.toml`'da `[env]` bloğunda **açıkça** `"8000"` set edilir (bkz. `fly.toml` satırı) — Fly'ın kendiliğinden enjekte ettiği bir değer **değildir**; `.env.example`'a girmez (yalnızca platform sözleşmesi) |
| `FLY_API_TOKEN` | **CI secret** | `gh secret set FLY_API_TOKEN` — app-scoped deploy token'ı (§3 adım 10); backend/frontend çalışma zamanında **hiç kullanılmaz**, yalnız CD pipeline'ında |
| `DEMO_MODE` | Fly `[env]` (commit'li — `#63` kendi `fly.toml`'ına ekliyor, sır DEĞİL) | `"true"` olmadan hosted sertleştirme hiç açılmaz; fail-closed açılış (§6) |
| `DEMO_RATE_WINDOW_S` | Fly (opsiyonel) | `fly secrets set` — kod default `60`; yalnız override gerekince set |
| `DEMO_AI_RATE_LIMIT` | Fly (opsiyonel) | kod default `10` — IP başına, AI-girdili yollar (`/query`, `/scope/check`) |
| `DEMO_AI_GLOBAL_LIMIT` | Fly (opsiyonel) | kod default `60` — tüm IP'ler toplamı, asıl fatura tavanı |
| `DEMO_RATE_LIMIT` | Fly (opsiyonel) | kod default `120` — IP başına, diğer (poll'lanan) yollar |
| `DEMO_CACHE_TTL_S` | Fly (opsiyonel) | kod default `900` — `CachedConflictJudge`/`CachedQueryJudge`/`CachedScopeJudge` TTL'i |
| `DEMO_CACHE_MAX_ENTRIES` | Fly (opsiyonel) | kod default `1024` |

### ⚠️ Tuzak kutusu — boş `DATABASE_URL=`

`.env.example`'daki `DATABASE_URL=` satırı **boş**. Bunu olduğu gibi `.env`'e kopyalarsan pydantic-settings **boş string'i** kod içi SQLite varsayılanının **önüne geçirir** (yerelde doğrulandı — env dosyasında anahtar *var* olmak default'u ezmeye yeter, değeri boş olsa bile):

```
ArgumentError: Could not parse SQLAlchemy URL from given URL string
```

**Yerel geliştirmede** ya satırı `.env`'den tamamen sil ya da `DATABASE_URL=sqlite:///ensemble.db` yaz. `.env.example`'ın kendisini düzeltmek bu PR'ın kapsamı **dışı** (ayrı issue — bkz. §8 sorun giderme).

### A2 · Çift-yönlü kilit: `CORS_ORIGINS` ↔ `VITE_API_BASE_URL`

```
Fly:    CORS_ORIGINS      = https://<vercel-prod>.vercel.app     # backend KİMİ kabul eder
Vercel: VITE_API_BASE_URL = https://<fly-app>.fly.dev            # frontend KİME gider
```

Biri güncellenince **diğeri aynı pencerede** güncellenir (§3 adım 8). Tek taraflı değişiklik = tarayıcıda "CORS error" — **gerçek hatayı gizler** (S2 #45/#150 dersi; hata cevapları da `Access-Control-Allow-Origin` taşır, bkz. `docs/sprint2-kontratlar.md` Ek D). Paralel çalışırken mock origin'lerle başlanır; entegrasyonda ikisi **aynı anda** gerçek değere çevrilir.

---

## 3. İlk deploy

Sıra **bağlayıcı** — atlanamaz. Ön-koşul: `flyctl` (bu runbook `v0.4.72` ile doğrulandı — komut isimleri farklıysa `flyctl <cmd> --help` ile teyit et) + `fly auth login`, `gh` CLI, bir Vercel hesabı, GitHub App PEM'i elde edilmiş (`docs/github-app-kurulum.md`).

### 1) Ön-koşullar

```bash
flyctl version        # bu runbook v0.4.72 ile doğrulandı
fly auth login
gh auth status
```

### 2) DB app'i kur (D-39 — self-host pgvector)

```bash
fly apps create grup54-db
fly volumes create pgdata -a grup54-db -r fra -s 1
```

`grup54-db` için **ayrı** bir Fly manifesti gerekir (imaj: `pgvector/pgvector:pg16`, volume mount `/var/lib/postgresql/data`) — bu manifest repoda **[`deploy/fly.db.toml`](../deploy/fly.db.toml)** olarak hazır duruyor, **elle yazmana gerek yok**. *(Gerekçe: bu adım `#182`'ye (Enes, self-host pgvector app + hosted DI) devredilebilirdi, ama `#182`'nin kapsamı store/DI katmanı — Fly app manifesti değil; `T-182-postgres-pgvector` dalı bunu içermiyor. Go-live'ı o dalın kendi kapsam kararına bağlamak yerine, bu iki satırlık manifest doğrudan burada veriliyor.)* ⚠️ **Tuzak:** bu manifest bilerek repo kökündeki `fly.toml` (app = `ensemble-backend`) ile **aynı dizinde değil** — `--config` unutulup çıplak `fly deploy -a grup54-db` çalıştırılırsa `flyctl` cwd'deki kök `fly.toml`'u okur ve **backend imajını** (Dockerfile build) yanlışlıkla `grup54-db` app'ine deploy etmeye çalışır; `fly volumes create pgdata` ile bağlanacağı `[mounts]` da bulunamaz. Bu yüzden aşağıdaki komutlarda `--config deploy/fly.db.toml` **hiçbir zaman atlanmaz**. **`[http_service]` / public port EKLEME** (manifestte zaten yok) — erişim yalnız Fly'ın özel ağı (`.internal:5432`) üzerinden olacak, dışarıya hiç açılmayacak.

```bash
fly secrets set --stage -a grup54-db \
  POSTGRES_USER=ensemble \
  POSTGRES_PASSWORD=<güçlü-parola> \
  POSTGRES_DB=ensemble
fly deploy -a grup54-db --config deploy/fly.db.toml
fly status -a grup54-db   # yeşil olana kadar bekle
```

### 3) Backend app'i kur

`fly.toml` **repoda zaten var** — `fly launch` **koşma** (üzerine yazıp `--no-deploy`/`--copy-config` sorularıyla karışmasın):

```bash
fly apps create ensemble-backend
```

### 4) Secret'ları set et — deploy'dan ÖNCE, `--stage` ile

`--stage` olmadan her `set` imajsız app'te bir deploy tetikler (henüz imaj yokken anlamsız). Sırayla:

```bash
fly secrets set --stage -a ensemble-backend \
  DATABASE_URL="postgresql+psycopg://ensemble:<pw>@grup54-db.internal:5432/ensemble" \
  CORS_ORIGINS="https://<vercel-prod>.vercel.app" \
  GEMINI_API_KEY="<gemini-anahtarı>" \
  GITHUB_APP_ID="4257285" \
  GITHUB_APP_INSTALLATION_ID="145474476" \
  GITHUB_REPO_OWNER="FatihErenCetin" \
  GITHUB_REPO_NAME="grup54"
```

**`GITHUB_APP_PRIVATE_KEY` — ayrı kutu (PEM içeriği, path DEĞİL):**

```bash
 fly secrets set --stage -a ensemble-backend GITHUB_APP_PRIVATE_KEY="$(cat <pem-dosya-yolu>)"
```
> Satır başındaki **boşluk bilerek var** — `HISTCONTROL=ignorespace` (ya da zsh eşdeğeri) açıksa bu komut shell geçmişine **yazılmaz**. Değeri asla `echo`/`cat` ile ekrana basma (argv'de de görünür — `ps`'e bakan biri okur). Çok-satırlı PEM'in `fly secrets set` argümanında doğru geçtiğini **operatör kendi ortamında doğrulayacak**; alternatif `fly secrets import` (stdin'den `NAME=VALUE`) daha güvenli olabilir ama çok-satırlı stdin davranışı burada test edilmedi — ilk kullanımda `fly secrets list` ile digest'in değiştiğini doğrula (aşağıda).

**`GITHUB_WEBHOOK_SECRET`** — bu adımda **rotate edilmiş yeni bir değerle** set edilir (D-35; hiç kimseyle paylaşılmaz, bkz. `docs/github-app-kurulum.md` "need-to-know" tablosu):

```bash
fly secrets set --stage -a ensemble-backend GITHUB_WEBHOOK_SECRET="<yeni-rotate-edilmiş-değer>"
```

**Doğrulama (değer asla görünmez, yalnız isim + digest):**

```bash
fly secrets list -a ensemble-backend
```

### 5) İlk deploy

```bash
make deploy       # = flyctl deploy --config fly.toml
fly status -a ensemble-backend
fly logs -a ensemble-backend
```

Deploy sonrası `/health`'te `github_auth: "configured"` bekle (bu **yalnız kimlik set edilmiş** demektir — PEM'in **geçerli** olduğunu kanıtlamaz; gerçek doğrulama ilk API çağrısına kadar bilinmez, health.py yorumu).

### 6) Migration — bugün elle, hedef `release_command` (#187)

**Bugünkü gerçek** (release_command yok, `fly.toml` başlığı bunu açıkça devretmiş):

```bash
fly ssh console -a ensemble-backend
cd /app/src/backend && alembic upgrade head
```

Bu, `CREATE EXTENSION IF NOT EXISTS vector` (migration `bfde4c8f644f`, postgres-dialect guard'lı) + `vector_index` tablosunu (migration `c4f1d6a2b8e9`) kurar.

**Hedef durum (#187 landed olunca):** `fly.toml`'a `release_command = "alembic upgrade head"` eklenir — `flyctl deploy` bunu otomatik, geçici bir makinede, uygulama trafiği açılmadan **önce** koşar; migration patlarsa deploy **fail-closed** iptal olur. Bu runbook `fly.toml`'a bu satırı **eklemez** (başka bir işin dilimi) — yalnızca iki durumu da belgeliyor.

### 7) Vercel

1. **New Project** → repo import.
2. ⚠️ **Root Directory = `src/frontend`** — `vercel.json` orada yaşıyor (repo kökünde **değil**); kök seçilirse build/rewrite hiç çalışmaz, derin-link/refresh 404 verir (bkz. §8).
3. Framework önayarı: **Vite** · Build Command: `npm run build` · Output Directory: `dist`.
4. **Environment Variables** → `VITE_API_BASE_URL` = `https://<fly-app>.fly.dev` (Production scope). **`VITE_MOCK` EKLEME.**
5. Deploy → prod URL'i not al.

### 8) A2 çift-yön kilidini kapat

Aynı pencerede, sırayla:

```bash
fly secrets set -a ensemble-backend CORS_ORIGINS="https://<vercel-prod>.vercel.app"
```

Vercel → Environment Variables → `VITE_API_BASE_URL` = `https://<fly-app>.fly.dev` → **Redeploy** (build-time — yalnız "Save" yetmez).

### 9) Webhook (D-35 / #62)

GitHub App → Webhook URL: `https://<fly-app>.fly.dev/webhooks/github` (⚠️ **`/webhook` DEĞİL** — kanonik route `src/backend/ensemble/api/routers/webhook.py`'de `POST /webhooks/github`, `openapi.json`'da da bu yol var; yanlış URL ile kaydedilirse GitHub'ın her teslimatı 404 alır ve hosted ingest **sessizce** hiç çalışmaz — board hiç dolmaz, hata da görünmez). `GITHUB_WEBHOOK_SECRET`'ı **rotate et** (yeni değer yalnız Fly secret'ta yaşar, hiçbir kanalda paylaşılmaz).

### 10) CD'yi aç (#192) — SIRA KRİTİK, en son

```bash
fly tokens create deploy -a ensemble-backend -x 8760h
gh secret set FLY_API_TOKEN --repo FatihErenCetin/grup54     # değer STDIN'den, argümanda DEĞİL
```

⚠️ **Bu adım 3–5 bitmeden yapılmaz.** Token app'ten önce eklenirse ilk yeşil CI'da `deploy` job'ı koşar ve "app not found" ile patlar — `main` commit'inde kırmızı "Deploy (Fly)" görünür (required check değil, kimseyi bloklamaz ama go-live haftasında gürültü, bkz. §8).

---

## 4. Doğrulama

`make smoke` (#189) ile doğrula:

```bash
make smoke SMOKE_API_URL=https://<fly-app>.fly.dev SMOKE_WEB_URL=https://<vercel-prod>.vercel.app
```

Ne kontrol eder: `/health` (4 alan) + hosted modda **otomatik strict** readiness (`SMOKE_STRICT` verilmezse `mode=="hosted"` iken secret eksikliği FAIL sayılır — canlıda "missing" istenmez kuralının makine hâli) + CORS preflight+GET (`Access-Control-Allow-Origin` tam eşleşme; `*` ayrı FAIL) + 6 SPA route'un (`/`, `/board`, `/scope`, `/graph`, `/activity`, `/ask`) doğrudan+refresh deep-link'i. `SMOKE_WEB_URL` verilmezse CORS+SPA bloğu **atlanır**, yalnız `/health` kontrol edilir ve çıktıda "kısmi smoke" WARN'ı görünür. `SMOKE_TIMEOUT_S`/`SMOKE_RETRIES` (varsayılan sırasıyla 15s/2 — yalnız **ilk** `/health` denemesi için, Fly `auto_stop_machines` soğuk-başlangıcı). Çıkış: `0` = yeşil, `1` = en az bir FAIL.

⚠️ **KURAL:** go-live checklist'inde `SMOKE_STRICT=0` ile yeşile **boyamak yasak** — bu, canlıda gerçekten eksik olan bir secret'ı (örn. `GEMINI_API_KEY`) gizler; gerçek regresyonu maskeler.

`make smoke` bir nedenle kullanılamıyorsa (örn. yerelde `uv`/ağ kısıtı) manuel eşdeğeri:

```bash
curl -s https://<fly-app>.fly.dev/health | jq .
curl -s -i -X OPTIONS https://<fly-app>.fly.dev/board \
  -H "Origin: https://<vercel-prod>.vercel.app" \
  -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin
curl -s -I https://<vercel-prod>.vercel.app/board       # 200 + SPA rewrite kanıtı
```

---

## 5. Rollback

### Fly (backend)

`flyctl v0.4.72`'de **`fly releases rollback` komutu YOK** — bu runbook'u yazarken yerelde doğrulandı (`flyctl releases --help` çıktısında böyle bir alt-komut yok). Panik anında yanlış komutu aramakla dakika kaybetme:

```bash
fly releases -a ensemble-backend --image      # geçmiş release'leri + imaj referanslarını listeler
fly deploy -a ensemble-backend --image <önceki-imaj-ref>
```

Sonra **tekrar `make smoke`** (§4).

### Vercel (frontend)

Dashboard → **Deployments** → önceki **Production** deploy → **⋯ → Instant Rollback** (rebuild yok, anında). ⚠️ `VITE_API_BASE_URL` build-time gömülü olduğu için rollback **eski base-URL'i geri getirir** — A2 kilidini (§2) yeniden doğrula, çakışmıyorsa CORS hatası alırsın.

### DB

`alembic downgrade -1` **son çare** (veri kaybı riski). Unutma: DB **kanonik değil**, `.harness/` + GitHub'dan `make rebuild` (ya da #191 seed) ile yeniden kurulabilir bir projeksiyondur (D-39) — kalıcı yedekleme stratejisi bilerek yok.

### CD etkileşimi

Rollback **geçicidir**. `main` düzelmeden bir sonraki yeşil CI aynı bozuk sürümü **tekrar** deploy eder (#192 push-tetiklemeli). Kalıcı çözüm her zaman: **revert PR**, sonra normal akış.

---

## 6. Hosted demo sertleştirme (#63)

`#63` `DEMO_MODE` bayrağını + altı `DEMO_*` ayarını ekliyor (rate cap, cached-verdict) — `fly.toml [env]`'e `DEMO_MODE = "true"` satırı da **#63'ün kendi PR'ının bir parçası** (bu runbook'un ayrıca ekleyeceği bir iş **değil**). Bu bölüm bağlayıcıdır:

- **Açılış fail-closed:** `DEMO_MODE=true` iken `GITHUB_REPO_OWNER`/`GITHUB_REPO_NAME` **zorunlu** — yoksa `Settings` doğrulaması **açılışta** `ValueError` fırlatır, uygulama **hiç ayağa kalkmaz** (deploy geri alınır, health-check hiç yeşil olmaz).
- **Rate cap:** AI-girdili yollar (`/query`, `/scope/check`) IP başına + global tavan; diğer (poll'lanan) yollar ayrı, daha yüksek bir tavan. Aşımda **429** + `Retry-After` (Ek D hata zarfı uzantısı).
- **Cached-verdict:** aynı çift/soru+belge/ref+aday üçlüsü tekrar Gemini'ye sorulmaz (`CachedConflictJudge`/`CachedQueryJudge`/`CachedScopeJudge`, TTL `DEMO_CACHE_TTL_S`, varsayılan 900s).
- **In-memory sınırı:** cache RAM'de tutulur — Fly makinesi `auto_stop_machines="stop"` ile durunca **sıfırlanır** (kalıcılık yok, bilerek).

> ⚠️ **Bilinen çapraz etkileşim (R1, henüz kapanmadı):** `DEMO_MODE=true` iken judge, `health.py`'nin `isinstance(radar_service.judge_port, GeminiJudgeAdapter)` kontrolünden **geçmeyen** bir sarmalayıcıya (`CachedConflictJudge`) sarılıyor → hosted `/health` bu durumda **her zaman** `gemini: "missing"` döner (gerçekte Gemini set edilmiş olsa da). `make smoke` hosted modda **otomatik strict** olduğu için bu, #63 landed olup `health.py` düzeltilmeden `make smoke`'u **kalıcı** `exit 1`'e mahkûm eder. **Düzeltme bu runbook'un işi değil** (kod değişikliği #63'ün dalında) — `SMOKE_STRICT=0` ile bunu gizlemek **yasak** (§4 kuralı); gerçek düzeltme beklenir.

---

## 7. SON CHECKLIST — go-live'dan önce hepsi ✅ olmalı

- [ ] `fly status -a ensemble-backend` yeşil + `curl .../health` → `200`
- [ ] `make smoke` **YEŞİL** (0 FAIL) — `SMOKE_STRICT=0` ile boyanmamış (§4)
- [ ] **README** [`## 🌐 Hosted demo`](../README.md) bölümüne canlı URL'ler yazıldı + ayrı bir PR ile commit'lendi
- [ ] **Bootcamp teslim formu → "Canlı ürün linki"** = **frontend (Vercel)** URL'i — backend URL'i **değil**
- [ ] Vercel prod origin ≡ Fly `CORS_ORIGINS` (birebir aynı, sondaki `/` **yok**)
- [ ] `VITE_MOCK` Vercel'de tanımsız + `prod-build-guard` CI job'ı yeşil
- [ ] `fly secrets list -a ensemble-backend` yalnız ad + digest gösteriyor (değer yok)
- [ ] `gh secret list --repo FatihErenCetin/grup54` içinde `FLY_API_TOKEN` var
- [ ] Hiçbir secret DEĞERİ PR/issue/WhatsApp/dokümanda yer almıyor

---

## 8. Sorun giderme

| Belirti | Kök neden | Çözüm |
|---|---|---|
| Tarayıcıda "CORS error" | `CORS_ORIGINS` ↔ `VITE_API_BASE_URL` tek taraflı değişti (A2) | İkisini aynı anda güncelle + Vercel'i redeploy et (§3 adım 8) |
| SPA route'u refresh'te **404** | Vercel Root Directory kökte seçilmiş, `src/frontend` değil | Vercel proje ayarları → Root Directory → `src/frontend` |
| `/health` → `gemini: "missing"` (anahtar set edilmiş olmasına rağmen) | (a) `GEMINI_API_KEY` gerçekten yok, **ya da** (b) `DEMO_MODE` (#63) judge'ı sarmalıyor (R1, §6) | (a) `fly secrets list` ile digest kontrolü; (b) bilinen sınır, henüz kapanmadı — bkz. §6 |
| `ModuleNotFoundError: psycopg2` | `DATABASE_URL` DSN'inde `+psycopg` eki yok (SQLAlchemy varsayılan sürücüye — psycopg2 — düşer) | DSN'i `postgresql+psycopg://…` şekline getir (D-39/Ek C3 kanonik şekil) |
| `ArgumentError: Could not parse SQLAlchemy URL` (yerelde) | `.env.example`'daki boş `DATABASE_URL=` satırı olduğu gibi `.env`'e kopyalanmış | Satırı sil ya da `sqlite:///ensemble.db` yaz (§2 tuzak kutusu) |
| `flyctl deploy` "app not found" (CI'da) | `FLY_API_TOKEN` app yaratılmadan **önce** eklendi | Sıra: app oluştur → secret'lar → deploy → **sonra** token (§3 adım 10) |
| GitHub App teslimatları sürekli **404**, board hiç dolmuyor (hosted ingest sessizce çalışmıyor) | GitHub App Webhook URL'i yanlış kaydedilmiş (`/webhook` — kanonik yol `/webhooks/github` değil) | GitHub App ayarları → Webhook URL → `https://<fly-app>.fly.dev/webhooks/github` olarak düzelt (§3 adım 9) |
| İlk istekte birkaç saniye gecikme | `auto_stop_machines="stop"` soğuk başlangıcı | Beklenen davranış; `make smoke`'un retry'ı bunu tolere eder |
| Uygulama Fly'da **hiç açılmıyor**, health-check sürekli kırmızı | (`#63` ile) `DEMO_MODE=true` ama `GITHUB_REPO_OWNER`/`GITHUB_REPO_NAME` eksik — fail-closed açılış | İkisini de `fly secrets set` ile ekle, yeniden deploy et |
| `fly releases rollback` diye bir komut aramak | O komut `v0.4.72`'de **yok** | `fly releases --image` + `fly deploy --image <ref>` kullan (§5) |

---

## 9. Sır hijyeni

- Secret set/oku her zaman `fly secrets set` / `fly secrets list` ile — değeri **asla** `echo`/`cat`/log satırına yazma.
- Argümanlı `fly secrets set NAME=VALUE` shell geçmişine yazılabilir riskini taşır — `HISTCONTROL=ignorespace` (satır başına boşluk) kullan ya da `fly secrets import` (stdin) tercih et.
- Deploy'dan önce her zaman `--stage` (aksi halde her `set` gereksiz bir deploy tetikler).
- Rotasyon prosedürü: GitHub App → Settings → Private keys → **yeni üret** → `fly secrets set` ile güncelle → **eskisini sil**. Webhook secret'ı da aynı mantıkla rotate edilir (D-35).
- `gitleaks` CI'ı (`.github/workflows/ci.yml`) zaten her PR'da sır taraması yapıyor — bu runbook'a yeni bir secret-tarama adımı **eklenmez**, mevcut kapı yeterli.

---

> Kaynak: `docs/sprint3-kontratlar.md` Ek A/A2/A3/C3 · `fly.toml` · `docker-compose.yml` · `Dockerfile` · `Makefile` (`deploy`) · `src/frontend/vercel.json` · `docs/github-app-kurulum.md`. Bu doküman referans aldığı, hâlâ ayrı/bekleyen işler (#187/#182/#183 — §0) `main`'e indikçe **bayatlayabilir**; (#63/#189/#192 zaten bu dalın kendisinden önce `main`'e inmiş varsayılıyor — §0.) `tests/unit/test_deploy_runbook.py` en azından env-kapsamasını (§2) sürekli kilitler; kalan bölümler ilgili PR'lar `main`'e inince gözden geçirilmeli.
