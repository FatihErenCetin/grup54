/* Graf yerleşim algoritmaları (#130 modları a + d) — SAF, React'siz, DOM'suz.
 *
 * Neden `lib/`de ve neden saf: ikisi de gerçek algoritma (kuvvet simülasyonu ·
 * şerit ataması) ve ikisinin de asıl kilidi DETERMİNİZM — bunu ancak DOM'suz,
 * doğrudan çağrılabilen bir fonksiyonda kanıtlayabiliriz. `isiRampasi.ts` ile
 * aynı desen: hesap `lib/`de, çizim `components/`te.
 *
 * ── Neden d3-force DEĞİL ────────────────────────────────────────────────────
 * Bu depoda bağımlılık ekleme yasağı var; #130 GATE notu tam bu yüzden
 * konmuştu ("güç-yönlü yeni kütüphane gerektirir → S3 sonrasına gate").
 * Fruchterman-Reingold ~70 satır — kütüphane eklemek yerine yazıldı, yasak
 * delinmedi. Kaynak: Fruchterman & Reingold 1991, "Graph Drawing by
 * Force-directed Placement" (itme k²/d, çekme d²/k, doğrusal soğutma).
 *
 * ── Neden Math.random YOK ───────────────────────────────────────────────────
 * Klasik FR rastgele tohumla başlar. Rastgele tohum her mount'ta BAŞKA bir
 * resim çizerdi: kullanıcı aynı veriye iki kez bakınca düğümler yer değiştirir
 * ve "bir şey mi değişti?" diye sorar — grafiğin tek işi olan "değişimi
 * göster"i bozar. Tohum bunun yerine (a) id'ye göre sıralı indeks + (b) id'nin
 * FNV-1a hash'i. Sonuç: aynı veri → aynı resim, HANGİ SIRADA gelirse gelsin
 * (backend `nodes` sırası için garanti vermiyor).
 */

export type YerlesimDugumu = {
  id: string;
  agirlik: number;
  /** Düğümün ETİKETİ DAHİL kapladığı kutu (nominal tuval birimi). Verilirse
      çakışma gevşetmesi bu kutuya göre yapılır; verilmezse küçük bir
      varsayılan. Neden kutu ve neden etiket dahil: canlı veride (30 Tem)
      merkeze çekilen üç aktörün DAİRELERİ değil, altlarındaki YAZILAR üst
      üste binip okunmaz oluyordu — ayrıştırılması gereken şey görünen
      alandır, düğümün kendisi değil. */
  en?: number;
  boy?: number;
};
export type YerlesimKenari = { kaynak: string; hedef: string; agirlik: number };
export type Konum = { id: string; x: number; y: number };

/** Düğümün çizim kutusunun dışına taşmaması için kenar boşluğu (nominal tuval). */
const KENAR_BOSLUK = 28;

/** FNV-1a 32-bit — kriptografik değil, sadece stabil dağılım için.
    `Math.imul` 32-bit taşmayı doğru yapar (düz `*` çift-duyarlıkta kayar). */
