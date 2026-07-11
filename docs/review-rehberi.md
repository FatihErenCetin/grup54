# Takım Review Rehberi — insan + AI ortak

> **Her review'dan ÖNCE bu dosya okunur.** AI aracına şunu de: *"`docs/review-rehberi.md`'yi oku ve PR #N'i buna göre review et."* (Claude Code: `/takim-review N`.) Onay/merge kararı **her zaman insanda**.

## 0. Üç ilke

1. **Kapsam-bağlı:** Review, issue'nun **kabul kriterlerine** karşı yapılır — mükemmeliyetçiliğe değil. Her bulguda test: *"bu, BU PR'ın işi mi?"* Değilse bulguyu düşürme — doğru adrese yönlendir (§4).
2. **Kanıtlı:** Bulgu = iddia + **kanıt** (satır/repro/deney) + **hazır reçete**. Rapordan önce her bulguyu **çürütmeye çalış**; "teoride sorun olabilir" çürütülür, "şu girdiyle şöyle kırılıyor" kalır. Emin değilsen bulguyu yazma.
3. **İnsan karar verir:** AI inceler ve raporlar; approve/değişiklik-iste/merge insanındır.

## 1. Boyutlandırma (orantılılık)

| Şerit | Ne zaman | Ne yapılır |
|---|---|---|
| **Hızlı** | docs/görsel/config, kod yok, küçük diff | §2 ön kontroller + **diff'i oku** + §5 hüküm (**özet gövdesi hızlı şeritte de yazılır** — jüri kanıtı) |
| **Tam** | kod PR'ı (özellikle `src/`, CI, şema) | §2 + §3 dört lens + §4 harita |
| **Çekirdek+** | dedektör/judge/eval'e dokunan PR (S2) | Tam + **eval kanıtı iste**: kabul edilebilir false-positive gösterilmeden "done" değil (`AGENTS.md`) |

## 2. Ön kontroller (her PR, 2 dk — nereye bakılır parantezde)

- [ ] CI **yeşil** *(`gh pr checks <N>` ya da PR sayfası → Checks)*
- [ ] PR gövdesinde **`Closes #<id>`** · başlık **`T-<id>: ...`** · branch `T-<id>-...`
- [ ] Commit'ler **Conventional-lite + Türkçe** (`feat:/fix:/docs:`) — ⚠️ mesajlar **merge sonrası düzeltilemez** (merge commit kalıcı)
- [ ] **Yazar = işi yapan kişi, kendi GitHub-bağlı email'i** (graded!) *(Commits sekmesi: avatar gri/profilsizse email bağlı DEĞİL)* · AI co-author YOK
- [ ] Diff'te sır yok *(`gh pr diff <N> | grep -iE "key|secret|token|BEGIN.*PRIVATE"`)*

## 3. Dört lens (tam review)

1. **Kabul kriteri:** issue'daki her kriter diff'te **kanıtıyla** karşılanıyor mu? (Karşılanıyorsa bulgu üretme.)
2. **Doğruluk:** kenar durumlar, gerçek kırılmalar — *"bu kod bir sonraki sprint'te nasıl kırılır?"* Simetri ara (örn. yazma yolu korunmuş, okuma yolu korunmamış mı?). Testler iddia edileni mi ölçüyor, ortamı mı?
3. **Mimari uyum:** `AGENTS.md` ilkeleri · **kontrat imzaları** (`docs/sprint2-kontratlar.md` — imza değiştiyse doküman da bu PR'da güncellenmeli) · **kapsam** (`docs/kapsam-sinirlari.md` YAPMA listesi). Plandan sapma varsa: *bilinçli ve savunulabilir mi?* → kabul + karar loguna (PO'ya söyle); değilse bulgu.
4. **Hijyen/güvenlik:** path traversal · sessiz bozulma (bozuk girdi + yeşil CI) · tmp/artıklar · exception'da bilgi sızması · paketleme (dosya ürünle mi geliyor, repoyla mı varsayılıyor?).

## 4. Bulgu haritası — her bulgu TEK adrese

| Bulgu tipi | Adres |
|---|---|
| ⚡ Merge'den önce bedava / sonra imkânsız (commit mesajı, PR başlığı) | **Bu PR'da, şimdi** |
| Bu PR'ın eklediği koddaki hata | **Bu PR'da** (küçükse) veya takip issue (PO kararı) |
| Gerçek ama bu PR'ın kapsamı dışı | **Takip issue** — hazır reçeteyle (örn. #77, #83) |
| Başka bir issue'nun işi | O issue'ya **yorum/not** |
| Kök neden **issue'nun muğlak yazımı** | Bulgu takip issue'da; **PR'a kusur atfedilmez** + issue-yazım dersi PO'ya |
| Doküman/karar işi (drift, sapma onayı) | docs PR + karar logu (PO) |

