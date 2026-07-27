# `.harness/locks/modules.md` — yumuşak (advisory) modül kilitleri

> **Kooperatif, git zorlamaz.** Bir gün+ sürecek işe başlarken satır ekle; iş
> bitince satırı **sil**. Amaç: "bu modülde uzun süreli bir iş var, üstüne
> yazmadan önce sahibiyle konuş" sinyali — `AGENTS.md` §".harness/ döngüsü"
> adım 1 (oku) bu dosyayı da kapsar.

Bu dosya bugün **boş şablon**; ilk kilidi ekleyen kişi aşağıdaki tabloyu
doldurur (front-matter'lı ayrı `locks/<id>.md` dosyaları da geçerlidir —
`lock.schema.json`: zorunlu `type: lock, id, owner, paths`, opsiyonel
`expires_at`).

## Kullanım

| Modül (path prefix) | Sahip (handle) | Sebep | Eklenme | `expires_at` |
|---|---|---|---|---|
| _(satır yok — kilit ekleyince buraya ekle)_ | | | | |

Kilit eklerken:
1. Modülü **path prefix** olarak yaz (ör. `src/backend/ensemble/engine/`), tek
   dosya değil — genelde bir alt-paketi kapsayan iş için kullanılır.
2. `expires_at` gerçekçi bir tarih olsun (bir gün+ süren işler için) — süresi
   geçmiş kilit fiilen geçersizdir, silinmesi beklenir.
3. İş bitince (PR merge) **satırı sil** — bayat kilit başkasını gereksiz
   yere durdurur.

Front-matter'lı tekil dosya kullanmak istersen:

```markdown
---
type: lock
id: L-1
owner: fatih
paths: [src/backend/ensemble/engine/]
expires_at: "2026-08-01"
---
Sebep: T-190 runbook + deploy CD dizisini tek elden bitiriyorum.
```
