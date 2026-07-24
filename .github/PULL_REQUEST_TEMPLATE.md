## Ne / Neden
<!-- 1-3 cümle: bu PR ne yapıyor, neden? -->

Closes #<id> <!-- tek issue — birden coksa ayri PR -->

## Kanıt
<!-- CI yeşil mi? UI işiyse ekran görüntüsü. Çekirdek (dedektör/judge) işiyse eval sonucu. -->

## DONE kapısı — [`docs/gelistirme-dongusu.md`](../docs/gelistirme-dongusu.md)
- [ ] Issue'nun **kabul kriterleri** karşılandı
- [ ] **Kontrat imzaları** değişmedi *(değiştiyse `docs/sprint2-kontratlar.md` güncellendi + daily'de duyuruldu)*
- [ ] Router/şemaya dokunulduysa **`make contracts`** çalıştırıldı; `openapi.json` + `schema.d.ts` bu PR'da commit'li ([`docs/kontrat-drift-guardrail.md`](../docs/kontrat-drift-guardrail.md))
- [ ] **Kapsam temiz** — `docs/kapsam-sinirlari.md` YAPMA listesine girilmedi
- [ ] `make test` + `make lint` yeşil
- [ ] **Çekirdekse** (dedektör/scope-drift/judge): eval/backtest **kabul edilebilir false-positive** gösteriyor
- [ ] Commit'ler **Conventional-lite + Türkçe** (`feat:/fix:/docs:`) · yazar = işi yapan kişi (AI co-author YOK)
