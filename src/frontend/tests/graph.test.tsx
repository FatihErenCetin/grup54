/** #130 testleri — mod seçici (sekme ailesi + localStorage), treemap yerleşim
    algoritması (alan korunumu + çakışmama), modül detay paneli, hayalet-panel
    temizliği (mod değişince diğer modun paneli kapanır). */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "../src/api/schema.d.ts";
import GraphPage, { treemapDizilimi } from "../src/pages/GraphPage";

type TouchGraph = components["schemas"]["TouchGraph"];

const mockUseGraph = vi.fn();
vi.mock("../src/lib/useGraph", () => ({ useGraph: () => mockUseGraph() }));

/* GraphPage git-ağacı sekmesi için `useEvents` de çağırıyor (#130 mod d).
   `useGraph` ile AYNI desenle mock'lanır — bu dosya QueryClientProvider'sız
   render ediyor, gerçek hook react-query bağlamı ister. */
const mockUseEvents = vi.fn();
vi.mock("../src/lib/useEvents", () => ({ useEvents: () => mockUseEvents() }));

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
  mockUseEvents.mockReturnValue({
    data: { events: [], latest_ts: null },
    error: null,
    isLoading: false,
    isFetching: false,
    dataUpdatedAt: Date.now(),
  });
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

  /* Bu test eskiden gate'i (iki modun YOKLUĞUNU) kilitliyordu. Gate #130 ile
     kaldırıldı — testi SİLMEK yerine tersine çevirdik: aynı kural ("dead-tab
     basma") artık dört sekmenin de GERÇEKTEN çalıştığını kanıtlayarak korunuyor.
     Sekmeyi eklemek ama gövdesini bağlamamak = bu testin yakaladığı hata. */
  it("dört mod da sekme ailesinde ve hiçbiri ölü değil (gate kalktı — #130)", async () => {
    const kullanici = userEvent.setup();
    render(<GraphPage />);
    for (const ad of ["Isı matrisi", "Treemap", "Güç-yönlü", "Git ağacı"]) {
      expect(screen.getByRole("tab", { name: ad })).toBeInTheDocument();
    }
    // Eski gerekçe metni kalıntı olarak KALMASIN (mod çalışıyorken "gate'li"
    // yazan bir açıklama, çalışan özelliği yok gösterirdi).
    expect(screen.queryByText(/gate'li/i)).not.toBeInTheDocument();

    // "Ölü değil" = sekmeye basınca gerçekten o modun gövdesi geliyor.
    await kullanici.click(screen.getByRole("tab", { name: "Güç-yönlü" }));
    expect(
      screen.getByRole("group", { name: /güç-yönlü dokunma grafı/i }),
    ).toBeInTheDocument();
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

/* ══ #130 modları a + d — sekme ailesinin kalan iki modu ═══════════════════ */

/** Git ağacı modu <Link to="/radar"> içerir → router bağlamı şart. */
function router({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

describe("GraphPage — güç-yönlü graf (#130 mod a)", () => {
  async function gucModunaGec() {
    const kullanici = userEvent.setup();
    render(<GraphPage />);
    await kullanici.click(screen.getByRole("tab", { name: "Güç-yönlü" }));
    return kullanici;
  }

  it("her aktör ve modül erişilebilir bir düğüm olarak çizilir", async () => {
    // SVG kendi başına ekran okuyucuya bir şey söylemez; düğümler gerçek
    // role=button + aria-label taşımazsa bu görünüm klavyeye kapalı olurdu.
    await gucModunaGec();
    expect(
      screen.getByRole("button", { name: "Aktör fatih, 5 dokunuş" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Aktör enes, 5 dokunuş" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Modül engine, 7 dokunuş, birden fazla aktör dokundu",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Modül frontend, 3 dokunuş" }),
    ).toBeInTheDocument();
  });

  it("düğüme tıklayınca komşularını listeleyen panel açılır", async () => {
    const kullanici = await gucModunaGec();
    await kullanici.click(screen.getByRole("button", { name: /^Modül engine/ }));
    const panel = screen.getByRole("complementary", { name: "Düğüm detayı" });
    expect(within(panel).getByText("Kim dokunuyor")).toBeInTheDocument();
    // engine'e fatih (5) ve enes (2) dokundu — ikisi de listede
    expect(within(panel).getByText("fatih")).toBeInTheDocument();
    expect(within(panel).getByText("enes")).toBeInTheDocument();
  });

  it("üstüne gelince İLGİSİZ düğümler %30'a söner (#130 kabul kriteri)", async () => {
    // MUTASYON KİLİDİ: `belirginlik`teki SONUK dönüşünü 1 yap -> bu test kırılır.
    const kullanici = await gucModunaGec();
    await kullanici.hover(screen.getByRole("button", { name: /^Modül engine/ }));
    // fatih engine'e dokunuyor → komşu → tam belirgin
    expect(screen.getByRole("button", { name: /^Aktör fatih/ })).toHaveAttribute(
      "opacity",
      "1",
    );
    // frontend engine'in komşusu DEĞİL → soluk
    expect(screen.getByRole("button", { name: /^Modül frontend/ })).toHaveAttribute(
      "opacity",
      "0.3",
    );
  });

  it("aynı ADA sahip aktör ve modül birbirine karışmaz (ad alanı ayrımı)", async () => {
    /* `engine` adlı bir GitHub kullanıcısı ile `engine` modülü aynı anda var
       olabilir. Komşuluk ham id ile tutulsaydı ikisi TEK düğüme çökerdi ve
       aktör-engine'in üstüne gelmek modül-engine'i de yakardı.
       MUTASYON KİLİDİ: `dugumAnahtari` çağrılarını ham `id`ye çevir -> bu
       test kırılır (modül-engine soluk yerine belirgin kalır). */
    mockUseGraph.mockReturnValue({
      ...dolu,
      data: {
        window_days: 14,
        nodes: [
          { id: "engine", type: "actor", weight: 2, actor_verified: true },
          { id: "fatih", type: "actor", weight: 3, actor_verified: true },
          { id: "engine", type: "module", weight: 3, actor_verified: true },
          { id: "frontend", type: "module", weight: 2, actor_verified: true },
        ],
        edges: [
          {
            actor: "engine",
            module: "frontend",
            count: 2,
            last_ts: "2026-07-20T09:00:00Z",
            is_active_declared: false,
          },
          {
            actor: "fatih",
            module: "engine",
            count: 3,
            last_ts: "2026-07-20T09:00:00Z",
            is_active_declared: false,
          },
        ],
      },
    });
    const kullanici = await gucModunaGec();
    // AKTÖR engine'in tek komşusu frontend; MODÜL engine ilgisiz → sönmeli.
    await kullanici.hover(screen.getByRole("button", { name: /^Aktör engine/ }));
    expect(screen.getByRole("button", { name: /^Modül frontend/ })).toHaveAttribute(
      "opacity",
      "1",
    );
    expect(screen.getByRole("button", { name: /^Modül engine/ })).toHaveAttribute(
      "opacity",
      "0.3",
    );
  });
});

describe("GraphPage — git ağacı şeridi (#130 mod d)", () => {
  const GUN = 86_400_000;

  /** Olaylar ŞİMDİYE göre kurulur: sabit tarih yazsaydık test, pencere
      filtresi yüzünden takvim ilerledikçe sessizce çürürdü. */
  function olaylariKur() {
    const t = (gunOnce: number) => new Date(Date.now() - gunOnce * GUN).toISOString();
    return [
      {
        id: "e1",
        type: "commit" as const,
        actor: "fatih",
        branch: "main",
        files: ["src/ortak.py"],
        ts: t(5),
        ref: "aaa111",
        actor_verified: true,
      },
      {
        id: "e2",
        type: "commit" as const,
        actor: "enes",
        branch: "T-9-radar",
        files: ["src/ortak.py", "src/yalniz.py"],
        ts: t(3),
        ref: "bbb222",
        actor_verified: true,
      },
      {
        id: "e3",
        type: "pr" as const,
        actor: "enes",
        branch: "T-9-radar",
        files: ["src/yalniz.py"],
        ts: t(2),
        ref: "#9",
        actor_verified: true,
      },
    ];
  }

  async function agacModunaGec(olaylar = olaylariKur()) {
    mockUseEvents.mockReturnValue({
      data: { events: olaylar, latest_ts: null },
      error: null,
      isLoading: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
    });
    const kullanici = userEvent.setup();
    render(<GraphPage />, { wrapper: router });
    await kullanici.click(screen.getByRole("tab", { name: "Git ağacı" }));
    return kullanici;
  }

  it("'commit ağacı DEĞİL' sınırı EKRANDA yazılı (kod yorumunda değil)", async () => {
    /* En önemli kilit. parent_sha olmadan gerçek DAG çizilemez; kullanıcı
       çizilen her oka İNANIR. Sınırı yalnız kod yorumuna yazmak, kullanıcı
       için hiç yazmamakla aynı şey.
       MUTASYON KİLİDİ: uyarı paragrafını sil -> bu test kırılır. */
    await agacModunaGec();
    expect(screen.getByText(/commit ağacı \(DAG\) değil/i)).toBeInTheDocument();
    expect(screen.getByText(/parent_sha/)).toBeInTheDocument();
  });

  it("her dal kendi şeridine düşer, main üstte", async () => {
    await agacModunaGec();
    expect(screen.getByText("main")).toBeInTheDocument();
    expect(screen.getByText("T-9-radar")).toBeInTheDocument();
  });

  it("iki dalda geçen dosya çakışma adayı işaretlenir, tek dalda geçen DEĞİL", async () => {
    await agacModunaGec();
    // e1 (main) ve e2 (T-9) ikisi de src/ortak.py'ye dokunuyor → ikisi de aday
    expect(
      screen.getByRole("button", { name: /main dalında commit.*başka dalda da dokunuldu/s }),
    ).toBeInTheDocument();
    // e3 yalnız src/yalniz.py'ye dokunuyor ve o dosya tek dalda → aday DEĞİL
    const pr = screen.getByRole("button", { name: /T-9-radar dalında PR/s });
    expect(pr.textContent).not.toMatch(/başka dalda da dokunuldu/);
  });

  it("çakışma adayına tıklayınca Radar çapraz-linki açılır (#130 kabul kriteri)", async () => {
    const kullanici = await agacModunaGec();
    await kullanici.click(
      screen.getByRole("button", { name: /main dalında commit/s }),
    );
    const panel = screen.getByRole("complementary", { name: "Olay detayı" });
    expect(within(panel).getByRole("link", { name: /Radar'da incele/ })).toHaveAttribute(
      "href",
      "/radar",
    );
    // Çakışan dosya panelde de işaretli
    expect(within(panel).getByText(/src\/ortak\.py/)).toBeInTheDocument();
  });

  it("tarihi okunamayan olay çizilmez ama SAYISI ekranda bildirilir", async () => {
    // Sessiz veri kaybı yok: çizilemeyen olay "hiç yokmuş" gibi gösterilmez.
    const olaylar = olaylariKur();
    await agacModunaGec([
      ...olaylar,
      { ...olaylar[0], id: "bozuk", ts: "bu-bir-tarih-degil" },
    ]);
    expect(screen.getByText(/tarihi okunamadığı için çizilmedi/)).toBeInTheDocument();
  });

  it("mod tercihi localStorage'da kalıcı (dört mod için de aynı kural)", async () => {
    await agacModunaGec();
    expect(window.localStorage.getItem(MOD_KEY)).toBe("agac");
  });
});
