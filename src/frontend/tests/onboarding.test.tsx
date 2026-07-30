/** #340 — OnboardingPage (/onboarding): üç giriş modu + K6 insan onayı +
 * degraded beyanı. `useOnboarding` MOCK'lanır (gerçek fetch YOK) —
 * `ayarlar.test.tsx` kalıbının aynısı.
 *
 * MUTASYON KİLİTLERİ:
 *  - Onay düğmesindeki `disabled={!onaylandi || !yazmaMumkun}` koşulundan
 *    `!onaylandi`'yı kaldır -> "onay kutusu işaretlenmeden yazma isteği
 *    atılmaz" testi kırılır (K6 istemci katmanı).
 *  - `yaz()` içindeki `if (!onaylandi ...) return` erken çıkışını kaldır ->
 *    aynı test kırılır (düğme devre dışıyken bile fonksiyon çağrılabilir).
 *  - `DegradedBlogu`'nu koşulsuz gizlersen -> "sağlayıcı düşünce beyan edilir"
 *    testi kırılır.
 *  - `eksik` rozetini kaldırıp alanı AI'ya doldurtursan -> "eksik alan
 *    uydurulmaz, işaretlenir" testi kırılır.
 *  - `!yazmaMumkun` uyarısını kaldırırsan -> "hosted'da yazma yok, sessizce
 *    değil AÇIKÇA söylenir" testi kırılır.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import OnboardingPage from "../src/pages/OnboardingPage";

const mockDurum = vi.fn();
const mockBriefUret = vi.fn();
const mockTaslakUret = vi.fn();
const mockPlanUret = vi.fn();
const mockUygula = vi.fn();
const mockSorulariGetir = vi.fn();

vi.mock("../src/lib/useOnboarding", async (importActual) => {
  const gercek = await importActual<typeof import("../src/lib/useOnboarding")>();
  return {
    ...gercek,
    useOnboardingDurum: () => mockDurum(),
    sorulariGetir: (g: unknown) => mockSorulariGetir(g),
    briefUret: (g: unknown) => mockBriefUret(g),
    taslakUret: (g: unknown) => mockTaslakUret(g),
    planUret: (g: unknown) => mockPlanUret(g),
    uygula: (g: unknown) => mockUygula(g),
  };
});

const DURUM_LOCAL = {
  tur: "basarili" as const,
  mode: "local" as const,
  yazma_mumkun: true,
  yazma_kok: "/Users/fatih/grup54",
  harness_var: false,
  saglayici: "gemini:gemini-2.5-flash",
  ai_kullanilabilir: true,
  maks_bosluk_turu: 2,
};

const DOLU_BRIEF = {
  urun_tek_cumle: "Ekipler için ortak proje beyni.",
  hedef_kullanicilar: ["geliştirici"],
  cekirdek_ozellikler: ["radar", "board", "scope"],
  kapsam_disi: ["mobil uygulama"],
  kisitlar: {
    ekip_buyuklugu: 4,
    yetkinlikler: [],
    sprint_sayisi: 2,
    sprint_gun: null,
    teknolojiler: [],
    entegrasyonlar: [],
  },
  basari_hedefi: "Canlı demoda çakışma radarda görünsün.",
  varsayimlar: [],
};

const TASLAK = {
  epicler: [{ id: "E1", baslik: "Radar", aciklama: "" }],
  storyler: [
    {
      id: "US1",
      epic_id: "E1",
      rol: "geliştirici",
      istek: "çakışmaları görmek",
      fayda: "erken fark edeyim",
      kabul_kriterleri: ["Radar'da kart görünür"],
      puan: 5,
      oncelik: 1,
      bagimliliklar: [],
    },
  ],
  dusenler: [],
};

function ekrandaCiz() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/onboarding"]}>
        <OnboardingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

/** Kendim-girerim modundan onay adımına kadar götürür (LLM'siz en kısa yol). */
async function onayAdiminaGit(kullanici: ReturnType<typeof userEvent.setup>) {
  await kullanici.click(screen.getAllByRole("button", { name: "Bu modla başla" })[2]);
  mockTaslakUret.mockResolvedValue({ tur: "basarili", taslak: TASLAK, degraded: null });
  await kullanici.click(screen.getByRole("button", { name: "Story taslağını üret" }));
  await screen.findByRole("button", { name: "Onaya geç (plansız)" });
  await kullanici.click(screen.getByRole("button", { name: "Onaya geç (plansız)" }));
  await screen.findByText("İnsan onayı (K6)");
}