**Bulgu formatı:** `[blocker|önemli|minor|nit] başlık — dosya (repro'landı | statik)` → gerekçe (kanıt) → öneri (hazır komut/kod). *Blocker = merge edilirse yanlış davranış/veri kaybı/sır sızması.*

## 5. Hüküm + kayıt

- **Hüküm → GitHub mekaniği** *(boş/gövdesiz Approve YOK — özet gövdesi jürinin gördüğü kalıcı kanıttır)*:
  - ✅ approve → `gh pr review <N> --approve --body "<özet>"` *(UI: Files changed → Review changes → Approve + gövde)*
  - 🟡 değişiklik iste / 🔴 blocker → `gh pr review <N> --request-changes --body "<özet>"`
- **Özet gövdesi:** kriter durumu + güçlü yönler + bulgular→issue linki. *("N bulgu, M çürütüldü" istatistiği: çürütme disiplinini UYGULA ama gövdeye yazmak opsiyonel — bkz. §6.5.)*
- Bulgular merge'i bloklamıyorsa: **takip issue aç → approve'la.** Takip issue **board-hazır** açılır: label (`task`/`story` + `sprint-N`) + milestone + puan tahmini + `"Kaynak: PR #<N> review"` satırı — örn. `gh issue create --label task --milestone "Sprint N" --title "..." --body "Kaynak: PR #<N> review — reçete: ..."`
- Konvansiyon: **≥1 onay → PR'ı açan merge'ler** (`CONTRIBUTING.md` §4).

## 6. Ton + yazarlık

Önce **somut takdir** (iyi olan neyse adıyla) → sonra bulgular. Kod hakkında konuş, kişi hakkında değil. Reçete ver, ödev verme.
**⚡ düzeltmeyi reviewer kendisi uygulayabilir** (yazarı bekletme) — **kanıt zorunlu:** author alanı aynen korunur (amend author'a dokunmaz) + `git rev-parse "HEAD^{tree}"` öncesi/sonrası **birebir aynı** (tree-hash değişmedi = içerik korundu, yalnızca mesaj/meta düzeltildi). Sonuç PR'a/yazara bildirilir.

## 6.5 İnsan sesi (v2 — "AI kokusu" düzeltmesi)

Review'un *yöntemi* (çürütme, kanıt, kapsam) değişmedi — *sesi* değişiyor. Tektip şablon herkesi aynı makine gibi konuşturuyordu:

1. **Bulgu yoksa 2-3 cümle yeter.** Örnek: *"Diff'i okudum, lokalde \`make test\` koştum (27 ✓). strip'li split çözümü temiz — approve."* Uzun yapı (başlıklar, bölümler) YALNIZ blocker'lı/karmaşık review'larda.
2. **Birinci-el iz ZORUNLU:** her review'da en az bir cümle, reviewer'ın **kendi yaptığı** şey — koştuğu komut, gördüğü çıktı, elle denediği senaryo. (Zaten §0 "kanıtlı" ilkesinin insan hâli; AI'ın senin yerine uyduramayacağı tek şey budur.)
3. **"AI bulur, insan konuşur":** AI ile incelemek serbest ve teşvikli — ama AI çıktısı **taslaktır**. Göndermeden önce: yarıya kırp, kendi kelimelerinle yaz, kendi gözlemini ekle. Kopyala-yapıştır gövde = kokunun kendisi.
4. **Biçim diyeti:** emoji ≤1 · istatistik satırı opsiyonel · madde işareti listesi yalnız 3+ bulguda.

## 7. AI aracıyla review tarifi (araç-bağımsız)

1. Bu dosyayı oku. 2. `gh issue view <id>` → kabul kriterleri. 3. `gh pr view <N>` + `gh pr diff <N>` → gövde/commit'ler/diff. 4. §2 ön kontroller → §1'e göre şerit seç → §3 lensler. 5. Her bulguyu **çürütmeye çalış** (mümkünse çalıştır/repro). 6. §4 haritası + §5 hüküm önerisiyle **raporu insana sun** — approve/merge'e sen basma.

> **`gh` yoksa / yalnız web:** PR URL'sinin sonuna `.diff` ekle (ham diff) · issue sayfasından kabul kriterlerini kopyala · bu rehberin metnini + ikisini AI'a yapıştır (Gemini AI Studio dahil — o yalnızca rapor yazar, repo işlemi yapmaz).

> Bu rehber, Sprint-1'deki PR #76 ve #82 review'larının damıtılmış hâlidir (bulgular → #77/#83 deseni) ve 3-lens eleştiri panelinden geçmiştir. Rehber değişirse: PR + daily'de duyuru.
