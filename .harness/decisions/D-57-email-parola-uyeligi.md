---
type: decision
id: D-57
title: "Email + parola üyeliği S3'e alındı — D-28'in evre-2 yerleşimi değişti"
date: "2026-07-28"
status: accepted
---

## Karar

**Email + parola ile gerçek üyelik**, "GitHub ile gir" akışının yanına Sprint 3
kapsamına alındı. Kullanıcı verisi için `users` tablosu açılır.

Bu, iki kayıtlı kararın kapsamını değiştirir:

- **D-23** (30 Haz, "KESİN"): *"kullanıcı-DB/login/tenant/RBAC YOK (tasarım
  gereği kapsam dışı)"* → **kullanıcı-DB artık var.**
- **D-28** (2 Tem): kimlik = C hibrit (email VE GitHub), ama **bootcamp dilimi
  = yalnız canlı "GitHub ile gir"**, *email/davet/fatura = evre-2* → **email
  dilimi evre-2'den S3'e çekildi.**

Kararı PO verdi (28 Tem). Ajan D-23/D-28 çelişkisini ve `internal/
grup54_ui_tasarim_paketi.md` §1 satır 12'nin *"Login / Profil / Üyelik →
YAPMA"* satırını **karar öncesinde** bildirdi; PO kararını yineledi.

## Neden kayda geçiyor

Bu bir uygulama detayı değil, **kapsam kararı**. Üç ayrı belge (D-23, D-28,
UI tasarım paketi §1) bugüne kadar tersini söylüyordu. Kayıt olmadan
değiştirilirse, ileride kimse bu üç belgenin neden geçersiz olduğunu bilemez —
`docs/karar-drifti-rehberi.md`'nin tarif ettiği "karar drifti"nin tam tanımı
budur. D-57 o drifti bir **karara** çevirir.

## Kapsam — ne yapılıyor, ne yapılmıyor

**Yapılan:**

| parça | not |
|---|---|
| `users` tablosu | `password_hash` ve `github_handle` ikisi de nullable; **CHECK**: en az biri dolu (kimlik doğrulama yolu olmayan hayalet satır olamaz) |
| argon2id parola hash'i | bcrypt değil — 72-bayt sessiz kırpma tuzağı var |
| `POST /auth/register` · `POST /auth/login` | mevcut `/me` ve `/logout` her iki kimlik türüyle çalışır |
| Oturum çerezi | geriye uyumlu genişletildi: `handle` artık opsiyonel (email kullanıcısının GitHub handle'ı yok), bugün verilmiş çerezler geçerli kalır, kurcalanmış çerez **fail-closed** |
| Kaba kuvvet koruması | `/auth/login` + `/auth/register` IP başına sıkı limit |
| Kullanıcı sayımı savunması | email bulunamasa da sahte hash doğrulanır; "bu email kayıtlı değil" **denmez** |

**Bilerek YAPILMAYAN — ve dürüstçe ilan edilen:**

- **Email doğrulaması yok.** SMTP yapılandırılmamış. *"Doğrulama e-postası
  gönderildi"* deyip hiç göndermemek, bu repoda 27 Tem boyunca avlanan
  **fail-open** deseninin ta kendisi olurdu (bkz. D-53: *"hata bir değere
  dönüştüğü an sistem ona veri gibi davranır"*). Kullanıcıya ve dokümana
  açıkça "henüz aktif değil" yazılır.
- **Parola sıfırlama yok** — email gerektirir, aynı sebeple ertelendi.

Bu iki eksik **güvenlik açığı olarak biliniyor**: doğrulanmamış email ile hesap
kapatma (squatting) mümkündür. Bootcamp demosu için kabul edildi, üretim
kullanımı için kapatılması gerekir.

## Reddedilen seçenekler

- **Yalnız GitHub OAuth (DB'siz)** — D-23/D-28 ile birebir uyumlu, aynı gece
  biterdi, backend zaten hazırdı. PO daha geniş kapsam istedi.
- **OAuth + yalnız `users` tablosu (parolasız)** — üyelik kaydı tutar ama
  "üye ol" formu vermez; PO email+parola istedi.

## Etkilenen belgeler

`internal/grup54_ui_tasarim_paketi.md` §1 satır 12 (*"Login / Profil / Üyelik
→ YAPMA"*) artık geçersiz; D-23 ve D-28 satırları "değişti → D-57" olarak
işaretlenmeli. Bu kayıt o güncellemeleri **yapmaz**, yalnız tetikler.