describe("OnboardingPage — üç giriş modu", () => {
  it("üç modu da sunar", () => {
    mockDurum.mockReturnValue({ data: DURUM_LOCAL, isLoading: false });
    ekrandaCiz();
    expect(screen.getByText("Anlat")).toBeInTheDocument();
    expect(screen.getByText("Soru-cevap")).toBeInTheDocument();
    expect(screen.getByText("Kendim girerim")).toBeInTheDocument();
  });

  it("sağlayıcı yoksa 'Anlat' kapalı, diğer ikisi AÇIK kalır (kota gerçeği)", () => {
    mockDurum.mockReturnValue({
      data: { ...DURUM_LOCAL, ai_kullanilabilir: false, saglayici: "yok" },
      isLoading: false,
    });
    ekrandaCiz();
    const dugmeler = screen.getAllByRole("button");
    expect(screen.getByRole("button", { name: "Sağlayıcı yok" })).toBeDisabled();
    // Diğer iki mod hâlâ başlatılabilir.
    expect(dugmeler.filter((d) => d.textContent === "Bu modla başla")).toHaveLength(2);
  });

  it("soru-cevap modu alan başına tek soru gösterir", async () => {
    const kullanici = userEvent.setup();
    mockDurum.mockReturnValue({ data: DURUM_LOCAL, isLoading: false });
    mockSorulariGetir.mockResolvedValue({
      tur: "basarili",
      soruTuru: 1,
      tur_bitti: false,
      eksikler: [],
      sorular: [
        {
          alan: "urun_tek_cumle",
          metin: "Ürünü tek cümlede anlat",
          ipucu: "ipucu",
          coklu: false,
        },
      ],
    });
    ekrandaCiz();
    await kullanici.click(screen.getAllByRole("button", { name: "Bu modla başla" })[1]);
    expect(await screen.findByLabelText("Ürünü tek cümlede anlat")).toBeInTheDocument();
  });

  it("kendim-girerim modu hiç LLM çağırmadan brief formuna geçer", async () => {
    const kullanici = userEvent.setup();
    mockDurum.mockReturnValue({ data: DURUM_LOCAL, isLoading: false });
    ekrandaCiz();
    await kullanici.click(screen.getAllByRole("button", { name: "Bu modla başla" })[2]);
    expect(await screen.findByText("Sabit şema (§8.5)")).toBeInTheDocument();
    expect(mockBriefUret).not.toHaveBeenCalled();
    expect(mockSorulariGetir).not.toHaveBeenCalled();
  });
});

