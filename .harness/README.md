# `.harness/` — Ensemble'ın ortak beyni

> **Kanonik.** Bu klasör git ile senkron — audit bedava. `store/` (DB) burdan
> türetilen bir **projeksiyondur**; ikisi çelişirse **`.harness/` kazanır**
> (`AGENTS.md` §"Mimari ilkeler", `internal/grup54_dizin_yapisi.md` §7).
>
> **#242 ile git'e alındı** (bu klasör önceden yalnızca onboarding sihirbazının
> (`src/backend/ensemble/onboarding/wizard.py`) tek seferlik çalıştırılınca
> diskte oluşan, hiç commit'lenmemiş bir çıktıydı — repoda 0 dosya vardı).

## 1. Şema haritası (front-matter → JSON-schema)

Her `.harness/<klasör>/*.md` dosyası **YAML front-matter + gövde** biçimindedir.
Front-matter, `src/shared/ensemble_shared/schemas/<type>.schema.json`'a göre
doğrulanır — okuma/yazma **tek** kapıdan geçer: `ensemble_shared.harness.FileHarnessPort`
(`scripts/harness_validate.py` de aynı `_read_markdown` yolunu kullanır, CI'da).

| Klasör | `type` | Şema | Zorunlu alanlar | Ne tutar | Kim yazar |
|---|---|---|---|---|---|
| `scope/sprint-N.md` | `scope` | `scope.schema.json` | `type, sprint, title` | Kararlaştırılan/dondurulan sprint kapsamı (hedef · kapsam-dışı) | **PO** yazar ve dondurur |
| `tasks/T-<id>-*.md` | `task` | `task.schema.json` | `type, task_id, title, status` | Her story/task = 1 dosya — **board'ın tek kaynağı** | Onboarding/backfill taslaklar, ekip onaylar; durum geçişini **yalnız ingest** yazar (gerçek PR/issue durumundan) |
| `active/<handle>.md` | `active` | `active.schema.json` | `type, handle, task_id, branch, paths, updated_at` | "Şu an neye dokunuyorum" — yazar başına **1 dosya** | Herkes **kendi** dosyasını günceller; AI ajan kendi `<handle>-<araç>.md`'sine yazar |
| `locks/*.md` | `lock` | `lock.schema.json` | `type, id, owner, paths` | Yumuşak (advisory) modül kilidi | Uzun süren iş için elle eklenir, bitince silinir |
| `decisions/D-NN-*.md` | `decision` | `decision.schema.json` | `type, id, title, date` | Operasyonel karar günlüğü (append-only) | SM/PO/dev önemli kararda ekler |

`additionalProperties: true` — şemalar yukarıdaki alanları **zorunlu** kılar,
fazladan alan eklemeyi yasaklamaz (ör. `task`'a `assignee`/`branch`/`paths`).

## 2. Front-matter sözleşmesi

```markdown
---
type: task            # şemanın "const"/"enum" alanı — parser bunu okuyup doğru şemayı seçer
task_id: T-190
title: "..."
status: in_review      # task.schema.json enum: backlog · todo · in_progress · in_review · done
---
Gövde — serbest metin (Markdown).
```

- İlk satır **tam olarak** `---`, front-matter'ı kapatan satır da **kolon-0'da tam** `---`
  (bir YAML block-scalar içindeki girintili `---` kapanış sayılmaz — bkz.
  `FileHarnessPort._parse_frontmatter`).
- Tarihsiz/tırnaksız ISO tarihler YAML tarafından `datetime`'a çevrilebilir;
  `_coerce_dates` bunu geri stringe çevirir (şemalar string bekler).
- Dosyalar UTF-8 (BOM'lu da kabul edilir — Windows editörleri için).
- **Path traversal kapalı:** `handle`/`sprint` girdileri `^[A-Za-z0-9_.-]+$` ile
  sınırlı; task/scope `title`'dan üretilen dosya-adı slug'ı yalnız
  `[a-z0-9-]` içerir (bkz. `_slugify` — Türkçe karakterler slug'ta düşer,
  bilinen/kabul edilmiş davranış).

## 3. Döngü (düzenlemeden ÖNCE — `AGENTS.md` §".harness/ döngüsü")

1. **Oku** — `active/*`: kim neye dokunuyor? (çakışma riski var mı?)
2. **Beyan et** — kendi `active/<handle>.md`'ni güncelle (task · modül · niyet ·
   branch). AI ajan kendi `<handle>-<araç>.md` dosyasına yazar (yazar başına 1
   dosya → çakışma yok).
3. **Kontrol et** — `scope/sprint-N.md`: yapılan iş kapsam içinde mi?

İş bitince `active/` beyanını **temizle**. MCP (S3, `#32`) `who_is_touching` /
`check_scope` ile okuma tarafını otomatikleştirir; yazma (`declare_work`) S3
stretch'tir — bkz. `docs/sprint3-kontratlar.md` Ek D.

## 4. `tasks/` — hangi issue'lar dosyalandı, hangileri değil

`tasks/` **aktif milestone'daki (Sprint 3, #3) TÜM issue'lar değil** — kural:

- **Yalnız `state=OPEN` issue'lar** birer `tasks/T-<id>-*.md` dosyası aldı (22
  dosya, `gh issue list --milestone "Sprint 3" --state all` çıktısındaki 49
  issue'nun `state=OPEN` olan 22'si — milestone'ın kendi `open_issues: 22`
  sayacıyla birebir örtüşüyor).
- **`state=CLOSED` (done) issue'lar bilerek DIŞARIDA bırakıldı.** Gerekçe:
  `tasks/` **süren işi** koordine etmek için var (dogfood: "kim neye
  dokunuyor" sorusuna cevap); tamamlanmış iş zaten PR/commit geçmişinde
  kalıcı ve sorgulanabilir kayıt altında — bu bir kerelik geriye-dönük
  yazımın onu tekrar üretmesi hem TDK'yi (tek doğruluk kaynağı = git
  geçmişi) hem "durum geçişini yalnız ingest yazar" ilkesini ihlal eder.
  İleride ingest (henüz yok) bir issue kapanınca `status: done` geçişini
  **gerçek zamanlı** yazacak — bu script/backfill değil.
- **`status` alanı üç gerçek sinyalden türetildi** (uydurma yok):
  - Issue'yu kapatan **açık bir PR** varsa (`Closes #<id>` gövdesinde
    eşleşti) → `status: in_review`, `branch:` o PR'ın `headRefName`'i.
  - Açık PR yok ama GitHub `assignee` atanmışsa → `status: todo`.
  - Ne PR ne assignee varsa → `status: backlog`.
  - `in_progress` **hiç kullanılmadı** — GitHub'da "birisi gerçekten
    kodlamaya başladı mı" diye ölçülebilir üçüncü bir sinyal yok; assignee
    varlığını "başladı" diye yorumlamak uydurma olurdu.
