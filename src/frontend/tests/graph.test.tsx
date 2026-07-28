/** #130 testleri — mod seçici (sekme ailesi + localStorage), treemap yerleşim
    algoritması (alan korunumu + çakışmama), modül detay paneli, hayalet-panel
    temizliği (mod değişince diğer modun paneli kapanır). */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "../src/api/schema.d.ts";
import GraphPage, { treemapDizilimi } from "../src/pages/GraphPage";

type TouchGraph = components["schemas"]["TouchGraph"];

const mockUseGraph = vi.fn();
vi.mock("../src/lib/useGraph", () => ({ useGraph: () => mockUseGraph() }));

const MOD_KEY = "grup54:graph:gorunum-modu";

const veri: TouchGraph = {
  window_days: 14,
  nodes: [
    { id: "fatih", type: "actor", weight: 5, actor_verified: true },
    { id: "enes", type: "actor", weight: 5, actor_verified: true },
    { id: "engine", type: "module", weight: 7, actor_verified: true },
    { id: "frontend", type: "module", weight: 3, actor_verified: true },
  ],
  edges: [
    {
      actor: "fatih",
      module: "engine",
      count: 5,
      last_ts: "2026-07-20T09:00:00Z",
      is_active_declared: true,
    },
    {
      actor: "enes",
      module: "frontend",
      count: 3,
      last_ts: "2026-07-10T09:00:00Z",
      is_active_declared: false,
    },
    {
      actor: "enes",
      module: "engine",
      count: 2,
      last_ts: "2026-07-25T09:00:00Z",
      is_active_declared: false,
    },
  ],
};

const dolu = {
  data: veri,
  error: null,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: Date.now(),
};

beforeEach(() => {
  window.localStorage.clear();
  mockUseGraph.mockReturnValue(dolu);
});

afterEach(() => {
  window.localStorage.clear();
});

describe("treemapDizilimi (saf yerleşim fonksiyonu)", () => {
  it("tek girdi tüm alanı kaplar", () => {
    expect(treemapDizilimi([{ modul: "a", deger: 5 }], 0, 0, 100, 50)).toEqual([
      { modul: "a", deger: 5, x: 0, y: 0, w: 100, h: 50 },
    ]);
  });

  it("boş girdi ya da sıfır/negatif kutu → boş dizi (NaN üretmez)", () => {
    expect(treemapDizilimi([], 0, 0, 100, 50)).toEqual([]);
    expect(treemapDizilimi([{ modul: "a", deger: 1 }], 0, 0, 0, 50)).toEqual([]);
    expect(treemapDizilimi([{ modul: "a", deger: 1 }], 0, 0, 100, 0)).toEqual([]);
  });

  it("iki eşit değer, geniş konteyner (w>=h) → dikey kesim, tam yarı yarıya", () => {
    const kutular = treemapDizilimi(
      [
        { modul: "a", deger: 1 },
        { modul: "b", deger: 1 },
      ],
      0,
      0,
      100,
      50,
    );
    expect(kutular).toEqual([
      { modul: "a", deger: 1, x: 0, y: 0, w: 50, h: 50 },
      { modul: "b", deger: 1, x: 50, y: 0, w: 50, h: 50 },
    ]);
  });

  it("orantısız değer (3:1), deterministik kesim noktası", () => {
    const kutular = treemapDizilimi(
      [
        { modul: "buyuk", deger: 3 },
        { modul: "kucuk", deger: 1 },
      ],
      0,
      0,
      100,
      50,
    );
    expect(kutular).toEqual([
      { modul: "buyuk", deger: 3, x: 0, y: 0, w: 75, h: 50 },
      { modul: "kucuk", deger: 1, x: 75, y: 0, w: 25, h: 50 },
    ]);
  });

  it("değersiz grup (hepsi 0) NaN/Infinity üretmez, dizilim yine de tam alanı kaplar", () => {
    const kutular = treemapDizilimi(
      [
        { modul: "a", deger: 0 },
        { modul: "b", deger: 0 },
        { modul: "c", deger: 0 },
      ],
      0,
      0,
      100,
      50,
    );
    for (const k of kutular) {
      expect(Number.isFinite(k.x)).toBe(true);
      expect(Number.isFinite(k.y)).toBe(true);
      expect(Number.isFinite(k.w)).toBe(true);
      expect(Number.isFinite(k.h)).toBe(true);
    }
    const toplamAlan = kutular.reduce((s, k) => s + k.w * k.h, 0);
    expect(toplamAlan).toBeCloseTo(100 * 50, 5);
  });

  it("5 rastgele-benzeri girdide alan korunur ve hiçbir kutu üst üste binmez", () => {
    const girdiler = [
      { modul: "a", deger: 13 },
      { modul: "b", deger: 7 },
      { modul: "c", deger: 5 },
      { modul: "d", deger: 3 },
      { modul: "e", deger: 1 },
    ];
    const kutular = treemapDizilimi(girdiler, 0, 0, 317, 191); // asimetrik boyut
    expect(kutular).toHaveLength(5);

    const toplamAlan = kutular.reduce((s, k) => s + k.w * k.h, 0);
    expect(toplamAlan).toBeCloseTo(317 * 191, 3);

    // ikili AABB kesişimi ~0 olmalı (kenar paylaşımı serbest, örtüşme YASAK)
    for (let i = 0; i < kutular.length; i++) {
      for (let j = i + 1; j < kutular.length; j++) {
        const a = kutular[i];
        const b = kutular[j];
        const kesisimGenislik = Math.max(
          0,
          Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x),
        );
        const kesisimYukseklik = Math.max(
          0,
          Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y),
        );
        expect(kesisimGenislik * kesisimYukseklik).toBeCloseTo(0, 6);
      }
    }
  });
});

