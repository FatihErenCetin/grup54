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

## 3. Asıl boşluk: vaka-2 hiçbir zorunlu check'e yakalanmıyor

İki check **farklı job'larda** yaşıyor ve main branch protection'ın zorunlu (required) status check listesi bugün yalnız:

```
required_status_checks.contexts = ["lint-test", "check-single-issue"]
```

`frontend` **listede yok**. Vaka matrisi:

| Vaka | `lint-test` (zorunlu) | `frontend` (zorunlu DEĞİL) | Sonuç |
|---|---|---|---|
| 1. Router değişti, ikisi de regen edilmedi | 🔴 KIRMIZI | 🟢 (drift-check kendi de kırmızı ama job zorunlu değil) | **yakalanır** — lint-test blokluyor |
| 2. Router değişti, `openapi.json` regen+commit, **client regen edilmedi** | 🟢 yeşil | 🔴 KIRMIZI | **merge edilebilir — açık delik** |
| 3. İkisi de regen edildi | 🟢 | 🟢 | temiz |

### Gerçek olay: #221 → main kırmızı → #235 hotfix

PR #221 (T-60, presence router ekledi) merge olurken `/presence` regen edilmeden gitti. Merge sonrası main'in commit'i (`13be385`) için check-run kayıtları (`gh api repos/.../commits/13be385/check-runs`):

```
lint-test          → FAILURE
frontend           → SUCCESS
check-single-issue → SUCCESS
gitleaks           → SUCCESS
```

Yani bu olayda **öten `lint-test`'ti** (openapi.json tarafı) — `frontend` (client tarafı) o an zaten yeşildi çünkü olay tek-taraflıydı (yalnız openapi.json regen edilmemişti, o da yoktu henüz). Ama **vaka-2'nin simetriği** (openapi.json regen edilir, client edilmez) bugünkü required-check listesinde **hiçbir zorunlu job'a değmez** — çünkü client-tarafı check `frontend`'de yaşıyor ve `frontend` zorunlu değil. #235 hotfix'i main'i düzeltti ama PR gövdesinde `Closes #56` yoktu (yalnız başlıkta `T-56:` vardı) → issue #56 açık kaldı; bu PR onu kapatıyor.

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

**Yapılması gereken tek gerçek kapanış hamlesi — PO kararı, kod değil:**

```
main branch protection → required_status_checks.contexts'e "frontend" ekle
```

Bugün: `["lint-test", "check-single-issue"]`. Eklendikten sonra doğrulama:

```bash
gh api repos/FatihErenCetin/grup54/branches/main/protection --jq '.required_status_checks.contexts'
```

çıktısında `frontend` görünmeli.

### Bilgi notları (PO kararı — bu PR'da değiştirilmedi)

- **`enforce_admins: false`** — zorunlu check'ler admin için **tavsiye niteliğinde**; admin bypass edebilir. (#221'in kırmızı `lint-test`'le nasıl merge edildiğinin olası açıklamalarından biri.)
- **`strict: false`** — branch'in `main` ile güncel olma zorunluluğu yok; iki ayrı yeşil PR ardışık merge edilince semantik çakışma (main kırmızı) olabilir. `strict: true` bunu kapatır ama merge'leri serileştirir (her merge sonrası CI yeniden) — go-live haftasında yüksek friction, bu PR'ın kapsamı değil.
