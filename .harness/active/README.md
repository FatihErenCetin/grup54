# `.harness/active/` — canlı beyanlar

Her dosya **1 yazara** ait: `active/<handle>.md` (insan) ya da
`active/<handle>-<araç>.md` (AI ajan, ör. `active/fatih-claude.md`) —
`AGENTS.md` §".harness/ döngüsü". İkinci bir kişi/ajan asla başkasının
dosyasına yazmaz; bu, çakışmayı dosya sisteminin kendisiyle önler (git merge
conflict'i değil, **kural** önler).

## Şema (`active.schema.json`)

Zorunlu alanlar: `type: active` · `handle` · `task_id` · `branch` · `paths`
(değişecek dosyalar, tahmini) · `updated_at` (ISO 8601). Opsiyonel: `module`,
`intent` (serbest metin, niyet).

```markdown
---
type: active
handle: fatih
task_id: T-190
branch: T-190-deploy-runbook
paths: [docs/deploy-runbook.md]
updated_at: "2026-07-25T17:40:00+03:00"
intent: "Runbook'a PGDATA notu ekliyorum"
---
```

## Döngü

1. İşe başlarken kendi dosyanı yaz/güncelle (yukarıdaki şablon).
2. İşi bitirince dosyanı **sil** (ya da boşalt) — bayat beyan kalmasın.
   Reaper/stale-cleanup (unutulmuş beyanları `since`/`expires` ile temizleyen
   otomasyon) henüz **planlı**, bu repoda yok (`internal/grup54_dizin_yapisi.md`
   §8) — bugün disiplin **kooperatif**.
3. Başkasının dosyasını okumadan (çakışma riski var mı?) kendi işine
   **başlama**.

Bugün bu klasör boş (`.gitkeep` dışında) — ilk beyan eden kişi/ajan bu
şablonu kullanır.
