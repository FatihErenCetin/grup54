/** #79'un kalan dilimi (T-79) — RepoSeciciPage (/repolar): kurulum listesi +
 * izlenen/aktif repo seçimi. `useAuth`/`useKurulumlar`/`useRepolar`/
 * `kurulumUrlIstegi`/`repolariGuncelle` MOCK'lanır (gerçek fetch/api YOK) —
 * sayfa mantığı (giriş yönlendirmesi, boş-kurulum dürüstlüğü, 403/503 mesaj
 * geçirme, anonim akışın BOZULMAMASI) izole test edilir.
 *
 * MUTASYON KİLİTLERİ (görev brifi):
 *  - kullanici===null iken /login'e yönlendirme dalını kaldır → ilk test kırılır
 *  - installations boşsa "hata" değil "App'i kur" dalı basılsın → ikinci test kırılır
 *  - 403 dalını kaldır (default'a düşsün) → backend mesajı testi kırılır
 *  - AppLayout'un anonim ziyaretçi için sabit demo etiketini koruduğu ayrı test
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import RepoSeciciPage from "../src/pages/RepoSeciciPage";

const mockUseAuth = vi.fn();
const mockUseKurulumlar = vi.fn();
const mockUseRepolar = vi.fn();
const mockKurulumUrlIstegi = vi.fn();
const mockRepolariGuncelle = vi.fn();

vi.mock("../src/lib/useAuth", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../src/lib/useRepoSecici", () => ({
  useKurulumlar: () => mockUseKurulumlar(),
  useRepolar: () => mockUseRepolar(),
  kurulumUrlIstegi: () => mockKurulumUrlIstegi(),
  repolariGuncelle: (repos: string[], active: string | null) =>
    mockRepolariGuncelle(repos, active),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/repolar"]}>
      <Routes>
        <Route path="/repolar" element={<RepoSeciciPage />} />
        <Route path="/login" element={<div>LOGIN SAYFASI</div>} />
        <Route path="/radar" element={<div>RADAR SAYFASI</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const girisliDurum = {
  enabled: false,
  emailEnabled: true,
  kullanici: { handle: null, email: "a@b.com", avatar_url: null },
  isLoading: false,
  error: null,
};

const kurulumYok = { data: { tur: "basarili", installations: [] }, isLoading: false };
const repolarBos = {
  data: { tur: "basarili", selected: [], active: null, demo: "grup54/ensemble" },
  isLoading: false,
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("RepoSeciciPage — giriş yönlendirmesi (MUTASYON KİLİDİ)", () => {
  it("kullanici===null iken /login'e yönlendirir", () => {
    mockUseAuth.mockReturnValue({
      enabled: false,
      emailEnabled: true,
      kullanici: null,
      isLoading: false,
      error: null,
    });
    mockUseKurulumlar.mockReturnValue(kurulumYok);
    mockUseRepolar.mockReturnValue(repolarBos);
    renderPage();
    expect(screen.getByText("LOGIN SAYFASI")).toBeInTheDocument();
    expect(screen.queryByText("Repo seçici")).not.toBeInTheDocument();
  });

  it("useAuth yükleniyorsa iskelet basar, yönlendirmez", () => {
    mockUseAuth.mockReturnValue({ ...girisliDurum, isLoading: true, kullanici: null });
    mockUseKurulumlar.mockReturnValue(kurulumYok);
    mockUseRepolar.mockReturnValue(repolarBos);
    renderPage();
    expect(screen.getByLabelText("Repo seçici yükleniyor")).toBeInTheDocument();
    expect(screen.queryByText("LOGIN SAYFASI")).not.toBeInTheDocument();
  });

  it("useAuth gerçek hata verirse HataDurumu basar (401 ile karıştırılmaz)", () => {
    mockUseAuth.mockReturnValue({
      ...girisliDurum,
      kullanici: null,
      error: new Error("patladı"),
    });
    mockUseKurulumlar.mockReturnValue(kurulumYok);
    mockUseRepolar.mockReturnValue(repolarBos);
    renderPage();
    expect(screen.getByText("Giriş durumu alınamıyor")).toBeInTheDocument();
  });

  it("installations/repos ORTASINDA 401 gelirse (oturum sona ermiş) yine /login'e gider", () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue({ data: { tur: "giris_gerekli" }, isLoading: false });
    mockUseRepolar.mockReturnValue(repolarBos);
    renderPage();
    expect(screen.getByText("LOGIN SAYFASI")).toBeInTheDocument();
  });
});

describe("RepoSeciciPage — hiç kurulum yok (dürüst boş durum, MUTASYON KİLİDİ)", () => {
  it("installations boşsa HATA değil 'App'i kur' eylemi basılır", () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue(kurulumYok);
    mockUseRepolar.mockReturnValue(repolarBos);
    renderPage();
    expect(screen.getByText("Henüz bir GitHub App kurulumun yok")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "GitHub App'i kur" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("'App'i kur' tıklanınca kurulumUrlIstegi çağrılır ve dönen url'e yönlendirir", async () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue(kurulumYok);
    mockUseRepolar.mockReturnValue(repolarBos);
    mockKurulumUrlIstegi.mockResolvedValue({
      tur: "basarili",
      url: "https://github.com/apps/ensemble-test/installations/new",
    });
    const originalLocation = window.location;
    // jsdom'da location'a doğrudan atama çalışmayabilir — writable bir stub.
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, href: "" },
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: "GitHub App'i kur" }));
    expect(mockKurulumUrlIstegi).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(window.location.href).toBe(
        "https://github.com/apps/ensemble-test/installations/new",
      ),
    );
    Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
  });

  it("kurulum adresi 503 dönerse backend'in mesajı AYNEN basılır", async () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue(kurulumYok);
    mockUseRepolar.mockReturnValue(repolarBos);
    mockKurulumUrlIstegi.mockResolvedValue({
      tur: "kapali",
      mesaj: "GitHub App kurulum akışı bu kurulumda yapılandırılmamış.",
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: "GitHub App'i kur" }));
    expect(
      await screen.findByText("GitHub App kurulum akışı bu kurulumda yapılandırılmamış."),
    ).toBeInTheDocument();
  });
});

describe("RepoSeciciPage — kurulumlar/repo uçları 503/beklenmeyen (uydurma yok)", () => {
  it("kurulumlar 503 (App hiç yapılandırılmamış) → dürüst mesaj, hata KUTUSU değil", () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue({
      data: { tur: "kapali", mesaj: "GitHub App entegrasyonu bu kurulumda yapılandırılmamış." },
      isLoading: false,
    });
    mockUseRepolar.mockReturnValue(repolarBos);
    renderPage();
    expect(
      screen.getByText("GitHub App entegrasyonu bu kurulumda yapılandırılmamış."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("kurulumlar beklenmeyen hata verirse HataDurumu basılır", () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue({
      data: { tur: "beklenmeyen", mesaj: "500 patladı" },
      isLoading: false,
    });
    mockUseRepolar.mockReturnValue(repolarBos);
    renderPage();
    expect(screen.getByText("Kurulumlar alınamıyor")).toBeInTheDocument();
  });

  it("repolar beklenmeyen hata verirse HataDurumu basılır", () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue(kurulumYok);
    mockUseRepolar.mockReturnValue({
      data: { tur: "beklenmeyen", mesaj: "500 patladı" },
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("Repo bilgisi alınamıyor")).toBeInTheDocument();
  });
});

describe("RepoSeciciPage — repo seçimi + kaydetme", () => {
  const kurulumluDurum = {
    data: {
      tur: "basarili",
      installations: [
        {
          installation_id: "1",
          account_login: "FatihErenCetin",
          repos: [
            { full_name: "FatihErenCetin/deneme-repo", private: false },
            { full_name: "FatihErenCetin/ozel-repo", private: true },
          ],
        },
      ],
    },
    isLoading: false,
  };

  it("kurulum + repo listesi render olur, dürüstlük notu HER ZAMAN görünür", () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue(kurulumluDurum);
    mockUseRepolar.mockReturnValue(repolarBos);
    renderPage();
    expect(screen.getByText("FatihErenCetin/deneme-repo")).toBeInTheDocument();
    expect(screen.getByText("FatihErenCetin/ozel-repo")).toBeInTheDocument();
    // Dürüstlük notu — scope/presence karıştırılmasın (görev brifi §DÜRÜSTLÜK)
    expect(
      screen.getByText("Kendi reponu seçtiğinde bilmen gerekenler"),
    ).toBeInTheDocument();
    expect(screen.getByText(/yapılandırılmamış" bir hata gösterecek/)).toBeInTheDocument();
  });

  it("bir repo seçilip Kaydet'e basılınca repolariGuncelle DOĞRU argümanlarla çağrılır", async () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue(kurulumluDurum);
    mockUseRepolar.mockReturnValue(repolarBos);
    mockRepolariGuncelle.mockResolvedValue({
      tur: "basarili",
      selected: ["FatihErenCetin/deneme-repo"],
      active: "FatihErenCetin/deneme-repo",
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByLabelText("FatihErenCetin/deneme-repo"));
    // Seçilen repo şimdi "aktif" radio'suyla işaretlenebilir olmalı.
    const aktifRadyolar = screen.getAllByRole("radio", { name: "aktif" });
    await user.click(aktifRadyolar[0]);
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    expect(mockRepolariGuncelle).toHaveBeenCalledWith(
      ["FatihErenCetin/deneme-repo"],
      "FatihErenCetin/deneme-repo",
    );
    expect(
      await screen.findByText(
        "Kaydedildi — artık FatihErenCetin/deneme-repo reposuna bakıyorsun.",
      ),
    ).toBeInTheDocument();
  });

  it("seçim kaldırılırsa (uncheck) o repo aktifken bile aktiflik de düşer", async () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue(kurulumluDurum);
    mockUseRepolar.mockReturnValue({
      data: {
        tur: "basarili",
        selected: ["FatihErenCetin/deneme-repo"],
        active: "FatihErenCetin/deneme-repo",
        demo: "grup54/ensemble",
      },
      isLoading: false,
    });
    mockRepolariGuncelle.mockResolvedValue({ tur: "basarili", selected: [], active: null });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByLabelText("FatihErenCetin/deneme-repo")); // uncheck
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    expect(mockRepolariGuncelle).toHaveBeenCalledWith([], null);
  });

  it("Kaydet 403 dönerse backend'in mesajı AYNEN basılır (MUTASYON KİLİDİ: case 403'ü kaldır)", async () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue(kurulumluDurum);
    mockUseRepolar.mockReturnValue(repolarBos);
    mockRepolariGuncelle.mockResolvedValue({
      tur: "izinsiz",
      mesaj: "Şu repolara erişiminiz yok (kurulumlarınızda değil): ['x/y']",
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByLabelText("FatihErenCetin/deneme-repo"));
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(
      await screen.findByText("Şu repolara erişiminiz yok (kurulumlarınızda değil): ['x/y']"),
    ).toBeInTheDocument();
  });

  it("Kaydet beklenmeyen bir hata verirse dürüst genel mesaj basılır", async () => {
    mockUseAuth.mockReturnValue(girisliDurum);
    mockUseKurulumlar.mockReturnValue(kurulumluDurum);
    mockUseRepolar.mockReturnValue(repolarBos);
    mockRepolariGuncelle.mockResolvedValue({
      tur: "beklenmeyen",
      mesaj: "Kaydedilemedi — az sonra tekrar dene.",
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByLabelText("FatihErenCetin/deneme-repo"));
    await user.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(await screen.findByText("Kaydedilemedi — az sonra tekrar dene.")).toBeInTheDocument();
  });
});
