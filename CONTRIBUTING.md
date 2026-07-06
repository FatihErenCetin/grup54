# Katkı Rehberi (CONTRIBUTING)

Bu repoda **insanlar ve AI araçları** aynı git akışını izler. Bu rehber, `AGENTS.md`'deki sözleşmenin detaylı hâlidir.

## Akış (özet)

**Issue (story/task)** → `main`'den branch aç (`T-<id>`) → küçük commit'ler → PR aç (`Closes #<id>`) → **≥1 review** → **merge commit** → branch silinir.

---

## 0. İşe başla (atanmış issue'yu devral)

Yeni issue *açmıyorsan* (genelde açmazsın — backlog hazır), sana **atanmış** olanı al:

1. **Bul:** `gh issue list --assignee "@me"` (veya board'da sana atalı kart).
2. **Sahiplen:** atanmamışsa kendine ata + board'da kartı **In Progress**'e taşı.
3. **Beyan et:** WhatsApp daily'ye *"`T-<id>`'ye başlıyorum (modül X)"* yaz **ve önce başkası aynı modüle/dosyaya dokunuyor mu bak** → **çift-branch yarışını önle.** *(`.harness` gelince bu `declare_work` olur — çakışma-radarı yaparken çakışma yaşamayalım.)*
4. **Güncel main:** `git checkout main && git fetch origin && git merge origin/main` → sonra branch (§2).

> Bitirme akışının tamamı + DONE kapısı: [`docs/gelistirme-dongusu.md`](docs/gelistirme-dongusu.md). Sıfırdan story oluşturuyorsan → §1.

## 1. Story / Issue (işin kaynağı)

Her iş bir **GitHub Issue**'dan başlar — **`<id>` = issue numarası**.

- **Story** (`story` label · 🔵): varsayılan bir **user story** = kullanıcı değeri. Format: **"Bir `<rol>` olarak `<istek>` istiyorum, böylece `<fayda>`."** + **kabul kriteri** (ne zaman "Done") + **puan** (1-2-3-5-8) + `sprint-N` label.
- **Task** (`task` label · 🔴): teknik adım. Küçük task'ler story issue'sunun **içinde checklist** (`- [ ]`); büyük/ayrı izlenen task → ayrı `task` issue.
- **Kim:** PO backlog'u oluşturur/önceliklendirir (AI taslak çıkarabilir); ekip Sprint Planning'de puanlar.
- **Board:** issue'lar **GitHub Projects**'te otomatik akar: `Backlog → To Do → In Progress → In Review → Done / Rejected`.
- Yeni story: **New Issue → "📘 Story" şablonu**.

> **Terimler:** "story" = varsayılan **user story** (rol + istek + **fayda** cümlesi — jüri bunu puanlar). Saf-teknik/altyapı işi fayda cümlesine sığmıyorsa **enabler story** (yine `story` label) ya da **task** yaz — formata zorlama. *(Ürünün kullanıcısı geliştirici olduğu için "Bir geliştirici olarak…" story'leri tam birer user story'dir.)* Hiyerarşi: **Epic > Story > Task** (proje küçük → epic'e gerek yok). Kısaca: **user story ⊂ story.**

## 2. Branch

- **`main` korunur:** doğrudan push **YOK**; her şey branch + PR.
- **İsim:** `T-<id>-kisa-aciklama` (kebab-case, ASCII), `<id>` = issue no. Örn: issue **#6** → `T-6-cakisma-radari`.
- **Bir branch = bir issue.** Küçük ve odaklı tut.
- Çalışmadan önce `main`'i çek (`git checkout main && git pull`), sonra branch aç.

## 3. Commit

- **Küçük ve anlamlı:** bir mantıksal değişiklik = bir commit. "WIP / her şeyi yaptım" toplu commit'lerinden kaçın.
- **Format — Conventional-lite (güçlü öneri):** `<tip>: Türkçe açıklama`
  - Tipler: `feat:` · `fix:` · `docs:` · `chore:` · `refactor:` · `test:` · `style:`
  - Örnek: `feat: çakışma radarı dosya kesişimi` · `fix: webhook imza doğrulaması`
- **Dil:** açıklama **Türkçe**; tip önekleri + teknik token'lar İngilizce.
- **Yazar = işi yapan kişi** (kendi git kimliği). **Co-Authored-By EKLENMEZ** — commit'ler insan katkısını yansıtmalı (değerlendirme kriteri). AI-destekli olsa bile yazar = işi yönlendiren insan; AI yazar/co-author eklenmez.
- **⚠️ Git kimliği (graded — KRİTİK):** her üye **kendi makinesinde**, **kendi GitHub'ına bağlı email**'iyle commit'ler:
  ```bash
  git config user.name "Ad Soyad"
  git config user.email "github-hesabina-bagli@email"   # GitHub > Settings > Emails
  ```
  Email GitHub hesabına bağlı değilse commit, **katkı grafiğinde görünmez** → katkın *sayılmaz*. Kendi işini kendin commit'le.
- **Sırlar/anahtarlar asla commit'lenmez** (`.env`, `.gitignore`).

## 4. Pull Request (PR)

- **Ne zaman:** görev review'a hazır olunca (erken görünürlük → **draft PR**).
- **Başlık:** `T-<id>: kısa açıklama`.
- **Açıklama:** **`Closes #<id>`** (issue'yu **otomatik kapatır**) + *ne / neden* + (UI değişikliğiyse) ekran görüntüsü.
- **Review:** merge'den önce **≥1 takım arkadaşı onayı** — **[`docs/review-rehberi.md`](docs/review-rehberi.md)'ne göre** (AI aracınla: rehberi okut, PR'ı incelet; karar sende). **SLA:** ≤24 saat (blocker'lar daha hızlı).
- **Merge yöntemi: Merge commit** (commit'ler korunur → katkı görünür). **Kim merge'ler:** PR'ı **açan kişi** (≥1 onaydan sonra). **Merge sonrası branch otomatik silinir.**
- **Çakışma:** PR'dan önce `main`'i branch'e çekip çakışmayı çöz.

## Manuel vs Otomatik

| Manuel (insan/ajan) | Otomatik |
|---|---|
| issue açma · branch · commit · PR açma · review · merge | board kartı (GitHub Projects, issue/PR durumundan) · `Closes #<id>` ile issue kapanışı · merge sonrası branch silme · *(ileride)* CI |

## Hızlı referans

```bash
# 0) GitHub'da issue aç (örn. #6) — "📘 Story" şablonu
git checkout main && git pull
git checkout -b T-6-cakisma-radari
# ... değişiklik ...
git add -p && git commit -m "feat: çakışma radarı dosya kesişimi"
git push -u origin T-6-cakisma-radari
gh pr create --title "T-6: çakışma radarı" --body "Closes #6 — ..."
# ≥1 onay → "Merge commit" ile merge → issue #6 kapanır, branch otomatik silinir
```

---

> Tam ajan sözleşmesi: [`AGENTS.md`](AGENTS.md). Ekip ritmi (cadence: daily 22:00) + backlog dağıtımı → ekip-içi süreç dokümanı.
