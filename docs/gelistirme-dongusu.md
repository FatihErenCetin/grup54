# Geliştirici Çalışma Döngüsü (issue → done)

> Sana **atanmış** bir issue'yu **bizimle tutarlı** bitirmenin **tek** rehberi. Araç-bağımsız (Claude · Codex · Gemini · Kiro · Antigravity). Kural detayları: [`AGENTS.md`](../AGENTS.md) + [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Akış (7 adım)

1. **AL.** `gh issue list --assignee @me` (veya board'da sana atalı kart) → birini seç. Kartı **In Progress**'e taşı. WhatsApp daily'ye *"`T-<id>`'ye başlıyorum (modül X)"* yaz + **başkası aynı yere dokunuyor mu bak** (çift-branch yarışını önle — ürünümüzün çözdüğü problemi kendimiz yaşamayalım). → [CONTRIBUTING §0](../CONTRIBUTING.md)
2. **ANLA (ortak vizyon).** Şunları oku: issue'nun **kabul kriteri** · [`AGENTS.md`](../AGENTS.md) **mimari ilkeleri** · ilgili **kontrat** ([`docs/sprint2-kontratlar.md`](sprint2-kontratlar.md) — port/endpoint imzası) · **kapsam** ([`docs/kapsam-sinirlari.md`](kapsam-sinirlari.md) — **YAPMA listesi**).
3. **BRANCH.** `git checkout main && git pull` → `git checkout -b T-<id>-kisa-aciklama`.
4. **GELİŞTİR.** Kontrat imzasını **DEĞİŞTİRME** (başkasının stub'ını kırarsın; gerekiyorsa önce `docs/`'a PR + daily'de duyur). Kapsam-dışına **çıkma**. Çekirdekse (çakışma/scope-drift) eval'siz "done" deme.
5. **COMMIT.** Conventional-lite (`feat:/fix:/docs:`), küçük, **kendi git kimliğin** (Co-Authored-By YOK). → [CONTRIBUTING §3](../CONTRIBUTING.md)
6. **DAILY.** Günün sonunda WhatsApp daily (dün/bugün/blocker) + kanıt → [`ProjectManagement/README.md`](../ProjectManagement/README.md).
7. **PR.** `Closes #<id>` + ne/neden + (UI ise) görsel. **≥1 review** ([`review-rehberi.md`](review-rehberi.md)'ne göre) → **merge commit** → branch otomatik silinir. → [CONTRIBUTING §4](../CONTRIBUTING.md)

## ✅ DONE kapısı — hepsi sağlanmadan "bitti" deme

- [ ] Issue **kabul kriteri** karşılandı
- [ ] **Kontrat imzasına** uyuldu (değiştiyse `docs/sprint2-kontratlar.md`'ye PR + daily duyuru)
- [ ] **Kapsam temiz** — `kapsam-sinirlari.md` YAPMA listesinden hiçbir şey yapılmadı (özellikle ⚠️ user-login/OAuth tuzağı)
- [ ] **Çekirdek** ise (çakışma/scope-drift/judge): eval/backtest **kabul edilebilir false-positive** gösteriyor
- [ ] Test yeşil *(kod/CI geldiğinde)*
- [ ] **≥1 review onayı** → merge

> Tek "done" tanımı budur — issue checklist'i + kontrat + kapsam + (çekirdekse) eval birlikte. Biri eksikse iş bitmemiştir.
