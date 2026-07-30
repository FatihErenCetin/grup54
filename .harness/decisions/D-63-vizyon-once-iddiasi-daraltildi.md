---
type: decision
id: D-63
title: "Vizyon §5 'olmadan önce uyarır' iddiası ölçümle daraltıldı — 'merge edilmeden önce'"
date: "2026-07-30"
status: accepted
---

# D-63 — "Önce uyarır" iddiası ölçümle daraltıldı

## Karar

Vizyon §5'in ilk maddesindeki **"dokunmak üzereyken, olmadan _önce_ uyarır"**
ifadesi **"aynı anda ilerleyen işleri kıyaslar ve merge edilmeden önce uyarır"**
olarak daraltıldı. §6'nın jüri cümlesi ve iki hendek maddesi de aynı ölçüye
göre güncellendi. Vizyon belgesi **v1.1**'e çekildi.

**Vaat düşürülmedi, kesinleştirildi.** Ürün gerçekten uyarıyor ve gerçekten
CodeRabbit'ten farklı; farklı olan, "ne zaman"ın tarifi.

## Neden — ölçülen gerçek (29–30 Tem 2026, canlı üründe)

| Ölçüm | Sonuç |
|---|---|
| Radar girdisi | GitHub olayları: commit'ler `sha=main` ile çekiliyor → **zaten merge edilmiş** iş |
| Canlıdaki en yüksek `high` tespit (29 Tem) | 21 Tem'de main'e girmiş **iki commit** arasında — 8 gün önce bitmiş iş |
| A1'in "önce uyarma"yı taşıyan yarısı (`.harness/active/` niyet beyanı) | proje tarihinde **sıfır** beyan dosyası; `/presence` boş liste |
| `engine/radar.py` içinde `harness_port` | **yok** — `grep -n harness radar.py` → 0 eşleşme |

Son satır belirleyici: `active/` beyanı **dolsaydı bile** tespitleri
etkilemezdi, çünkü radar o kaynağı hiç okumuyor. Yani eksik olan yalnız
kullanım değil, **kablolama** da.

## Bugün doğru olan cümle

> Aynı anda ilerleyen işleri **birbiriyle** kıyaslar ve çakışmayı **merge
> edilmeden önce**, gerekçesiyle söyler.

Bu hâlâ ayırt edici: CodeRabbit **tek bir PR'ın kendi içine** bakar; biz **iki
iş arasındaki kesişime** bakarız. Ama "sen daha yazmadan" değildir.

## Kapatılmadı — evrelendi (evre-2)

Düzenleme-anı (pre-edit) uyarısı için gereken iki şey:

1. `.harness/active/` beyanının **gerçekten yazılması** (MCP `declare_work` —
   donmuş S3 kapsamında **non-goal**, bkz. `scope/sprint-3.md`)
2. Radar'ın `harness_port` alması ve beyanları aday üretimine katması

İkisi de teknik olarak yapılabilir; bootcamp penceresine sığmadığı için
ertelendi. **Bunun bilinçli bir erteleme olduğu buraya yazılmasaydı**, iddia
ile gerçek arasındaki fark kayıtsız kalırdı — bu projede "karar sızıntısı"
diye adlandırdığımız şeyin ta kendisi (D-45).

## Bağlantılı

- Vizyon: `internal/grup54_vizyon_ve_karar_kaydi.md` v1.1 (⚠️ v1.1 notu)
- A1 (branch/PR + `active` beyanı) · K3 (farklılaşma çekirdeği) · §13 risk-1
- D-45 (karar sızıntısı vakası) — aynı sınıf: açık bırakılmış bir iddia,
  kayıtsız katılaşma
