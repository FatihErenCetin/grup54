# Deploy Runbook — Ensemble (Self-host VDS + Vercel)

> **Ne:** Ensemble backend'ini **kendi VDS'imize** (Docker Compose + host Caddy), frontend'ini Vercel'e canlıya almanın **operatör** rehberi — env→platform eşlemesi, ilk deploy sırası, doğrulama, rollback. **Kim:** infra dilimini yürüten kişi (bugün: Fatih); ekip içinde herkes okuyabilir. **Ne zaman:** go-live'da ve her rollback/rotasyon gerektiğinde.
>
> ⚠️ **Mimari 25–26 Temmuz'da değişti (D-46, #246):** Fly.io **tamamen terk edildi** — `fly.toml` ve `deploy/fly.db.toml` silindi, `flyctl`/`FLY_API_TOKEN` artık **hiçbir yerde** kullanılmıyor. Backend + Postgres artık **BogaHost VDS**'te (`2.59.181.226`), `deploy/docker-compose.prod.yml` ile, sunucudaki **host** Caddy'nin arkasında çalışıyor. Bu doküman bu yeni gerçeği anlatır; aşağıdaki her iddia `deploy/docker-compose.prod.yml` · `deploy/caddy/ensemble.caddy` · `deploy/.env.production.example` · `.github/workflows/deploy.yml` (T-192 dalı) · `.env.example` okunarak doğrulandı — Fly döneminden kalan hiçbir cümle kopyalanmadı.
>
> **Sır hijyeni (baştan, tekrar tekrar):** bu dosyada hiçbir yerde **gerçek** bir secret DEĞERİ yazılmaz — yalnız `<placeholder>`. Bir değeri kopyalayıp buraya yapıştırmak yasak. Alan adları (`recommend2me.com` vb.) ve sunucu IP'si secret DEĞİL — zaten DNS'te herkese açık, bu yüzden placeholder'a çevrilmedi.
>
> **Kanonik kaynak zinciri** (çelişki olursa bu sıra kazanır):
> 1. [`docs/sprint3-kontratlar.md`](sprint3-kontratlar.md) **Ek A** — 🔒 FROZEN env→platform eşleme tablosu; bu runbook onun **operasyonel uygulamasıdır** (kod/komut seviyesi). Ek A'da satırı olmayan ama `.env.example`'da olan anahtarlar bu dosyada **§2 sonunda ayrıca not edilir** — kontrat metnine dokunulmadı.
>    ⚠️ **Bilinen çelişki (kontrat metni DEĞİŞTİRİLMEDİ, yalnız burada raporlanıyor):** Ek A hâlâ D-46 öncesi Fly diliyle yazılı (`Fly secret`, `FLY_API_TOKEN` sütunları) — platform ismi düzeyinde bu runbook'la **çelişiyor**. Ek A "🔒 FROZEN" olduğu için bu PR'da düzenlenmedi; Ek A'yı self-host'a taşımak ayrı bir karar/PR (infra sahibi) gerektirir. Bu runbook'u kullanan operatör "Fly secret" yerine aşağıdaki §2'deki gerçek mekanizmayı (`sunucu env dosyası`) esas alsın.
> 2. [`docs/github-app-kurulum.md`](github-app-kurulum.md) — GitHub App kimliği + PEM elde etme.
> 3. [`docs/gelistirme-dongusu.md`](gelistirme-dongusu.md) — DONE kapısı (bu iş bittiğinde neyin kanıtlanması gerektiği).
>
> **Bu doküman bir uygulama günlüğü değildir** — komutları verir, gerçek deploy'u yapan kişi kendi terminalinde koşturur. Placeholder'lar `<bu-şekilde>` yazılır.

---

## 0. Önce oku, sonra koş

Aşağıdaki adımlar **sıralıdır** — atlarsan bir sonraki adım anlamsız bir hatayla patlar. İlk kez deploy ediyorsan §3'ü baştan sona, tek oturumda takip et. Yalnızca bir secret'ı rotate ediyorsan §9'a, yalnızca geri alıyorsan §5'e atla.

Bu dosya `T-190-deploy-runbook` dalının kendisi. Bağımlı/ilişkili işlerin **bugünkü** (bu dal yazılırken ölçülen) gerçek durumu:

| Bağımlı iş | Durum | Bu runbook'taki karşılığı |
|---|---|---|
| **#246 (D-46)** — self-host compose + Caddy bloğu + env şablonu | ✅ `main`'de | §1 topoloji, §3 ilk deploy — bu runbook'un temel dayanağı |
| **#242 (#251)** — `.harness/` git'e alındı + imaja `COPY` edilir | ✅ `main`'de | §3 not — bind-mount artık host checkout'undan gelir |
| **#252/#254/#255** — judge fail-open kapanışı, `RADAR_JUDGE_CONCURRENCY`, Groq yedek judge | ✅ `main`'de | §2 env tablosu (`GROQ_*`, `RADAR_JUDGE_CONCURRENCY`) |
| **#63** — `DEMO_MODE` hosted sertleştirme | ✅ `main`'de | §2, §6 |
| **#192 (T-192-deploy-cd-fly dalı, PR #236)** — `.github/workflows/deploy.yml`, self-hosted runner + `vars.DEPLOY_ENABLED` | ⛔ `main`'de **DEĞİL** — PR açık, kod okunarak doğrulandı ama henüz merge olmadı | §3 adım son ("CD'yi aç") — **hedef durum** olarak işaretli |
| **#189 (T-189-live-smoke dalı, PR #238)** — `scripts/smoke.py` + `make smoke` | ⛔ `main`'de **DEĞİL** — PR açık | §4 doğrulama — **hedef durum**, bugünkü birincil yol manuel `curl` |
| **#187** — Fly'daki `release_command`in konsepti | Fly ile birlikte **anlamsızlaştı** — self-host compose zaten aynı fail-closed garantiyi kendi mekanizmasıyla (§3 adım 3) veriyor; issue GitHub'da hâlâ açık ama bu PR onu kapatmıyor (PO kararı) | §3 adım 3 |

