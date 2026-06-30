# ProjectManagement — Scrum Kanıtı

Bu klasör, bootcamp'in **ayrı puanlanan** proje-yönetimi akışının kanıtıdır. Her sprint sonunda **6 zorunlu başlık** `SprintN/README.md`'de doldurulur; görsel kanıtlar aşağıdaki alt klasörlere **o an (canlı)** eklenir.

## 📁 Klasör → ne girer → ne zaman yakala

| Klasör | İçerik | Hangi başlık | Ne zaman |
|---|---|---|---|
| `SprintN/Meetings/` | **Toplantı screenshot'ları:** Sprint Planning · **Review** · **Retrospective** · ad-hoc ekip toplantıları (katılımcılar görünür) | Review (5) · Retro (6) | **toplantı ANINDA** |
| `SprintN/DailyScrum/` | Günlük scrum kanıtı (WhatsApp/Slack thread screenshot, 22:00) | Daily Scrum (2) | **her gün** |
| `SprintN/Board/` | GitHub Projects + Miro board screenshot'ı (sprint **başı** + **sonu**) + renk kodu açıklaması | Sprint Board Update (3) | sprint başı/sonu |
| `SprintN/Burndown/` | Burndown grafiği (`.png`) + verisi (`.csv`) | Burndown (bonus) | sprint sonu |
| `SprintN/Screenshots/` | Çalışan ürün görselleri / GIF | Ürün Durumu (4) | özellik çalışınca |
| `General/` | logo · persona · lean-canvas · ekip fotoğrafları | (genel) | bir kez |

## 🏷️ Adlandırma (ASCII · ISO tarih · **dış link YOK**, görsel repoya commit'lenir)

- **Toplantı:** `sprint-planning-2026-06-30.png` · `sprint-review-2026-07-05.png` · `retro-2026-07-05.png` · `meeting-2026-07-01.png`
- **Daily:** `daily-2026-07-01.png`
- **Board:** `board-2026-07-01-start.png` · `board-2026-07-05-end.png`
- **Burndown:** `burndown-sprint1.png` · `burndown-sprint1.csv`
- Türkçe karakter/boşluk **yok** (cross-OS güvenli).

## ⚠️ CANLI yakala — kurtarılamaz

Daily, board ve toplantı görüntüleri **o an** alınmazsa **sonradan üretilemez** → sprint sonunda PM puanını sessizce kaybedersin. Özellikle:
- **Sprint Planning / Review / Retro** toplantısı bittiği an → ekran görüntüsü al, `Meetings/`'e koy.
- **Daily** mesajları → günün sonunda thread screenshot'ı → `DailyScrum/`.
- **Board** → sprint açılışı + kapanışı → `Board/`.

**Sorumlu:** SM (Esma) toplar + `SprintN/README.md`'de bu görsellere atıf verir; herkes kendi kanıtını ekler.
