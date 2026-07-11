# Tema Raporu Rehberi — "hangi konu ne durumda?" (insan + AI ortak)

> **Ne zaman:** Haftada bir (harita-turu daily'si öncesi) ya da istendiğinde. AI'a: *"`docs/tema-raporu-rehberi.md`'yi oku, '<Milestone>' için tema raporu ver."* (Claude Code: `/tema-raporu [milestone]` — boşsa aktif sprint.)
> **Amaç:** Konu kaybına karşı düzenli fotoğraf (F-04, problem 1). Board'daki "📚 Temalar" görünümü canlı hâlidir; bu rapor **anlık özet + uyarılar** üretir.

## Veri toplama

1. Milestone issue'ları: `gh issue list --milestone "<M>" --state all --limit 200 --json number,title,state,assignees,labels,closedAt`
2. Tema alanı (birincil): `gh project item-list 1 --owner <owner> --limit 200 --format json` → her item'ın "Tema" değeri. *(Fallback: alan yoksa label ekseniyle grupla ve raporda belirt.)*

## Çıktı formatı — oturumda sunulur + daily'ye yapıştırılık blok

1. **Tema ilerleme tablosu:** `Tema · Done/Toplam · Çubuk (▓▓▓░░) · In Progress'tekiler (#no+sahip)` — her tema tek satır.
2. **Bu hafta kapananlar** (closedAt son 7 gün), tema-gruplu, tek satır özetlerle.
3. **Uyarılar:** hiç ilerlemeyen tema ("X 0/5 — iki haftadır hareketsiz") · Tema atanmamış issue'lar · sahipsiz issue'lar · milestone'suz/label'sız yeni kayıtlar (yaşandı: 6+16 issue label'sızdı).
4. **Konu haritası cümleleri:** her temanın şu anki odağı TEK cümle ("AI çekirdek: geçit bitti, cosine'de; judge #50'yi bekliyor"). Konu kaybının asıl ilacı bu 5 cümledir.

## Kurallar

- Rapor **issue/PR üretmez** (hafif ritüel); kanıt gerektiğinde daily-scrum-log'a yapıştırılır, sprint README'ye SM taşır.
- Sayı uydurma yok — her rakam `gh` çıktısından; tarih ver.
- Uyarı dili süreçe bakar, kişiye değil.

> Kaynak: F-04 problem 1 (konu kaybı). Ürün karşılığı (tema/epic ilerleme görünümü) S3-planning adayıdır; bu rapor onun manuel prototipi.
