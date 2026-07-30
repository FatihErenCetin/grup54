/** #130 modları a + d — saf yerleşim algoritmalarının testleri.
 *
 * Bu dosyanın asıl işi DETERMİNİZMİ kilitlemek. Kuvvet-yönlü yerleşimin
 * klasik hali `Math.random()` tohumla başlar; öyle olsaydı kullanıcı aynı
 * veriye iki kez baktığında farklı bir resim görürdü. "Aynı veri → aynı
 * resim" bir ince ayar değil, grafiğin okunabilmesinin ÖN KOŞULU — o yüzden
 * teste bağlanıyor, yorumda söz olarak bırakılmıyor.
 */
import { describe, expect, it } from "vitest";
import {
  altSatirAta,
  gucYonluYerlesim,
  seritDizilimi,
  zamanYuzdesi,
  type SeritOlayi,
  type YerlesimDugumu,
  type YerlesimKenari,
} from "../src/lib/grafYerlesimi";

const G = 1000;
const Y = 620;

const dugumler: YerlesimDugumu[] = [
  { id: "fatih", agirlik: 8 },
  { id: "enes", agirlik: 5 },
  { id: "semih", agirlik: 3 },
  { id: "src/backend", agirlik: 9 },
  { id: "src/frontend", agirlik: 7 },
];

const kenarlar: YerlesimKenari[] = [
  { kaynak: "fatih", hedef: "src/backend", agirlik: 8 },
  { kaynak: "enes", hedef: "src/backend", agirlik: 2 },
  { kaynak: "enes", hedef: "src/frontend", agirlik: 3 },
  { kaynak: "semih", hedef: "src/frontend", agirlik: 3 },
];

function uzaklik(
  konumlar: { id: string; x: number; y: number }[],
  a: string,
  b: string,
): number {
  const ka = konumlar.find((k) => k.id === a);
  const kb = konumlar.find((k) => k.id === b);
  if (!ka || !kb) throw new Error(`konum yok: ${a} / ${b}`);
  return Math.hypot(ka.x - kb.x, ka.y - kb.y);
}

describe("gucYonluYerlesim — determinizm", () => {
  it("aynı girdi iki kez → BİREBİR aynı konumlar", () => {
    // MUTASYON KİLİDİ: tohuma Math.random() ekle -> bu test kırılır.
    const a = gucYonluYerlesim(dugumler, kenarlar, G, Y);
    const b = gucYonluYerlesim(dugumler, kenarlar, G, Y);
    expect(a).toEqual(b);
  });

  it("girdi SIRASI değişse de aynı resim çıkar", () => {
    // Backend `nodes`/`edges` sırası için garanti vermiyor; sıraya duyarlı bir
    // yerleşim, veri değişmediği hâlde sayfayı yeniden dizerdi.
    // MUTASYON KİLİDİ: fonksiyondaki `[...dugumler].sort(...)` satırını sil
    // -> tohum indeksleri kayar, bu test kırılır.
    const dus = [...dugumler].reverse();
    const kes = [...kenarlar].reverse();
    const a = gucYonluYerlesim(dugumler, kenarlar, G, Y);
    const b = gucYonluYerlesim(dus, kes, G, Y);
    const sirala = (k: typeof a) => [...k].sort((p, q) => (p.id < q.id ? -1 : 1));
    expect(sirala(b)).toEqual(sirala(a));
  });
});

