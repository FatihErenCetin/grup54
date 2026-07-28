---
type: decision
id: D-59
title: "/events + /presence kontrat sapması — dokümanı gerçeğe uydur (has_more/filtreler/presence-304 uygulanmıyor)"
date: "2026-07-28"
status: accepted
---

## Bağlam

#265 (madde 3), S2 Ek B5'te donan `/events` + `/presence` sözleşmesiyle
üretilen gerçek şema arasında sapma tespit etti:

| Kontrat (S2 Ek B5, 🔒) | Üretilen |
|---|---|
| `/events?since=&before=&limit=&actor=&branch=` | yalnız `since` + `If-None-Match` |
| `{ events, has_more }` | `{ events, latest_ts }` |
| `/presence` → `ETag`/`304` | `/presence` düz `200`, ETag YOK |

Issue'nun kendi reçetesi: *"ya uygula ya dokümanı güncelle + karar logu (D-NN)
+ daily duyurusu."*

## Karar

**Dokümanı gerçeğe uydur, `before/limit/actor/branch` sayfalamasını VE
`/presence` ETag/304'ünü uygulamıyoruz.** `docs/sprint3-kontratlar.md` §B2
bu kararla güncellendi (kod fence artık gerçek `EventsResponse`/
`PresenceResponse` şeklini yansıtıyor).

### Neden bu yönde (koda uydurmak değil, dokümanı uydurmak)

1. **Ölçülen hacim küçük.** Üretimde ~763 olay (#265 metni) — tam feed +
   `since` daraltması (#273 perf, 760x kazanç canlı ölçümle kanıtlı) bu
   ölçekte yeterli. `before/limit` sayfalaması, henüz var olmayan bir
   büyüme sorununu çözerdi.
2. **Hiçbir istemci filtreleri kullanmıyor.** `actor=`/`branch=` client-side
   zaten var olan filtrelemeyi tekrarlardı (Ek B5 notu, `type=` için de
   aynısı zaten kabul edilmişti). `has_more` da aynı sebepten: UI tam feed'i
   zaten tüketiyor (`useEvents.ts` birikim deseni), sayfalama gerektiren bir
   akış YOK.
3. **`/presence` ETag/304 için de istemci yok.** `usePresence.ts` /
   `useEvents.ts` hiçbiri `If-None-Match` GÖNDERMİYOR (10 sn'lik polling,
   `usePolling.ts`) — sunucu tarafında 304 mekanizması kursak bile bugün
   hiçbir baytı kısaltmaz. `/presence` zaten küçük (aktif çalışan sayısı,
   TTL'li #60) — `/events`'in "763 olay → 218 KB" büyüme riskiyle aynı
   kategoride değil.
4. **Teslime az kaldı (2 Ağustos).** Yarım bir sayfalama (yalnızca
   `before`+`limit`, `actor`/`branch` olmadan ya da tersi) hem test yükü
   hem de sözleşmede yeni bir yarı-doğru yaratırdı — issue'nun kendi
   uyarısı: *"filtreleri uygulamak istersen TAM uygula, yarım bırakma."*
   Bu kapsamda tam uygulamanın karşılığı yok; ötelemek yerine dürüstçe
   kayda geçiriyoruz.

### Kabul edilen açık

- `/events` sayfalama (`before`/`limit`) ve sunucu-taraflı filtreleme
  (`actor`/`branch`) **YOK** — istemci tam feed'i (veya `since`-daraltılmış
  artımlı gövdeyi) alıp kendi filtreler. Olay hacmi büyürse (binlerce+) bu
  yeniden değerlendirilmeli — o zaman `has_more` + `before` **TAM**
  uygulanmalı (yarım değil).
- `/presence` `ETag`/`304` **YOK** — her poll tam gövde döner. Presence
  listesi büyük değil (aktif çalışan sayısı), bu bugün ölçülebilir bir
  maliyet değil.
- `/events` ETag/304 mekanizması **VAR ama istemcisiz** — bugün hiçbir
  tüketici `If-None-Match` göndermiyor. Doğru davranış (madde 2, geç gelen
  olayda 304 DEĞİL 200) test kilidiyle korunuyor (`tests/unit/
  test_events_db_okuma.py::test_etag_tum_db_uzerinden_hesaplanir`) — ileride
  bir istemci eklenirse (ör. MCP `who_is_touching` canlı-tail) davranış
  zaten doğru.

## Etkilenen belgeler

`docs/sprint3-kontratlar.md` §B2 (Ek B) bu kararla güncellendi — kod fence +
"Cursor sözleşmesi" satırı artık uygulanan hâli anlatıyor, S2 Ek B5'in
orijinal `has_more`/filtre imzasını **AYNEN** iddia etmiyor.

## Daily duyurusu

Bu sapma + karar, teslim öncesi son daily'de backend/PO'ya sözlü olarak da
duyurulacak (§3 giriş notu: "kontrat değişirse buraya PR aç + daily'de
duyur") — bu kayıt PR'ın açtığı yazılı iz, sözlü duyuru ekip tarafından ayrıca
yapılır.
