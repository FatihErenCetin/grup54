# Bağımlılık Haritası Rehberi — sprint (veya milestone) başına üretim (insan + AI ortak)

> **Ne zaman:** Her sprint planlamasında (gün-1) üret; sprint ortasında bir kez tazele; kapanışta "akış raporu"na çevir. AI aracına şunu de: *"`docs/bagimlilik-harita-rehberi.md`'yi oku ve '<Milestone adı>' için haritayı üret."* (Claude Code: `/bagimlilik-haritasi <milestone>`.)
> **Örnek çıktı (kanonik format):** `docs/sprint2-bagimlilik.md` — yeni harita onunla aynı iskelette olmalı.
> **İlke:** Kanonik durum her zaman GitHub'dadır (issue/atama/milestone); bu belge *sıralama rehberi*dir. Harita ile GitHub çelişirse GitHub kazanır.

## 1. Veri toplama

```bash
gh issue list --milestone "<Milestone>" --state all --limit 200 \
  --json number,title,state,assignees,labels,body
```
- `--limit 200` ZORUNLU (gh varsayılanı 30 — sessizce eksik liste verir, yaşandı).
- `state all`: kapananlar da haritada görünür (✓ işaretli).

## 2. Bağımlılık çıkarımı (üç kaynak, öncelik sırasıyla)

1. **"Ön-koşul" alanı** (issue şablonundaki makine-okur satır: `#16, #41`) — birincil kaynak.
2. **Gövde metni:** "bağımlı", "ön-koşul", "bekler", "#N varsayıyor", "#N'i kilitliyor" kalıpları.
3. **Kontrat dosyası** (`docs/sprintN-kontratlar.md` vb.): kim kimin çıktısını tüketiyor — imzalardan çıkar.

**Sert vs yumuşak ayrımı (kritik):** *Yumuşak bağımlılık* = mock/fixture/stub ile beklemeden başlanabilir, yalnız **canlı** için ön-koşul gerekir (kontrat-önce ilkesi). Haritada kesik ok (`-.->`) + etiket. Bu ayrımı atlamak sahte "her şey birbirini bekliyor" haritası üretir — paralelliği öldürür.

**Uydurma yok:** Kaynağı gösterilemeyen kenar çizilmez. Şüpheli bağımlılığı "❓ doğrulanacak" olarak listele, PO'ya sor.

## 3. Çıktı formatı — 5 bölüm (sprint2 belgesiyle birebir)

1. **Mermaid graf** (`graph LR`): kişi başına `classDef` renk · tema/şerit başına `subgraph` · gün-1 blocker'ları ayrı çerçevede · sert ok düz, yumuşak ok kesik+etiketli · ⭐/🔑/⚠️ işaretleri. Sahipsiz issue = kırmızı kesikli çerçeve (`stroke-dasharray`).
2. **Dalga tablosu:** D0 (şimdi, tamamen paralel) → D1 → … kişi adlarıyla. Not sütununda mock-ile-başlama açıklamaları.
3. **Kişi bazlı kuyruklar:** herkes için `→` sıralı liste + bekleme notları + aşırı yük uyarısı (en yüklü kuyruk işaretlenir).
4. **🔴 Blocker/sahipsiz tablosu:** aciliyet + gerekçe ("bugün yapılmazsa X kayar").
5. **Düz liste:** `# · Sahip · Bağımlı olduğu · Kilitlediği (blocks)` — her issue tek satır.

## 4. Kalite kontrolleri (yayınlamadan önce)

- [ ] Milestone'daki TÜM issue'lar düz listede (sayıyı `gh` çıktısıyla karşılaştır)
- [ ] Döngü yok (A→B→A) — varsa bağımlılık yanlış çıkarılmıştır, PO'ya sor
- [ ] Kritik yol belirtilmiş (en uzun zincir + sahibi)
- [ ] Sahipsiz/label'sız issue'lar raporlanmış (yaşandı: 6 issue hem sahipsiz hem label'sızdı)
- [ ] Mermaid GitHub'da render oluyor (sözdizimi hatası = boş kutu)

## 5. Yayın + yaşam döngüsü

- Dosya: `docs/<milestone-slug>-bagimlilik.md` (örn. `sprint3-bagimlilik.md`) → konvansiyonel PR (issue + `Closes #N`).
- Atama/kapsam değişince: haritayı güncelleyen küçük PR (yaşandı: S2'de 6 sahipsiz issue atanınca harita revize edildi).
- **Sprint kapanışında:** aynı veriden "akış raporu" — planlanan sıra vs gerçekleşen; beklemeler nerede oldu → retro girdisi + PM kanıtı.

## Başka projede kullanım (taşınabilirlik)

Önkoşullar: `gh` CLI + milestone-bazlı sprint takibi. Bu rehber + örnek çıktı (`sprint2-bagimlilik.md`) kopyalanır; "Ön-koşul" alanı yoksa yalnız kaynak 2-3 (gövde+kontrat) kullanılır — kalite düşer ama çalışır. Tema/şerit adları projeye uyarlanır.

> Kaynak: S2 haritasının (PR #109) damıtılmış yöntemi — 8 Tem brainstorm F-04. Bu sürecin ürünleşmiş hâli (otomatik bağımlılık grafı) S3-planning adayıdır; rehber onun manuel prototipidir. Rehber değişirse: PR + daily'de duyuru.