function fnv1a(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** Kenar ağırlığının çekim çarpanı — [1, 2] arasına SIKIŞTIRILIR.
    Ham `count` ile orantılı çeksek 40 dokunuşlu bir kenar 1 dokunuşlukları
    ekranın dışına atardı; log ölçek yoğunluğu gösterir, yerleşimi ezmez. */
function agirlikCarpani(agirlik: number, enBuyuk: number): number {
  if (enBuyuk <= 1) return 1;
  return 1 + Math.log1p(Math.max(agirlik, 0)) / Math.log1p(enBuyuk);
}

/**
 * Fruchterman-Reingold kuvvet-yönlü yerleşim.
 *
 * @returns Her düğüm için `{id, x, y}` — `0..genislik` × `0..yukseklik`
 *          nominal tuvalinde; çizim katmanı yüzdeye çevirir.
 */
export function gucYonluYerlesim(
  dugumler: YerlesimDugumu[],
  kenarlar: YerlesimKenari[],
  genislik = 1000,
  yukseklik = 620,
): Konum[] {
  const n = dugumler.length;
  if (n === 0 || genislik <= 0 || yukseklik <= 0) return [];

  // Girdi sırası yerleşimi ETKİLEMESİN: id'ye göre sırala. Aynı graf farklı
  // sırada gelirse aynı resim çıkar (kanıt: grafYerlesimi.test.ts).
  const sirali = [...dugumler].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  if (n === 1) return [{ id: sirali[0].id, x: genislik / 2, y: yukseklik / 2 }];

  const indeks = new Map(sirali.map((d, i) => [d.id, i]));
  const x = new Float64Array(n);
  const y = new Float64Array(n);

  // Tohum: id-sırasına göre eşit açılı çember + hash'ten yarıçap sapması.
  // Saf çember SİMETRİKtir ve FR simetrik başlangıçta kilitlenebilir (tüm
  // kuvvetler birbirini götürür); sapma simetriyi deterministik olarak kırar.
  const merkezX = genislik / 2;
  const merkezY = yukseklik / 2;
  const R = Math.min(genislik, yukseklik) * 0.38;
  for (let i = 0; i < n; i++) {
    const aci = (2 * Math.PI * i) / n;
    const sapma = ((fnv1a(sirali[i].id) % 1000) / 1000 - 0.5) * 0.35; // ±%17.5
    x[i] = merkezX + R * (1 + sapma) * Math.cos(aci);
    y[i] = merkezY + R * (1 + sapma) * Math.sin(aci);
  }

  const k = Math.sqrt((genislik * yukseklik) / n); // ideal kenar uzunluğu
  const enBuyukAgirlik = kenarlar.reduce((m, e) => Math.max(m, e.agirlik), 0);

  // Kenarlar da sıralanır — düğümleri sıralamak TEK BAŞINA yetmiyor: çekme
  // döngüsü `dx`/`dy` üstünde toplama yapıyor ve kayan nokta toplaması
  // birleşme özelliği taşımaz (a+b+c ≠ a+c+b, son bitlerde). Tek başına
  // görünmez bir fark, 300 adımlık doğrusal-olmayan bir simülasyonda büyüyüp
  // gözle görülür konum farkına dönüşüyor (kanıt: grafYerlesimi.test.ts
  // "girdi SIRASI değişse de aynı resim" testi tam bunu yakaladı).
  const siraliKenarlar = [...kenarlar].sort((a, b) =>
    a.kaynak < b.kaynak
      ? -1
      : a.kaynak > b.kaynak
        ? 1
        : a.hedef < b.hedef
          ? -1
          : a.hedef > b.hedef
            ? 1
            : 0,
  );

  // Adım sayısı düğüm sayısıyla ölçekli: itme her adımda O(n²). 50 düğüm ×
  // 300 adım ≈ 375k çift-hesabı (tarayıcıda ~10 ms, useMemo ile bir kez).
  // Büyük grafta adımı kısıyoruz — yerleşim biraz daha az oturur ama sayfa
  // DONMAZ (donan bir sekme, gevşek bir yerleşimden kötüdür).
  const adimSayisi = n > 120 ? 120 : 300;

  const dx = new Float64Array(n);
  const dy = new Float64Array(n);
  const t0 = Math.min(genislik, yukseklik) / 10; // başlangıç "sıcaklığı"

  for (let adim = 0; adim < adimSayisi; adim++) {
    dx.fill(0);
    dy.fill(0);

    // İtme — her düğüm çifti birbirini k²/d ile iter
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let ax = x[i] - x[j];
        let ay = y[i] - y[j];
        let d2 = ax * ax + ay * ay;
        if (d2 < 1e-9) {
          // Tam üst üste düşen iki düğüm: 0'a bölmemek için hash'e göre SABİT
          // bir yönde ayır (rastgele değil — determinizm burada da korunur).
          ax = ((fnv1a(sirali[i].id + " " + sirali[j].id) % 200) / 100 - 1) || 0.5;
          ay = 0.5;
          d2 = ax * ax + ay * ay;
        }
        const d = Math.sqrt(d2);
        const kuvvet = (k * k) / d;
        const ux = (ax / d) * kuvvet;
        const uy = (ay / d) * kuvvet;
        dx[i] += ux;
        dy[i] += uy;
        dx[j] -= ux;
        dy[j] -= uy;
      }
    }

    // Çekme — yalnız kenarla bağlı düğümler, d²/k ile birbirine yaklaşır
    for (const e of siraliKenarlar) {
      const i = indeks.get(e.kaynak);
      const j = indeks.get(e.hedef);
      // Tanımsız uç = grafta olmayan düğüme kenar; SESSİZCE atlanır (uydurma
      // düğüm yaratmak, kenarı düşürmekten daha yanıltıcı olurdu).
      if (i === undefined || j === undefined || i === j) continue;
      const ax = x[i] - x[j];
      const ay = y[i] - y[j];
      const d = Math.max(Math.sqrt(ax * ax + ay * ay), 0.01);
      const kuvvet = ((d * d) / k) * agirlikCarpani(e.agirlik, enBuyukAgirlik);
      const ux = (ax / d) * kuvvet;
      const uy = (ay / d) * kuvvet;
      dx[i] -= ux;
      dy[i] -= uy;
      dx[j] += ux;
      dy[j] += uy;
    }

    // Soğutma: adım boyu sıcaklıkla sınırlanır (sonlara doğru titreşim durur)
    const t = t0 * (1 - adim / adimSayisi);
    for (let i = 0; i < n; i++) {
      const d = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]);
      if (d > 1e-9) {
        const olcek = Math.min(d, t) / d;
        x[i] += dx[i] * olcek;
        y[i] += dy[i] * olcek;
      }
      x[i] = Math.min(genislik - KENAR_BOSLUK, Math.max(KENAR_BOSLUK, x[i]));
      y[i] = Math.min(yukseklik - KENAR_BOSLUK, Math.max(KENAR_BOSLUK, y[i]));
    }
  }

  /* ── Çakışma gevşetmesi ────────────────────────────────────────────────
     NEDEN ayrı bir geçiş: ana döngüde sıcaklık (t) sona doğru 0'a iner, yani
     geç kalan bir çakışma bir daha AÇILAMAZ — kuvvet hesaplansa bile adım
     boyu sıfırlanmıştır. Bu geçiş sıcaklıktan bağımsız, konumu DOĞRUDAN
     düzeltir.
     NEDEN kutu (daire değil): canlı veride üst üste binen şey düğümlerin
     kendisi değil, altlarındaki ETİKETLERdi. Ayrıştırılması gereken görünen
     alandır. Deterministik: sıra `sirali`den gelir, rastgelelik yok. */
  const en = sirali.map((d) => Math.max(d.en ?? 24, 8));
  const boy = sirali.map((d) => Math.max(d.boy ?? 24, 8));
  for (let gecis = 0; gecis < 80; gecis++) {
    let ayrildi = false;
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const gerekliX = (en[i] + en[j]) / 2;
        const gerekliY = (boy[i] + boy[j]) / 2;
        const farkX = x[i] - x[j];
        const farkY = y[i] - y[j];
        const asimX = gerekliX - Math.abs(farkX);
        const asimY = gerekliY - Math.abs(farkY);
        // Kutular yalnız İKİ eksende birden örtüşüyorsa çakışır.
        if (asimX <= 0 || asimY <= 0) continue;
        ayrildi = true;
        // Daha AZ itmeyi gerektiren eksenden aç (en kısa çıkış yolu):
        // yatay ayırmak yeterliyse dikey düzeni bozmuyoruz.
        if (asimX < asimY) {
          const yon = farkX === 0 ? (i % 2 === 0 ? 1 : -1) : Math.sign(farkX);
          x[i] += (yon * asimX) / 2;
          x[j] -= (yon * asimX) / 2;
        } else {
          const yon = farkY === 0 ? (i % 2 === 0 ? 1 : -1) : Math.sign(farkY);
          y[i] += (yon * asimY) / 2;
          y[j] -= (yon * asimY) / 2;
        }
      }
    }
    // Her geçişte tuvale geri sıkıştır, yoksa ayırma düğümü dışarı taşır.
    for (let i = 0; i < n; i++) {
      x[i] = Math.min(genislik - KENAR_BOSLUK, Math.max(KENAR_BOSLUK, x[i]));
      y[i] = Math.min(yukseklik - KENAR_BOSLUK, Math.max(KENAR_BOSLUK, y[i]));
    }
    if (!ayrildi) break; // yakınsadı — boşuna dönme
  }

  return sirali.map((d, i) => ({ id: d.id, x: x[i], y: y[i] }));
}

