/** Mod rozeti CANLI `/health`'ten okunmalı — Vite BUILD modundan değil.
 *
 * Ölçülen hata (2026-07-28): rozet `config.mode`'dan besleniyordu ve o değer
 * `import.meta.env.MODE === "production" ? "hosted" : "local"` idi. Masaüstü
 * paketi (#305) de üretim derlemesi taşır ama YERELDE çalışır — kullanıcı
 * kendi bilgisayarına kurduğu uygulamada "hosted" görürdü. Rozet bilmediği
 * bir şeyi iddia ediyordu.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const saglikDurumu = vi.hoisted(() => ({ data: undefined as unknown }));

vi.mock("../src/lib/useSaglik", () => ({ useSaglik: () => saglikDurumu }));
// Mock sekilleri `tests/ayarlarNavGorunurlugu.test.tsx`'ten alindi — ayni
// kabugu render ediyoruz, ayni bagimliliklari karsilamak gerekiyor.
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

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  saglikDurumu.data = undefined;
});

describe("mod rozeti", () => {
  it("sunucu 'local' derse ROZET 'local' gösterir (üretim derlemesi olsa bile)", async () => {
    // MUTASYON KİLİDİ: rozeti `config.mode`'a geri çevir -> bu test kırılır.
    // Masaüstü paketinin senaryosu tam bu: prod build + yerel sunucu.
    saglikDurumu.data = { status: "ok", mode: "local" };
    render(<AppLayout />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("local")).toBeTruthy();
    });
    expect(screen.queryByText("hosted")).toBeNull();
  });

  it("sunucu 'hosted' derse ROZET 'hosted' gösterir", async () => {
    saglikDurumu.data = { status: "ok", mode: "hosted" };
    render(<AppLayout />, { wrapper });
    await waitFor(() => {
      expect(screen.getByText("hosted")).toBeTruthy();
    });
  });

  it("cevap GELMEDEN uydurmaz — derleme varsayılanını gösterir", () => {
    // Boş bırakmak da uydurmak da yanlış olurdu; elimizdeki en iyi bilgi
    // derleme varsayılanı ve `title` bunun beklendiğini söylüyor.
    saglikDurumu.data = undefined;
    render(<AppLayout />, { wrapper });
    const rozet = screen.getByTitle(/mod bilgisi bekleniyor/i);
    expect(rozet.textContent).toBeTruthy();
  });
});
