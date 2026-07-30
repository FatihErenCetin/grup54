---
type: decision
id: D-46
title: "Backend + DB ekibin KENDİ sunucusunda (Fly.io değil); frontend Vercel'de kalır"
date: "2026-07-25"
status: accepted
---

# D-46 — Barındırma: Fly.io bırakıldı, backend kendi sunucumuzda

> **Bu kayıt 30 Temmuz'da yazıldı, kararın kendisi 25 Temmuz'da alındı.**
> Neden geç: karar ekip-içi karar loguna yazılmıştı ama o dosya `internal/`
> altında ve **gitignored** — yani ne public repoda ne de ürünün okuyabildiği
> yerde vardı. Sonucu aşağıda; bu geç aynanın sebebi de o.

## Karar

**Backend + Postgres/pgvector ekibin kendi sunucusunda çalışır. Fly.io
kullanılmaz. Frontend Vercel'de kalır (değişiklik yok).**

D-39'u (*"Hosted DB = self-host pgvector on Fly"*) ve ondan önceki örtük Fly
kararını **supersede eder**. PO kararı.

- Backend imajı (`Dockerfile`) + Postgres/pgvector (`docker compose`) **aynı
  sunucuda**.
- CI/CD **korunur**: `deploy.yml`'in değerli kısmı platformdan bağımsızdı
  (CI-yeşil kapısı · yalnız-`main` dispatch · `concurrency` · test kapısı) —
  yalnız `flyctl deploy` **adımı** değişti.
- `fly.toml` kalktı.

## Neden

- Ekipte **boşta bekleyen bir sunucu** var → barındırma maliyeti sıfır, tam
  kontrol.
- D-39'un asıl gerekçesi (*"managed free-tier duraklaması / dış hesap
  sürprizi"*) kendi sunucuda zaten **doğmuyor**; *"tek platform + özel ağ +
  tam kontrol"* gerekçesi ise burada **daha güçlü** karşılanıyor.
- `docker compose` + gerçek pgvector üstüne yapılan iş self-host'ta **daha
  doğrudan** işe yarıyor → boşa emek yok.

## Bedeli (kabul edildi)

- **HTTPS pazarlık konusu değil**: Vercel'in HTTPS sayfasından HTTP bir API'ye
  tarayıcı *mixed-content* engeli koyar, ayrıca GitHub webhook HTTPS ister →
  hostname + sertifika yeni bir iş kalemi oldu.
- **Tek nokta arıza** riski jüri gününde bizde.

## Bu kaydın kendisi bir bulgunun sonucu (D-65 ②)

30 Temmuz'da Ask (`/query`) test edilirken şu ölçüldü:

> *"Hosted demo kararı neydi?"* → **"Fly backend + Vercel + webhook"**

Ürün, kararla **çürütülmüş** eski bir görev metnini (T-34) alıntılıyordu.
İki ayrı eksik üst üste binmişti:

1. **Kod:** karar günlüğü Ask korpusuna hiç girmiyordu (`read_decisions()`
   yoktu) — D-65 ① ile düzeltildi.
2. **Süreç:** düzeltildikten sonra bile cevap değişmedi, çünkü **bu kayıt
   yoktu**. Kararı düzelten şey `internal/`de, ürünün göremediği yerdeydi.

Ders, D-50'nin kardeşi: *bir karar, yalnız ekip-içi bir kayıtta yaşıyorsa
ürün için var değildir.* Karar logu kayıttır, **yayın değildir** — jüriye ve
ürüne açık olması gereken kararlar `.harness/decisions/` altına da yazılır.

## İlgili

- Supersede ettiği: D-39 (Fly + self-host pgvector)
- Netleştirme: D-50 ("canlı Fly kanıtı" kriterinin hedefi değişti)
- Bulgu zinciri: D-65 (Ask'ın altı kusuru)
- Ekip-içi tam kayıt: `internal/grup54_karar_logu.md` (gitignored)
