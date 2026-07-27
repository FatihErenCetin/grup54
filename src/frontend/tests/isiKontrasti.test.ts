/** T-293 — "dokunma grafında harita üstündeki her yazı beyaz olsun" (PO).
 *
 * Kök neden: `ISI_SINIFLARI` (src/lib/isiRampasi.ts — Isı matrisi + Treemap +
 * Radar'daki IsiMatrisi paneli, üç yüzey de TEK bu tablodan besleniyor) en
 * sıcak 2 kademede `text-primary-foreground` (koyu metin) kullanıyordu; PO'nun
 * gördüğü "bazı hücreler beyaz, bazıları siyah" tutarsızlığı buydu.
 *
 * Salt "hepsini beyaz yap" YETMEZ: düz `--primary` (L=0.7) üstünde beyaz metin
 * WCAG AA eşiği 4.5:1'in altında kalır (bkz. aşağıdaki mutasyon notu). Bu
 * yüzden bu test iki şeyi BİRDEN doğrular:
 *   1) Her kademe `text-foreground` kullanıyor, `text-primary-foreground`
 *      hiçbirinde YOK (basit string kontrolü).
 *   2) Her kademenin GERÇEK zemin rengi (index.css'ten OKUNUR, hardcode
 *      edilmez) `--foreground` ile en az 4.5:1 kontrast veriyor (WCAG 2.1,
 *      oklch → lineer sRGB → göreli parlaklık → kontrast oranı — bu depoda
 *      yeni bir renk kütüphanesi bağımlılığı YOK, formül elle uygulanıyor).
 *
 * Kapsam notu: index.css'te `.light` teması da tanımlı ama repoda HİÇBİR
 * yerde uygulanmıyor (`document.documentElement`'e `light` class'ı ekleyen
 * kod yok — grep ile doğrulandı). Bugün gerçekte render edilen tek tema
 * `:root` (dark, varsayılan); test de onu ölçüyor. `.light` erişilebilir
 * hale gelirse (bir tema anahtarı eklenirse) o zaman ayrı bir ölçüm gerekir.
 *
 * Mutasyon kanıtı (elle koşulup PR gövdesine yazıldı, burada KALICI değil):
 *   (a) bir kademeyi `text-primary-foreground`'a geri çevir → aşağıdaki
 *       "text-foreground kullanır" testi KIRMIZI olur.
 *   (b) `--primary-strong`'u eski (koyulaştırılmamış, `--primary` ile aynı
 *       L=0.7) değerine döndür → "kontrast >= 4.5" testi KIRMIZI olur.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ISI_SINIFLARI } from "../src/lib/isiRampasi";

// `vitest run` (package.json "test") her zaman src/frontend'den koşar
// (vite.config.ts kökü) — cwd'ye göreli, import.meta.url'e göre DEĞİL (vitest
// test modüllerine gerçek bir `file://` URL'i garanti etmez).
const CSS_YOLU = resolve(process.cwd(), "src/index.css");

// ── oklch → WCAG kontrast — bağımsız, bağımlılıksız uygulama ───────────────
// (Björn Ottosson'un OKLab matrisleri; WCAG 2.1 göreli parlaklık formülü.)

type Oklch = { l: number; c: number; h: number };

function oklchAyristir(ham: string): Oklch {
  const m = ham.match(/oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)/);
  if (!m) throw new Error(`oklch(...) çözülemedi: "${ham}"`);
  return { l: Number(m[1]), c: Number(m[2]), h: Number(m[3]) };
}

/** index.css'in `:root { ... }` bloğundan tek bir `--isim: oklch(...)` değerini
    OKUR (hardcode edilmiş bir tabloya bakmaz — dosya değişirse test de değişir). */
function kokTokenOku(kokBlogu: string, isim: string): Oklch {
  const re = new RegExp(`--${isim}:\\s*(oklch\\([^)]*\\))`);
  const m = kokBlogu.match(re);
  if (!m) throw new Error(`--${isim} index.css :root içinde bulunamadı`);
  return oklchAyristir(m[1]);
}

type LinRGB = { r: number; g: number; b: number };

/** OKLCH → lineer sRGB (gamut dışı bileşenler [0,1]'e kenetlenir — tarayıcının
    tam gamut-mapping algoritmasının basitleştirilmiş bir yaklaşıklığı; bu
    depodaki tüm token'lar sınırın çok altında/üstünde kaldığı için eşik
    kararını değiştirmez). */
function oklchToLinearSrgb({ l, c, h }: Oklch): LinRGB {
  const hRad = (h * Math.PI) / 180;
  const a = c * Math.cos(hRad);
  const b = c * Math.sin(hRad);

  const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = l - 0.0894841775 * a - 1.291485548 * b;

  const ll = l_ ** 3;
  const mm = m_ ** 3;
  const ss = s_ ** 3;

  return {
    r: 4.0767416621 * ll - 3.3077115913 * mm + 0.2309699292 * ss,
    g: -1.2684380046 * ll + 2.6097574011 * mm - 0.3413193965 * ss,
    b: -0.0041960863 * ll - 0.7034186147 * mm + 1.707614701 * ss,
  };
}

function kenetle(x: number): number {
  return Math.min(1, Math.max(0, x));
}

/** sRGB EOTF/OETF (IEC 61966-2-1) — alfa harmanlamayı (bir tarayıcının basit
    "source-over" kompozisyonu gibi) gama-kodlu uzayda yapmak için. */
function linToGamma(c: number): number {
  const x = kenetle(c);
  return x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055;
}
function gammaToLin(c: number): number {
  const x = kenetle(c);
  return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
}

