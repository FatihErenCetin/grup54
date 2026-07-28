/** #21 testleri — FeedItem anatomisi, filtre, empty/loading/error, presence dürüstlüğü,
    mock zinciri + global rozet. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AppLayout from "../src/components/AppLayout";
import { FeedItem, moduleOf } from "../src/components/FeedItem";
import { PresenceStrip } from "../src/components/PresenceStrip";
import { mockDetections, mockFetch } from "../src/mocks/radar";
import RadarPage from "../src/pages/RadarPage";

const mockUseRadar = vi.fn();
vi.mock("../src/lib/useRadar", () => ({ useRadar: () => mockUseRadar() }));
// Presence şeridi #60'tan beri CANLI (GET /presence) → RadarPage'i provider'sız
// render edebilmek için hook mock'lanır (useRadar ile aynı kalıp)
const mockUsePresence = vi.fn();
vi.mock("../src/lib/usePresence", () => ({ usePresence: () => mockUsePresence() }));
// AppLayout rozet testi için mock:true; apiBaseUrl mockFetch önek testiyle uyumlu
vi.mock("../src/lib/config", () => ({
  config: { apiBaseUrl: "http://localhost:8000", mode: "local", mock: true },
}));

const dolu = {
  data: { detections: mockDetections, updated_at: "2026-07-13T09:00:00Z" },
  error: null,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: Date.now(),
};

const presenceBos = {
  data: { entries: [], latest_ts: "2026-07-13T09:00:00Z" },
  error: null,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: Date.now(),
};

beforeEach(() => {
  // RadarPage şeridi gömüyor; varsayılan = dürüst boş presence
  mockUsePresence.mockReturnValue(presenceBos);
});

describe("moduleOf", () => {
  it("yoldan modül etiketi çıkarır", () => {
    expect(moduleOf(["src/backend/ensemble/engine/radar.py"])).toBe("engine");
    expect(moduleOf(["src/backend/ensemble/config.py"])).toBe("backend"); // paket kökü
    expect(moduleOf(["src/frontend/src/lib/api.ts"])).toBe("frontend");
    expect(moduleOf([".github/workflows/ci.yml"])).toBe("ci");
    expect(moduleOf([".env.example"])).toBe("repo");
  });
});

describe("FeedItem", () => {
  const det = mockDetections[0]; // config.py vakası — high, %93

  it("satır anatomisi: severity + rationale + confidence + modül görünür", () => {
    // MemoryRouter şart: aktör çipi artık linkli (#129) → <Link> router context ister.
    render(
      <MemoryRouter>
        <ul>
          <FeedItem detection={det} onSelect={() => {}} />
        </ul>
      </MemoryRouter>,
    );
    expect(screen.getByText("yüksek")).toBeInTheDocument();
    expect(screen.getByText(/Settings'e aynı bölgede alan ekliyor/)).toBeInTheDocument();
    expect(screen.getByText("%93")).toBeInTheDocument();
    expect(screen.getByText("backend")).toBeInTheDocument(); // config.py paket kökünde → genel etiket
  });

  it("ajan aktörü kare/etiketli, insan değil", () => {
    const ajanli = mockDetections.find((d) => d.actors.includes("fatih-claude"))!;
    render(
      <MemoryRouter>
        <ul>
          <FeedItem detection={ajanli} onSelect={() => {}} />
        </ul>
      </MemoryRouter>,
    );
    expect(screen.getByTitle("fatih-claude (AI ajanı)")).toBeInTheDocument();
    expect(screen.getByTitle("asmarufoglu")).toBeInTheDocument();
  });
});

describe("PresenceStrip (canlı GET /presence — #60)", () => {
  const canli = {
    ...presenceBos,
    data: {
      entries: [
        {
          actor: { handle: "asmarufoglu", type: "human" as const, responsible: null },
          module: "engine",
          task: "T-17",
          branch: "T-17-cakisma-radari",
          since: "2026-07-13T08:20:00Z",
        },
        {
          actor: {
            handle: "fatih-claude",
            type: "agent" as const,
            responsible: "FatihErenCetin",
          },
          module: "frontend",
          task: "T-21",
          branch: null,
          since: "2026-07-13T08:55:00Z",
        },
      ],
      latest_ts: "2026-07-13T08:55:00Z",
    },
  };

  it("veri gelince aktör + modül çizer; ajan tipini ActorRef'ten okur (sezgiden değil)", () => {
    mockUsePresence.mockReturnValue(canli);
    render(<PresenceStrip />);
    expect(screen.getByText("asmarufoglu")).toBeInTheDocument();
    expect(screen.getByText("engine")).toBeInTheDocument();
    expect(screen.getByTitle("fatih-claude (AI ajanı)")).toBeInTheDocument();
  });

  it("boş: şerit KAYBOLMAZ, dürüst 'kimse beyan etmemiş' basar", () => {
    mockUsePresence.mockReturnValue(presenceBos);
    render(<PresenceStrip />);
    expect(screen.getByText(/kimse çalışma beyan etmemiş/)).toBeInTheDocument();
  });

  it("hata: sessizce kaybolmaz, görünür uyarı + teknik ayrıntı basar", () => {
    mockUsePresence.mockReturnValue({
      ...presenceBos,
      data: undefined,
      error: { message: "Failed to fetch" },
    });
    render(<PresenceStrip />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Presence alınamadı/)).toBeInTheDocument();
    expect(screen.getByText(/Failed to fetch/)).toBeInTheDocument();
  });

  it("falsy error ('') yutulmaz — sahte 'kimse yok' basılmaz", () => {
    // openapi-fetch boş-gövdeli non-ok cevapta error="" verebilir (RadarPage bulgusu)
    mockUsePresence.mockReturnValue({ ...presenceBos, data: undefined, error: "" });
    render(<PresenceStrip />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/kimse çalışma beyan etmemiş/)).not.toBeInTheDocument();
  });

  it("geçici poll hatası eldeki şeridi GİZLEMEZ", () => {
    mockUsePresence.mockReturnValue({ ...canli, error: new Error("tek poll patladı") });
    render(<PresenceStrip />);
    expect(screen.getByText("asmarufoglu")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("yükleniyor: iskelet yer tutar (sayfa zıplamaz)", () => {
    mockUsePresence.mockReturnValue({ ...presenceBos, data: undefined, isLoading: true });
    render(<PresenceStrip />);
    expect(screen.getByLabelText("Presence yükleniyor")).toBeInTheDocument();
  });
});

describe("RadarPage", () => {
  it("loading: skeleton, aria-busy", () => {
    mockUseRadar.mockReturnValue({ ...dolu, data: undefined, isLoading: true });
    render(<MemoryRouter><RadarPage /></MemoryRouter>);
    expect(screen.getByLabelText("Radar yükleniyor")).toBeInTheDocument();
  });

  it("hata: ulaşılamıyor durumu", () => {
    mockUseRadar.mockReturnValue({ ...dolu, data: undefined, error: new Error("x") });
    render(<MemoryRouter><RadarPage /></MemoryRouter>);
    expect(screen.getByText("Radar'a ulaşılamıyor")).toBeInTheDocument();
  });

  it("falsy error ('') yutulmaz — sahte 'radar temiz' basılmaz", () => {
    // openapi-fetch boş-gövdeli non-ok cevapta error="" verebilir (doğrulama bulgusu)
    mockUseRadar.mockReturnValue({ ...dolu, data: undefined, error: "" });
    render(<MemoryRouter><RadarPage /></MemoryRouter>);
    expect(screen.getByText("Radar'a ulaşılamıyor")).toBeInTheDocument();
    expect(screen.queryByText("Radar temiz — çakışma yok")).not.toBeInTheDocument();
  });

  it("geçici poll hatası eldeki listeyi GİZLEMEZ", () => {
    mockUseRadar.mockReturnValue({ ...dolu, error: new Error("tek poll patladı") });
    render(<MemoryRouter><RadarPage /></MemoryRouter>);
    expect(screen.queryByText("Radar'a ulaşılamıyor")).not.toBeInTheDocument();
    expect(screen.getByRole("list")).toBeInTheDocument(); // liste durur, polling sürer
  });

  it("boş: dürüst 'radar temiz' durumu", () => {
    mockUseRadar.mockReturnValue({
      ...dolu,
      data: { detections: [], updated_at: "2026-07-13T09:00:00Z" },
    });
    render(<MemoryRouter><RadarPage /></MemoryRouter>);
    expect(screen.getByText("Radar temiz — çakışma yok")).toBeInTheDocument();
  });

  it("dolu: tespitler listelenir + severity filtresi çalışır", async () => {
    const user = userEvent.setup();
    mockUseRadar.mockReturnValue(dolu);
    render(<MemoryRouter><RadarPage /></MemoryRouter>);
    // sorgular LİSTEYE scope'lu — filtre butonlarındaki metinle karışma riski
    // kalıcı olarak kapalı (doğrulama bulgusu: kırılganlık sınırındaydı)
    const list = () => within(screen.getByRole("list", { name: "Tespit listesi" }));
    // 4 fixture: 2 high, 1 med, 1 low
    expect(list().getAllByText("yüksek")).toHaveLength(2);
    expect(list().getAllByText("orta")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "▲ yüksek" }));
    expect(list().getAllByText("yüksek")).toHaveLength(2);
    expect(list().queryByText("orta")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "● düşük" }));
    expect(list().getAllByText("düşük")).toHaveLength(1);
  });
});

describe("mock zinciri (PR manşet kararı — commit'li testte)", () => {
  it("mockFetch: /radar 200 + tipli gövde; bilinmeyen yol 404", async () => {
    const ok = mockFetch(new Request("http://localhost:8000/radar"));
    expect(ok.status).toBe(200);
    const body = await ok.json();
    expect(body.detections.length).toBeGreaterThan(0);
    expect(mockFetch(new Request("http://localhost:8000/bilinmeyen")).status).toBe(404);
  });

  it("mockFetch: /presence 200 + PresenceResponse gövdesi", async () => {
    const ok = mockFetch(new Request("http://localhost:8000/presence"));
    expect(ok.status).toBe(200);
    const body = await ok.json();
    expect(body.entries.length).toBeGreaterThan(0);
    expect(body.entries[0].actor.type).toMatch(/human|agent/);
    expect(body.latest_ts).toBeTruthy();
  });

  it("api → mockFetch zinciri VITE_MOCK=1 iken uçtan uca çalışır", async () => {
    vi.stubEnv("VITE_MOCK", "1");
    vi.resetModules(); // api.ts modül-anı değerlendiriyor → taze import şart
    const { api } = await import("../src/lib/api");
    const { data, error } = await api.GET("/radar");
    expect(error).toBeUndefined();
    expect(data?.detections.length).toBeGreaterThan(0);
    vi.unstubAllEnvs();
  });
});

describe("global dürüstlük rozeti", () => {
  it("mock modunda AppLayout 'Örnek veri' basar (D-34: ALL-CAPS değil)", () => {
    // #79/T-79'dan beri AppLayout'un aktif-repo göstergesi de bir react-query
    // hook'u (useRepolar) kullanıyor → RadarPage'in shell.test.tsx'teki gerekçesiyle
    // AYNI: provider şart (gerçek istek atılmaz, anonimken enabled=false kalır).
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<div />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText("Örnek veri")).toBeInTheDocument();
  });
});


describe("DetailSheet (#156 — Pencil MOGXv'ye dönüş)", () => {
  async function acikSayfa() {
    const user = userEvent.setup();
    mockUseRadar.mockReturnValue(dolu);
    render(<MemoryRouter><RadarPage /></MemoryRouter>);
    // ilk satıra tıkla → sağdan panel
    await user.click(within(screen.getByRole("list", { name: "Tespit listesi" })).getAllByRole("button")[0]);
    return user;
  }

  it("satır tıklanınca panel açılır: dosyalar + deterministik sinyaller + gate notu", async () => {
    await acikSayfa();
    const panel = screen.getByLabelText("Tespit detayı");
    expect(within(panel).getByText("DOSYALAR")).toBeInTheDocument();
    expect(within(panel).getByText("src/backend/ensemble/config.py")).toBeInTheDocument();
    expect(within(panel).getByText("DETERMİNİSTİK SİNYALLER")).toBeInTheDocument();
    expect(within(panel).getByText(/çakışan dosya: 3/)).toBeInTheDocument();
    // aksiyon butonu YOK, dürüst gate notu VAR (Ek B6)
    expect(within(panel).queryByRole("button", { name: /Yanlış alarm/ })).not.toBeInTheDocument();
    expect(within(panel).getByText(/S3'te gelir/)).toBeInTheDocument();
  });

  it("X ve Esc kapatır; aynı satıra tekrar tıklamak da kapatır", async () => {
    const user = await acikSayfa();
    await user.click(screen.getByLabelText("Detayı kapat"));
    expect(screen.queryByLabelText("Tespit detayı")).not.toBeInTheDocument();
    // tekrar aç → Esc
    await user.click(within(screen.getByRole("list", { name: "Tespit listesi" })).getAllByRole("button")[0]);
    expect(screen.getByLabelText("Tespit detayı")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByLabelText("Tespit detayı")).not.toBeInTheDocument();
    // tekrar aç → aynı satıra tıkla (toggle)
    await user.click(within(screen.getByRole("list", { name: "Tespit listesi" })).getAllByRole("button")[0]);
    await user.click(within(screen.getByRole("list", { name: "Tespit listesi" })).getAllByRole("button")[0]);
    expect(screen.queryByLabelText("Tespit detayı")).not.toBeInTheDocument();
  });

  it("↑↓ görünür listede gezinir", async () => {
    const user = await acikSayfa();
    // ilk satır seçili (yüksek, config.py) → ↓ ikinciye geçer (.env.example)
    await user.keyboard("{ArrowDown}");
    const panel = screen.getByLabelText("Tespit detayı");
    expect(within(panel).getByText(".env.example")).toBeInTheDocument();
  });

  it("filtre seçili tespiti görünürden düşürürse panel dürüstçe kapanır", async () => {
    const user = await acikSayfa(); // seçili: high (config.py)
    await user.click(screen.getByRole("button", { name: "● düşük" }));
    expect(screen.queryByLabelText("Tespit detayı")).not.toBeInTheDocument();
  });
});


describe("DetailSheet — doğrulama bulgularının kilitleri", () => {
  // #158 sonrası tespit satırları TEK liste değil: yüksek/orta "Tespit listesi"nde,
  // düşük-güvenliler katlanan "Düşük güvenli tespitler" listesinde duruyor. Helper
  // yalnız ana listeye baksaydı klavye gezinmesi bölüm sınırını geçtiği anda satırı
  // bulamazdı (bu testi kırdıran şey buydu) — satırlar DOM sırasında aranıyor.
  // aria-controls="detay-paneli" yalnız FeedItem satırlarında var: filtre butonları
  // ve katlama düğmesi bu seçime girmez.
  const feedBtn = (i: number) =>
    screen.getAllByRole("button").filter((b) => b.getAttribute("aria-controls") === "detay-paneli")[
      i
    ];

  it("hayalet panel yok: filtre gidiş-dönüşünde panel tıklamasız GERİ AÇILMAZ", async () => {
    const user = userEvent.setup();
    mockUseRadar.mockReturnValue(dolu);
    render(<MemoryRouter><RadarPage /></MemoryRouter>);
    await user.click(screen.getByRole("button", { name: "● düşük" }));
    await user.click(feedBtn(0)); // ci.yml tespiti seçili
    expect(screen.getByLabelText("Tespit detayı")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "▲ yüksek" }));
    expect(screen.queryByLabelText("Tespit detayı")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "● düşük" }));
    expect(screen.queryByLabelText("Tespit detayı")).not.toBeInTheDocument(); // state de temiz
  });

  it("focus seçimi takip eder (roving) + sınırlarda sessiz durur", async () => {
    const user = userEvent.setup();
    mockUseRadar.mockReturnValue(dolu);
    render(<MemoryRouter><RadarPage /></MemoryRouter>);
    await user.click(feedBtn(0));
    await user.keyboard("{ArrowUp}"); // ilk satırda ↑ → değişmez
    expect(
      within(screen.getByLabelText("Tespit detayı")).getByText("src/backend/ensemble/config.py"),
    ).toBeInTheDocument();
    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(feedBtn(1)); // ring seçimle birlikte
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}"); // son satırı aşmaya çalış
    // 4. satır katlanan bölümde (#158): ↑↓ oraya adım atınca bölüm AÇILMALI, yoksa
    // focus mount olmamış satıra gidemez. Önce onu doğruluyoruz ki bir regresyonda
    // hata "satır bulunamadı" diye değil, sebebiyle görünsün.
    expect(
      screen.getByRole("button", { name: /düşük-güven tespit/ }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(document.activeElement).toBe(feedBtn(3)); // son satırda durdu
  });

  it("polling tazelemesi (aynı id'ler, yeni nesneler) seçimi KORUR", async () => {
    const user = userEvent.setup();
    mockUseRadar.mockReturnValue(dolu);
    const { rerender } = render(<MemoryRouter><RadarPage /></MemoryRouter>);
    await user.click(feedBtn(0));
    // yeni referanslar, aynı id'ler — gerçek poll davranışı
    mockUseRadar.mockReturnValue({
      ...dolu,
      data: { detections: dolu.data.detections.map((d) => ({ ...d })), updated_at: "x" },
    });
    rerender(<MemoryRouter><RadarPage /></MemoryRouter>);
    expect(screen.getByLabelText("Tespit detayı")).toBeInTheDocument();
  });
});
