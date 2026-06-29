# Katkı Rehberi (CONTRIBUTING)

Bu repoda **insanlar ve AI araçları** aynı git akışını izler. Bu rehber, `AGENTS.md`'deki sözleşmenin detaylı hâlidir.

## Akış (özet)

`main`'den branch aç → küçük commit'ler → PR aç (`Closes T-<id>`) → **≥1 review** → **merge commit** → branch silinir.

---

## 1. Branch

- **`main` korunur:** doğrudan push **YOK**; her şey branch + PR ile gelir.
- **İsim:** `T-<id>-kisa-aciklama` (kebab-case, ASCII). Örn: `T-12-auth-formu`, `T-7-cakisma-radari`.
- **`<id>`** = görev/story numarası. *(İleride GitHub Issue numarası → `Closes T-<id>` issue'yu otomatik kapatır; şimdilik manuel sıra.)*
- **Bir branch = bir görev/story.** Küçük ve odaklı tut.
- Çalışmadan önce `main`'i çek (`git checkout main && git pull`), sonra branch aç.

## 2. Commit

- **Küçük ve anlamlı:** bir mantıksal değişiklik = bir commit. "WIP / her şeyi yaptım" toplu commit'lerinden kaçın.
- **Format — Conventional-lite (güçlü öneri):** `<tip>: Türkçe açıklama`
  - Tipler: `feat:` (yeni özellik) · `fix:` (hata) · `docs:` (doküman) · `chore:` (bakım/config) · `refactor:` · `test:` · `style:`
  - Örnek: `feat: çakışma radarı dosya kesişimi` · `fix: webhook imza doğrulaması` · `docs: README takım tablosu`
- **Dil:** açıklama **Türkçe**; tip önekleri + teknik token'lar İngilizce.
- **Yazar = işi yapan kişi** (kendi git kimliği). **Co-Authored-By EKLENMEZ** — commit'ler insan katkısını yansıtmalı (değerlendirme kriteri).
- **Sırlar/anahtarlar asla commit'lenmez** (`.env`, `.gitignore`).

## 3. Pull Request (PR)

- **Ne zaman:** görev review'a hazır olunca. Erken görünürlük istersen **draft PR** aç.
- **Başlık:** `T-<id>: kısa açıklama`.
- **Açıklama:** `Closes T-<id>` + *ne / neden* + (UI değişikliğiyse) ekran görüntüsü.
- **Review:** merge'den önce **≥1 takım arkadaşı onayı**. **SLA:** en geç ertesi **22:00 daily**'ye kadar review (blocker PR'lar daha hızlı).
- **Merge yöntemi: Merge commit** — her commit main'de korunur → herkesin katkısı görünür. *(Squash/rebase kullanma.)*
- **Kim merge'ler:** PR'ı **açan kişi**, ≥1 onaydan sonra kendi PR'ını merge eder.
- **Merge sonrası branch silinir** (GitHub otomatik siler).
- **Çakışma:** PR'dan önce `main`'i branch'e çekip çakışmayı çöz.

## Manuel vs Otomatik

| Manuel (insan/ajan) | Otomatik |
|---|---|
| branch açma · commit · PR açma · review · merge | board kartı (GitHub Projects, PR/issue durumundan) · merge sonrası branch silme · *(ileride)* CI |

## Hızlı referans

```bash
git checkout main && git pull
git checkout -b T-12-auth-formu
# ... değişiklik ...
git add -p && git commit -m "feat: auth formu doğrulaması"
git push -u origin T-12-auth-formu
gh pr create --title "T-12: auth formu" --body "Closes T-12 — ..."
# ≥1 onay → "Merge commit" ile merge → branch otomatik silinir
```

---

> Tam ajan sözleşmesi: [`AGENTS.md`](AGENTS.md). Ekip ritmi (cadence: daily 22:00, sprint doldurma) → ekip-içi süreç dokümanı.
