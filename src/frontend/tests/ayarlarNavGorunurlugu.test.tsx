/** T-309 — AppLayout'un "Ayarlar" nav linki: YALNIZ `GET /settings/saglayici`
 * GERÇEKTEN 200 dönerse (yerel kurulum) görünür; 404 (hosted), yükleniyor ya
 * da beklenmeyen hata durumlarının HİÇBİRİNDE gösterilmez — görev brifi §3
 * "hosted'da bu sayfa GÖRÜNMESİN" + "menüde ölü bir Ayarlar bağlantısı
 * bırakma". `repoGostergesi.test.tsx`'in kalıbının AYNISI.
 *
 * MUTASYON KİLİTLERİ (görev brifi §Testler):
 *  - `ayarlar.data?.tur === "basarili"` kontrolünü kaldırıp linki HER ZAMAN
 *    basarsan → "hosted'da (404) link GİZLENİR" testi kırılır
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

vi.mock("../src/lib/useSettings", () => ({
  useSaglayiciAyarlari: () => mockUseSaglayiciAyarlari(),
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

  it("hosted'da (404 → tur:'yok') 'Ayarlar' linki GİZLİDİR", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    mockUseSaglayiciAyarlari.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    renderShell();
    expect(screen.queryByRole("link", { name: "Ayarlar" })).not.toBeInTheDocument();
    // Kalan 6 kalem AYNEN yerinde kalmalı — yeni link diğerlerini itmemeli.
    for (const label of ["Radar", "Board", "Scope", "Graf", "Activity", "Ask"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("henüz yükleniyorsa (data yok) 'Ayarlar' linki GİZLİDİR — emin olmadan gösterme", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    mockUseSaglayiciAyarlari.mockReturnValue({ data: undefined, isLoading: true });
    renderShell();
    expect(screen.queryByRole("link", { name: "Ayarlar" })).not.toBeInTheDocument();
  });

  it("beklenmeyen bir hata verirse 'Ayarlar' linki GİZLİDİR (fail-closed)", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
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
    mockUseSaglayiciAyarlari.mockReturnValue({ data: { tur: "yok" }, isLoading: false });
    renderShell();
    expect(screen.getByText("RADAR SAYFASI")).toBeInTheDocument();
    expect(screen.getByText("grup54/ensemble")).toBeInTheDocument();
  });
});