describe("GraphPage — görünüm modu seçici (#130)", () => {
  it("varsayılan mod ısı matrisi — matris tablosu görünür, treemap yok", () => {
    render(<GraphPage />);
    expect(screen.getByRole("tab", { name: "Isı matrisi" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /treemap/i })).not.toBeInTheDocument();
  });

  it("Treemap sekmesine tıklayınca matris kalkar, treemap görünür", async () => {
    const user = userEvent.setup();
    render(<GraphPage />);
    await user.click(screen.getByRole("tab", { name: "Treemap" }));
    expect(screen.getByRole("tab", { name: "Treemap" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: /treemap/i })).toBeInTheDocument();
    // her iki modül de görünür (alan = toplam dokunuş)
    expect(screen.getByTitle(/^engine: 7 dokunuş/)).toBeInTheDocument();
    expect(screen.getByTitle(/^frontend: 3 dokunuş/)).toBeInTheDocument();
  });

  it("mod tercihi localStorage'a yazılır ve yeniden mount'ta korunur", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<GraphPage />);
    await user.click(screen.getByRole("tab", { name: "Treemap" }));
    expect(window.localStorage.getItem(MOD_KEY)).toBe("treemap");
    unmount();

    render(<GraphPage />);
    expect(screen.getByRole("tab", { name: "Treemap" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("bozuk localStorage değeri sessizce varsayılana düşer (whitescreen yok)", () => {
    window.localStorage.setItem(MOD_KEY, "bozuk-deger-xyz");
    render(<GraphPage />);
    expect(screen.getByRole("tab", { name: "Isı matrisi" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("gate'li modlar için ölü sekme YOK, gerekçe metni görünür", () => {
    render(<GraphPage />);
    expect(screen.queryByRole("tab", { name: /güç-yönlü/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /git ağacı/i })).not.toBeInTheDocument();
    expect(screen.getByText(/gate'li — bkz\. #130/)).toBeInTheDocument();
  });
});

describe("GraphPage — başlık + legend yazımı (#316/A5, H1)", () => {
  it("başlık Title Case: 'Dokunma Grafı', 'Dokunma grafı' DEĞİL", () => {
    // MUTASYON KİLİDİ: h1'i eski "Dokunma grafı"ya geri çevir -> bu test kırılır.
    render(<GraphPage />);
    expect(screen.getByRole("heading", { name: "Dokunma Grafı" })).toBeInTheDocument();
  });

  it("ısı matrisi legend'i 'soluk' yazar, yazım hatası 'solar' YOK", () => {
    // MUTASYON KİLİDİ: "(soluk)"i "(solar)"a geri çevir -> ikinci expect kırılır.
    render(<GraphPage />);
    expect(screen.getByText(/7\+ gün önce \(soluk\)/)).toBeInTheDocument();
    expect(screen.queryByText(/solar/)).not.toBeInTheDocument();
  });

  it("treemap legend'i de 'soluk' yazar, 'solar' YOK", async () => {
    const user = userEvent.setup();
    render(<GraphPage />);
    await user.click(screen.getByRole("tab", { name: "Treemap" }));
    expect(screen.getByText(/7\+ gün önce \(soluk\)/)).toBeInTheDocument();
    expect(screen.queryByText(/solar/)).not.toBeInTheDocument();
  });
});

describe("GraphPage — ısı matrisi yatay kaydırma (#316/H3)", () => {
  it("26 modülde konteyner overflow-x-auto taşır, aktör sütunu sticky kalır", () => {
    // Canlıda doğrulanan bulgu (2026-07-28): 26 modülde matris sağdan
    // taşıyor/kırpılıyordu. MUTASYON KİLİDİ: Matris'in `overflow-x-auto`
    // sınıfını sil -> ilk expect kırılır; sticky satır başlığının
    // `sticky left-0` sınıfını sil -> ikinci expect kırılır.
    const cokModulluVeri: TouchGraph = {
      window_days: 14,
      nodes: [
        { id: "fatih", type: "actor", weight: 26, actor_verified: true },
        ...Array.from({ length: 26 }, (_, i) => ({
          id: `modul-${i}`,
          type: "module" as const,
          weight: 1,
          actor_verified: true,
        })),
      ],
      edges: Array.from({ length: 26 }, (_, i) => ({
        actor: "fatih",
        module: `modul-${i}`,
        count: i + 1,
        last_ts: "2026-07-20T09:00:00Z",
        is_active_declared: false,
      })),
    };
    mockUseGraph.mockReturnValue({ ...dolu, data: cokModulluVeri });
    render(<GraphPage />);

    const table = screen.getByRole("table");
    const kap = table.parentElement as HTMLElement;
    expect(kap.className).toMatch(/overflow-x-auto/);

    // Sütun başlığındaki "Aktör \ Modül" hücresi + her satırın aktör hücresi
    // sticky olmalı (yatay kayarken sabit kalan sütun).
    const koseBasligi = screen.getByText("Aktör \\ Modül");
    expect(koseBasligi.className).toMatch(/sticky/);
    const aktorHucresi = screen.getByText("fatih").closest("th");
    expect(aktorHucresi?.className).toMatch(/sticky/);

    // 26 sütun da gerçekten render oldu (kırpılıp kaybolmadı, DOM'da var —
    // görünürlüğü sağlayan `overflow-x-auto`, kırpma değil).
    for (let i = 0; i < 26; i++) {
      expect(screen.getByTitle(new RegExp(`^fatih → modul-${i}:`))).toBeInTheDocument();
    }
  });
});

describe("GraphPage — treemap modül detay paneli", () => {
  async function treemapeGec() {
    const user = userEvent.setup();
    render(<GraphPage />);
    await user.click(screen.getByRole("tab", { name: "Treemap" }));
    return user;
  }

  it("modül kutusuna tıklayınca kim-dokunuyor paneli açılır", async () => {
    const user = await treemapeGec();
    await user.click(screen.getByTitle(/^engine: 7 dokunuş/));
    const panel = screen.getByLabelText("Modül detayı");
    expect(within(panel).getByText("engine")).toBeInTheDocument();
    // paylaşılan modül: iki aktör de listelenir
    expect(within(panel).getByText("fatih")).toBeInTheDocument();
    expect(within(panel).getByText("enes")).toBeInTheDocument();
  });

  it("X ve Esc kapatır", async () => {
    const user = await treemapeGec();
    await user.click(screen.getByTitle(/^engine: 7 dokunuş/));
    await user.click(screen.getByLabelText("Detayı kapat"));
    expect(screen.queryByLabelText("Modül detayı")).not.toBeInTheDocument();

    await user.click(screen.getByTitle(/^engine: 7 dokunuş/));
    expect(screen.getByLabelText("Modül detayı")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByLabelText("Modül detayı")).not.toBeInTheDocument();
  });

  it("aynı kutuya tekrar tıklamak paneli kapatır (toggle)", async () => {
    const user = await treemapeGec();
    const kutu = screen.getByTitle(/^frontend: 3 dokunuş/);
    await user.click(kutu);
    expect(screen.getByLabelText("Modül detayı")).toBeInTheDocument();
    await user.click(kutu);
    expect(screen.queryByLabelText("Modül detayı")).not.toBeInTheDocument();
  });

  it("mod değişince hayalet panel kalmaz: ısı matrisinde açılan panel treemap'e geçince kapanır ve tersi", async () => {
    const user = userEvent.setup();
    render(<GraphPage />);
    // ısı matrisinde bir hücre seç
    await user.click(screen.getByRole("button", { name: /fatih, engine: 5 dokunuş/ }));
    expect(screen.getByLabelText("Dokunuş detayı")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Treemap" }));
    expect(screen.queryByLabelText("Dokunuş detayı")).not.toBeInTheDocument();

    await user.click(screen.getByTitle(/^frontend: 3 dokunuş/));
    expect(screen.getByLabelText("Modül detayı")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Isı matrisi" }));
    expect(screen.queryByLabelText("Modül detayı")).not.toBeInTheDocument();
  });
});

describe("GraphPage — GraphNode.actor_verified göstergesi (#296)", () => {
  // PO bu hatayı grafta gördü ("Merge Simulation" 5. takım üyesi gibi
  // göründü) - işaretleme burada da (Activity'nin yanında) çalışmalı.
  const veriDogrulamaSiz = {
    window_days: 14,
    nodes: [
      { id: "esma6", type: "actor" as const, weight: 5, actor_verified: true },
      { id: "Merge Simulation", type: "actor" as const, weight: 2, actor_verified: false },
      { id: "backend", type: "module" as const, weight: 7, actor_verified: true },
    ],
    edges: [
      {
        actor: "esma6",
        module: "backend",
        count: 5,
        last_ts: "2026-07-20T09:00:00Z",
        is_active_declared: false,
      },
      {
        actor: "Merge Simulation",
        module: "backend",
        count: 2,
        last_ts: "2026-07-19T09:00:00Z",
        is_active_declared: false,
      },
    ],
  };

  beforeEach(() => {
    mockUseGraph.mockReturnValue({
      data: veriDogrulamaSiz,
      error: null,
      isLoading: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
    });
  });

  it("Isı matrisi satır başlığı: yalnız eşleşmeyen aktörde rozet var", () => {
    render(<GraphPage />);
    const satirlar = screen.getAllByRole("row");
    const merge = satirlar.find((r) => r.textContent?.includes("Merge Simulation"));
    const esma = satirlar.find((r) => r.textContent?.includes("esma6"));
    expect(merge?.querySelector('[data-testid="actor-unverified-badge"]')).not.toBeNull();
    expect(esma?.querySelector('[data-testid="actor-unverified-badge"]')).toBeNull();
  });

  it("Dokunuş detay paneli (hücre tıklama): eşleşmeyen aktör için rozet açık", async () => {
    const user = userEvent.setup();
    render(<GraphPage />);
    await user.click(screen.getByRole("button", { name: /Merge Simulation, backend: 2 dokunuş/ }));
    const panel = screen.getByLabelText("Dokunuş detayı");
    expect(within(panel).getByTestId("actor-unverified-badge")).toBeInTheDocument();
  });

  it("Treemap modül detay paneli: karışık aktör listesinde yalnız eşleşmeyen rozet taşır", async () => {
    const user = userEvent.setup();
    render(<GraphPage />);
    await user.click(screen.getByRole("tab", { name: "Treemap" }));
    await user.click(screen.getByTitle(/^backend: 7 dokunuş/));
    const panel = screen.getByLabelText("Modül detayı");
    const satirlar = within(panel).getAllByRole("listitem");
    const merge = satirlar.find((r) => r.textContent?.includes("Merge Simulation"));
    const esma = satirlar.find((r) => r.textContent?.includes("esma6"));
    expect(merge?.querySelector('[data-testid="actor-unverified-badge"]')).not.toBeNull();
    expect(esma?.querySelector('[data-testid="actor-unverified-badge"]')).toBeNull();
  });
});
