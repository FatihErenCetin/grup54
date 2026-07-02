# Kapsam Sınırları — ne YAPIYORUZ, ne YAPMIYORUZ

> **Ekip için net tablo.** Ensemble = **local-first** MVP (A). Bir şeyi yapmadan önce: "bu kapsam içinde mi?" Aşağıdaki "YAPMA" listesindeyse → **yapma, vakit harcama.** Şüphedeysen PO'ya sor.

## 🧠 5 cümlede zihinsel model

1. **Kullanıcı/login YOK** *(çekirdek üründe)*. "Kim ne yaptı" = commit/PR'daki GitHub adı. İnsan saklamıyorsun, repo aktivitesinin **fotoğrafını** saklıyorsun. *(Hosted üyelik = evreli yol haritası → son bölüm; çekirdeğe asla sızmaz.)*
2. **Tek sır = 2 makine anahtarı:** GitHub App `.pem` + Gemini key → local `.env` (gitignored). `.pem`'i **asla** commit'leme, DB'ye koyma. *(Tecrübesiz ekibin yaptığı tek gerçek hata budur.)*
3. **DB bir müsvedde, kasa değil.** `.harness/` + GitHub'dan yeniden kurulabilir **cache**. Bozulursa `make rebuild`. → yedek gerekmez, yıkıcı migration serbest.
4. **Source of truth = `.harness/` + GitHub.** UI'daki her şey (board · presence · radar · activity) bunlardan **hesaplanır**. İşin özü: *kaynağı oku → cache'i doldur → göster.*
5. **Herkes kendi laptop'unda, kendi GitHub token'ıyla** çalıştırır (local = polling). + **tek opsiyonel hosted demo** (no-login, tek read-only repo, IP/rate cap).

## ✅ KAPSAM İÇİ (MVP — bunları yap)

| Alan | Ne |
|---|---|
| **AI çekirdek** ⭐ | çakışma radarı (dosya-kesişim → semantik → Gemini judge) · scope-drift · **false-positive kalibrasyonu/eval** |
| **Engine** | ingest (polling) · projeksiyon (events→board/presence) · NL "projeye sor" |
| **Web** | React pano: Radar · Board · Scope · Ask · Activity (üretilen OpenAPI client + polling) |
| **MCP** | `who_is_touching` · `check_scope` (read-first) · `declare_work` (tek write-back, stretch) |
| **Altyapı** | `.harness/` IO + şema · GitHub App auth (makine) · Postgres/SQLite + pgvector/FAISS (cache) · tek hosted demo (Fly+Vercel) |

## 🚫 KAPSAM DIŞI — YAPMA (tasarım gereği yok)

> Bunlar klasik bir SaaS'ta var; **local-first MVP'de bilerek YOK.** Biri bunlardan birine başlarsa = B'ye (çok-kullanıcılı) kaydının işareti → **dur, PO'ya sor.**

- ❌ **users/accounts/profiles tablosu** — kimlik = GitHub adı (zaten her commit/PR'da). *(Hosted üyelik tabloları = yalnızca #79 kapsamında, gate sonrası.)*
- ❌ **Login / şifre / session** — korunacak insan oturumu yok. **Şifre saklama her fazda YASAK** (bootcamp diliminde şifre yok; evre-2'de önce magic-link).
- ❌ **"GitHub ile giriş" OAuth-user akışı — ŞİMDİ BAŞLAMA.** #16'daki **makine** App-auth'tan tamamen farklı. Bu iş artık planlı: **#79 (S3 stretch, D-28)** — ama ⛔ **GATE'i var:** çekirdek eval (#17+#18) yeşil olmadan kimse başlamaz. Gate'ten önce OAuth callback yazan olursa → durdur.
- ❌ **organizations/teams/tenants + `tenant_id` + multi-tenant izolasyon** — tek kurulum tek repo okur.
- ❌ **roles/permissions/RBAC/ACL** — kullanıcı yoksa authz da yok.
- ❌ **per-user API key / token tablosu** — her dev kendi token'ını local verir; DB'de saklanmaz.
- ❌ **billing/subscription/Stripe** · **2FA/MFA/hesap ayarları** — MVP'de gelir/hesap yok.
- ❌ **DB audit-log tablosu** — audit git-native (PR diff + `.harness/decisions/`). DB'de tekrarlama.
- ❌ **notifications/email/queue/worker (Celery/RabbitMQ)** — radar pull-tabanlı polling.
- ❌ **backup/replication/PITR** — DB rebuildable cache; kurtarma = `make rebuild`.
- ❌ **Write/CRUD REST (POST/PUT/DELETE board/task/scope)** — durum GitHub'dan **türetilir**; MCP read-first.
- ❌ **WebSocket/SSE push** — sözleşme polling (#20). *(Hosted webhook = GitHub→backend, farklı yön.)*
- ❌ **Kendi GraphQL sunucun** — GraphQL sadece *GitHub'ı çağırırken* (#16). Senin yüzeyin REST+OpenAPI.
- ❌ **API versioning / kendi rate-limit'in / ağır pagination** — tek-ekip aracı; `since=`/ETag cursor yeter.
- ❌ **Local'de webhook/ngrok/tunnel** — laptop'un public URL'i yok; local = polling.
- ❌ **Local MCP'de auth** — stdio, OS-kullanıcı güveni. *(Sadece hosted HTTP MCP = B'de gerekir.)*
- ❌ **Full observability (Prometheus/Grafana/Sentry/OTel)** · **K8s/Helm/Terraform/canary** — tek küçük Fly + Vercel; minimal log yeter.

## 🔭 Hosted üyelik — EVRELİ yol haritası (D-28)

Yukarıdaki "YAPMA"ların çoğu = **üyelik katmanının işi** ve artık planlı — ama **evreli**, çekirdeği asla baskılamaz:

| Faz | Ne | Koşul |
|---|---|---|
| **S2** | üyelik işi YOK — 35p AI penceresi | — |
| **S3 stretch (#79)** | SADECE canlı "GitHub ile gir" + App installation (şifre yok, fatura yok, davet yok) | ⛔ **GATE: #17+#18 eval yeşil**; video/cila riske girerse düşer → videoda mock |
| **Evre-2 (bootcamp sonrası)** | email/magic-link hesap · workspace+davet · org=tenant + seat · Marketplace(+Stripe?) fatura | tasarım: ekip-içi üyelik tasarım dokümanı |

Free (local + Ollama, hesapsız) ↔ Paid (hosted üyelik) = iş modelinin ekseni. **Kural değişmedi:** gate'ten önce bu satırlardan herhangi birine başlayan olursa → dur, PO'ya sor.
