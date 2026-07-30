/** T-294 (#297/#298) — LoginPage (/login): GitHub OAuth + email/parola
 * girişinin YAN YANA, BİRBİRİNDEN BAĞIMSIZ gate'lenmesi + 401'de backend'in
 * GENEL hatası (kullanıcı varlığı sızdırmaz). `useAuth`/`girisYapIstegi`
 * mock'lanır — gerçek fetch/api.POST YOK.
 *
 * MUTASYON KİLİTLERİ (görev brifi):
 *  - 401 → GENEL mesaj basılır, "kayıtlı değil" gibi bir AYRIM asla üretilmez
 *  - iki kapı birbirinden bağımsız (dört kombinasyon da doğru render eder)
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import LoginPage from "../src/pages/LoginPage";

const mockUseAuth = vi.fn();
const mockGirisYap = vi.fn();

vi.mock("../src/lib/useAuth", () => ({
  useAuth: () => mockUseAuth(),
  useCikisYap: () => ({ cikisYap: vi.fn(), yukleniyor: false, hata: null }),
  gorunenAd: (k: { handle: string | null; email: string | null }) => k.handle ?? k.email ?? "kullanıcı",
  girisYapIstegi: (email: string, password: string) => mockGirisYap(email, password),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/radar" element={<div>RADAR SAYFASI</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("LoginPage — iki bağımsız kapı", () => {
  it("ikisi de kapalı: ne GitHub butonu ne email formu var, dürüst mesaj basılır", () => {
    mockUseAuth.mockReturnValue({
      enabled: false,
      emailEnabled: false,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.getByText("Giriş bu kurulumda yapılandırılmamış.")).toBeInTheDocument();
    expect(screen.queryByText("GitHub ile devam et")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("E-posta")).not.toBeInTheDocument();
  });

  it("yalnız GitHub açık: email formu YOK", () => {
    mockUseAuth.mockReturnValue({
      enabled: true,
      emailEnabled: false,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.getByText("GitHub ile devam et")).toBeInTheDocument();
    expect(screen.queryByLabelText("E-posta")).not.toBeInTheDocument();
  });

  it("yalnız email açık: GitHub butonu YOK", () => {
    mockUseAuth.mockReturnValue({
      enabled: false,
      emailEnabled: true,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.queryByText("GitHub ile devam et")).not.toBeInTheDocument();
    expect(screen.getByLabelText("E-posta")).toBeInTheDocument();
  });

  it("ikisi de açık: ikisi de görünür (aralarında ayraç)", () => {
    mockUseAuth.mockReturnValue({
      enabled: true,
      emailEnabled: true,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.getByText("GitHub ile devam et")).toBeInTheDocument();
    expect(screen.getByLabelText("E-posta")).toBeInTheDocument();
  });
});

describe("LoginPage — email girişi", () => {
  const acikSadeceEmail = {
    enabled: false,
    emailEnabled: true,
    kullanici: null,
    isLoading: false,
    error: null,
  };

  it("401 → backend'in GENEL mesajı basılır; 'kayıtlı değil' gibi bir ayrım İCAT EDİLMEZ", async () => {
    mockUseAuth.mockReturnValue(acikSadeceEmail);
    mockGirisYap.mockResolvedValue({
      tur: "gecersiz_giris",
      mesaj: "E-posta ya da parola hatalı.",
    });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("E-posta"), "yok@b.com");
    await user.type(screen.getByLabelText("Parola"), "yanlisparola");
    await user.click(screen.getByRole("button", { name: "E-posta ile giriş yap" }));
    expect(await screen.findByText("E-posta ya da parola hatalı.")).toBeInTheDocument();
    expect(screen.queryByText(/kayıtlı değil/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/bulunamadı/i)).not.toBeInTheDocument();
  });

  it("başarılı girişte /radar'a yönlendirir (iyimser state YOK, gerçek sayfa geçişi)", async () => {
    mockUseAuth.mockReturnValue(acikSadeceEmail);
    mockGirisYap.mockResolvedValue({
      tur: "basarili",
      kullanici: { handle: null, email: "a@b.com", avatar_url: null },
    });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("E-posta"), "a@b.com");
    await user.type(screen.getByLabelText("Parola"), "dogruparola");
    await user.click(screen.getByRole("button", { name: "E-posta ile giriş yap" }));
    expect(mockGirisYap).toHaveBeenCalledWith("a@b.com", "dogruparola");
    await waitFor(() => expect(screen.getByText("RADAR SAYFASI")).toBeInTheDocument());
  });

  it("429 → Retry-After saniyesi gösterilir", async () => {
    mockUseAuth.mockReturnValue(acikSadeceEmail);
    mockGirisYap.mockResolvedValue({
      tur: "cok_fazla_deneme",
      mesaj: "Çok fazla deneme yapıldı — birazdan tekrar deneyin.",
      saniye: 7,
    });
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText("E-posta"), "a@b.com");
    await user.type(screen.getByLabelText("Parola"), "x");
    await user.click(screen.getByRole("button", { name: "E-posta ile giriş yap" }));
    expect(await screen.findByText("7 saniye sonra tekrar deneyin.")).toBeInTheDocument();
  });
});

describe("LoginPage — girişli görünüm (handle/email fallback)", () => {
  it("handle YOKSA email gösterilir (gorunenAd fallback — email-only hesap)", () => {
    mockUseAuth.mockReturnValue({
      enabled: false,
      emailEnabled: true,
      kullanici: { handle: null, email: "a@b.com", avatar_url: null },
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.getByText("a@b.com")).toBeInTheDocument();
    expect(screen.getByText("Çıkış yap")).toBeInTheDocument();
  });

  it("401 hook hatası DEĞİL, isLoading/error state'i sessizce ele alınır (anonim = normal)", () => {
    mockUseAuth.mockReturnValue({
      enabled: true,
      emailEnabled: false,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    renderPage();
    // Anonim + enabled=true → giriş seçenekleri gösterilir, hata kutusu YOK
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("GitHub ile devam et")).toBeInTheDocument();
  });
});

describe("LoginPage — kayıt sayfasına yol (#335)", () => {
  it("email girişi açıkken 'Üye ol' linki /kayit'e gider", () => {
    // MUTASYON KİLİDİ: linki kaldır → kırılır. RegisterPage VAR ve /kayit'a
    // bağlı, ama bu sayfada ona giden hiç yol yoktu — yeni kullanıcı için
    // giriş ekranı çıkmaz sokaktı (ölçüm: grep -c kayit -> 0).
    mockUseAuth.mockReturnValue({
      enabled: false,
      emailEnabled: true,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    renderPage();

    const link = screen.getByTestId("kayit-linki");
    expect(link).toBeInTheDocument();
    expect(link.getAttribute("href")).toBe("/kayit");
  });

  it("email girişi kapalıyken kayıt linki BASILMAZ", () => {
    // Üyelik e-posta+parola akışıdır (#297); o kapı kapalıyken kullanıcıyı
    // çalışmayan bir kayıt sayfasına göndermek yanlış olurdu.
    mockUseAuth.mockReturnValue({
      enabled: true,
      emailEnabled: false,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    renderPage();

    expect(screen.queryByTestId("kayit-linki")).not.toBeInTheDocument();
  });
});