/* ── Git şeridi (#130 mod d) ─────────────────────────────────────────────────
 *
 * ÖNEMLİ, ve arayüzde de yazılı: bu bir commit DAG'ı DEĞİL.
 * Gerçek ağaç ebeveyn-çocuk bağı (`parent_sha`) ister; `NormalizedEvent`
 * bunu taşımıyor (Ek-B B6 ertelemesi) ve uydurulmayacak. Çizilen şey
 * kontratın GERÇEKTEN taşıdığı bilgi: dal başına bir şerit + o şeritteki
 * olayların ZAMAN sırası. #130'un kendi tanımı da zaten bu ("şerit-temelli …
 * NormalizedEvent'ten deterministik, kontrat eki GEREKMEZ").
 */

export type SeritOlayi = {
  id: string;
  tip: "commit" | "pr" | "issue" | "branch";
  aktor: string;
  /** #296 — aktör gerçek bir GitHub hesabıyla eşleşti mi (ActorChip'e taşınır). */
  dogrulandi: boolean;
  dal: string | null;
  ts: string;
  ref: string;
  files: string[];
};

/** Şerit üstüne yerleşmiş tek olay; `t` = ms epoch, `cakisan` = bu olayın
    dosyalarından BAŞKA bir şeritte de dokunulmuş olanlar. */
