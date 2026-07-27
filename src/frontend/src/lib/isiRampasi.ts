/* Isı rampası — TEK KAYNAK (T-293). Daha önce `GraphPage.tsx` (Isı matrisi +
   Treemap) ve `IsiMatrisi.tsx` (Radar paneli, #105) bu tabloyu BİREBİR
   kopyalanmış iki ayrı yerde tutuyordu; PO'nun "bazı hücrelerde metin siyah"
   şikayeti (T-293) aslında ikisinde de aynı hataydı ama drift riski gerçekti
   (biri düzeltilip diğeri unutulabilirdi). Üç yüzey (Isı matrisi, Treemap,
   Radar paneli) artık BURADAN besleniyor.

   Tailwind JIT literal sınıf adı tarar, bu yüzden dinamik `bg-primary/${n}`
   KURULMAZ; tam sınıf adları sabit tabloda (aşağıdaki `as const` dizi).

   Kontrast kararı (T-293, WCAG 2.1 AA >= 4.5:1): TÜM kademeler `text-foreground`
   kullanır (koyu temada beyaza yakın, bkz. index.css `--foreground`).
   `text-primary-foreground` (koyu metin) hiçbir kademede KULLANILMAZ — PO'nun
   şikayeti tam olarak bu tutarsızlıktı (bazı hücreler beyaz, bazıları siyah).

   Ama salt "hepsini beyaz yap" yeterli değildi: en sıcak 2 kademe düz
   `--primary` (L=0.7) üstünde beyaz metinle 2.30:1 / 3.96:1 verir — AA'nın
   (4.5) ALTINDA, okunmaz. Bu yüzden en sıcak 2 kademe `--primary-strong`
   (index.css, aynı ton/kroma, L=0.50) kullanır — ölçülen kontrast 5.19:1 /
   7.51:1 (bkz. tests/isiKontrasti.test.ts — gerçek oklch değerlerinden
   ölçülür, hardcode edilmiş bir sayı değil).

   Neden yeni bir token (Tailwind'in hazır `orange-900` gibi bir sınıfı DEĞİL):
   index.css'teki D-34 kuralı bileşenlerin YALNIZCA isimlendirilmiş tasarım
   token'larını kullanmasını şart koşuyor ("bileşenlere hex YAZILMAZ; yalnız
   bu adlar kullanılır") — ham Tailwind paleti bu tek-doğruluk-kaynağı
   ilkesini kısa devre yapar ve marka rengi (`--primary`) değişince bu rampa
   sessizce senkron dışı kalırdı. */
export const ISI_SINIFLARI = [
  "bg-primary/10 text-foreground",
  "bg-primary/25 text-foreground",
  "bg-primary/45 text-foreground",
  "bg-primary-strong/70 text-foreground",
  "bg-primary-strong text-foreground",
] as const;

/** Hücrenin/modülün ısı sınıfı. Ölçek en yoğun değere GÖRECELİdir (legend
    bunu sayıyla söyler — gizli normalizasyon yok). İndeks daima kenetlenir:
    bozuk/0 bir `count` gelse bile className'e `undefined` sızmaz. */
export function isiSinifi(count: number, enYogun: number): string {
  const oran = enYogun > 0 ? count / enYogun : 0;
  const k = Math.ceil(oran * ISI_SINIFLARI.length);
  const i = Math.min(ISI_SINIFLARI.length - 1, Math.max(0, k - 1));
  return ISI_SINIFLARI[i];
}