describe("gucYonluYerlesim — geçerlilik", () => {
  it("boş graf → boş dizi (NaN/çökme yok)", () => {
    expect(gucYonluYerlesim([], [], G, Y)).toEqual([]);
    expect(gucYonluYerlesim(dugumler, kenarlar, 0, Y)).toEqual([]);
  });

  it("tek düğüm tam ortaya konur", () => {
    expect(gucYonluYerlesim([{ id: "tek", agirlik: 1 }], [], G, Y)).toEqual([
      { id: "tek", x: G / 2, y: Y / 2 },
    ]);
  });

  it("tüm konumlar tuval İÇİNDE ve sonlu", () => {
    // MUTASYON KİLİDİ: döngü sonundaki Math.min/Math.max sıkıştırmasını sil
    // -> itme kuvveti düğümleri tuval dışına atar, bu test kırılır.
    const k = gucYonluYerlesim(dugumler, kenarlar, G, Y);
    expect(k).toHaveLength(dugumler.length);
    for (const { x, y } of k) {
      expect(Number.isFinite(x)).toBe(true);
      expect(Number.isFinite(y)).toBe(true);
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(G);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(Y);
    }
  });

  it("üst üste düşen düğümlerde bile NaN üretmez", () => {
    // Aynı id'ye sahip olmayan ama tohumu çok yakın düşebilen kenar durumu:
    // itme adımındaki 0'a bölme savunması olmasaydı NaN yayılırdı.
    const cok = Array.from({ length: 12 }, (_, i) => ({ id: `d${i}`, agirlik: 1 }));
    for (const { x, y } of gucYonluYerlesim(cok, [], G, Y)) {
      expect(Number.isNaN(x)).toBe(false);
      expect(Number.isNaN(y)).toBe(false);
    }
  });

  it("bağlı düğümler bağsızlardan DAHA YAKIN durur (algoritma işini yapıyor)", () => {
    // Determinizm tek başına yetmez: sabit ama ANLAMSIZ bir yerleşim de
    // deterministik olurdu. Asıl vaat "birlikte çalışan işler yan yana düşer".
    // MUTASYON KİLİDİ: çekme (attraction) döngüsünü sil -> hepsi eşit dağılır,
    // bu test kırılır.
    const iki: YerlesimDugumu[] = [
      { id: "a1", agirlik: 5 },
      { id: "m1", agirlik: 5 },
      { id: "a2", agirlik: 5 },
      { id: "m2", agirlik: 5 },
    ];
    const ikiKenar: YerlesimKenari[] = [
      { kaynak: "a1", hedef: "m1", agirlik: 5 },
      { kaynak: "a2", hedef: "m2", agirlik: 5 },
    ];
    const k = gucYonluYerlesim(iki, ikiKenar, G, Y);
    expect(uzaklik(k, "a1", "m1")).toBeLessThan(uzaklik(k, "a1", "m2"));
    expect(uzaklik(k, "a2", "m2")).toBeLessThan(uzaklik(k, "a2", "m1"));
  });

  it("grafta olmayan uca sahip kenar sessizce atlanır (uydurma düğüm yok)", () => {
    const k = gucYonluYerlesim(dugumler, [
      ...kenarlar,
      { kaynak: "fatih", hedef: "olmayan-modul", agirlik: 3 },
    ]);
    expect(k.map((d) => d.id)).not.toContain("olmayan-modul");
    expect(k).toHaveLength(dugumler.length);
  });
});

/* ── Git şeridi ───────────────────────────────────────────────────────────── */

function olay(o: Partial<SeritOlayi> & { id: string; ts: string }): SeritOlayi {
  return {
    tip: "commit",
    aktor: "fatih",
    dogrulandi: true,
    dal: "main",
    ref: "abc123",
    files: [],
    ...o,
  };
}

