# CLAUDE.md — Claude Code yönlendiricisi (router)

> Bu repoda **çalışma kuralları, mimari ve konvansiyonlar `AGENTS.md`'dedir** — tüm AI araçları için kanonik, public sözleşme. **Claude Code: `AGENTS.md`'yi oku ve uygula.** Kuralları burada tekrar etmiyoruz (tek kaynak → drift yok).

## Claude Code'a özel

- **Özel bağlam** (strateji · plan · YZ puan kriterleri · karar kaydı) `CLAUDE.local.md` ile yüklenir — **gitignored, ekip-içi, push edilmez.** (Bu mekanizma Claude Code'a özeldir; diğer araçlar `OKU.md`'deki yola bakar.)
- **Public ürün + takım özeti:** `README.md`.
- Ajan davranışı (riskli değişiklikte önce plan · belirsizlikte varsayımı belirt · `.harness/` döngüsü) → `AGENTS.md`.

> Repo durumu: henüz kod yok; `git init` + iskele birlikte kurulacak. Public/özel ayrımı: kod + kanıt + sözleşme public; strateji `internal/` (gitignored). Detay: `AGENTS.md` + `CLAUDE.local.md`.