> ⚠️ Bu tablo **ölçülerek** yazıldı (varsayım değil): `#236`/`#238` gerçekten açık PR olduğu `gh pr view` ile, `#246`/`#242`/`#63`/`#253` gerçekten `main`'de olduğu `git log main` ile doğrulandı. `#236`/`#238` merge olduğunda §3/§4'teki "hedef durum" işaretleri kaldırılıp davranış "bugünkü" olarak yeniden yazılmalı — operatör deploy anında `git log main -- .github/workflows/deploy.yml` / `-- Makefile` ile gerçek durumu teyit etsin.

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
┌────────────────┐  build-time   ┌──────────────────────────────────────────────┐
│  Vercel (SPA)   │◄──────────────┤  BogaHost VDS (2.59.181.226, Ubuntu 22.04)    │
│  recommend2me   │  VITE_API_    │ ┌────────────────────────────────────────┐   │
│  .com (www)     │  BASE_URL     │ │ host Caddy (systemd, zaten ayakta,      │   │
│  vite build     │               │ │ tesvik-api'yi de servis ediyor)         │   │
│  Root Dir:      │               │ │  api.recommend2me.com → 127.0.0.1:8001 │   │
│  src/frontend   │  CORS_ORIGINS │ └───────────────────┬────────────────────┘   │
│  ─────────────► │◄──────────────┤                     │ reverse_proxy         │
└─────────────────┘  (A2 çift-yön)│  ┌──────────────────▼─────────────────┐     │
                                  │  │ docker compose "ensemble" (deploy/) │     │
                                  │  │  api   — 127.0.0.1:8001→8000        │     │
                                  │  │  migrate — tek-atımlık, api'den ÖNCE│     │
                                  │  │           fail-closed biter (§3.3)  │     │
                                  │  │  db    — pgvector/pgvector:pg16,    │     │
                                  │  │          host portu YOK             │     │
                                  │  └──────────────────────────────────────┘     │
                                  │  (tesvik-* yığını AYRI konteynerler/ağ,       │
                                  │   bu compose'a hiç dokunmuyor)                │
                                  └────────────────────────────────────────────────┘
                          GitHub Actions ──────┘  (workflow_run: CI TAMAMI yeşil →
                          CI (lint-test + gitleaks + frontend) → Deploy (Self-host, #236 — ✅ main'de, 27 Tem)
```

- **Frontend (Vercel):** statik SPA, `vite build`; `VITE_API_BASE_URL` **build-time** gömülür (rewrite kuralları `src/frontend/vercel.json`'da). İki domain de bağlı ve **ikisi de canlı** — 26 Temmuz'da doğrudan doğrulandı: `curl -I https://recommend2me.com` ve `curl -I https://www.recommend2me.com` ikisi de `200` dönüyor (bkz. §2 A2 notu — hangisinin "primary" sayıldığından bağımsız olarak ikisi de `CORS_ORIGINS`'te listeli, bu yüzden hangi domainden geldiği önemli değil).
- **Backend (`ensemble-api:prod` imajı, VDS'te tek makine):** `deploy/docker-compose.prod.yml`, `db`/`migrate`/`api` üç servisi tek proje adı (`ensemble`) altında; `/health` → Caddy üzerinden `api.recommend2me.com`.
- **DB (`db` servisi):** aynı compose stack'inin İÇİNDE — Fly döneminde olduğu gibi ayrı bir app **değil**. Host portu yok, yalnız `ensemble-net` bridge ağı üzerinden `db:5432`'den erişilir. DB kanonik değil, **projeksiyon** (`.harness/` + GitHub kanonik → bozulursa `make rebuild` / #191 seed).
- **CD (GitHub Actions → `deploy.yml`, #192 — T-192-deploy-cd-fly dalı, PR #236, ⛔ henüz `main`'de değil):** yalnız `main`'e **push** + CI workflow'unun (`ci.yml`, `name: CI`) **TAMAMI** yeşil olunca **self-hosted runner** (`[self-hosted, linux, x64, ensemble-prod]`) üzerinde `docker compose ... up -d --build` koşar — `workflow_run`'ın `conclusion == 'success'`ü tek bir job'a değil, CI'in **üçünün de** (`lint-test` + `gitleaks` + `frontend`) yeşil olduğu anlamına gelir (`eval-gate` ayrı bir job değil, `lint-test`'in içinde bir adım). ⚠️ Bu, main'in required-check listesiyle (`lint-test` + `check-single-issue` + `frontend`) **"aynı kural" DEĞİL** — iki katman **örtüşüyor ama özdeş değil**, kümeler farklı ve biri diğerinin yerine geçmez:
  - **deploy kapısı** (bu satır, `workflow_run`): `lint-test` + `gitleaks` + `frontend`. **`check-single-issue` bu kümede YOK** — deploy, PR'ın tek-issue kuralına hiç bakmaz.
  - **PR/main required-check listesi**: `lint-test` + `check-single-issue` + `frontend`. **`gitleaks` bu kümede YOK** — gitleaks her PR'da çalışır ama branch protection'ın zorunlu listesine hiç eklenmemiş (bkz. `docs/kontrat-drift-guardrail.md` §7).

  Kesişim yalnız `lint-test` + `frontend`; her katmanın diğerinde olmayan kendine özgü bir kontrolü var (deploy kapısında `gitleaks`, PR kapısında `check-single-issue`) — biri yeşil diye diğeri de yeşildir **varsayılmaz**. PR/fork çalıştırmaz (fail-safe hedef+CI-yeşil kapısı, §3 son adım).

  **Fly'dan devralınmayan şey:** self-host CD'nin GitHub tarafında **hiçbir secret'a ihtiyacı yok** (`FLY_API_TOKEN` benzeri bir token **kaldırılmadı** — hiç **var olmadı**, çünkü runner sunucudan GitHub'a kendi outbound bağlantısını kurar, PULL modeli). Kapı bir secret değil, bir repo **variable**'ı (`vars.DEPLOY_ENABLED`) + runner'ın kendisi Idle olması.

---

## 2. Env → platform eşleme tablosu

`.env.example`'daki **48 anahtarın tamamı** aşağıda (**47'si düz `ANAHTAR=` satırı, 1'i — `CORS_ORIGINS` — yalnız yorum-satırı örneği; ikisi de sayılır**). Bu sayı, T-190 ilk taslağının iddia ettiği 38'den **10 fazla** — aradaki fark `main`'e bu dal yazıldıktan sonra inen `#252/#254/#255` (Groq yedek judge + judge paralelleştirme) ile `.env.example`'a eklenen `GROQ_API_KEY` · `GROQ_MODEL` · `RADAR_JUDGE_CONCURRENCY` `#218` ile eklenen `ENSEMBLE_ALLOW_FAKE_SEED` `#259` ile eklenen `VERDICT_TTL_DAYS` ve `#79` ile eklenen beş auth anahtarı (`GITHUB_OAUTH_*`, `AUTH_*`). *(38 değil 48 — bu PR'ın kendi drift-kilidi test'i bu farkı yakaladığı için yeniden sayıldı, uydurulmadı.)*

Dört sınıf — Fly döneminden **isim değişti**, kavram aynı:

- **sunucu env dosyası** — VDS'te `/etc/ensemble/ensemble.env` (640, `root:docker`); repodaki `deploy/.env.production` ona **symlink**. Compose'un `env_file:` alanı bunu okuyup konteynerin İÇİNE enjekte eder (Fly'daki `fly secrets set`in şifreli-depo eşdeğeri — burada şifreleme yok, dosya izniyle korunuyor, bkz. §9).
- **compose `environment:` (commit'li)** — `deploy/docker-compose.prod.yml`'in kendi YAML'ında düz metin (Fly'daki `fly.toml [env]` eşdeğeri); `env_file:`'den GELEN değeri **override eder**. `ENSEMBLE_MODE`, `PORT`, `DATABASE_URL` böyle — sunucu env dosyasına yazsan bile **etkisi yok**, gerçek değer burada.
- **Vercel env (build-time)** — değişmedi, frontend tarafı Fly'dan bağımsızdı zaten.
- **yalnız-local** — hiçbir platforma girilmez.
- **CI secret** — ⚠️ **bugün fiilen boş küme.** Fly'daki `FLY_API_TOKEN` (deploy pipeline'ının tek CI secret'ı) self-host'ta **hiç yok** (yukarıdaki §1 notu — self-hosted runner PULL modeli, GitHub'a secret vermez). `GEMINI_API_KEY`'in CI secret olarak eklenmesi hâlâ yalnız "ileride, eval canlı provider'a bağlanınca" teorik bir ihtimal (aşağıda #3).

| # | Anahtar | Nerede | Mekanizma | Not |
|---|---|---|---|---|
| 1 | `ENSEMBLE_MODE` | compose `environment:` | `docker-compose.prod.yml` (commit'li, `"hosted"` sabit) | sunucu env dosyasına yazma — override edilir; local `.env` = `local` |
| 2 | `DEMO_MODE` | sunucu env dosyası | `/etc/ensemble/ensemble.env` | `"true"` — public demo (D-46 sonrası recommend2me.com public); fail-closed açılış (§6) |
| 3 | `DEMO_RATE_WINDOW_S` | sunucu env dosyası (opsiyonel) | — | kod default `60` |
| 4 | `DEMO_AI_RATE_LIMIT` | sunucu env dosyası (opsiyonel) | — | kod default `10` — IP başına, `/query` + `/scope/check` |
| 5 | `DEMO_AI_GLOBAL_LIMIT` | sunucu env dosyası (opsiyonel) | — | kod default `60` — tüm IP'ler toplamı, asıl fatura tavanı |
| 6 | `DEMO_RATE_LIMIT` | sunucu env dosyası (opsiyonel) | — | kod default `120` — IP başına, diğer (poll'lanan) yollar |
| 7 | `DEMO_CACHE_TTL_S` | sunucu env dosyası (opsiyonel) | — | kod default `900` |
| 8 | `DEMO_CACHE_MAX_ENTRIES` | sunucu env dosyası (opsiyonel) | — | kod default `1024` |
| 9 | `LLM_PROVIDER` | sunucu env dosyası (opsiyonel) | — | hosted'da `gemini` kalır — VDS'te Ollama **kurulu değil**; kod default'u zaten `gemini` |
| 10 | `GEMINI_API_KEY` | sunucu env dosyası **+** CI secret (ileride, bugün gerekmiyor) | `/etc/ensemble/ensemble.env` | yoksa engine `FakeJudgeAdapter`'a düşer (canlıda **istenmez**); CI bugün `eval-gate`'i `FakeJudgeAdapter` ile offline koşuyor |
| 11 | `GEMINI_MODEL` | sunucu env dosyası (opsiyonel) | — | kod default `gemini-2.5-flash` |
| 12 | `GROQ_API_KEY` | sunucu env dosyası (opsiyonel) | — | 🆕 `#255` — set edilirse judge `FallbackJudge(Gemini, Groq)` ile sarılır (Gemini birincil, Groq yalnız Gemini hiç yargı üretemeyince); boşsa hiçbir şey değişmez |
| 13 | `GROQ_MODEL` | sunucu env dosyası (opsiyonel) | — | kod default `llama-3.3-70b-versatile` |
| 14 | `RADAR_JUDGE_CONCURRENCY` | sunucu env dosyası (opsiyonel) | — | 🆕 `#254` — kod default `8`; sağlayıcının RPM tavanına göre ayarla, `1` = tamamen sıralı |
| 15 | `ENSEMBLE_ALLOW_FAKE_SEED` | **hiçbir yerde set EDİLMEZ** (varsayılan kapalı) | — | 🆕 `#218` — `make rebuild` gerçek GitHub App'e ulaşamayıp `FakeGitHubAdapter`'a düşerse **SystemExit(1)** ile reddeder (D-51 fail-closed: sahte veri gerçek DB'nin üstüne YAZILMAZ). `1` yalnız **bilinçli demo-seed** için, üretimde ASLA |
| 16 | `VERDICT_TTL_DAYS` | sunucu env dosyası (opsiyonel) | — | 🆕 `#259` — kod default `7.0`. Kalıcı judge yargı önbelleğinin (`judge_verdicts`) tazelik sınırı. **Çok kısa**: #259'un amacı olan "CD redeploy'ları arasında restart maliyeti ~0" kaybolur. **Çok uzun**: prompt/rubrik veya model drift'i sonsuza kadar gizlenir — çünkü prompt `cache_key`'in parçası DEĞİL |
| 17 | `GITHUB_OAUTH_CLIENT_ID` | sunucu env dosyası | — | 🆕 `#79` — GitHub App'in **user-authorization** Client ID'si. Sır DEĞİL (OAuth adresinde zaten açıkta gider). Boşsa `/auth/config` `{enabled:false}` döner ve giriş **kapalı** açılır — uygulama yine çalışır, demo giriş İSTEMEZ |
| 18 | `GITHUB_OAUTH_CLIENT_SECRET` | sunucu env dosyası | — | 🆕 `#79` — SIR. Hiçbir log/hata mesajı/yanıta girmez (yalnız *değişken adı* "eksik" uyarısında geçer) |
| 19 | `AUTH_SESSION_SECRET` | sunucu env dosyası | — | 🆕 `#79` — oturum çerezini imzalayan HMAC anahtarı. **Sunucuda yerinde üretilir** (`secrets.token_urlsafe(48)`), hiçbir yerde görünmez. Değiştirmek TÜM oturumları düşürür |
| 20 | `AUTH_POST_LOGIN_URL` | sunucu env dosyası | — | 🆕 `#79` — **MUTLAK URL zorunlu**, fail-closed validator ile doğrulanır. Göreli yol (`/radar`) verilirse tarayıcı bunu callback'in çalıştığı origin'e (`api.recommend2me.com`) göre çözer → **404**. Üretim: `https://recommend2me.com/radar` |
| 21 | `AUTH_COOKIE_DOMAIN` | sunucu env dosyası (opsiyonel) | — | 🆕 `#79` — **boş bırakılır**: çerez yalnız `api` alt alanına bağlanır (host-only). Frontend çerezi OKUMAZ, tarayıcı yalnız API çağrılarında gönderir — daha dar, dolayısıyla daha güvenli |
| 22 | `GEMINI_EMBEDDING_MODEL` | sunucu env dosyası (opsiyonel) | — | kod default `gemini-embedding-001` |
| 23 | `GEMINI_EMBEDDING_DIMENSIONS` | sunucu env dosyası (opsiyonel) | — | kod default `768`; `vector(N)` migration'ıyla **hizalı** olmalı (Ek C3) |
| 24 | `GEMINI_TIMEOUT_S` | sunucu env dosyası (opsiyonel) | — | kod default `10` |
| 25 | `GEMINI_MAX_RETRIES` | sunucu env dosyası (opsiyonel) | — | kod default `3` |
| 26 | `OLLAMA_BASE_URL` | yalnız-local | — | VDS'te Ollama çalıştırılmıyor; kod zaten yalnız `127.0.0.1`/`localhost` kabul ediyor (loopback zorunluluğu) |
| 27 | `OLLAMA_MODEL` | yalnız-local | — | tam-yerel gizlilik modu (#78) |
| 28 | `OLLAMA_EMBEDDING_MODEL` | yalnız-local | — | " |
| 29 | `OLLAMA_EMBEDDING_DIMENSIONS` | yalnız-local | — | " |
| 30 | `OLLAMA_TIMEOUT_S` | yalnız-local | — | " |
| 31 | `OLLAMA_MAX_RETRIES` | yalnız-local | — | " |
| 32 | `GITHUB_APP_ID` | sunucu env dosyası | `/etc/ensemble/ensemble.env` | `4257285` (sır değil, yine de env dosyasında set edilir) |
| 33 | `GITHUB_APP_PRIVATE_KEY_PATH` | yalnız-local | — | sunucuda **boş bırak** (mount yok — imajda `.pem` dosyası yok) |
| 34 | `GITHUB_APP_PRIVATE_KEY` | sunucu env dosyası (**PEM İÇERİĞİ**) | bkz. §3.1 adım 2, ayrı kutu | **path DEĞİL**, ham PEM metni; `config.py` çözümleme sırası: PATH varsa PATH kazanır (yerel), yoksa bu alan (hosted) |
| 35 | `GITHUB_APP_INSTALLATION_ID` | sunucu env dosyası | — | `145474476` |
| 36 | `GITHUB_REPO_OWNER` | sunucu env dosyası | — | izlenen repo sahibi — **`#63` ile**: `DEMO_MODE=true` iken bu ikisi eksikse uygulama **hiç açılmaz** (fail-closed, §6) |
| 37 | `GITHUB_REPO_NAME` | sunucu env dosyası | — | izlenen repo adı — aynı fail-closed şart |
| 38 | `GITHUB_DEFAULT_BRANCH` | sunucu env dosyası (opsiyonel) | — | kod default `main` |
| 39 | `GITHUB_BACKFILL_LIMIT` | sunucu env dosyası (opsiyonel) | — | kod default `50` |
| 40 | `GITHUB_WEBHOOK_SECRET` | sunucu env dosyası | — | webhook imza doğrulaması (D-35); **rotate** prosedürü §9 |
| 41 | `GITHUB_WEBHOOK_PROXY_URL` | yalnız-local | — | hosted'da webhook doğrudan sunucu URL'ine gelir (smee kanalı yalnız local geliştirme) |
| 42 | `RADAR_WINDOW_DAYS` | sunucu env dosyası (opsiyonel) | — | kalibrasyon çıktısı (#18); kod default `14` |
| 43 | `RADAR_MIN_JACCARD` | sunucu env dosyası (opsiyonel) | — | kod default `0.0` (kalibrasyon sonucu, placeholder değil) |
| 44 | `RADAR_MIN_SIMILARITY` | sunucu env dosyası (opsiyonel) | — | kod default `0.0` |
| 45 | `DATABASE_URL` | compose `environment:` (**türetilir**, sunucu env dosyasına YAZILMAZ) | `docker-compose.prod.yml`: `postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}` | ⚠️ **tuzak** — aşağıdaki kutuya bak; Fly'daki `grup54-db.internal` yerine artık compose ağındaki `db` servis adı |
| 46 | `VITE_API_BASE_URL` | **Vercel env** (build-time) | Vercel dashboard → *Environment Variables* → Production | `= https://api.recommend2me.com`; **yalnız origin (+ opsiyonel path öneki)** — query/hash `lib/config.ts` tarafından reddedilir; değişince **redeploy şart** (build-time gömülür, "Save" yetmez) |
| 47 | `VITE_MOCK` | yalnız-local; Vercel'de **BOŞ** | — | yalnız `"1"` mock açar; prod'da tanımlarsan `vite.config.ts` build'i **kendi kırar** (#188 guard) |
| 48 | `CORS_ORIGINS` | sunucu env dosyası | `/etc/ensemble/ensemble.env` | `= https://recommend2me.com,https://www.recommend2me.com` (A2 çift-yön, aşağıda ayrı bölüm); asla `*` — config açılışta reddeder (`config.py::_decode_cors_origins`) |

> **yalnız-local** = platforma hiç girilmez · **sunucu env dosyası** = backend çalışma-zamanı (`/etc/ensemble/ensemble.env` → `env_file:`) · **compose `environment:`** = backend çalışma-zamanı ama sır değil, `docker-compose.prod.yml`'de commit'li · **Vercel env** = frontend build-time · **CI secret** = pipeline (bugün fiilen kullanılmıyor). Aynı anahtar iki sütunda **olamaz** — istisna: local ile hosted'ın **farklı** değeri (`ENSEMBLE_MODE`, `DATABASE_URL`, PEM yolu-vs-içeriği).

### Ek A'nın kapsamadığı anahtarlar (bulgu — kod/kontrat DEĞİŞTİRİLMEDİ)

`docs/sprint3-kontratlar.md` Ek A "bu tablo runbook'un tek kaynağıdır" diyor ama `.env.example`'da olup Ek A'nın satırında **olmayan** 11 anahtar var: `LLM_PROVIDER`, 6× `OLLAMA_*`, `GITHUB_BACKFILL_LIMIT`, `GROQ_API_KEY`, `GROQ_MODEL`, `RADAR_JUDGE_CONCURRENCY` (son üçü Ek A donduktan çok sonra, `#255`/`#254` ile eklendi — Ek A hiç güncellenmedi). Yukarıdaki tablo bu yüzden Ek A'nın **üst kümesi** — kabul kriteri "her `.env.example` anahtarı" olduğu için hepsini kapsamak zorunlu. Ek A'ya satır eklemek bu PR'ın işi **değil** — ayrı bir takip issue'da (sahibi: infra) kapatılmalı; bu, yukarıdaki platform-ismi çelişkisiyle (Fly vs self-host) **aynı** takip işine bağlanabilir.

### Platform-only ekstra anahtarlar (`.env.example`'da YOK, yine de gerekli)

| Anahtar | Nerede | Not |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | sunucu env dosyası (**zorunlu**) | Yalnız `docker-compose.prod.yml`'in `db`/`migrate`/`api` servislerinin `${VAR:?...}` interpolasyonu okur — `config.py`'de karşılığı YOK. Eksikse `docker compose up` "required variable ... is missing" ile **derhal** patlar (parse-zamanı, konteyner hiç başlamadan) |
| `PORT` | compose `environment:` (commit'li) | `docker-compose.prod.yml`'de `api` servisinde açıkça `"8000"` set edilir — platformun kendiliğinden enjekte ettiği bir değer **değildir**; `.env.example`'a girmez |
| `ENSEMBLE_ENV_FILE` | CD job-seviyesi env değişkeni (`.github/workflows/deploy.yml`, #236 — henüz `main`'de değil) | Runner kendi checkout'unda `deploy/.env.production` **yok** (gitignored) — CD bunun yerine `/etc/ensemble/ensemble.env`'i işaret eder; compose'un `env_file: - ${ENSEMBLE_ENV_FILE:-.env.production}` satırı elle-kurulumun varsayılanını korur |
| `DEPLOY_ENABLED` | GitHub Actions **repo variable** (secret DEĞİL, #236) | CD kill-switch: `"true"` olmadan `deploy` job'ı hiç çalışmaz; `gh variable set DEPLOY_ENABLED --body false` ile saniyeler içinde kapanır |
| `SMOKE_API_URL` / `SMOKE_WEB_URL` | GitHub Actions repo variable (#236 `smoke` job'ı + #238) | Tanımsızsa smoke adımı fail-safe atlanır (`::warning::` ile görünür) |
| `API_DOMAIN` benzeri bir değişken | **YOK — bilerek** | `api.recommend2me.com` `deploy/caddy/ensemble.caddy` içinde SABİT yazılı; ayrı bir env-enjeksiyonu yok (alan adı artık belli, D-46) |
| ~~`FLY_API_TOKEN`~~ | **KALDIRILDI** | Fly ile birlikte gitti — self-hosted runner PULL modeli hiçbir GitHub secret'ına ihtiyaç duymaz (§1) |

### ⚠️ Tuzak kutusu — boş `DATABASE_URL=`

`.env.example`'daki `DATABASE_URL=` satırı **boş**. Bunu olduğu gibi `.env`'e kopyalarsan pydantic-settings **boş string'i** kod içi SQLite varsayılanının **önüne geçirir** (yerelde doğrulandı — env dosyasında anahtar *var* olmak default'u ezmeye yeter, değeri boş olsa bile):

```
ArgumentError: Could not parse SQLAlchemy URL from given URL string
```

**Yerel geliştirmede** ya satırı `.env`'den tamamen sil ya da `DATABASE_URL=sqlite:///ensemble.db` yaz. **Prod'da bu tuzak zaten devre dışı** — `DATABASE_URL` sunucu env dosyasına hiç yazılmaz, compose kendi `environment:` bloğunda türetir (§2 tablosu, #38).

### A2 · Çift-yönlü kilit: `CORS_ORIGINS` ↔ `VITE_API_BASE_URL`

```
Sunucu: CORS_ORIGINS      = https://recommend2me.com,https://www.recommend2me.com   # backend KİMİ kabul eder
Vercel: VITE_API_BASE_URL = https://api.recommend2me.com                            # frontend KİME gider
```

İkisi de listelendi ve bu **bilinçli**: apex (`recommend2me.com`) ve `www` alt-alan adının **hangisi** tarayıcıda açılacağı Vercel'in domain yönlendirme ayarına bağlı ve zaman içinde değişebilir (26 Temmuz ölçümünde ikisi de doğrudan `200` dönüyordu, yönlendirme yoktu — ama bu davranış Vercel panelinden sessizce değiştirilebilir). Yalnız birini yazıp diğerini unutursak: backend açılır, `/health` 200 döner, smoke geçer, sayfa açılır ve uygulama tarayıcıda **tam da o unutulan domainden** açıldığı gün API çağrılarının **tamamı** sessizce kırılır (hata yalnız tarayıcı konsolunda görünür, `/health` yeşil kalmaya devam eder). İkisini de listelemek bu riski domain-yönlendirme ayarından **bağımsız** hale getirir.

Biri güncellenince **diğeri aynı pencerede** güncellenir (§3.1 adım 6). Tek taraflı değişiklik = tarayıcıda "CORS error" — **gerçek hatayı gizler** (S2 #45/#150 dersi; hata cevapları da `Access-Control-Allow-Origin` taşır, bkz. `docs/sprint2-kontratlar.md` Ek D).

---

## 3. İlk deploy

Sıra **bağlayıcı** — atlanamaz. Ön-koşul: VDS'e SSH erişimi (kullanıcı `fatih`, `docker` grubunda → sudo'suz `docker compose` çalışır), Docker 29.5.2 + Compose v5.1.4 kurulu (zaten kurulu), `gh` CLI, bir Vercel hesabı, GitHub App PEM'i elde edilmiş (`docs/github-app-kurulum.md`). **Fly hesabı/`flyctl` gerekmiyor — hiçbir adımda kullanılmıyor.**

### 3.1 · Sunucu tarafı (backend + db)

#### 1) Repo'yu sunucuya klonla + env dosyasını hazırla

```bash
git clone https://github.com/FatihErenCetin/grup54.git
cd grup54/deploy
sudo mkdir -p /etc/ensemble
sudo cp .env.production.example /etc/ensemble/ensemble.env
sudo chmod 640 /etc/ensemble/ensemble.env
sudo chown root:docker /etc/ensemble/ensemble.env
ln -s /etc/ensemble/ensemble.env .env.production   # repo'daki deploy/.env.production BU sembolik link
```

`deploy/.env.production` kök `.gitignore`'da (satır: `deploy/.env.production`) — gerçek sır hiçbir git ağacında yaşamaz, yalnız sunucudaki `/etc/ensemble/ensemble.env`'de.

Şimdi `/etc/ensemble/ensemble.env`'i doldur (`sudo $EDITOR /etc/ensemble/ensemble.env`) — §2 tablosundaki **sunucu env dosyası** satırlarının hepsi + `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` (platform-only, §2). `GEMINI_API_KEY`, `GITHUB_APP_*`, `GITHUB_WEBHOOK_SECRET`, `CORS_ORIGINS` **zorunlu**.

**`GITHUB_APP_PRIVATE_KEY` — ayrı kutu (PEM içeriği, path DEĞİL):** çok-satırlı PEM'i env-dosyası formatında tek satıra `\n` ile indirgenmiş, çift tırnak içinde yaz (`.env.production.example` başlığındaki not aynen geçerli). Değeri asla `echo`/`cat` ile terminale basma (shell geçmişi + `ps` çıktısında görünür).

**`GITHUB_WEBHOOK_SECRET`** — bu adımda **rotate edilmiş yeni bir değerle** yazılır (D-35; hiç kimseyle paylaşılmaz, bkz. `docs/github-app-kurulum.md` "need-to-know" tablosu).

#### 2) `.harness/` mevcudiyetini doğrula (artık git-tracked, ekstra adım YOK)

`#242` ile `.harness/` git'e alındı (29 dosya, `git ls-files | grep -c '^\.harness'`) — repo klonlandığı anda **zaten** diskte. `docker-compose.prod.yml`'in `api` servisi bunu `../.harness:/app/.harness:ro` olarak bind-mount eder (`create_host_path: false` — dizin yoksa `docker compose up` **fail-loud** patlar, sessizce boş kalmaz). Repo'yu klonladıysan bu adım kendiliğinden geçer; yalnız **sığ/kısmi checkout** (örn. sparse-checkout) kullanıyorsan `.harness/` dizininin gerçekten diskte olduğunu `ls ../.harness` ile teyit et.

> ℹ️ **Bulgu (kod değiştirilmedi, yalnız not):** `docker-compose.prod.yml`'in kendi yorum bloğu hâlâ D-46 anındaki ölçümü anlatıyor ("`.harness/` dizini bu repoda HİÇ YOK... sessizce boş board"). `#242` bu riski kapattı (dizin artık git-tracked, imaja da `COPY .harness/`) — compose dosyasındaki yorum artık **bayat**, ama davranış zaten doğru (dizin var olduğu için sorun yaşanmıyor). Yorumun güncellenmesi bu PR'ın kapsamı dışı; infra sahibine not düşüldü.

#### 3) İlk build + up (migration OTOMATİK — elle adım YOK)

```bash
cd grup54/deploy
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
# = make deploy (Makefile hedefi, repo kökünden `cd deploy && ...` ile aynı komut)
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
```

**Fly'dan en büyük fark burada:** Fly'da migration `#187` (`release_command`) beklenene kadar elle `fly ssh console` ile koşuyordu. Self-host compose'ta bu **zaten otomatik**: `migrate` servisi (`restart: "no"`, tek atımlık) `alembic upgrade head`'i `api` başlamadan **önce** koşar; `api.depends_on.migrate.condition: service_completed_successfully` migration sıfır-dışı bir kodla biterse `api`'yi **hiç başlatmaz** — Fly'ın `release_command`iyle **aynı fail-closed garanti**, ayrı bir adım gerekmeden. `CREATE EXTENSION IF NOT EXISTS vector` (migration `bfde4c8f644f`) + `vector_index` tablosu (`c4f1d6a2b8e9`) bu ilk `up`'ta kurulur.

Bir sonraki kod yayınında **`docker compose restart api` KULLANMA** — `restart` migrate'i yeniden koşturmaz. Doğru komut her zaman yukarıdaki `up -d --build` (compose dosyasının kendi "İŞLETME NOTLARI" bölümü aynısını söylüyor).

Deploy sonrası `curl http://127.0.0.1:8001/health` (sunucu üzerinde, henüz Caddy kurulmadıysa loopback'ten) ile `github_auth: "configured"` bekle (bu **yalnız kimlik set edilmiş** demektir — PEM'in **geçerli** olduğunu kanıtlamaz).

#### 4) DNS

`api.recommend2me.com` → `2.59.181.226` (A kaydı, Cloudflare) — zaten yapılandırılmış olmalı; değilse Cloudflare panelinden ekle, ACME doğrulaması için proxy'yi (turuncu bulut) geçici kapatmak gerekebilir.

#### 5) Caddy site bloğunu kur — **elle, sudo ister, CD OTOMATİKLEŞTİREMEZ**

```bash
sudo mkdir -p /etc/caddy/conf.d /var/log/caddy
sudo chown caddy:caddy /var/log/caddy
sudo install -m 0644 -o root -g root \
     deploy/caddy/ensemble.caddy /etc/caddy/conf.d/ensemble.caddy
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

`/etc/caddy/Caddyfile`'a **bir kez** `import /etc/caddy/conf.d/*` satırı eklenmeli (dosya kökünde, mevcut `api.ikarus.mcvconsultancy.com` ve `:80 redir` bloklarına **dokunmadan** — bkz. `deploy/caddy/ensemble.caddy` başlığı). `validate` başarılı olmadan `reload` etme — bozuk bir blok **tesvik sitesini de düşürür** (tek Caddy prosesi, tek config). Bu adım sunucuda şifresiz sudo olmadığı için **CD'den (self-hosted runner) hiçbir zaman otomatikleştirilemez** — her Caddy config değişikliğinde elle tekrarlanır.

#### 6) Vercel

1. **New Project** → repo import.
2. ⚠️ **Root Directory = `src/frontend`** — `vercel.json` orada yaşıyor (repo kökünde **değil**); kök seçilirse build/rewrite hiç çalışmaz, derin-link/refresh 404 verir (bkz. §8).
3. Framework önayarı: **Vite** · Build Command: `npm run build` · Output Directory: `dist`.
4. **Environment Variables** → `VITE_API_BASE_URL` = `https://api.recommend2me.com` (Production scope). **`VITE_MOCK` EKLEME.**
5. Domain: `recommend2me.com` + `www.recommend2me.com` ikisi de projeye bağlanır, primary = `www` (§2 A2 notu).
6. Deploy.

Aynı pencerede sunucu tarafında `CORS_ORIGINS` = `https://recommend2me.com,https://www.recommend2me.com` yazıldığından emin ol (A2 çift-yön, §2) — tek taraflı değişirse tarayıcıda "CORS error".

#### 7) Webhook (D-35 / #62)

GitHub App → Webhook URL: `https://api.recommend2me.com/webhooks/github` (⚠️ **`/webhook` DEĞİL** — kanonik route `src/backend/ensemble/api/routers/webhook.py`'de `POST /webhooks/github`, `openapi.json`'da da bu yol var; yanlış URL ile kaydedilirse GitHub'ın her teslimatı 404 alır ve hosted ingest **sessizce** hiç çalışmaz — board hiç dolmaz, hata da görünmez).

#### 8) CD'yi aç (#192, PR #236) — ✅ **YAPILDI (27 Tem), aşağıdaki adımlar uygulandı**

Sıra kritikti ve buna uyuldu:

```bash
# 1) Sunucuda self-hosted runner'ı kaydet (Settings → Actions → Runners → New self-hosted runner)
#    Etiket: ensemble-prod (linux/x64 GitHub kendiliğinden ekler)
# 2) Runner'ın Idle göründüğünü GitHub UI'da doğrula
# 3) Ancak O ZAMAN:
gh variable set DEPLOY_ENABLED --body true --repo FatihErenCetin/grup54
```

⚠️ **Sıra ters çevrilirse:** `DEPLOY_ENABLED=true` runner Idle olmadan set edilirse, ilk yeşil CI'da `deploy` job'ı **kuyruğa girer ve orada sessizce asılı kalır** (kırmızı olmaz, ama hiç bitmez) — Fly döneminin "app not found" hatasından farklı bir sessiz-asılma riski. Runner'ın Idle olduğunu **önce** doğrula.

**Canlı kanıt (27 Tem 12:21 UTC)** — ilk otomatik deploy:

```
run        : https://github.com/FatihErenCetin/grup54/actions/runs/30265557197
preflight  ✅ success   (ubuntu-latest)
deploy     ✅ success   (self-hosted, linux, x64, ensemble-prod)
smoke      ✅ success

CD'nin deploy ettiği SHA : 93b2579
main HEAD                : 93b2579        <- eşleşiyor
konteyner Created        : 2026-07-27T12:21:49Z
/health                  : 200 {"status":"ok","mode":"hosted"}
```

Runner: `ensemble-prod-vds` · online · systemd servisi (yeniden başlatmada da kalkar).

Fly'daki `FLY_API_TOKEN` adımının (`gh secret set`) self-host'ta **karşılığı yok** — bu bir eksik değil, mimari sadeleşme: self-hosted runner PULL modeli GitHub'a hiçbir kimlik bilgisi vermez.

---

## 4. Doğrulama

**Hedef durum (#189, T-189-live-smoke dalı, PR #238 — henüz `main`'de değil):** `make smoke` ile doğrulanacak:

```bash
make smoke SMOKE_API_URL=https://api.recommend2me.com SMOKE_WEB_URL=https://www.recommend2me.com
```

Ne kontrol edecek (kod okunarak doğrulandı, henüz `main`'de değil): `/health` (4 alan) + hosted modda **otomatik strict** readiness (`SMOKE_STRICT` verilmezse `mode=="hosted"` iken secret eksikliği FAIL sayılır) + CORS preflight+GET (`Access-Control-Allow-Origin` tam eşleşme; `*` ayrı FAIL) + 6 SPA route'un (`/`, `/board`, `/scope`, `/graph`, `/activity`, `/ask`) doğrudan+refresh deep-link'i. `SMOKE_TIMEOUT_S`/`SMOKE_RETRIES` varsayılanları (15s/2) Fly'ın `auto_stop_machines` soğuk-başlangıcı için tasarlanmıştı — **VDS'te konteynerler `restart: unless-stopped` ile sürekli ayakta**, soğuk-başlangıç riski yok; retry mekanizması yine de zararsız bir güvenlik payı olarak kalır.

⚠️ **KURAL (değişmedi):** go-live checklist'inde `SMOKE_STRICT=0` ile yeşile **boyamak yasak** — bu, canlıda gerçekten eksik olan bir secret'ı (örn. `GEMINI_API_KEY`) gizler.

**Bugünkü birincil yol (`#189` main'e inene kadar) — manuel eşdeğeri:**

```bash
curl -s https://api.recommend2me.com/health | jq .
curl -s -i -X OPTIONS https://api.recommend2me.com/board \
  -H "Origin: https://www.recommend2me.com" \
  -H "Access-Control-Request-Method: GET" | grep -i access-control-allow-origin
curl -s -I https://www.recommend2me.com/board       # 200 + SPA rewrite kanıtı
```

---

## 5. Rollback

### Backend (self-host — Fly'ın `fly releases --image` mekanizması YOK)

⚠️ **Bulgu (ölçüldü, önemli):** `deploy/docker-compose.prod.yml`'de imaj etiketi **statik**: `image: ensemble-api:prod` — `${IMAGE_TAG}` gibi bir SHA-bazlı interpolasyon **yok**. `.github/workflows/deploy.yml` (#236) `build`/`up` adımlarına `env: IMAGE_TAG: ${{ needs.preflight.outputs.sha }}` set ediyor ama compose dosyasının hiçbir yerinde `${IMAGE_TAG}` **kullanılmıyor** — yani bu env değişkeni bugün fiilen **etkisizdir** (compose'a hiç ulaşmıyor). Sonuç: sunucuda **SHA-bazlı, adreslenebilir bir imaj geçmişi yok**; her deploy aynı `ensemble-api:prod` etiketini overwrite eder. Fly'daki `fly releases --image` + `fly deploy --image <ref>` deseni bu yüzden **birebir taşınamaz** — kanonik rollback yolu **git-bazlı**:

```bash
cd grup54
git log --oneline -5                     # bozuk commit'ten önceki iyi SHA'yı bul
git checkout <iyi-sha>                   # ya da: git revert <bozuk-sha> && git checkout main
cd deploy
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

**Acil/hızlı yol (rebuild'siz, yalnız önceki imaj hâlâ yerel Docker cache'inde ise işe yarar):** kötü bir deploy'dan **önce** `docker inspect --format='{{.Id}}' ensemble-api:prod` ile o anki imaj ID'sini bir yere not al (`docker images -a` ile "dangling" hâlâ diskte kalır, `docker image prune` çalıştırılmadıysa). Rollback gerekirse:

```bash
docker tag <onceki-imaj-id> ensemble-api:prod
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build
```

Bu yol **kırılgan** (prune edilmişse imaj gitmiş olabilir) — kalıcı çözüm her zaman yukarıdaki git-bazlı yeniden build. *(Bulgu, düzeltilmedi: `IMAGE_TAG`'in compose'a hiç bağlanmaması muhtemelen `#236`'nın kendi bir eksiği/takip maddesi — bu runbook'un kapsamı değil, infra sahibine ayrıca bildirildi.)*

Rollback sonrası **tekrar smoke doğrulaması** yap (§4).

### Vercel (frontend) — değişmedi

Dashboard → **Deployments** → önceki **Production** deploy → **⋯ → Instant Rollback** (rebuild yok, anında). ⚠️ `VITE_API_BASE_URL` build-time gömülü olduğu için rollback **eski base-URL'i geri getirir** — A2 kilidini (§2) yeniden doğrula, çakışmıyorsa CORS hatası alırsın.

### DB — değişmedi

`docker compose exec api sh -c "cd src/backend && alembic downgrade -1"` **son çare** (veri kaybı riski). Unutma: DB **kanonik değil**, `.harness/` + GitHub'dan `make rebuild` (ya da #191 seed) ile yeniden kurulabilir bir projeksiyondur (D-39) — kalıcı yedekleme stratejisi bilerek yok.

### CD etkileşimi

Rollback **geçicidir**. `main` düzelmeden bir sonraki yeşil CI aynı bozuk sürümü **tekrar** deploy eder (#192 push-tetiklemeli, `concurrency.group: deploy` ile aynı anda yalnız bir koşu). Kalıcı çözüm her zaman: **revert PR**, sonra normal akış. Acil durumda CD'yi tamamen durdurmak için: `gh variable set DEPLOY_ENABLED --body false` (saniyeler içinde etkili, sonraki her koşu preflight'ta fail-safe atlanır).

---

## 6. Hosted demo sertleştirme (#63)

`#63` `DEMO_MODE` bayrağını + altı `DEMO_*` ayarını ekliyor (rate cap, cached-verdict) — sunucu env dosyasına `DEMO_MODE=true` satırı da **#246/`#63`'ün kendi env şablonunun bir parçası** (`deploy/.env.production.example`'da zaten `true`, bilinçli — recommend2me.com public bir demo). Bu bölüm bağlayıcıdır:

- **Açılış fail-closed:** `DEMO_MODE=true` iken `GITHUB_REPO_OWNER`/`GITHUB_REPO_NAME` **zorunlu** — yoksa `Settings` doğrulaması **açılışta** `ValueError` fırlatır. Self-host'ta bu hata **önce `migrate` servisinde** patlar (alembic `env.py` da `get_settings()` çağırır) ve `api` hiç başlamaz — Fly'daki "deploy geri alınır, health-check hiç yeşil olmaz" davranışının compose eşdeğeri.
- **Rate cap:** AI-girdili yollar (`/query`, `/scope/check`) IP başına + global tavan; diğer (poll'lanan) yollar ayrı, daha yüksek bir tavan. Aşımda **429** + `Retry-After`.
- **Cached-verdict:** aynı çift/soru+belge/ref+aday üçlüsü tekrar Gemini'ye sorulmaz (`CachedConflictJudge`/`CachedQueryJudge`/`CachedScopeJudge`, TTL `DEMO_CACHE_TTL_S`, varsayılan 900s).
- **In-memory sınırı — Fly'dan farklı sebep, aynı sonuç:** cache RAM'de tutulur. Fly'da bu `auto_stop_machines="stop"` ile makine durunca sıfırlanıyordu; self-host'ta konteyner `restart: unless-stopped` ile **sürekli ayakta** — sıfırlama artık yalnız **yeni bir deploy** (`up -d --build`, konteyner yeniden yaratılır) veya sunucu reboot'unda olur. Kalıcılık yine yok, bilerek (Redis gibi dağıtık bir sayaç kapsam dışı).
- **`X-Forwarded-For` doğruluğu artık Caddy'ye bağlı (Fly'da yoktu bu adım):** `client_ip()` önceliği `Fly-Client-IP` > `X-Forwarded-For` ilk kayıt > `request.client.host`. Self-host'ta `Fly-Client-IP` diye bir başlık **gerçek değil** — `deploy/caddy/ensemble.caddy` bunu bilinçli olarak siler (`header_up -Fly-Client-IP`, sahte istemcinin bu başlığı kendisi göndererek rate cap'i atlatmasını önlemek için) ve `X-Forwarded-For`'u **üzerine yazar** (`header_up X-Forwarded-For {remote_host}`, Caddy'nin varsayılan "ekle" davranışı yerine). **Bu Caddy bloğu kurulmadan** (§3.1 adım 5) rate cap per-IP olarak kolayca atlatılabilir — Caddy kurulumu bu yüzden §6'nın bir ön-koşulu.

> ✅ **Çapraz etkileşim R1 — KAPANDI (#63), platformdan bağımsız.** Bir ara `DEMO_MODE=true` iken judge, `health.py`'nin `isinstance(..., GeminiJudgeAdapter)` kontrolünden geçmeyen bir sarmalayıcıya sarılıyordu → `/health` **her zaman** `gemini: "missing"` derdi. #63 bunu düzeltti: `health.py` artık `getattr(judge_port, "inner", judge_port)` ile sarmalayıcıyı açıyor, regresyon testiyle kilitli. `SMOKE_STRICT=0` ile smoke'u boyamak yine **yasak** (§4 kuralı).

---

## 7. SON CHECKLIST — go-live'dan önce hepsi ✅ olmalı

- [ ] `docker compose -f docker-compose.prod.yml ps` → `db`/`migrate`/`api` beklenen durumda (`migrate` = `Exited (0)`, diğer ikisi `Up`) + `curl https://api.recommend2me.com/health` → `200`
- [ ] Smoke **YEŞİL** (0 FAIL) — `make smoke` main'e indiyse onunla, inmediyse §4'teki manuel `curl` seti ile; `SMOKE_STRICT=0` ile boyanmamış
- [ ] **README** [`## 🌐 Hosted demo`](../README.md) bölümünde `recommend2me.com` (frontend) + `api.recommend2me.com` (backend) canlı olarak işaretli
- [ ] **Bootcamp teslim formu → "Canlı ürün linki"** = **frontend (Vercel/`recommend2me.com`)** URL'i — backend URL'i **değil**
- [ ] Vercel prod origin'leri ≡ sunucu `CORS_ORIGINS` (birebir aynı iki domain, sondaki `/` **yok**)
- [ ] `VITE_MOCK` Vercel'de tanımsız + `prod-build-guard` CI job'ı yeşil
- [ ] `/etc/ensemble/ensemble.env` izinleri `640 root:docker` (`ls -l` ile doğrula) — dünyaya okunabilir DEĞİL
- [ ] `deploy/.env.production` kök `.gitignore`'da (satır var, `git check-ignore deploy/.env.production` boş dönmüyor)
- [ ] Hiçbir secret DEĞERİ PR/issue/WhatsApp/dokümanda yer almıyor
- [ ] (CD `main`'e indiyse) `gh variable list --repo FatihErenCetin/grup54` içinde `DEPLOY_ENABLED=true` + runner Idle

---

## 8. Sorun giderme

| Belirti | Kök neden | Çözüm |
|---|---|---|
| Tarayıcıda "CORS error" | `CORS_ORIGINS` (sunucu env dosyası) ↔ `VITE_API_BASE_URL` (Vercel) tek taraflı değişti (A2) | İkisini aynı anda güncelle + Vercel'i redeploy et + sunucuda `docker compose up -d --build` (§3.1 adım 6) |
| SPA route'u refresh'te **404** | Vercel Root Directory kökte seçilmiş, `src/frontend` değil | Vercel proje ayarları → Root Directory → `src/frontend` |
| `/health` → `gemini: "missing"` | **`GEMINI_API_KEY` gerçekten yok / sunucu env dosyasına ulaşmamış.** (R1 — `DEMO_MODE` sarmalayıcı sorunu — #63 ile kapandı, §6.) Bu belirti artık **tek anlama gelir: gerçek bir yapılandırma eksiği.** | `/etc/ensemble/ensemble.env`'de `GEMINI_API_KEY` satırını kontrol et; eksikse doldur, `docker compose up -d --build` ile yeniden başlat, `curl .../health` ile teyit et |
| `docker compose up` → "required variable POSTGRES_PASSWORD is missing" | `--env-file .env.production` bayrağı unutuldu, ya da symlink kırık | `deploy/.env.production`'ın `/etc/ensemble/ensemble.env`'e symlink olduğunu (`ls -l`) ve komutun `--env-file`'la çağrıldığını doğrula |
| `docker compose up` → "bind source path does not exist" (`.harness`) | `.harness/` dizini checkout'ta yok (sparse-checkout / eksik klon) | Repo'yu tam klonla — `#242` ile `.harness/` git-tracked, normal `git clone`'da her zaman gelir |
| `ModuleNotFoundError: psycopg2` | `DATABASE_URL` DSN'inde `+psycopg` eki yok | Prod'da bu satır elle yazılmaz (compose türetir, §2 #38) — yalnız local `.env`'de görülürse DSN'i `postgresql+psycopg://…` yap |
| `ArgumentError: Could not parse SQLAlchemy URL` (yerelde) | `.env.example`'daki boş `DATABASE_URL=` satırı olduğu gibi `.env`'e kopyalanmış | Satırı sil ya da `sqlite:///ensemble.db` yaz (§2 tuzak kutusu) |
| CD job'ı (#236 main'e indiyse) sessizce kuyrukta asılı kalıyor | `DEPLOY_ENABLED=true` runner Idle olmadan set edildi | Runner'ı Settings → Actions → Runners'da Idle'a getir; job kendiliğinden devam eder |
| GitHub App teslimatları sürekli **404**, board hiç dolmuyor | GitHub App Webhook URL'i yanlış kaydedilmiş (`/webhook` — kanonik yol `/webhooks/github` değil) | GitHub App ayarları → Webhook URL → `https://api.recommend2me.com/webhooks/github` (§3.1 adım 7) |
| Sunucuda tesvik-api'de kesinti oluştu | Caddy config'i bozuk `validate` edilmeden `reload` edildi | `sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile` her zaman `reload`'dan **önce** |
| "grup54-db" / `fly.db.toml` / `flyctl` arıyorum | Bu isimler **artık yok** — Fly D-46 ile tamamen kaldırıldı | `db` artık `docker-compose.prod.yml`'in bir servisi, ayrı bir app/manifest değil (§1) |

---

## 9. Sır hijyeni

- Sunucudaki sır dosyasını her zaman `sudo $EDITOR /etc/ensemble/ensemble.env` ile düzenle — değeri **asla** `echo`/`cat`/log satırına yazma.
- Dosya izinleri `640 root:docker` — `chmod`/`chown`'ı bozma; dünyaya okunabilir yapma.
- `deploy/.env.production` symlink'i git'e **girmez** (`.gitignore`) — `git add -f` ile zorlamaya çalışma.
- Rotasyon prosedürü: GitHub App → Settings → Private keys → **yeni üret** → `/etc/ensemble/ensemble.env`'i güncelle → `docker compose up -d --build` (yeniden başlat) → **eskisini sil**. Webhook secret'ı da aynı mantıkla rotate edilir (D-35).
- `gitleaks` CI'ı (`.github/workflows/ci.yml`) zaten her PR'da sır taraması yapıyor — bu runbook'a yeni bir secret-tarama adımı **eklenmez**, mevcut kapı yeterli.
- Fly'dan devralınan hiçbir secret/token **yok** — rotasyon listesi yalnızca yukarıdakiler.

---

> Kaynak: `deploy/docker-compose.prod.yml` · `deploy/caddy/ensemble.caddy` · `deploy/.env.production.example` · `.github/workflows/deploy.yml` (T-192-deploy-cd-fly dalı, PR #236) · `scripts/smoke.py`+`Makefile` (T-189-live-smoke dalı, PR #238) · `Makefile` (`deploy`) · `src/frontend/vercel.json` · `docs/github-app-kurulum.md` · `docs/sprint3-kontratlar.md` Ek A (⚠️ bilinen çelişki, §0/§2 — hâlâ Fly diliyle FROZEN). `#236`/`#238` `main`'e indikçe §0'daki "hedef durum" işaretleri kaldırılıp bu doküman güncellenmeli. `tests/unit/test_deploy_runbook.py` en azından env-kapsamasını (§2) ve Fly-sızıntısı olmadığını sürekli kilitler.
