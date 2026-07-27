/** T-294 (#298) — LandingPage: PO şikayeti "üye ol/giriş yap yok" için eklenen
 * iki CTA, `/auth/config`e göre KOŞULLU (`useAuth` mock'lanır). Demo CTA'sı
 * (#260 kabul kriteri: "backend kapalıyken bile açılır") bu sorgudan BAĞIMSIZ
 * her koşulda görünür kalmalı — auth sorgusu hata verse bile.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import LandingPage from "../src/pages/LandingPage";

const mockUseAuth = vi.fn();

vi.mock("../src/lib/useAuth", () => ({
  useAuth: () => mockUseAuth(),
  gorunenAd: (k: { handle: string | null; email: string | null }) => k.handle ?? k.email ?? "kullanıcı",
}));

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("LandingPage — auth CTA gate", () => {
  it("ikisi de kapalıysa: Üye ol/Giriş yap YOK, demo CTA'sı YİNE DE var", () => {
    mockUseAuth.mockReturnValue({
      enabled: false,
      emailEnabled: false,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    renderLanding();
    expect(screen.queryByText("Üye ol")).not.toBeInTheDocument();
    expect(screen.queryByText("Giriş yap")).not.toBeInTheDocument();
    expect(screen.getByText("Demoyu aç →")).toBeInTheDocument();
  });

  it("config sorgusu HATA verirse (backend kapalı): CTA'lar gizli, sayfa YİNE tam render olur (#260)", () => {
    mockUseAuth.mockReturnValue({
      enabled: false,
      emailEnabled: false,
      kullanici: null,
      isLoading: false,
      error: new Error("ağ hatası"),
    });
    renderLanding();
    expect(screen.queryByText("Giriş yap")).not.toBeInTheDocument();
    expect(screen.queryByText("Üye ol")).not.toBeInTheDocument();
    expect(screen.getByText("Demoyu aç →")).toBeInTheDocument();
    expect(screen.getByText("GitHub'da incele")).toBeInTheDocument();
  });

  it("isLoading iken de CTA'lar henüz basılmaz (yükleniyor durumunda dahi çalışmayan buton yok)", () => {
    mockUseAuth.mockReturnValue({
      enabled: true,
      emailEnabled: true,
      kullanici: null,
      isLoading: true,
      error: null,
    });
    renderLanding();
    expect(screen.queryByText("Giriş yap")).not.toBeInTheDocument();
    expect(screen.getByText("Demoyu aç →")).toBeInTheDocument();
  });

  it("email_enabled=true: Üye ol GÖRÜNÜR", () => {
    mockUseAuth.mockReturnValue({
      enabled: false,
      emailEnabled: true,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    renderLanding();
    expect(screen.getByText("Üye ol")).toBeInTheDocument();
    expect(screen.getByText("Giriş yap")).toBeInTheDocument();
  });

  it("yalnız GitHub açık: Giriş yap var, Üye ol YOK", () => {
    mockUseAuth.mockReturnValue({
      enabled: true,
      emailEnabled: false,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    renderLanding();
    expect(screen.getByText("Giriş yap")).toBeInTheDocument();
    expect(screen.queryByText("Üye ol")).not.toBeInTheDocument();
  });

  it("giriş yapılmışsa: 'Giriş yap' yerine görünen ad basılır", () => {
    mockUseAuth.mockReturnValue({
      enabled: false,
      emailEnabled: true,
      kullanici: { handle: null, email: "a@b.com", avatar_url: null },
      isLoading: false,
      error: null,
    });
    renderLanding();
    expect(screen.getByText(/a@b.com olarak giriş yaptın/)).toBeInTheDocument();
    expect(screen.queryByText("Giriş yap")).not.toBeInTheDocument();
  });
});
