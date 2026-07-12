# Sprint Akış Raporu Rehberi — planlanan vs gerçekleşen (insan + AI ortak)

> **Ne zaman:** Sprint kapanışında, retro'dan ÖNCE (retro'nun ham maddesi budur). AI'a: *"`docs/sprint-akis-raporu-rehberi.md`'yi oku, '<Milestone>' için akış raporu üret."* (Claude Code: `/sprint-akis-raporu <milestone>`.)
> **Amaç:** "İşler planlandığı sırayla mı aktı, nerede bekledik?" — retro girdisi + jüri kanıtı (F-04, problem 3'ün kapanış ayağı).

## Veri toplama

1. **Plan:** `docs/<slug>-bagimlilik.md` — dalgalar (D0-D4), kişi kuyrukları, kritik yol.
2. **Gerçekleşen:** `gh issue list --milestone "<M>" --state all --limit 200 --json number,title,assignees,closedAt` + `gh pr list --state merged --limit 200 --json number,title,mergedAt,body` (Closes #N eşlemesiyle issue↔PR bağla).

## Çıktı formatı — `docs/<slug>-akis-raporu.md` (konvansiyonel PR ile — kanıt kalıcı)

1. **Zaman çizelgesi:** merge sırasına göre `tarih · #issue · sahip · hangi dalgadandı` — plandaki dalga sırasıyla yan yana.
2. **Sapma tablosu:** planlanan dalgasından erken/geç akan issue'lar + tek cümle neden ("#24, #50'nin sahiplenilmesini bekledi — 3 gün").
3. **Kritik yol gerçekleşmesi:** planlanan zincir vs fiilî zincir; en uzun bekleme nerede oldu.
4. **Bekleme analizi:** kayda değer beklemeler (issue açık kalma süresi ile kabaca; hassas süre iddiası YOK — elimizde In Progress zaman damgası yoksa "gün" hassasiyetinde kal).
5. **Retro girdileri:** 3-5 madde önerisi — "neyi farklı sıralardık" formatında. *(Karar retro'nundur; rapor öneri sunar.)*

## Kurallar

- **Suçlama dili yasak** — özne süreç/bağımlılıktır, kişi değil ("Esma geç kaldı" ❌ · "#46 sahiplenmesi 1 gün gecikince veri şeridi kaydı" ✓).
- Her iddia tarihli/kanıtlı; tarih yoksa iddia da yok.
- Sprint README'nin 6 başlığından "Sprint Review/Retro"ya SM bu rapordan besleme yapar (rapor kaynaktır, kopyası değil — TDK).

> Kaynak: F-04. `bagimlilik-harita-rehberi.md` §5'in ("kapanışta akış raporu") komutlaşmış hâli.