describe("OnboardingPage — K6: insan onayı (MUTASYON KİLİDİ)", () => {
  it("onay kutusu işaretlenmeden yazma isteği ATILMAZ", async () => {
    const kullanici = userEvent.setup();
    mockDurum.mockReturnValue({ data: DURUM_LOCAL, isLoading: false });
    ekrandaCiz();
    await onayAdiminaGit(kullanici);

    const yazDugmesi = screen.getByRole("button", { name: ".harness/ dizinine yaz" });
    expect(yazDugmesi).toBeDisabled();
    await kullanici.click(yazDugmesi);
    expect(mockUygula).not.toHaveBeenCalled();
  });

  it("onay işaretlenince yazar ve onay kaydını GÖNDERIR", async () => {
    const kullanici = userEvent.setup();
    mockDurum.mockReturnValue({ data: DURUM_LOCAL, isLoading: false });
    mockUygula.mockResolvedValue({
      tur: "basarili",
      yazilan: [".harness/scope/sprint-1.md"],
      sprint_dosyalari: [".harness/scope/sprint-1.md"],
      task_dosyalari: ["tasks/T-1-*.md"],
      kok: "/Users/fatih/grup54",
    });
    ekrandaCiz();
    await onayAdiminaGit(kullanici);

    await kullanici.click(screen.getByLabelText("Taslağı okudum, onaylıyorum"));
    await kullanici.type(screen.getByLabelText(/Onaylayan/), "fatiherencetin");
    await kullanici.click(screen.getByRole("button", { name: ".harness/ dizinine yaz" }));

    await waitFor(() => expect(mockUygula).toHaveBeenCalledTimes(1));
    expect(mockUygula.mock.calls[0][0].onay).toEqual({
      onaylandi: true,
      onaylayan: "fatiherencetin",
    });
    expect(await screen.findByText("Yazıldı")).toBeInTheDocument();
    // Son adım: dosyalar diskte ama Board bir PROJEKSİYON — söylenmezse
    // kullanıcı "yazdı ama hiçbir şey olmadı" görür (#340 duman testi bulgusu).
    //
    // Bu iddia DEĞİŞTİ, zayıflamadı: eskiden `make rebuild` talimatı aranıyordu,
    // ama doğrulama turunda ölçüldü ki O KOMUT HEDEF KURULUMDA ÇALIŞMIYOR
    // (gerçek GitHub App yoksa rebuild fail-closed kapıya çarpıyor, D-51).
    // Yani test, kullanıcıyı kapalı bir kapıya gönderen davranışı şartname
    // olarak kodluyordu. Artık uç projeksiyonu KENDİSİ tazeliyor ve ekran
    // SONUCU basıyor.
    expect(await screen.findByTestId("projeksiyon-ozeti")).toBeInTheDocument();
    expect(screen.queryByText(/make rebuild/)).not.toBeInTheDocument();
  });

  it("sunucu 403 derse (K6) mesaj DÜRÜSTÇE basılır", async () => {
    const kullanici = userEvent.setup();
    mockDurum.mockReturnValue({ data: DURUM_LOCAL, isLoading: false });
    mockUygula.mockResolvedValue({
      tur: "onaysiz",
      mesaj: "İnsan onayı olmadan .harness/ yazılamaz (K6).",
    });
    ekrandaCiz();
    await onayAdiminaGit(kullanici);
    await kullanici.click(screen.getByLabelText("Taslağı okudum, onaylıyorum"));
    await kullanici.click(screen.getByRole("button", { name: ".harness/ dizinine yaz" }));

    expect(
      await screen.findByText("İnsan onayı olmadan .harness/ yazılamaz (K6)."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Yazıldı")).not.toBeInTheDocument();
  });

  it("hosted kurulumda yazma yok — sessizce değil AÇIKÇA söylenir", async () => {
    const kullanici = userEvent.setup();
    mockDurum.mockReturnValue({
      data: { ...DURUM_LOCAL, mode: "hosted", yazma_mumkun: false },
      isLoading: false,
    });
    ekrandaCiz();
    await onayAdiminaGit(kullanici);

    expect(screen.getByText(/Bu kurulumda yazma adımı yok/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: ".harness/ dizinine yaz" })).toBeDisabled();
  });
});

describe("OnboardingPage — sessiz düşüş yasağı", () => {
  it("story taslağı üretilemezse degraded BEYAN edilir, boş ekran basılmaz", async () => {
    const kullanici = userEvent.setup();
    mockDurum.mockReturnValue({ data: DURUM_LOCAL, isLoading: false });
    mockTaslakUret.mockResolvedValue({
      tur: "basarili",
      taslak: { epicler: [], storyler: [], dusenler: [] },
      degraded: {
        asama: "story",
        saglayici: "gemini+groq",
        neden: "iki sağlayıcı da taslak üretemedi (kota)",
      },
    });
    ekrandaCiz();
    await kullanici.click(screen.getAllByRole("button", { name: "Bu modla başla" })[2]);
    await kullanici.click(screen.getByRole("button", { name: "Story taslağını üret" }));

    const uyari = await screen.findByTestId("onboarding-degraded");
    expect(uyari).toHaveTextContent("iki sağlayıcı da taslak üretemedi");
    expect(screen.getByText("Story taslağı yok")).toBeInTheDocument();
    // Uydurma story YOK.
    expect(screen.queryByText(/Bir geliştirici olarak/)).not.toBeInTheDocument();
  });

  it("eksik alan UYDURULMAZ — rozetle işaretlenir", async () => {
    const kullanici = userEvent.setup();
    mockDurum.mockReturnValue({ data: DURUM_LOCAL, isLoading: false });
    mockBriefUret.mockResolvedValue({
      tur: "basarili",
      brief: { ...DOLU_BRIEF, kapsam_disi: [] },
      eksikler: [
        { alan: "kapsam_disi", neden: "bos", aciklama: "Kapsam dışı boş — sınır çizilmemiş." },
      ],
      uyarilar: [],
      ai_kullanildi: false,
      degraded: null,
    });
    ekrandaCiz();
    await kullanici.click(screen.getAllByRole("button", { name: "Bu modla başla" })[2]);
    await kullanici.click(screen.getByRole("button", { name: "Alanları yeniden doğrula" }));

    expect(await screen.findByText("eksik")).toBeInTheDocument();
    expect(screen.getByText(/Kapsam dışı boş/)).toBeInTheDocument();
    // Alan gerçekten BOŞ bırakıldı (uydurma metin yok).
    expect(screen.getByLabelText("Kapsam dışı")).toHaveValue("");
  });

  it("AI'nın doldurduğu alan 'AI varsayımı' rozetiyle ayrılır", async () => {
    const kullanici = userEvent.setup();
    mockDurum.mockReturnValue({ data: DURUM_LOCAL, isLoading: false });
    mockBriefUret.mockResolvedValue({
      tur: "basarili",
      brief: {
        ...DOLU_BRIEF,
        varsayimlar: [
          {
            alan: "basari_hedefi",
            deger_ozeti: "demoda tek akış gösterilecek",
            gerekce: "metinde hedef geçmiyor",
          },
        ],
      },
      eksikler: [],
      uyarilar: [],
      ai_kullanildi: true,
      degraded: null,
    });
    ekrandaCiz();
    await kullanici.click(screen.getAllByRole("button", { name: "Bu modla başla" })[2]);
    await kullanici.click(screen.getByRole("button", { name: "Alanları yeniden doğrula" }));

    expect(await screen.findByText("AI varsayımı")).toBeInTheDocument();
    expect(screen.getByText(/metinde hedef geçmiyor/)).toBeInTheDocument();
  });
});

describe("OnboardingPage — sprint dağıtımı", () => {
  it("kapasiteye göre dağıtımı çizer ve uyarıları saklamaz", async () => {
    const kullanici = userEvent.setup();
    mockDurum.mockReturnValue({ data: DURUM_LOCAL, isLoading: false });
    mockTaslakUret.mockResolvedValue({ tur: "basarili", taslak: TASLAK, degraded: null });
    mockPlanUret.mockResolvedValue({
      tur: "basarili",
      plan: {
        toplam_puan: 5,
        dilimler: [
          { sprint: 1, butce: 3, yuk: 5, story_idler: ["US1"] },
          { sprint: 2, butce: 2, yuk: 0, story_idler: [] },
        ],
        uyarilar: ["US1 (5 puan) hiçbir sprintin bütçesine sığmadı."],
      },
    });
    // Kapasite brief'in KISITLAR alanından gelir — dolu bir brief olmadan
    // dağıtım hesaplanamaz (uydurulmaz), o yüzden önce brief doldurulur.
    mockBriefUret.mockResolvedValue({
      tur: "basarili",
      brief: DOLU_BRIEF,
      eksikler: [],
      uyarilar: [],
      ai_kullanildi: false,
      degraded: null,
    });
    ekrandaCiz();
    await kullanici.click(screen.getAllByRole("button", { name: "Bu modla başla" })[2]);
    await kullanici.click(screen.getByRole("button", { name: "Alanları yeniden doğrula" }));
    await screen.findByDisplayValue("Ekipler için ortak proje beyni.");
    await kullanici.click(screen.getByRole("button", { name: "Story taslağını üret" }));
    await screen.findByRole("button", { name: "Sprint dağıtımını öner" });
    await kullanici.click(screen.getByRole("button", { name: "Sprint dağıtımını öner" }));

    expect(await screen.findByText("Sprint 1")).toBeInTheDocument();
    expect(screen.getByText(/hiçbir sprintin bütçesine sığmadı/)).toBeInTheDocument();
  });
});
