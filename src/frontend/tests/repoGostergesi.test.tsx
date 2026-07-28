/** #79/T-79 — AppLayout'un "hangi repoya bakıyorum" göstergesi (AktifRepoGostergesi)
 * + anonim akışın BOZULMAMASI (D-23'ün korunan vaadi).
 *
 * MUTASYON KİLİTLERİ (görev brifi):
 *  - anonim ziyaretçi hâlâ demo reposunu (ve /radar'ı) GİRİŞSİZ görüyor —
 *    yanlışlıkla bir auth kapısı eklenirse BU TEST kırılır (regresyon buradan gelir)
 *  - anonimken useRepolar `enabled=false` ile çağrılır (boşuna istek atma) —
 *    `kullanici !== null` kontrolünü kaldır → bu test kırılır
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import AppLayout from "../src/components/AppLayout";

const mockUseAuth = vi.fn();
const mockUseRepolar = vi.fn();

vi.mock("../src/lib/useAuth", () => ({
  useAuth: () => mockUseAuth(),
  gorunenAd: (k: { handle: string | null; email: string | null }) => k.handle ?? k.email ?? "kullanıcı",
  useCikisYap: () => ({ cikisYap: vi.fn(), yukleniyor: false, hata: null }),
}));

vi.mock("../src/lib/useRepoSecici", () => ({
  useRepolar: (enabled: boolean) => mockUseRepolar(enabled),
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

describe("AktifRepoGostergesi — anonim akış BOZULMAMALI (regresyon kilidi)", () => {
  it("anonim ziyaretçi GİRİŞSİZ /radar'ı görmeye devam eder, demo etiketi basılır", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    renderShell();
    expect(screen.getByText("RADAR SAYFASI")).toBeInTheDocument();
    expect(screen.getByText("grup54/ensemble")).toBeInTheDocument();
  });

  it("anonimken demo etiketi bir LİNK değil (seçici oturum ister, gizli-CTA yok)", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    renderShell();
    expect(screen.queryByRole("link", { name: "grup54/ensemble" })).not.toBeInTheDocument();
    expect(screen.getByText("grup54/ensemble")).toBeInTheDocument();
  });

  it("anonimken useRepolar enabled=false ile çağrılır — boşuna istek atılmaz", () => {
    mockUseAuth.mockReturnValue(anonimAuth);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    renderShell();
    expect(mockUseRepolar).toHaveBeenCalledWith(false);
  });

  it("auth hiç yapılandırılmamışsa (enabled=false, emailEnabled=false) da demo etiketi AYNEN kalır", () => {
    mockUseAuth.mockReturnValue({
      enabled: false,
      emailEnabled: false,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: false });
    renderShell();
    expect(screen.getByText("grup54/ensemble")).toBeInTheDocument();
  });
});

describe("AktifRepoGostergesi — girişli kullanıcı", () => {
  const girisli = {
    enabled: false,
    emailEnabled: true,
    kullanici: { handle: null, email: "a@b.com", avatar_url: null },
    isLoading: false,
    error: null,
  };

  it("girişliyken useRepolar enabled=true ile çağrılır", () => {
    mockUseAuth.mockReturnValue(girisli);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: true });
    renderShell();
    expect(mockUseRepolar).toHaveBeenCalledWith(true);
  });

  it("aktif repo seçilmişse onun adı /repolar'a giden bir link olarak basılır", () => {
    mockUseAuth.mockReturnValue(girisli);
    mockUseRepolar.mockReturnValue({
      data: {
        tur: "basarili",
        selected: ["FatihErenCetin/deneme-repo"],
        active: "FatihErenCetin/deneme-repo",
        demo: "grup54/ensemble",
      },
      isLoading: false,
    });
    renderShell();
    const link = screen.getByRole("link", { name: "FatihErenCetin/deneme-repo" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/repolar");
  });

  it("aktif repo seçilmemişse (active=null) demo reposunun adı gösterilir", () => {
    mockUseAuth.mockReturnValue(girisli);
    mockUseRepolar.mockReturnValue({
      data: { tur: "basarili", selected: [], active: null, demo: "grup54/ensemble" },
      isLoading: false,
    });
    renderShell();
    expect(screen.getByRole("link", { name: "grup54/ensemble" })).toHaveAttribute(
      "href",
      "/repolar",
    );
  });

  it("repo verisi henüz gelmediyse/hata verdiyse sessizce sabit etikete düşer (gürültü yok)", () => {
    mockUseAuth.mockReturnValue(girisli);
    mockUseRepolar.mockReturnValue({ data: undefined, isLoading: true });
    renderShell();
    expect(screen.getByRole("link", { name: "grup54/ensemble" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
