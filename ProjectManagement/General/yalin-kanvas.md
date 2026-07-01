# Ensemble — Yalın Kanvas

**Tarih:** 29 Haziran 2026 · **Durum:** v1 (hipotezler — doğrulanacak) · **Ürün:** Ensemble — paylaşılan proje beyni

> Yalın Kanvas, iş modelinin bloklarını **test edilebilir hipotezler** olarak tutar. 💡 = ekibin doğrulayacağı varsayım. *(Başlıklar YZTA Yalın Kanvas template'iyle hizalı.)*

## Tek bakışta

| Blok | Özet |
|---|---|
| **PROBLEM** | AI-destekli paralel çalışmada **çakışma · scope-drift · dağınık bağlam** |
| **HEDEF KİTLE** | Küçük, AI-destekli yazılım ekipleri; erken benimseyen: AI-forward indie/startup/hackathon |
| **BENZERSİZ DEĞER** | Çakışmayı + kapsam kaymasını — insan & ajan için, olmadan **önce**, `.harness/` üzerinden söyler |
| **ÇÖZÜM** | Proaktif çakışma radarı · canlı scope-drift · `.harness/` + MCP ortak bağlam |
| **KANALLAR** | GitHub Marketplace · source-available local-first · dev toplulukları · MCP ekosistemi |
| **GELİR KAYNAKLARI** 💡 | Source-available: çekirdek noncommercial $0; open-core = gelecek opsiyonu 💡 · hosted **Team** (koltuk başı) · **Org** |
| **MALİYET YAPISI** | LLM çıkarım (Gemini) · hosting · geliştirme — local-first maliyeti kullanıcıya kaydırır |
| **KİLİT METRİKLER** | Önlenen çakışma · yakalanan scope-drift · **false-positive oranı** · aktif takım |
| **REKABET AVANTAJI** | 4 parçanın kombinasyonu + git-yazılabilir `.harness/` + kalibrasyon know-how + dogfood |

---

## PROBLEM

AI ile herkes kendi asistanıyla (Cursor / Claude Code / Codex) kod yazınca ekip eşgüdümü kopar:
1. **Çakışma** — iki kişi *ya da onların AI ajanları* aynı yere dokunup merge çakışması / tekrarlı iş üretir; kimse **önceden** görmez.
2. **Kapsam kayması (scope-drift)** — iş, kararlaştırılan story'lerin dışına taşar; ancak PR-*sonrası* (CodeRabbit) ya da hiç fark edilmez.
3. **Dağınık bağlam** — her üyenin AI aracı izole; ortak, *yazılabilir*, denetlenebilir "kim ne yapıyor" bağlamı yok.

**Varolan Alternatifler:** Jira/Linear (durumu *gösterir*) · GitKraken/GitLive (dosya-düzeyi çakışma, ajan yok) · CodeRabbit (scope-drift ama PR-*sonrası*) · Slack standup (manuel) · AGENTS.md (salt-okuma). **Hiçbiri dördünü birleştirmez.**

## HEDEF KİTLE

**Birincil:** Küçük yazılım ekipleri (≈2–8 kişi), **özellikle herkesin kendi AI aracıyla paralel kod yazdığı** takımlar — çok-ajanlı dağınıklığı bugün yaşayanlar.
İkincil pazar: birden çok kişi + AI aracının aynı repoda çalıştığı her takım (büyüdükçe).

**Erken benimseyenler:** AI-forward **indie / startup** ekipleri · açık kaynak çekirdek ekipleri · **hackathon / bootcamp** grupları. *(Biz de buradayız → dogfood = otantik ihtiyaç; öğrenci/bootcamp = doğrulama köprübaşı, ödeyen segment değil.)*

## BENZERSİZ DEĞER

> **"Jira/Linear durumu *gösterir*, GitKraken çakışmayı *dosya düzeyinde* sezer, CodeRabbit *PR'dan sonra* kapsamı bakar — Ensemble bunları birleştirip, çalışma anında, hem insanların hem onların AI araçlarının çakışmasını ve kapsam kaymasını, repo içi `.harness/` ortak bağlamı üzerinden *önceden* söyler."**

**Üst-seviye kavram:** AI çağı ekipleri için *çarpışma-önleyici radar* + AI araçları için *ortak hafıza*.

## ÇÖZÜM (3 çekirdek özellik → 3 probleme)

| Probleme karşı | Özellik |
|---|---|
| Çakışma | **Proaktif çakışma radarı** — dosya/semantik kesişim, merge öncesi uyarı; ajanı ayrı aktör sayar |
| Scope-drift | **Canlı scope-drift bekçisi** — iş, `.harness/scope` story'lerine karşı; çalışma anında, PR-öncesi |
| Dağınık bağlam | **`.harness/` + MCP** — git-senkron, insan+ajan okur/yazar; kendiliğinden dolan board + "projeye sor" |

## KANALLAR

- **GitHub App / Marketplace** — repoya tek tık dağıtım + faturalama.
- **Source-available + local-first** (`pip`/`npx`) — sıfır-kurulum deneme.
- **Dev toplulukları** — HN · Reddit · X/dev · Discord/Slack; **build-in-public** (dogfood hikâyesi).
- **AI-araç ekosistemi** — MCP server dizinleri · Cursor/Claude Code toplulukları.
- **Bootcamp / hackathon ağları** — erken benimseyen kanalı.

## GELİR KAYNAKLARI  💡 *(hipotez — doğrulanacak)*

**Model: source-available + freemium** (open-core = gelecek opsiyonu 💡), GitHub Marketplace üzerinden faturalama. **Değer metriği = hosted katmanda geliştirici koltuğu (seat).**

| Katman | Ne | Fiyat (hipotez) |
|---|---|---|
| **Free** | local-first çekirdek (radar/scope/board), kendi makinende; BYO LLM anahtarı / yerel Ollama. Source-available (noncommercial). | $0 (noncommercial) |
| **Team** (hosted) | yönetilen hosting · gerçek-zamanlı presence/webhook · paylaşılan web pano · yönetilen çıkarım · sıfır kurulum | ≈ **$8–12 / geliştirici / ay** |
| **Org** | SSO · gizlilik modu (Ollama/on-prem) · öncelikli destek · audit | özel |

*Free = benimseme motoru; gelir hosted Team/Org'dan. Bootcamp'te gelir hedefi yok, odak benimseme + dogfood. Doğrulanacak: free→Team dönüşümü + fiyat noktası.*

## MALİYET YAPISI

- **Değişken (en büyük):** LLM çıkarım — Gemini embeddings + "judge"; çakışma/scope kararı başına. Hosting (Fly/Render + Vercel) hosted modda.
- **Sabit:** GitHub App altyapısı · geliştirme zamanı · alan adı/temel servisler.
- **Maliyet düşürücüler:** **local-first** (kullanıcının kendi token'ı + opsiyonel yerel Ollama → çıkarım+hosting maliyeti kullanıcıya kayar) · **ucuz-geçit** (dosya kesişimi, LLM çağrısından önce → çağrı sayısını azaltır).

## KİLİT METRİKLER

- **Önlenen çakışma** sayısı (merge öncesi yakalanan örtüşme) — *asıl değer kanıtı*.
- **Yakalanan scope-drift** sayısı + ⚠️ **false-positive oranı** — *en kritik kalibrasyon metriği* (gürültülü radar kapatılır).
- Aktif takım · takım başına bağlı AI aracı (MCP bağlantısı) · board oto-doldurma doğruluğu.
- Haftalık aktif kullanım / retention · "radar uyarısı → aksiyon" dönüşümü.

## REKABET AVANTAJI

- **Kombinasyon:** 4 parçayı (proaktif+semantik çakışma · canlı scope-drift · insan & ajan ortak farkındalık · git-*yazılabilir* `.harness/`) tek üründe, sıfıra yakın kurulumla birleştiren tek ürün — **birebir rakip yok**.
- **Git-native, insan+ajan yazılabilir `.harness/`:** mevcut yaklaşımlar ya salt-okuma (AGENTS.md) ya tek-kullanıcı (Agent Teams kilitleri) ya repo-dışı (mem0).
- **Kalibrasyon know-how'ı:** "ne zaman uyar" (düşük false-positive) — backtest + eşik kalibrasyonu; gürültüsüz radar kopyalanması güç.
- **Otantik dogfood:** ekibin kendi acısını yaşayıp çözmesi → güven + hız.

> ⚠️ **Dürüst sınır:** proaktif çakışma *tek başına* yeni değil (GitKraken/GitLive). Gerçek hendek = **kombinasyon + koordinasyon konumlandırması** (bilgi-beyni değil). En büyük risk: Linear/Augment/AGENTS.md ekosisteminin koordinasyon katmanını eklemesi.

---

> Kaynak strateji: ekip-içi vizyon + rakip araştırması (özel). Görsel (9-kutu) bu kanonik metinden üretilecek.
