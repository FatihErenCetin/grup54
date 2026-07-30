# `.harness/` — bu projenin ortak bağlamı

Bu klasör **kasıtlı olarak boştur.** Masaüstü paketi buraya hiçbir örnek
proje verisi koymaz — çünkü tohum, *senin* projenin başlangıç durumudur.

## Neden boş (ölçülmüş gerekçe, 30 Tem)

Paket eskiden geliştirici reposunun (`grup54`) **kendi** `.harness/`'ini
tohumluyordu. İki sonucu vardı:

1. Uygulamayı ilk açan kişi **başka bir projenin** donmuş sprint kapsamını,
   22 görev dosyasını ve karar kayıtlarını kendi başlangıç durumu olarak
   görüyordu.
2. Onboarding sihirbazı 3 sprintlik bir plan yazmak istediğinde
   `scope/sprint-3.md` zaten var olduğu için **tüm yazma reddediliyordu**
   (HTTP 409) — yani sihirbaz paketlenmiş uygulamada hiç çalışamıyordu.
   (Reddetme davranışının kendisi doğrudur: var olan kapsamın üstüne
   sessizce yazmak, kullanıcının işini kaybettirirdi.)

Boş iskelet, açılış kontrolünün (`_verify_harness_boot`) istediği tek şeyi —
klasörlerin **okunabilir** olmasını — karşılar. Beyan/görev/kapsam yokluğu
meşru bir durumdur ve hata üretmez.

## Buraya ne gelir

| Klasör | İçerik |
|---|---|
| `scope/sprint-N.md` | Kararlaştırılan kapsam — kapsam sapması buna göre ölçülür |
| `tasks/T-<id>-*.md` | Her görev/story ayrı dosya; board'ın kaynağı |
| `active/<kişi>.md` | "Şu an şuraya dokunuyorum" beyanı (insan ya da AI ajanı) |
| `locks/modules.md` | Yumuşak (kooperatif) modül kilitleri |
| `decisions/D-NN-*.md` | Karar günlüğü (denetim izi) |

İlk içeriği **Sihirbaz** sayfasından üretebilirsin: ürünü bir cümleyle anlat,
AI taslaklar, sen onaylarsın — onay olmadan diske hiçbir şey yazılmaz.