export type YerlesikOlay = SeritOlayi & { t: number; cakisan: string[] };

export type Serit = {
  /** Görünen ad. `dalBilinmiyor` ise gerçek bir dal adı DEĞİL, etikettir. */
  dal: string;
  dalBilinmiyor: boolean;
  olaylar: YerlesikOlay[];
};

export type SeritDizilimi = {
  seritler: Serit[];
  /** Zaman ekseninin uçları (ms epoch); olay yoksa null. */
  bas: number | null;
  son: number | null;
  /** Birden fazla şeritte geçen dosyalar — çakışma ADAYI (radar'ın baktığı şey). */
  cakisanDosyalar: Set<string>;
  /** `ts`'i çözülemediği için ÇİZİLMEYEN olay sayısı — sessizce yutulmaz. */
  okunamayan: number;
  /** Üst sınır yüzünden gösterilmeyen şerit sayısı — GÖRÜNÜR bildirilir. */
  gizlenenSerit: number;
  /** O şeritlerdeki toplam olay sayısı. */
  gizlenenOlay: number;
};

/** Ana dal adları en üstte gösterilir (okuma alışkanlığı: main yukarıda). */
const ANA_DALLAR = new Set(["main", "master"]);

export const DALSIZ_ETIKET = "dal bilgisi yok";

/**
 * Olayları dal şeritlerine dizer ve çakışma adayı dosyaları işaretler.
 *
 * Determinizm: şerit sırası (ana dal → ilk olay zamanı → ad) ve şerit içi
 * sıra (zaman → id) tamamen veriden türer; girdi sırasından bağımsızdır.
 *
 * @param enFazlaSerit Gösterilecek en fazla şerit sayısı. Neden gerekli:
 *   canlı veride 14 günlük pencerede **130 şerit** ölçüldü (30 Tem 2026) ve
 *   82'si tek olaylı — 130 satır çizmek sayfayı kullanılamaz hâle getirir.
 *   Kırpma SESSİZ DEĞİL: kaç şerit/olay gizlendiği döndürülür ve arayüz onu
 *   basar ("gizli üst sınır yok" kuralı). `Infinity` = kırpma yok.
 */
