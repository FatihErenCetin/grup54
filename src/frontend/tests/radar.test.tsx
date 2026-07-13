/** #21 testleri — FeedItem anatomisi, filtre, empty/loading/error, presence dürüstlüğü,
    mock zinciri + global rozet. */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import AppLayout from "../src/components/AppLayout";
import { FeedItem, moduleOf } from "../src/components/FeedItem";
import { PresenceStrip } from "../src/components/PresenceStrip";
import { mockDetections, mockFetch } from "../src/mocks/radar";
import RadarPage from "../src/pages/RadarPage";

const mockUseRadar = vi.fn();
vi.mock("../src/lib/useRadar", () => ({ useRadar: () => mockUseRadar() }));
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
    render(<ul><FeedItem detection={det} onSelect={() => {}} /></ul>);
    expect(screen.getByText("yüksek")).toBeInTheDocument();
    expect(screen.getByText(/Settings'e aynı bölgede alan ekliyor/)).toBeInTheDocument();
    expect(screen.getByText("%93")).toBeInTheDocument();
    expect(screen.getByText("backend")).toBeInTheDocument(); // config.py paket kökünde → genel etiket
  });

  it("ajan aktörü kare/etiketli, insan değil", () => {
    const ajanli = mockDetections.find((d) => d.actors.includes("fatih-claude"))!;
    render(<ul><FeedItem detection={ajanli} onSelect={() => {}} /></ul>);
    expect(screen.getByTitle("fatih-claude (AI ajanı)")).toBeInTheDocument();
    expect(screen.getByTitle("asmarufoglu")).toBeInTheDocument();
  });
});

describe("PresenceStrip", () => {
  it("dürüstlük etiketi HER ZAMAN görünür (Ek B1 — canlı S3'te)", () => {
    render(<PresenceStrip />);
    expect(screen.getByText("(örnek — canlı S3'te)")).toBeInTheDocument();
    expect(screen.getByText("asmarufoglu")).toBeInTheDocument();
  });
});

describe("RadarPage", () => {
  it("loading: skeleton, aria-busy", () => {
    mockUseRadar.mockReturnValue({ ...dolu, data: undefined, isLoading: true });
    render(<RadarPage />);
    expect(screen.getByLabelText("Radar yükleniyor")).toBeInTheDocument();
  });

  it("hata: ulaşılamıyor durumu", () => {
    mockUseRadar.mockReturnValue({ ...dolu, data: undefined, error: new Error("x") });
    render(<RadarPage />);
    expect(screen.getByText("Radar'a ulaşılamıyor")).toBeInTheDocument();
  });

  it("falsy error ('') yutulmaz — sahte 'radar temiz' basılmaz", () => {
    // openapi-fetch boş-gövdeli non-ok cevapta error="" verebilir (doğrulama bulgusu)
    mockUseRadar.mockReturnValue({ ...dolu, data: undefined, error: "" });
    render(<RadarPage />);
    expect(screen.getByText("Radar'a ulaşılamıyor")).toBeInTheDocument();
    expect(screen.queryByText("Radar temiz — çakışma yok")).not.toBeInTheDocument();
  });

  it("geçici poll hatası eldeki listeyi GİZLEMEZ", () => {
    mockUseRadar.mockReturnValue({ ...dolu, error: new Error("tek poll patladı") });
    render(<RadarPage />);
    expect(screen.queryByText("Radar'a ulaşılamıyor")).not.toBeInTheDocument();
    expect(screen.getByRole("list")).toBeInTheDocument(); // liste durur, polling sürer
  });

  it("boş: dürüst 'radar temiz' durumu", () => {
    mockUseRadar.mockReturnValue({
      ...dolu,
      data: { detections: [], updated_at: "2026-07-13T09:00:00Z" },
    });
    render(<RadarPage />);
    expect(screen.getByText("Radar temiz — çakışma yok")).toBeInTheDocument();
  });

  it("dolu: tespitler listelenir + severity filtresi çalışır", async () => {
    const user = userEvent.setup();
    mockUseRadar.mockReturnValue(dolu);
    render(<RadarPage />);
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
    render(
      <MemoryRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<div />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Örnek veri")).toBeInTheDocument();
  });
});


describe("DetailSheet (#156 — Pencil MOGXv'ye dönüş)", () => {
  async function acikSayfa() {
    const user = userEvent.setup();
    mockUseRadar.mockReturnValue(dolu);
    render(<RadarPage />);
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
  const feedBtn = (i: number) =>
    within(screen.getByRole("list", { name: "Tespit listesi" })).getAllByRole("button")[i];

  it("hayalet panel yok: filtre gidiş-dönüşünde panel tıklamasız GERİ AÇILMAZ", async () => {
    const user = userEvent.setup();
    mockUseRadar.mockReturnValue(dolu);
    render(<RadarPage />);
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
    render(<RadarPage />);
    await user.click(feedBtn(0));
    await user.keyboard("{ArrowUp}"); // ilk satırda ↑ → değişmez
    expect(
      within(screen.getByLabelText("Tespit detayı")).getByText("src/backend/ensemble/config.py"),
    ).toBeInTheDocument();
    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(feedBtn(1)); // ring seçimle birlikte
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}"); // son satırı aşmaya çalış
    expect(document.activeElement).toBe(feedBtn(3)); // son satırda durdu
  });

  it("polling tazelemesi (aynı id'ler, yeni nesneler) seçimi KORUR", async () => {
    const user = userEvent.setup();
    mockUseRadar.mockReturnValue(dolu);
    const { rerender } = render(<RadarPage />);
    await user.click(feedBtn(0));
    // yeni referanslar, aynı id'ler — gerçek poll davranışı
    mockUseRadar.mockReturnValue({
      ...dolu,
      data: { detections: dolu.data.detections.map((d) => ({ ...d })), updated_at: "x" },
    });
    rerender(<RadarPage />);
    expect(screen.getByLabelText("Tespit detayı")).toBeInTheDocument();
  });
});
