# Review Koku Testi Rehberi — göndermeden önce insan-sesi kontrolü

> **Ne zaman:** Review gövdeni yazdın, göndermeden ÖNCE. AI'a: *"`docs/review-koku-testi-rehberi.md`'yi oku, şu taslağımı test et: <taslak>"* (Claude Code: `/review-koku-testi` + taslağı yapıştır.)
> **Kritik ilke:** Bu test taslağı **YENİDEN YAZMAZ** — AI'ın "insanlaştırdığı" metin yine AI kokar. Test yalnız İŞARETLER; düzeltmeyi insan kendi kelimeleriyle yapar. (review-rehberi §6.5'in denetim aracı.)

## Kontrol listesi (her madde: ✓ geçti / ✗ işaretle + neden)

1. **Birinci-el iz var mı?** Taslakta reviewer'ın KENDİ yaptığı en az bir şey var mı (koştuğu komut, gördüğü çıktı, elle denediği senaryo)? YOKSA: *"Birinci-el iz eksik — kendi çalıştırdığın bir şeyi ekle. Ben öneremem; benim uydurmam tam olarak yasak olan şey."*
2. **Uzunluk:** Bulgu yoksa ≤3 cümle mi? Bulgu varsa gövde bulgu sayısıyla orantılı mı?
3. **Biçim diyeti:** emoji ≤1 · kısa review'da başlık/bölüm yok · madde listesi yalnız 3+ bulguda · "N bulgu M çürütüldü" istatistiği varsa gerçekten gerekli mi?
4. **Kalıp cümle taraması:** şablon kokan ifadeleri işaretle ("Güçlü yönler:", "Özetle...", "...olduğunu belirtmek isterim", boş övgü: "harika iş!"). Somut olmayan takdir = kalıp.
5. **Ses:** birinci tekil şahıs var mı ("okudum", "denedim", "bence")? Edilgen/rapor dili baskınsa işaretle.
6. **İçerik korunumu (tek istisna):** kısaltma önerirken teknik iddiaların (bulgu, kanıt, hüküm) düşmediğini doğrula — koku testi içerik testi değildir, ikisini karıştırma.

## Çıktı formatı

```
KOKU TESTİ: 4/6 ✓
✗ (1) Birinci-el iz yok → kendi koştuğun bir komutu/gözlemi ekle
✗ (4) "Güçlü yönler:" etiketi kalıp → cümle içinde doğal söyle
```
Geçen taslak için tek satır yeter: "Koku testi temiz — gönder."

> Kaynak: F-04 problem 4 ("review'lar AI kokuyor") · review-rehberi.md §6.5'in uygulama aracı.
