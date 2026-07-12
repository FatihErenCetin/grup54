# GitHub App (ensemble-radar) — kurulum & kimlik runbook'u

> **Ne:** Ensemble'ın GitHub'daki makine kimliği — ingest (#16) bununla repo olaylarını okur; S3'te "GitHub ile gir" (#79) aynı App'in üstüne kurulur (D-28: tek App). Kayıt **9 Tem 2026'da yapıldı** (D-35); bu doküman yeni üyenin `.env` kurulumu + doğrulama içindir.

## Kayıtlı App (değişmez bilgiler)

- **Ad/slug:** `ensemble-radar` · **App ID:** `4257285` · sahip: FatihErenCetin (kişisel hesap)
- **İzinler (minimal, D-28):** Contents · Pull requests · Issues · Metadata — **hepsi read-only** + Email addresses (read). ⛔ `members:read` bilinçli YOK (org-owner bariyeri; güven hikâyemizin parçası).
- **Olaylar:** push · pull_request · issues · **Webhook:** aktif, geçici hedef smee.io kanalı (S3 #62'de Fly URL'iyle değişir — D-35).
- Kurulum: yalnız `FatihErenCetin/grup54` (Only select repositories).

## Yeni üye `.env` kurulumu

1. `cp .env.example .env` (yoksa).
2. **Özel anahtarı al:** `ensemble-radar.*.private-key.pem` dosyası ekip-içi ÖZEL kanaldan paylaşılır (Drive özel klasörü — **asla** commit/DM-grup kanalı değil). Repo köküne koy (`*.pem` gitignored) + `chmod 600`.
3. `.env` alanları: `GITHUB_APP_ID=4257285` · `GITHUB_APP_PRIVATE_KEY_PATH=<pem dosya adı>` · `GITHUB_APP_INSTALLATION_ID=145474476`. (`GITHUB_WEBHOOK_SECRET` **boş bırak** — bkz. aşağıda.)
4. **Doğrula:**
   ```bash
   uv run --with pyjwt --with cryptography --with requests python scripts/verify_github_app.py
   ```
   Beklenen çıktı: 4 adım ✓ + `ZİNCİR TAM ✅` (JWT → installation → anlık token → repo okuma).

## Kimlik zinciri (ingest'in kullanacağı akış — #16)

```
.pem + APP_ID ──JWT (≤10 dk)──▶ /app/installations ──▶ POST access_tokens
                                                        └─▶ 1 saatlik token ──▶ REST/GraphQL okuma
```
Kalıcı token YOK — her istek zinciri anlık token üretir (D-23/D-28 ilkesi). Token süreleri değişebilir; koda sabitleme, yanıttaki `expires_at`/`expires_in`'i oku.

## Sır paylaşım ilkesi: need-to-know

| Sır | Kim alır |
|---|---|
| `.pem` özel anahtarı | Yalnız canlı ingest geliştiren (bugün: #16 sahibi) — özel kanaldan, tek tek |
| `GITHUB_WEBHOOK_SECRET` | **Şimdilik hiç kimse** — webhook'u yalnız alıcı sunucu doğrular (S3 #62); o gün secret **rotate edilir** ve yalnız deploy ortamına konur |
| `GEMINI_API_KEY` | Paylaşılmaz — **herkes kendi anahtarını alır** (kota + sızıntı izi kişisel) |
| App ID / installation ID | Sır değil (pem'siz işe yaramaz) — bu dokümanda açık |

## Sırlar hijyeni

`.env`, `*.pem` gitignored ✓ · webhook secret yalnız `.env` + GitHub formunda yaşar · pem kaybolursa: App ayarları → Private keys → yeni üret + **eskisini sil**.