describe("seritDizilimi", () => {
  it("dala göre gruplar; main üstte, 'dal bilgisi yok' en altta", () => {
    // MUTASYON KİLİDİ: sıralamadaki `dalBilinmiyor` dalını sil -> artık kovası
    // gerçek dalların arasına karışır, bu test kırılır.
    const d = seritDizilimi([
      olay({ id: "1", ts: "2026-07-02T10:00:00Z", dal: "T-9-feature" }),
      olay({ id: "2", ts: "2026-07-01T10:00:00Z", dal: null }),
      olay({ id: "3", ts: "2026-07-03T10:00:00Z", dal: "main" }),
    ]);
    expect(d.seritler.map((s) => s.dal)).toEqual([
      "main",
      "T-9-feature",
      "dal bilgisi yok",
    ]);
    expect(d.seritler[2].dalBilinmiyor).toBe(true);
  });

  it("şerit içi sıra ZAMANA göre — girdi sırasından bağımsız", () => {
    const ham = [
      olay({ id: "gec", ts: "2026-07-05T10:00:00Z" }),
      olay({ id: "erken", ts: "2026-07-01T10:00:00Z" }),
      olay({ id: "orta", ts: "2026-07-03T10:00:00Z" }),
    ];
    const a = seritDizilimi(ham);
    const b = seritDizilimi([...ham].reverse());
    const sira = (d: typeof a) => d.seritler[0].olaylar.map((o) => o.id);
    expect(sira(a)).toEqual(["erken", "orta", "gec"]);
    expect(sira(b)).toEqual(sira(a));
  });

  it("İKİ farklı dalda geçen dosya çakışma adayı; tek dalda geçen DEĞİL", () => {
    // MUTASYON KİLİDİ: `s.size > 1` -> `s.size > 0` yap; "yalniz.py" da
    // çakışan sayılır, bu test kırılır.
    const d = seritDizilimi([
      olay({ id: "1", ts: "2026-07-01T10:00:00Z", dal: "main", files: ["ortak.py", "yalniz.py"] }),
      olay({ id: "2", ts: "2026-07-02T10:00:00Z", dal: "T-9", files: ["ortak.py"] }),
    ]);
    expect([...d.cakisanDosyalar]).toEqual(["ortak.py"]);
    const mainOlayi = d.seritler.find((s) => s.dal === "main")!.olaylar[0];
    expect(mainOlayi.cakisan).toEqual(["ortak.py"]);
  });

  it("AYNI dalda iki kez geçen dosya çakışma adayı DEĞİL", () => {
    const d = seritDizilimi([
      olay({ id: "1", ts: "2026-07-01T10:00:00Z", dal: "main", files: ["a.py"] }),
      olay({ id: "2", ts: "2026-07-02T10:00:00Z", dal: "main", files: ["a.py"] }),
    ]);
    expect(d.cakisanDosyalar.size).toBe(0);
  });

  it("tarihi çözülemeyen olay ÇİZİLMEZ ama SAYILIR (sessizce yutulmaz)", () => {
    // MUTASYON KİLİDİ: `okunamayan += 1` yerine olayı "bugün" say -> sayaç
    // sıfır kalır, bu test kırılır.
    const d = seritDizilimi([
      olay({ id: "1", ts: "2026-07-01T10:00:00Z" }),
      olay({ id: "bozuk", ts: "bu-bir-tarih-degil" }),
    ]);
    expect(d.okunamayan).toBe(1);
    expect(d.seritler.flatMap((s) => s.olaylar).map((o) => o.id)).toEqual(["1"]);
  });

  it("hiç olay yoksa bas/son null (0 epoch'a düşmez)", () => {
    const d = seritDizilimi([]);
    expect(d.seritler).toEqual([]);
    expect(d.bas).toBeNull();
    expect(d.son).toBeNull();
  });
});

describe("zamanYuzdesi", () => {
  it("uçları %0 ve %100'e oturtur", () => {
    expect(zamanYuzdesi(100, 100, 200)).toBe(0);
    expect(zamanYuzdesi(200, 100, 200)).toBe(100);
    expect(zamanYuzdesi(150, 100, 200)).toBe(50);
  });

  it("tüm olaylar aynı ana düşerse hepsi ORTAYA (sahte yayılım yok)", () => {
    // MUTASYON KİLİDİ: `son <= bas` savunmasını sil -> 0/0 = NaN döner.
    expect(zamanYuzdesi(100, 100, 100)).toBe(50);
    expect(zamanYuzdesi(100, null, null)).toBe(50);
  });
});

describe("altSatirAta", () => {
  it("üst üste binen noktalar farklı alt-satıra, ayrık olanlar aynı satıra", () => {
    // MUTASYON KİLİDİ: `>= enAzAralik` -> `>= 0` yap; hepsi 0. satıra yığılır,
    // bu test kırılır.
    expect(altSatirAta([0, 1, 5], 2.2)).toEqual([0, 1, 0]);
  });

  it("yeterince ayrık noktalar tek satırda kalır", () => {
    expect(altSatirAta([0, 10, 20, 30], 2.2)).toEqual([0, 0, 0, 0]);
  });

  it("boş girdi → boş çıktı", () => {
    expect(altSatirAta([])).toEqual([]);
  });
});