- `paths: []` — hepsi boş bırakıldı: hangi dosyaların değişeceği issue
  başlığından **tahmin edilmedi** (uydurma riski); gerçek `paths` ancak PR
  diff'inden (ingest, henüz yok) doğru şekilde doldurulabilir.
- Kaynak veri: `gh issue list --milestone "Sprint 3" --state all --json
  number,title,state,labels,milestone,assignees` + `gh pr list --state open
  --json number,title,headRefName,body` (Closes-# eşlemesi için). Üretim
  `FileHarnessPort.write_task` üzerinden yapıldı (production ile aynı
  slug/atomic-write yolu).

## 5. `scope/sprint-3.md` — kaynağı

`goal`/`in_scope`/`non_goals` **uydurulmadı**; `docs/sprint3-kontratlar.md`
(Ek A–F, 🔒 FROZEN) + GitHub milestone "Sprint 3" (#3, bitiş 2026-08-02)
metninden birebir taşındı. `commit_sha`/`frozen_at`, o dosyaya en son dokunan
gerçek commit'e (`5cf2009`) işaret eder. Kapsam değişirse **PO** bu dosyayı
düzenler/dondurur (`internal/grup54_dizin_yapisi.md` §3).

`status` alanının **`ScopeService`'in okuduğu tek geçerli "kullanılabilir"
değeri `frozen`'dır** (`engine/scope.py::get_current_scope`, `casefold`
karşılaştırması — `GET /scope/current`). `draft` **açıkça** yasak
(`scope_context.py::scope_items` — judge hiç çalışmaz, `check_scope` de
kapanır). PO taslağı gözden geçirip dondurana kadar başka bir ara değer
(`accepted` gibi) kullanılabilir ama bu durumda `GET /scope/current` **503
`scope_unavailable`** döner — "PO onayı bekleniyor" durumu kanıtsız
görünmesin diye kasıtlı (#242 BLOCKER 2: bu dosya bir süre `status: accepted`
taşıdı ve endpoint'i sessizce 503'te bıraktı — `docs/sprint3-kontratlar.md`
zaten FROZEN işaretliyken front-matter'ın kendisi geride kalmıştı).

## 6. `active/` — henüz boş

Canlı beyanlar kişiye/ajana ait; kimse başkasının dosyasına dokunmaz. Bugün
`.gitkeep` dışında dosya yok — ilk `active/<handle>.md`'yi ekleyecek kişi/ajan
§3'teki döngüyü izler.

## 7. `locks/modules.md` — kullanım

Bir gün+ sürecek iş için satır ekle (modül, sahip, sebep, `expires_at`); iş
bitince satırı sil. Tamamen **kooperatif** — git bunu zorlamaz, sadece
görünür kılar. Dosyanın kendisi `type: lock` şemasına uyan front-matter'lı
**ayrı dosyalar** olarak da tutulabilir (`locks/<id>.md`); bu repo şimdilik
tek bir boş şablon (`locks/modules.md`) ile başlıyor.

## 8. `decisions/` — operasyonel karar günlüğü + migrasyon notu

`decisions/D-NN-*.md` **append-only** — SM/PO/dev önemli bir karar alınca
ekler, geçmiş dosyalar düzenlenmez (yalnız `status` alanı güncellenebilir).

⚠️ **Migrasyon bilerek yapılmadı:** ekibin bugüne kadarki operasyonel karar
kaydı `internal/grup54_karar_logu.md`'de yaşıyor — ama o dosya **gitignored**
(özel strateji, `CLAUDE.local.md` @import zinciriyle yüklenir, push
edilmez). Oradaki kararları buraya **kopyalamak** iki doğruluk kaynağı
yaratır ve özel bağlamı public repoya sızdırma riski taşır (hangi kararın
public'e taşınabilir olduğuna PO karar vermeli). Bu yüzden `decisions/`
bugün **boş** (`.gitkeep`) başlıyor; geriye dönük migrasyon — hangi D-NN'lerin
buraya taşınacağı — ayrı bir PO kararı bekliyor.

## 9. Açılış (boot) sözleşmesi — fail-closed + `/board` ön koşulu

- **Fail-closed açılış kontrolü** (`ensemble.app.lifespan`, #242 BLOCKER 1b):
  uygulama açılırken `harness_port.read_scope(sprint)` başarısız olursa
  (`HarnessError`) süreç **gürültülü** çöker — sessizce boş board/scope'a
  düşmez. Gerekçe: bir konteyner dağıtımında `.harness/` host'tan salt-okunur
  bind-mount edilirse ve host'ta dizin yoksa, Docker orada **boş bir dizin**
  yaratıp imaja gömülü kopyayı maskeler; bu kontrol olmadan uygulama
  `read_tasks() == []` / `read_scope()` hatasıyla sessizce yarım açılırdı.
  Kontrol **yalnız uygulama açılışında** koşar (port/servis kurulumunda
  değil) — `tmp_path` köklü `FileHarnessPort` kullanan mevcut testler
  (`test_scope.py`, `test_harness.py`, ...) bundan etkilenmez.
- **`GET /board` belgelenmemiş ön koşulu:** taze bir checkout'ta `task_projection`
  tablosu henüz yok — `alembic upgrade head` (`cd src/backend && uv run alembic
  upgrade head`, ya da `make rebuild`) koşulmadan `GET /board`
  `sqlite3.OperationalError: no such table: task_projection` ile **500**
  döner. `.harness/` ile ilgisi yok (DB projeksiyonu, §7 "DB vs `.harness/`"
  kuralı) ama aynı "açılış ön koşulu" ailesinde olduğu için burada not
  düşülüyor — bkz. `tests/unit/test_harness_git.py` tüketici-seviyesi kilidi.

---

Şema kaynağı: `src/shared/ensemble_shared/schemas/*.json` · IO kaynağı:
`src/shared/ensemble_shared/harness.py` (`FileHarnessPort`) · CI doğrulaması:
`.github/workflows/harness-validate.yml` (`scripts/harness_validate.py`) +
`tests/unit/test_harness_git.py` (bu klasörün gerçekten var + şema-geçerli
olduğunu, gerçek repo köküne karşı, kilitler — #242).