export function seritDizilimi(
  olaylar: SeritOlayi[],
  enFazlaSerit = 12,
): SeritDizilimi {
  const gruplar = new Map<string, { dalBilinmiyor: boolean; olaylar: YerlesikOlay[] }>();
  let okunamayan = 0;

  for (const o of olaylar) {
    const t = new Date(o.ts).getTime();
    if (Number.isNaN(t)) {
      // Zaman eksenine yerleştirilemeyen olay UYDURMA bir yere konmaz
      // (örn. "bugün" sayılmaz); sayılır ve arayüzde görünür şekilde bildirilir.
      okunamayan += 1;
      continue;
    }
    const dalBilinmiyor = o.dal === null || o.dal === "";
    const anahtar = dalBilinmiyor ? DALSIZ_ETIKET : (o.dal as string);
    let grup = gruplar.get(anahtar);
    if (!grup) gruplar.set(anahtar, (grup = { dalBilinmiyor, olaylar: [] }));
    grup.olaylar.push({ ...o, t, cakisan: [] });
  }

  // Dosya -> ona dokunan şeritler. Çakışma adayı = 2+ şeritte geçen dosya.
  const dosyaSeritleri = new Map<string, Set<string>>();
  for (const [ad, grup] of gruplar) {
    for (const o of grup.olaylar) {
      for (const f of o.files) {
        let s = dosyaSeritleri.get(f);
        if (!s) dosyaSeritleri.set(f, (s = new Set()));
        s.add(ad);
      }
    }
  }
  const cakisanDosyalar = new Set(
    [...dosyaSeritleri].filter(([, s]) => s.size > 1).map(([f]) => f),
  );

  let bas: number | null = null;
  let son: number | null = null;
  const tumSeritler: Serit[] = [];

  for (const [ad, grup] of gruplar) {
    grup.olaylar.sort((a, b) => a.t - b.t || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    for (const o of grup.olaylar) {
      // DİKKAT — çakışma işareti KIRPMADAN ÖNCE hesaplanır (`cakisanDosyalar`
      // yukarıda TÜM gruplardan kuruldu). Sonra hesaplasaydık bir şeridi
      // gizlemek, o dosyayı "tek dalda geçiyor" hâline getirip GERÇEK bir
      // çakışma adayını sessizce yok ederdi — görünürlük kararı, doğruluk
      // kararını asla değiştirmemeli.
      o.cakisan = o.files.filter((f) => cakisanDosyalar.has(f));
      // Eksen uçları GİZLENENLER DAHİL tüm olaylardan: "tümünü göster"e
      // basınca eksen kaymasın, noktalar yer değiştirmesin. Sabit eksen,
      // tam genişlik kullanmaktan daha okunur (kullanıcı karşılaştırıyor).
      if (bas === null || o.t < bas) bas = o.t;
      if (son === null || o.t > son) son = o.t;
    }
    tumSeritler.push({ dal: ad, dalBilinmiyor: grup.dalBilinmiyor, olaylar: grup.olaylar });
  }

  /* Kırpma SEÇİMİ olay sayısına göre (en hareketli şeritler kalır), ama
     GÖSTERİM sırası zamana göre — ikisi ayrı karar. Tek olaylı 82 şeridin
     ilk 12'sini zamana göre seçseydik, main ve asıl iş dalları düşerdi. */
  const secili = [...tumSeritler]
    .sort((a, b) => {
      // Ana dal her hâlükârda kalır: kapsamı okumanın çapası.
      const aAna = ANA_DALLAR.has(a.dal);
      const bAna = ANA_DALLAR.has(b.dal);
      if (aAna !== bAna) return aAna ? -1 : 1;
      if (a.olaylar.length !== b.olaylar.length) return b.olaylar.length - a.olaylar.length;
      return a.dal < b.dal ? -1 : a.dal > b.dal ? 1 : 0;
    })
    .slice(0, Math.max(0, enFazlaSerit));

  const seciliKume = new Set(secili);
  const gizlenen = tumSeritler.filter((s) => !seciliKume.has(s));

  // Şerit sırası: ana dal(lar) üstte → en erken başlayan → ad. "dal bilgisi
  // yok" şeridi EN ALTA: gerçek bir dal değil, artık kovası.
  const seritler = secili.sort((a, b) => {
    if (a.dalBilinmiyor !== b.dalBilinmiyor) return a.dalBilinmiyor ? 1 : -1;
    const aAna = ANA_DALLAR.has(a.dal);
    const bAna = ANA_DALLAR.has(b.dal);
    if (aAna !== bAna) return aAna ? -1 : 1;
    const aIlk = a.olaylar[0]?.t ?? Infinity;
    const bIlk = b.olaylar[0]?.t ?? Infinity;
    if (aIlk !== bIlk) return aIlk - bIlk;
    return a.dal < b.dal ? -1 : a.dal > b.dal ? 1 : 0;
  });

  return {
    seritler,
    bas,
    son,
    cakisanDosyalar,
    okunamayan,
    gizlenenSerit: gizlenen.length,
    gizlenenOlay: gizlenen.reduce((s, x) => s + x.olaylar.length, 0),
  };
}

/**
 * Olayın zaman eksenindeki yatay konumu (%0–%100).
 *
 * Tüm olaylar aynı ana düşerse (`bas === son`) bölme 0/0 olurdu; o durumda
 * eksen anlamsızdır ve hepsi ORTAYA konur — sahte bir yayılım çizilmez.
 */
export function zamanYuzdesi(t: number, bas: number | null, son: number | null): number {
  if (bas === null || son === null || son <= bas) return 50;
  return ((t - bas) / (son - bas)) * 100;
}

/**
 * Aynı şeritte üst üste düşen olayları alt-satırlara dağıtır.
 *
 * NEDEN Y'yi kullanmak dürüst: şeridin İÇİNDEKİ dikey konum hiçbir anlam
 * taşımıyor (anlam taşıyan tek eksen X = zaman, bir de hangi şeritte olduğu).
 * Boş bir kanalı üst üste binmeyi çözmek için kullanmak, X'i kaydırıp ZAMANI
 * yalan söylemekten kesinlikle iyidir — bu yüzden nokta kaydırma (jitter)
 * X'e değil Y'ye uygulanır.
 *
 * @param yuzdeler Şeritteki olayların X yüzdeleri, ZAMAN SIRASINDA.
 * @param enAzAralik İki noktanın aynı alt-satırda durabilmesi için gereken
 *                   en küçük yüzde farkı.
 * @param enFazlaSatir Şerit yüksekliği tavanı. Neden gerekli: canlı ölçüm
 *   (30 Tem) "dal bilgisi yok" şeridinde **309 olay** gösterdi; sınırsız
 *   açılım o şeridi tek başına **1009 piksel** yaptı — ekranın üç katı.
 *   Tavana ulaşınca olay, son noktası EN ESKİ olan satıra konur (en az kötü
 *   çakışma). Yani çok yoğun şeritte noktalar üst üste binebilir; bu bir
 *   kayıp değil — yoğunluğun kendisi okunabilir bir sinyal, ve zaman (X)
 *   hiçbir koşulda kaydırılmıyor.
 * @returns Her olay için alt-satır indeksi (0 = şeridin ortası).
 */
export function altSatirAta(
  yuzdeler: number[],
  enAzAralik = 2.2,
  enFazlaSatir = 6,
): number[] {
  /** Alt-satır -> o satırdaki SON noktanın yüzdesi. */
  const sonYuzde: number[] = [];
  return yuzdeler.map((y) => {
    for (let satir = 0; satir < sonYuzde.length; satir++) {
      if (y - sonYuzde[satir] >= enAzAralik) {
        sonYuzde[satir] = y;
        return satir;
      }
    }
    if (sonYuzde.length < enFazlaSatir) {
      sonYuzde.push(y);
      return sonYuzde.length - 1;
    }
    // Tavan doldu: son noktası en geride kalan satır en az çakışmayı verir.
    // Deterministik (ilk eşitlikte en küçük indeks kazanır).
    let enIyi = 0;
    for (let s = 1; s < sonYuzde.length; s++) {
      if (sonYuzde[s] < sonYuzde[enIyi]) enIyi = s;
    }
    sonYuzde[enIyi] = y;
    return enIyi;
  });
}
