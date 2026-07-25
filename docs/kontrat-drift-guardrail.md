# Kontrat Drift Guardrail — OpenAPI ↔ TS Client (#56)

> **Amaç:** `src/shared/openapi.json` (backend kontratı) ile `src/frontend/src/api/schema.d.ts` (üretilen TS client) **senkron kalsın** — biri değişip diğeri regen edilmezse main'e sessizce sızmasın. Bu doküman #56'nın "audit boşluğu" teslimatıdır: mekanizma zaten **büyük ölçüde vardı** (aşağıda birinci-elden kanıtlanmıştır); asıl boşluk **bağlantı dokusuydu** — hangi check hangi vakayı yakalıyor, hangi vaka hâlâ açık, neden.

## 1. Codegen zinciri (frozen — `docs/sprint3-kontratlar.md` Ek E)

```
router / Pydantic model  (src/backend/ensemble/api/…)
        │  make openapi
        ▼
src/shared/openapi.json
        │  npm run gen:api  (openapi-typescript)
        ▼
src/frontend/src/api/schema.d.ts
        │  (elle tüketilir)
        ▼
src/frontend/src/lib/api.ts   (openapi-fetch, tip-güvenli)
```

Tek reçete (bu PR'da eklendi): **`make contracts`** — ikisini de birlikte regen eder (`Makefile`).

## 2. İki drift-check ZATEN var ve gerçekten çalışıyor (birinci-elden kanıt)

`.github/workflows/ci.yml`:

- **`OpenAPI drift-check`** (`lint-test` job'ı içinde): `make openapi` + `git diff --exit-code src/shared/openapi.json`.
- **`Client tip drift-check`** (`frontend` job'ı içinde): `npm run gen:api` + `git diff --exit-code -- src/api/schema.d.ts`.

Bu PR'ı hazırlarken izole bir worktree'de **kasten drift ürettim** ve geri aldım (ana ağaca dokunulmadı):

| Deney | Adım | Sonuç |
|---|---|---|
| **Taban (temiz ağaç)** | `make openapi` → diff | `exit 0` |
| **Kas testi A** | `HealthResponse`'a `drift_probe_dummy: str` eklendi → `make openapi` → `git diff --exit-code src/shared/openapi.json` | **`exit 1`** (5 satır fark) ✅ kırmızı |
| **Kas testi B** | (A)'nın openapi.json'ı yerinde bırakılıp `npm run gen:api` → `git diff --exit-code -- src/api/schema.d.ts` | **`exit 1`** (5 satır fark) ✅ kırmızı |
| **Pathspec tuzağı** | aynı anda, `frontend` job'ının cwd'sinden (`src/frontend`) repo-kökü stilinde pathspec (`src/frontend/src/api/schema.d.ts`) | **`exit 0`** — sessiz no-op (aşağıda §4) |
| **Taban geri** | değişiklikler `git checkout --` ile geri alındı → `make contracts` sonrası diff | `exit 0` (temiz) |

Yani mekanizmanın kendisi **doğru çalışıyor** — kod yazmaya gerek yoktu, bu doğrulamanın kendisi teslimat.

## 3. Geçmiş boşluk (🟢 KAPANDI 24 Tem): vaka-2 artık zorunlu check'e yakalanıyor

> **Güncel durum:** main branch protection'ın zorunlu (required) status check listesine `frontend` **eklendi** — bkz. §7. Bu bölüm önce açığı (nasıl oluştuğunu, hangi vakanın kaçtığını), sonra kapanışı anlatır.

İki check **farklı job'larda** yaşıyor. Bu PR açıldığında main branch protection'ın zorunlu (required) status check listesi yalnızdı:

```
required_status_checks.contexts = ["lint-test", "check-single-issue"]   # eskiden (frontend YOKTU)
```

`frontend` **listede yoktu**. O zamanki vaka matrisi:

| Vaka | `lint-test` (zorunlu) | `frontend` (o zaman zorunlu DEĞİLDİ, şimdi 🔒 zorunlu) | Sonuç (o zaman) | Sonuç (şimdi) |
|---|---|---|---|---|
| 1. Router değişti, ikisi de regen edilmedi | 🔴 KIRMIZI | 🟢 (client bayat `openapi.json`'dan regen edildiği için fark üretmez — check gerçekten yeşil, KIRMIZI DEĞİL — ölçüldü: `schemas.py`'ye dummy alan eklenip hiçbir şey regen edilmeden `frontend` adımı koşuldu, `exit 0`) | **yakalanır** — lint-test blokluyor | **yakalanır** — lint-test blokluyor (değişmedi) |
| 2. Router değişti, `openapi.json` regen+commit, **client regen edilmedi** | 🟢 yeşil | 🔴 KIRMIZI | **merge edilebilirdi — açık delik** | **artık merge edilemez** — `frontend` zorunlu, PR pending'de bekler |
| 3. İkisi de regen edildi | 🟢 | 🟢 | temiz | temiz |

> Vaka-1'in düzeltmesi önemli: satır o zaman "drift-check kendi de kırmızı ama job zorunlu değil" diyordu — bu **olgusal yanlıştı**. `frontend` job'ı `make openapi` **koşmuyor**; yalnız committed (o an bayat kalmış) `openapi.json`'dan `npm run gen:api` ile client üretiyor. Router/schema kaynağı değişse de `openapi.json` dosyası regen edilmediyse sıfır fark oluşur → check zaten yeşildi (vaka-1'de zorunlu olsun ya da olmasın fark etmiyordu, çünkü hiç kırmızıya dönmüyordu). Asıl risk hep vaka-2'ydeydi.

### Gerçek olay: #221 → main kırmızı → #235 hotfix

PR #221 (T-60, presence router ekledi) merge olurken `/presence` regen edilmeden gitti. Merge sonrası main'in commit'i (`13be385`) için check-run kayıtları (`gh api repos/.../commits/13be385/check-runs`):

```
lint-test          → FAILURE
frontend           → SUCCESS
check-single-issue → SUCCESS
gitleaks           → SUCCESS
```

Yani bu olayda **öten `lint-test`'ti** (openapi.json tarafı) — `frontend` (client tarafı) o an zaten yeşildi çünkü olay tek-taraflıydı (yalnız openapi.json regen edilmemişti, o da yoktu henüz). Vaka-2'nin simetriği (openapi.json regen edilir, client edilmez) **o zamanki** required-check listesinde hiçbir zorunlu job'a değmiyordu — çünkü client-tarafı check `frontend`'de yaşıyor ve `frontend` henüz zorunlu değildi. #235 hotfix'i main'i düzeltti ama PR gövdesinde `Closes #56` yoktu (yalnız başlıkta `T-56:` vardı) → issue #56 açık kaldı. §7'deki ayar değişikliğiyle bu açık artık kapandı; bu PR issue'yu kapatıyor.

## 4. Pathspec tuzağı — neden cwd-göreli yazmak zorunlu

`frontend` job'ının `defaults.run.working-directory: src/frontend` olması nedeniyle, `Client tip drift-check` adımındaki `git diff` **cwd'den göreli** pathspec kullanmalı: `-- src/api/schema.d.ts`. Repo-kökü stilinde yazılırsa (`-- src/frontend/src/api/schema.d.ts`), git bunu cwd'ye (`src/frontend`) göre çözer → `src/frontend/src/frontend/src/api/schema.d.ts` aranır, hiçbir dosyayla eşleşmez → **`git diff --exit-code` sessizce `exit 0` döner** (fail-open, hiçbir hata/uyarı yok). Doğrulandı (§2 tablosu). `ci.yml`'deki yorum bunu işaretler — **pathspec'i değiştirirken dikkat**.

## 5. Neden saf-git kuplaj heuristiği ("openapi.json değiştiyse client de değişmiş olmalı") kullanılmıyor

Ölçülmüş karşı-örnek: `openapi.json`'da yalnız `info.version` + `tags` değiştirildi (router/schema şekli **aynı**) → `npm run gen:api` → `schema.d.ts`'te **sıfır fark** (`exit 0`). Yani "openapi.json diff'i boş değilse client diff'i de boş olmamalı" kuralı burada **yanlış-alarm** üretirdi — meşru-temiz bir PR'ı (yalnız metadata değişse bile) kırardı. Bu yüzden böyle bir saf-git guard **eklenmedi**; enforcement openapi-typescript'in kendi (deterministik) çıktısına bırakıldı.

## 6. CI süre maliyeti — neden client-check `lint-test`'e kopyalanmıyor

Son başarılı run'ın adım süreleri:

| Job | Toplam | Not |
|---|---|---|
| `lint-test` | ~22-25 sn | `uv sync` ~1 sn, test ~10 sn |
| `frontend` | ~92 sn | **`npm ci` ~80 sn**; `Client tip drift-check`'in kendisi **<1 sn** |

`npm`'i zorunlu `lint-test` job'ına sokmak süreyi **~4-5x** yapar ve 80 saniyelik `npm ci`'yi tekrarlar — drift-check'in kendisi anlık olduğu için bu bedel anlamsız. Ücretsiz bir GitHub ayarı (required-check listesine `frontend` ekleme) varken bu takas savunulamaz.

## 7. Kapanış — kod değil, ayar + belge

**Kod tarafında yapılan (bu PR):**
- `ci.yml` iki drift-check adımına açıklayıcı hata mesajı (`::error::` + `make contracts` reçetesi) — job'lar **taşınmadı/adı değişmedi**.
- `Makefile`'a **`make contracts`** (openapi + client'i birlikte regen eden tek komut).
- Bu doküman + `CONTRIBUTING.md`/`AGENTS.md` pointer satırları + `PULL_REQUEST_TEMPLATE.md` DONE-kapısı satırı.
- `tests/unit/test_ci_drift_guard.py` — `ci.yml`'i statik olarak doğrular (pathspec + job coupling).

**Kod tarafında yapılMAYAN (bilinçli, gerekçeli):**
- Client-check'in `lint-test`'e kopyalanması (§6).
- Saf-git kuplaj heuristiği (§5).
- `docs/sprint3-kontratlar.md:222` prose düzeltmesi ("derleme kırılır" → "CI drift-check kırılır") — 🔒FROZEN Ek E içinde, imza değil betimleyici metin; ayrı PO-onaylı docs PR'ına bırakıldı. Bu bulgunun kanıtı: kas testi B'de kıran şey `tsc`/`vite build` değil, `git diff --exit-code` adımıydı.

**Tek gerçek kapanış hamlesi — PO kararı, kod değil — 🟢 UYGULANDI (24 Tem):**

```
main branch protection → required_status_checks.contexts'e "frontend" eklendi
```

Önce: `["lint-test", "check-single-issue"]` → şimdi: `["lint-test", "check-single-issue", "frontend"]`. Doğrulama (24 Tem itibarıyla çalıştırıldı):

```bash
gh api repos/FatihErenCetin/grup54/branches/main/protection --jq '.required_status_checks.contexts'
# ["lint-test","check-single-issue","frontend"]
```

`frontend` artık listede — **vaka-2 deliği kapandı** (§3): client-tarafı drift (`openapi.json` regen edilir, `schema.d.ts` edilmez) artık `frontend` job'ı üzerinden zorunlu kapıya değiyor, merge PR pending'de bekler.

### Bilgi notları (PO kararı — bu PR'da değiştirilmedi)

- **`enforce_admins: false`** — zorunlu check'ler admin için **tavsiye niteliğinde**; admin bypass edebilir. (#221'in kırmızı `lint-test`'le nasıl merge edildiğinin olası açıklamalarından biri.)
- **`strict: false`** — branch'in `main` ile güncel olma zorunluluğu yok; iki ayrı yeşil PR ardışık merge edilince semantik çakışma (main kırmızı) olabilir. `strict: true` bunu kapatır ama merge'leri serileştirir (her merge sonrası CI yeniden) — go-live haftasında yüksek friction, bu PR'ın kapsamı değil.