/** WCAG 2.1 göreli parlaklık — lineer sRGB bileşenlerinden. */
function goreliParlaklik(rgb: LinRGB): number {
  return 0.2126 * kenetle(rgb.r) + 0.7152 * kenetle(rgb.g) + 0.0722 * kenetle(rgb.b);
}

/** WCAG 2.1 kontrast oranı: (açık+0.05)/(koyu+0.05). */
function kontrastOrani(l1: number, l2: number): number {
  const acik = Math.max(l1, l2);
  const koyu = Math.min(l1, l2);
  return (acik + 0.05) / (koyu + 0.05);
}

/** `fg`'yi `alpha` (0-1) oranında `bg` üstüne bindirir (gama-kodlu uzayda
    basit lineer harman — Tailwind'in opaklık varyantlarının (`bg-x/NN`)
    şeffaf'a `color-mix` ile indirgenip asıl zeminle kompoze olma şeklinin
    pratik yaklaşıklığı), sonucu tekrar lineer sRGB'ye çevirip döner. */
function ustuneBindir(fg: LinRGB, bg: LinRGB, alpha: number): LinRGB {
  const blend = (a: number, b: number) => alpha * linToGamma(a) + (1 - alpha) * linToGamma(b);
  return {
    r: gammaToLin(blend(fg.r, bg.r)),
    g: gammaToLin(blend(fg.g, bg.g)),
    b: gammaToLin(blend(fg.b, bg.b)),
  };
}

// ── ISI_SINIFLARI class-adı ayrıştırma (uydurma alfa/token yok, string'den) ──

type RampaKademesi = {
  ham: string;
  token: "primary" | "primary-strong";
  alpha: number; // 0..1 — slash yoksa 1 (bg-primary = tam opak)
  metinSinifi: string;
};

function rampaKademesiAyristir(cls: string): RampaKademesi {
  const m = cls.match(/^bg-(primary(?:-strong)?)(?:\/(\d+))?\s+(.+)$/);
  if (!m) throw new Error(`ISI_SINIFLARI girdisi beklenen kalıpta değil: "${cls}"`);
  const [, token, alphaYuzde, metinSinifi] = m;
  return {
    ham: cls,
    token: token as "primary" | "primary-strong",
    alpha: alphaYuzde ? Number(alphaYuzde) / 100 : 1,
    metinSinifi,
  };
}

describe("Isı rampası — WCAG AA kontrastı (T-293, gerçek index.css değerinden ölçülür)", () => {
  const css = readFileSync(CSS_YOLU, "utf-8");
  const kokMatch = css.match(/:root\s*\{([^}]*)\}/);
  if (!kokMatch) throw new Error("index.css içinde :root { ... } bloğu bulunamadı");
  const kokBlogu = kokMatch[1];

  const card = kokTokenOku(kokBlogu, "card");
  const foreground = kokTokenOku(kokBlogu, "foreground");
  const tokenler: Record<"primary" | "primary-strong", Oklch> = {
    primary: kokTokenOku(kokBlogu, "primary"),
    "primary-strong": kokTokenOku(kokBlogu, "primary-strong"),
  };

  const cardLin = oklchToLinearSrgb(card);
  const fgLin = oklchToLinearSrgb(foreground);
  const fgParlaklik = goreliParlaklik(fgLin);

  const kademeler = ISI_SINIFLARI.map(rampaKademesiAyristir);

  it("sanity: ölçüm fonksiyonu doğru çalışıyor (siyah/beyaz = 21:1)", () => {
    const siyah = goreliParlaklik({ r: 0, g: 0, b: 0 });
    const beyaz = goreliParlaklik({ r: 1, g: 1, b: 1 });
    expect(kontrastOrani(siyah, beyaz)).toBeCloseTo(21, 1);
  });

  it("5 kademe var, hepsi bg-primary(-strong) + tanınan bir slash/alfa kalıbında", () => {
    expect(ISI_SINIFLARI).toHaveLength(5);
    expect(kademeler.every((k) => Number.isFinite(k.alpha) && k.alpha > 0 && k.alpha <= 1)).toBe(
      true,
    );
  });

  it.each(kademeler.map((k, i) => [i + 1, k] as const))(
    "kademe %i (%s): text-foreground kullanır, text-primary-foreground YOK",
    (_i, kademe) => {
      expect(kademe.metinSinifi).toContain("text-foreground");
      expect(kademe.metinSinifi).not.toContain("text-primary-foreground");
    },
  );

  it.each(kademeler.map((k, i) => [i + 1, k] as const))(
    "kademe %i (%s): --card üstüne bindirilmiş zemin, --foreground metinle >= 4.5:1",
    (_i, kademe) => {
      const zeminTokenLin = oklchToLinearSrgb(tokenler[kademe.token]);
      const bindirilmisZemin = ustuneBindir(zeminTokenLin, cardLin, kademe.alpha);
      const zeminParlaklik = goreliParlaklik(bindirilmisZemin);
      const kontrast = kontrastOrani(fgParlaklik, zeminParlaklik);
      expect(kontrast).toBeGreaterThanOrEqual(4.5);
    },
  );

  it("belgeleme: düz --primary (koyulaştırılmamış) üstünde beyaz metin AA'yı GEÇMEZ — bu yüzden --primary-strong var", () => {
    // Bu, T-293'ün kök nedenini yeniden üretir (regresyon değil, gerekçe kaydı):
    // en sıcak kademe hâlâ düz `--primary` kullansaydı bu assert kırılırdı.
    const primaryLin = oklchToLinearSrgb(tokenler.primary);
    const primaryParlaklik = goreliParlaklik(primaryLin);
    const kontrast = kontrastOrani(fgParlaklik, primaryParlaklik);
    expect(kontrast).toBeLessThan(4.5);
  });
});
