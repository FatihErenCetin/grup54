/** #21 testleri — FeedItem anatomisi, filtre, empty/loading/error, presence dürüstlüğü. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FeedItem, moduleOf } from "../src/components/FeedItem";
import { PresenceStrip } from "../src/components/PresenceStrip";
import { mockDetections } from "../src/mocks/radar";
import RadarPage from "../src/pages/RadarPage";

const mockUseRadar = vi.fn();
vi.mock("../src/lib/useRadar", () => ({ useRadar: () => mockUseRadar() }));

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
    render(<ul><FeedItem detection={det} /></ul>);
    expect(screen.getByText("yüksek")).toBeInTheDocument();
    expect(screen.getByText(/Settings'e aynı bölgede alan ekliyor/)).toBeInTheDocument();
    expect(screen.getByText("%93")).toBeInTheDocument();
    expect(screen.getByText("backend")).toBeInTheDocument(); // config.py paket kökünde → genel etiket
  });

  it("expand: dosyalar ve branch'ler açılır", async () => {
    const user = userEvent.setup();
    render(<ul><FeedItem detection={det} /></ul>);
    expect(screen.queryByText("src/backend/ensemble/config.py")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("src/backend/ensemble/config.py")).toBeInTheDocument();
    expect(screen.getByText("T-50-gemini-adapter")).toBeInTheDocument();
  });

  it("ajan aktörü kare/etiketli, insan değil", () => {
    const ajanli = mockDetections.find((d) => d.actors.includes("fatih-claude"))!;
    render(<ul><FeedItem detection={ajanli} /></ul>);
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
    // 4 fixture: 2 high, 1 med, 1 low
    expect(screen.getAllByText("yüksek")).toHaveLength(2);
    expect(screen.getAllByText("orta")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "▲ yüksek" }));
    expect(screen.getAllByText("yüksek")).toHaveLength(2);
    expect(screen.queryByText("orta")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "● düşük" }));
    expect(screen.getAllByText("düşük")).toHaveLength(1);
  });
});
