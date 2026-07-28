/** #316 — Tasarım paritesi 1/4: ortak kabuk. Pencil (design/ensemble.pen) ile
 * canlı ürün karşılaştırıldı (2026-07-28); dört A-bulgusunun testleri burada:
 *   A1 logo (iç içe iki halka) · A2 sidebar ikonları · A3 künye (local/v.../
 *   source-available) · A4 topbar canlılık nabzı (CANLI · N sn önce).
 *
 * Mock şekli `tests/modRozeti.test.tsx`'ten alındı — aynı kabuğu render
 * ediyoruz, aynı bağımlılıkları karşılamak gerekiyor.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const saglikDurumu = vi.hoisted(() => ({
  data: undefined as unknown,
  error: null as unknown,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: 0,
}));

vi.mock("../src/lib/useSaglik", () => ({ useSaglik: () => saglikDurumu }));
vi.mock("../src/lib/useSettings", () => ({
  useSaglayiciAyarlari: () => ({ data: undefined, error: null, isLoading: false }),
}));
vi.mock("../src/lib/useAuth", () => ({
  useAuth: () => ({ kullanici: null, yukleniyor: false, emailEnabled: false, enabled: false }),
  gorunenAd: (k: { handle: string | null; email: string | null }) =>
    k.handle ?? k.email ?? "kullanıcı",
  useCikisYap: () => ({ cikisYap: vi.fn(), yukleniyor: false, hata: null }),
}));
vi.mock("../src/lib/useRepoSecici", () => ({
  useRepolar: () => ({ data: undefined, error: null, isLoading: false }),
}));

import AppLayout from "../src/components/AppLayout";
import pkg from "../package.json";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  Object.assign(saglikDurumu, {
    data: undefined,
    error: null,
    isLoading: false,
    isFetching: false,
    dataUpdatedAt: 0,
  });
});

describe("A1 — logo (iç içe iki halka)", () => {
  it("sidebar başlığında iki <circle>'lı bir SVG var, eski tek-nokta placeholder YOK", () => {
    // MUTASYON KİLİDİ: EnsembleLogo'yu eski `<span class="... rounded-full
    // bg-primary" />` noktasına geri çevir -> `circle` sayısı 0 olur, kırılır.
    const { container } = render(<AppLayout />, { wrapper });
    const logo = container.querySelector('[data-testid="ensemble-logo"]');
    expect(logo).not.toBeNull();
    expect(logo?.querySelectorAll("circle").length).toBe(2);
    // Eski placeholder (turuncu dolu tek nokta) kalıntısı kalmamalı.
    expect(container.querySelector("aside .bg-primary.rounded-full")).toBeNull();
  });
});

describe("A2 — sidebar ikonları", () => {
  it("altı nav linkinin HER BİRİNDE bir <svg> ikonu var", () => {
    // MUTASYON KİLİDİ: NAV dizisinden bir `Icon` alanını sil (örn. Board) ->
    // o linkin `querySelector('svg')` sonucu null olur, kırılır.
    render(<AppLayout />, { wrapper });
    for (const label of ["Radar", "Board", "Scope", "Graf", "Activity", "Ask"]) {
      const link = screen.getByText(label).closest("a");
      expect(link?.querySelector("svg")).not.toBeNull();
    }
  });
});

describe("A3 — sidebar künyesi", () => {
  it("'local · v<gerçek sürüm> · source-available' basar (package.json'dan, uydurma DEĞİL)", () => {
    // MUTASYON KİLİDİ: künye satırını sil YA DA sürümü "v0.1" gibi sabit bir
    // string'e geri çevir -> ikisi de kırılır (`pkg.version` GERÇEKTE "0.0.1",
    // sabit "v0.1" onunla eşleşmez).
    saglikDurumu.data = { status: "ok", mode: "local" };
    render(<AppLayout />, { wrapper });
    expect(screen.getByText(`local · v${pkg.version} · source-available`)).toBeInTheDocument();
  });

  it("mod bilgisi gelmeden derleme varsayılanına düşer (config.mode), uydurmaz", () => {
    saglikDurumu.data = undefined;
    render(<AppLayout />, { wrapper });
    expect(screen.getByText(/local · v[\d.]+ · source-available/)).toBeInTheDocument();
  });
});

describe("A4 — topbar canlılık nabzı", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("hiç başarılı /health yanıtı yokken 'CANLI' YAZMAZ — 'Bağlanıyor…' basar", () => {
    // MUTASYON KİLİDİ: dataUpdatedAt===0 kontrolünü kaldır, doğrudan 'CANLI'
    // bas -> bu test kırılır (sahte-canlılık, D-34).
    saglikDurumu.dataUpdatedAt = 0;
    saglikDurumu.error = null;
    render(<AppLayout />, { wrapper });
    expect(screen.getByText("Bağlanıyor…")).toBeInTheDocument();
    expect(screen.queryByText("CANLI")).not.toBeInTheDocument();
  });

  it("hiç başarılı yanıt yokken VE hata varsa 'Bağlantı yok' basar", () => {
    saglikDurumu.dataUpdatedAt = 0;
    saglikDurumu.error = new Error("network fail");
    render(<AppLayout />, { wrapper });
    expect(screen.getByText("Bağlantı yok")).toBeInTheDocument();
  });

  it("başarılı yanıt sonrası 'CANLI · N sn önce' basar ve saniye saniye İLERLER", () => {
    // MUTASYON KİLİDİ: useSimdi'yi sil / gecenSn'yi sabit 0 yap -> ikinci
    // expect (5 sn sonrası) ilkiyle AYNI kalır, kırılır.
    vi.useFakeTimers();
    const simdi = Date.now();
    vi.setSystemTime(simdi);
    saglikDurumu.dataUpdatedAt = simdi;
    saglikDurumu.error = null;

    render(<AppLayout />, { wrapper });
    expect(screen.getByText("CANLI")).toBeInTheDocument();
    expect(screen.getByText("· 0 sn önce")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByText("· 5 sn önce")).toBeInTheDocument();
  });
});
