/** T-294 (#297/#298) — RegisterPage (/kayit): email+parola üyeliğin kayıt uç
 * noktası. `useAuth`/`kayitOlIstegi` mock'lanır (gerçek fetch/api.POST YOK) —
 * sayfa mantığı (email_enabled gate'i, backend mesajı çevirisi, parola-tekrar
 * kontrolü) izole test edilir.
 *
 * MUTASYON KİLİTLERİ (görev brifi):
 *  - email_enabled=false iken form gizli (gate'i kaldır → ilk test kırılır)
 *  - 409 → backend'in mesajı basılır (case 409 dalını kaldır → üçüncü test kırılır)
 *  - parola tekrarı uyuşmazsa istek ATILMAZ (kontrolü kaldır → dördüncü test kırılır)
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import RegisterPage from "../src/pages/RegisterPage";

const mockUseAuth = vi.fn();
const mockKayitOl = vi.fn();

vi.mock("../src/lib/useAuth", () => ({
  useAuth: () => mockUseAuth(),
  useCikisYap: () => ({ cikisYap: vi.fn(), yukleniyor: false, hata: null }),
  gorunenAd: (k: { handle: string | null; email: string | null }) => k.handle ?? k.email ?? "kullanıcı",
  kayitOlIstegi: (email: string, password: string) => mockKayitOl(email, password),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/kayit"]}>
      <Routes>
        <Route path="/kayit" element={<RegisterPage />} />
        <Route path="/radar" element={<div>RADAR SAYFASI</div>} />
        <Route path="/login" element={<div>LOGIN SAYFASI</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const acikDurum = {
  enabled: false,
  emailEnabled: true,
  kullanici: null,
  isLoading: false,
  error: null,
};

async function formuDoldurGonder(
  user: ReturnType<typeof userEvent.setup>,
  { email = "a@b.com", parola = "sifre1234", tekrar = "sifre1234" } = {},
) {
  await user.type(screen.getByLabelText("E-posta"), email);
  await user.type(screen.getByLabelText("Parola"), parola);
  await user.type(screen.getByLabelText("Parola (tekrar)"), tekrar);
  await user.click(screen.getByRole("button", { name: /Kayıt ol|Kayıt oluşturuluyor/ }));
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("RegisterPage — email_enabled gate", () => {
  it("email_enabled=false iken form GİZLİ, dürüst 'yapılandırılmamış' mesajı basılır", () => {
    mockUseAuth.mockReturnValue({ ...acikDurum, emailEnabled: false });
    renderPage();
    expect(
      screen.getByText("E-posta ile üyelik bu kurulumda yapılandırılmamış."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("E-posta")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Kayıt ol" })).not.toBeInTheDocument();
  });

  it("email_enabled=true iken form GÖRÜNÜR + dürüstlük notu her zaman basılı", () => {
    mockUseAuth.mockReturnValue(acikDurum);
    renderPage();
    expect(screen.getByRole("button", { name: "Kayıt ol" })).toBeInTheDocument();
    expect(
      screen.getByText(/E-posta doğrulaması ve parola sıfırlama bu sürümde yok/),
    ).toBeInTheDocument();
    // "Şifremi unuttum" bu sürümde HİÇBİR yerde yok (çalışmıyor — D-57)
    expect(screen.queryByText(/şifremi unuttum/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/doğrulama e-postası gönderildi/i)).not.toBeInTheDocument();
  });
});

describe("RegisterPage — parola tekrar kontrolü (istek atmadan)", () => {
  it("parolalar UYUŞMAZSA istek ATILMAZ, inline hata basılır", async () => {
    mockUseAuth.mockReturnValue(acikDurum);
    const user = userEvent.setup();
    renderPage();
    await formuDoldurGonder(user, { tekrar: "farkli9999" });
    expect(screen.getByText("Parolalar eşleşmiyor.")).toBeInTheDocument();
    expect(mockKayitOl).not.toHaveBeenCalled();
  });

  it("parolalar EŞLEŞİRSE istek ATILIR ve başarıda /radar'a yönlendirir", async () => {
    mockUseAuth.mockReturnValue(acikDurum);
    mockKayitOl.mockResolvedValue({
      tur: "basarili",
      kullanici: { handle: null, email: "a@b.com", avatar_url: null },
    });
    const user = userEvent.setup();
    renderPage();
    await formuDoldurGonder(user);
    expect(mockKayitOl).toHaveBeenCalledWith("a@b.com", "sifre1234");
    await waitFor(() => expect(screen.getByText("RADAR SAYFASI")).toBeInTheDocument());
  });
});

describe("RegisterPage — backend hata çevirisi (uydurma yok, backend'in mesajı)", () => {
  it("409 → backend'in 'zaten bir hesap var' mesajı basılır", async () => {
    mockUseAuth.mockReturnValue(acikDurum);
    mockKayitOl.mockResolvedValue({
      tur: "email_kayitli",
      mesaj: "Bu e-posta ile zaten bir hesap var.",
    });
    const user = userEvent.setup();
    renderPage();
    await formuDoldurGonder(user);
    expect(await screen.findByText("Bu e-posta ile zaten bir hesap var.")).toBeInTheDocument();
  });

  it("422 → backend'in politika mesajı AYNEN basılır (kendi metni uydurulmaz)", async () => {
    mockUseAuth.mockReturnValue(acikDurum);
    mockKayitOl.mockResolvedValue({
      tur: "politika_ihlali",
      mesaj: "Parola en az 8 karakter olmalı.",
    });
    const user = userEvent.setup();
    renderPage();
    await formuDoldurGonder(user);
    expect(await screen.findByText("Parola en az 8 karakter olmalı.")).toBeInTheDocument();
  });

  it("429 → Retry-After saniyesi 'N saniye sonra tekrar deneyin' biçiminde basılır", async () => {
    mockUseAuth.mockReturnValue(acikDurum);
    mockKayitOl.mockResolvedValue({
      tur: "cok_fazla_deneme",
      mesaj: "Çok fazla deneme yapıldı — birazdan tekrar deneyin.",
      saniye: 12,
    });
    const user = userEvent.setup();
    renderPage();
    await formuDoldurGonder(user);
    expect(await screen.findByText("12 saniye sonra tekrar deneyin.")).toBeInTheDocument();
  });

  it("429 → Retry-After başlığı okunamazsa backend'in genel mesajına düşülür", async () => {
    mockUseAuth.mockReturnValue(acikDurum);
    mockKayitOl.mockResolvedValue({
      tur: "cok_fazla_deneme",
      mesaj: "Çok fazla deneme yapıldı — birazdan tekrar deneyin.",
      saniye: null,
    });
    const user = userEvent.setup();
    renderPage();
    await formuDoldurGonder(user);
    expect(
      await screen.findByText("Çok fazla deneme yapıldı — birazdan tekrar deneyin."),
    ).toBeInTheDocument();
  });
});

describe("RegisterPage — zaten giriş yapılmış", () => {
  it("kullanici doluysa form yerine 'zaten giriş yapılmış' görünümü basılır", () => {
    mockUseAuth.mockReturnValue({
      ...acikDurum,
      kullanici: { handle: null, email: "gecici@b.com", avatar_url: null },
    });
    renderPage();
    expect(screen.getByText("gecici@b.com")).toBeInTheDocument();
    expect(screen.queryByLabelText("E-posta")).not.toBeInTheDocument();
  });
});
