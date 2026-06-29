# AGENTS.md — grup54 / Ensemble · AI Ajan Sözleşmesi

> Bu dosya, bu repoda çalışan **tüm AI araçları için kanonik çalışma sözleşmesidir** (araç-bağımsız: Claude Code, Codex, Gemini CLI, Antigravity, Kiro …). Aracın bunu doğrudan okur ya da kendi dosyası (örn. `CLAUDE.md`) buna yönlendirir. **Kurallar burada; tek kaynak — başka yerde tekrar etme.**

**Takım (4 kişi, herkes geliştirir):** PO **Fatih Eren Çetin** · SM **Esma Fazilet Karagülle** · Developer **Enes Talha Erdem** & **Semih Marufoğlu**. (Detay + sosyal: `README.md`.)

---

## Proje

Ensemble *(çalışma adı)* — AI çağı yazılım ekipleri için **paylaşılan proje beyni / koordinasyon aracı**: GitHub aktivitesinden proaktif **çakışma radarı**, canlı **scope-drift bekçisi**, kendiliğinden dolan **sprint board**, doğal dille **"projeye sor"**. Ortak bağlam repo içindeki `.harness/`'ta yaşar; hem insanlar (web pano) hem AI araçları (MCP) aynı bağlamı okur/yazar.

**Stack:** Python + FastAPI (engine) · React + Tailwind (web) · Postgres + pgvector (MVP: SQLite + FAISS, yalnızca index/cache) · Gemini (embeddings + "judge") · MCP server (önce-okuma MVP) · GitHub App (webhook + API). Çalışma modu **local-first**; demo için tek hosted örnek.

## Mimari ilkeler (uyulacak)

- **`.harness/` kanoniktir** (git ile senkron, audit bedava). DB ondan türetilen projeksiyondur; çelişkide **`.harness/` kazanır**.
- **Onboarding ≠ Ingest:** Onboarding tek seferlik (`.harness/` üretir); Ingest sürekli (git olaylarını akıtır).
- **MCP bir senkron değil, ajan arayüzüdür.** Senkronu git (local) ya da sunucu + webhook (hosted) yapar.
- **Engine katmanlı:** çekirdek mantık (çakışma · scope-drift · judge) FastAPI/React'ten bağımsız → bağımsız test edilebilir.

## Çalışma konvansiyonları  🟢 *(şimdi geçerli)*

- **Branch:** `T-<id>-kisa-aciklama` (board eşleşmesi için). **PR açıklaması:** `Closes T-<id>`.
- **Commit'ler küçük ve anlamlı.** main'e doğrudan push / tek-commit toplu yükleme **YOK** → her üyenin katkısı git geçmişinde **ayrı görünür** (değerlendirme kriteri). **Yazar = işi yapan kişi** (kendi GitHub-bağlı email'i); **AI yazar/co-author olarak EKLENMEZ.**
- **Her PR**, merge'den önce **en az 1 takım arkadaşı review onayı** alır.
- **Commit formatı = Conventional-lite** (`feat:/fix:/docs:/chore:` + Türkçe açıklama) · **merge = merge commit** (commit'ler korunur) · merge sonrası branch **sil** · PR'ı **açan kişi merge'ler**. Tam akış → [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Sırlar `.env`'de**, asla commit'lenmez (`.gitignore`'da); anahtar/secret koda gömülmez.
- **Doküman dili Türkçe; dosya/klasör adları ASCII** (Türkçe karakter/boşluk yok) — cross-OS güvenli.

## Kapsam disiplini

- **ÇEKİRDEK (mükemmel olmalı):** semantik çakışma + scope-drift tespiti + "ne zaman uyar" kalibrasyonu.
- **KABUK (ince yeter):** web pano · self-dolan board · onboarding sihirbazı.
- **STRETCH:** MCP write-back · agentic aksiyon · Slack/Discord · IDE eklentisi.
- Yeni özellikten önce ilgili dokümanı ve (oluşunca) `.harness/scope/`'u dikkate al — **kapsam dışına çıkma.** ⚠️ "OS/platform" şişmesinden kaçın; bir şey olağanüstü (radar), gerisi ince.

## `.harness/` döngüsü  🟡 *(henüz yok — `.harness/` oluşunca zorunlu)*

`.harness/` geldiğinde **her ajan ve insan** düzenlemeden önce (dogfood):
1. **Oku** — `.harness/active/*`: kim neye dokunuyor? (çakışma riski var mı?)
2. **Beyan et** — kendi `.harness/active/<handle>.md`'ni güncelle (task · modül · niyet · branch). Ajan kendi `<handle>-<arac>.md` dosyasına yazar (yazar başına 1 dosya → çakışma yok).
3. **Kontrol et** — `.harness/scope/sprint-N.md`: yapılan iş kapsam içinde mi?

İş bitince `active/` beyanını **temizle**. MCP geldiğinde döngü `who_is_touching` / `declare_work` / `check_scope` araçlarıyla otomatikleşir.
Şema: `scope/` · `tasks/T-<id>-*.md` (board'ın tek kaynağı) · `active/<handle>.md` · `locks/` · `decisions/`.

## Ne nereye (repo haritası)

- `README.md` — public ürün açıklaması + takım tablosu.
- `AGENTS.md` — bu dosya (ajan sözleşmesi). `CLAUDE.md` → Claude Code'u buraya yönlendirir.
- `src/` — kod (backend/engine · mcp · frontend · shared)  🟡 *henüz yok*
- `ProjectManagement/SprintN/` — sprint kanıtı (DailyScrum · Board · Burndown · Screenshots)  🟡 *henüz yok*
- `.harness/` — kanonik ortak bağlam (scope · tasks · active · locks · decisions)  🟡 *henüz yok*

## Build / test / çalıştırma  🟡 *(scaffold edilince doldurulacak)*

Henüz kod yok. Mimariye göre beklenen (kesinleşince burada güncelle):
- **backend:** `uv run uvicorn ...` · **test:** `uv run pytest` (tek test: `uv run pytest path::test_x`)
- **frontend:** `npm run dev` / `npm test` · **MCP:** lokal stdio
- Çalışma modu local-first → arayüz `localhost:PORT`. Kanonik komut listesi: `Makefile` (geldiğinde).

## Ajan davranışı

- Riskli / çok-dosyalı değişikliklerde **önce plan sun, onay bekle.**
- Belirsizlikte makul varsay, **varsayımı açıkça belirt.**
- Çekirdek (çakışma/scope-drift) gibi **kalibrasyona duyarlı** yerlerde: bir değişiklik, eval/backtest kabul edilebilir false-positive oranı gösterene dek "bitti" sayılmaz.
- Mevcut kod ve desenleri izle; bir dosya büyüdüyse bu çoğu zaman "çok iş yapıyor" sinyalidir.
- **Sprint dokümanı (cadence):** AI, `ProjectManagement/SprintN/README.md`'nin 6 başlığını sürekli taslaklar (daily log + board + görsellerden); **finalize + commit = SM (insan rakam/katılımcı doğrular).** Ajan README'yi tek başına commit'lemez — girdileri derler. Detay süreç: ekip-içi süreç dokümanı.

---

> **Bu dosya public'tir.** Strateji, rakip analizi, değerlendirme kriterleri, karar kaydı gibi **özel** bağlam burada **yer almaz** (ekip-içi tutulur, repo'ya push edilmez). **Sırlar hiçbir yerde commit edilmez.** Kişisel araç tercihleri her üyenin kendi makinesinde (`~/.claude` vb.).
