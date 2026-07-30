/** T-309 (+#332) — AppLayout'un "Ayarlar" nav linki: sayfada GERÇEKTEN
 * gösterilecek bir şey olduğu KANITLANINCA görünür. İki kaynak var:
 * `GET /settings/saglayici` 200 (yerel kurulum) **ya da** `GET /settings/mcp`
 * 200 (MCP bağlanma reçetesi — hosted'da da döner, #332). İkisi de yoksa,
 * yükleniyorsa ya da hata verdiyse GÖSTERİLMEZ — görev brifi §3 "menüde ölü
 * bir Ayarlar bağlantısı bırakma". `repoGostergesi.test.tsx`'in kalıbı.
 *
 * MUTASYON KİLİTLERİ (görev brifi §Testler):
 *  - `ayarlar.data?.tur === "basarili"` kontrolünü kaldırıp linki HER ZAMAN
 *    basarsan → "iki uç da yoksa link GİZLENİR" testi kırılır
 *  - `|| mcp.data?.tur === "basarili"` dalını kaldırırsan (#332 öncesine dön)
 *    → "hosted'da MCP varsa link GÖRÜNÜR" testi kırılır; o dal olmadan hosted
 *    kullanıcı bağlanma reçetesine hiç ulaşamaz (uç 200 dönse bile)
 *  - anonim/hosted akışın (radar + demo repo etiketi) BOZULMADIĞINI da ayrıca
 *    kilitler — bu dosyanın asıl amacı SADECE nav linkiyse de mevcut akışın
 *    kazara kırılmadığını doğrular
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import AppLayout from "../src/components/AppLayout";

const mockUseAuth = vi.fn();
const mockUseRepolar = vi.fn();
const mockUseSaglayiciAyarlari = vi.fn();

vi.mock("../src/lib/useAuth", () => ({
  useAuth: () => mockUseAuth(),
  gorunenAd: (k: { handle: string | null; email: string | null }) => k.handle ?? k.email ?? "kullanıcı",
  useCikisYap: () => ({ cikisYap: vi.fn(), yukleniyor: false, hata: null }),
}));

vi.mock("../src/lib/useRepoSecici", () => ({
  useRepolar: (enabled: boolean) => mockUseRepolar(enabled),
}));

const mockUseMcpConfig = vi.fn();

vi.mock("../src/lib/useSettings", () => ({
  useSaglayiciAyarlari: () => mockUseSaglayiciAyarlari(),
  useMcpConfig: (enabled: boolean) => mockUseMcpConfig(enabled),
}));

function renderShell(path = "/radar") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="radar" element={<div>RADAR SAYFASI</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const anonimAuth = {
  enabled: true,
  emailEnabled: true,
  kullanici: null,
  isLoading: false,
  error: null,
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("AppLayout — 'Ayarlar' nav linki (MUTASYON KİLİDİ)", () => {
  it("yerel kurulumda (200/basarili) 'Ayarlar' linki görünür, /ayarlar'a gider", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    mockUseSaglayiciAyarlari.mockReturnValue({
      data: {
        tur: "basarili",
        mode: "local",
        saglayici: "gemini",
        anahtarlar: { gemini: null, groq: null },
        ollama_url: "http://localhost:11434",
      },
      isLoading: false,
    });
    renderShell();
    const link = screen.getByRole("link", { name: "Ayarlar" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/ayarlar");
  });

  it("İKİ uç da yoksa (tur:'yok') 'Ayarlar' linki GİZLİDİR", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    mockUseSaglayiciAyarlari.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    renderShell();
    expect(screen.queryByRole("link", { name: "Ayarlar" })).not.toBeInTheDocument();
    // Kalan 6 kalem AYNEN yerinde kalmalı — yeni link diğerlerini itmemeli.
    for (const label of ["Radar", "Board", "Scope", "Graf", "Activity", "Ask"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("hosted'da sağlayıcı ucu 404 olsa BİLE MCP reçetesi varsa link GÖRÜNÜR (#332)", () => {
    // Bu, #332'nin "son santim"i: uç 200 dönüyor ama menüde link yoksa hosted
    // kullanıcı bağlanma yolunu hiç göremez ("kodda var ≠ çalışıyor").
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    mockUseSaglayiciAyarlari.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    mockUseMcpConfig.mockReturnValue({
      data: { tur: "basarili", mod: "hosted", araclar: [], hosted_notu: "…" },
      isLoading: false,
    });
    renderShell();
    expect(screen.getByRole("link", { name: "Ayarlar" })).toBeInTheDocument();
  });

  it("henüz yükleniyorsa (data yok) 'Ayarlar' linki GİZLİDİR — emin olmadan gösterme", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    mockUseSaglayiciAyarlari.mockReturnValue({ data: undefined, isLoading: true });
    renderShell();
    expect(screen.queryByRole("link", { name: "Ayarlar" })).not.toBeInTheDocument();
  });

  it("beklenmeyen bir hata verirse 'Ayarlar' linki GİZLİDİR (fail-closed)", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    mockUseSaglayiciAyarlari.mockReturnValue({
      data: { tur: "beklenmeyen", mesaj: "500 patladı" },
      isLoading: false,
    });
    renderShell();
    expect(screen.queryByRole("link", { name: "Ayarlar" })).not.toBeInTheDocument();
  });

  it("anonim/hosted akış BOZULMAMALI — demo etiketi ve Radar erişimi AYNEN korunur", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    mockUseMcpConfig.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    mockUseSaglayiciAyarlari.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    renderShell();
    expect(screen.getByText("RADAR SAYFASI")).toBeInTheDocument();
    expect(screen.getByText("grup54/ensemble")).toBeInTheDocument();
  });
});
