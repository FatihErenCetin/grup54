/** #33 (Kapsam bekçisi) + #318 (tasarım paketiyle görsel parite) testleri.
    ScopePage'in bugüne kadar hiç unit testi yoktu — bu dosya hem #318'in YENİ
    davranışını (kompakt "🔒 DONMUŞ · v1 · kısa tarih" künyesi) hem de sayfanın
    zaten var olan temel akışlarını (loading/error/empty/dolu) kilitler. */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "../src/api/schema.d.ts";
import ScopePage from "../src/pages/ScopePage";

type ScopeCurrent = components["schemas"]["ScopeCurrent"];
type ScopeVerdictsResponse = components["schemas"]["ScopeVerdictsResponse"];

const mockUseScope = vi.fn();
const mockUseScopeVerdicts = vi.fn();
vi.mock("../src/lib/useScope", () => ({
  useScope: () => mockUseScope(),
  useScopeVerdicts: () => mockUseScopeVerdicts(),
}));

const scopeVerisi: ScopeCurrent = {
  goal: "Sprint 3 amacı: go-live + web MVP'nin gerisi.",
  in_scope: ["Go-live mekanigi kurulur", "Kalan API router'lari acilir"],
  non_goals: ["MCP write-back yapilmaz"],
  version: "1",
  frozen_at: "2026-07-06T17:33:02+03:00",
  ref: ".harness/scope/sprint-3.md",
  commit_sha: "18f846fba6b2c45c3374b61a69d43a328254d1a0",
};

const verdictsBos: ScopeVerdictsResponse = {
  verdicts: [],
  counts: { in_scope: 0, drift: 0, non_goal_violation: 0 },
  judged_at: null,
};

const doluScope = {
  data: scopeVerisi,
  error: null,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: Date.now(),
};

const doluVerdicts = {
  data: verdictsBos,
  error: null,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: Date.now(),
};

beforeEach(() => {
  mockUseScope.mockReturnValue(doluScope);
  mockUseScopeVerdicts.mockReturnValue(doluVerdicts);
});

describe("ScopePage — temel akışlar", () => {
  it("loading: iskelet basar", () => {
    mockUseScope.mockReturnValue({ ...doluScope, data: undefined, isLoading: true });
    render(<ScopePage />);
    expect(screen.getByLabelText("Kapsam yükleniyor")).toBeInTheDocument();
  });

  it("hata: ulaşılamıyor durumu (503 scope_unavailable ihtimali dahil anlatılır)", () => {
    mockUseScope.mockReturnValue({ ...doluScope, data: undefined, error: new Error("x") });
    render(<ScopePage />);
    expect(screen.getByText("Kapsam belgesine ulaşılamıyor")).toBeInTheDocument();
  });

  it("falsy error ('') yutulmaz — sahte 'kapsam yok' basılmaz", () => {
    // openapi-fetch boş-gövdeli non-ok cevapta error="" verebilir (RadarPage bulgusu)
    mockUseScope.mockReturnValue({ ...doluScope, data: undefined, error: "" });
    render(<ScopePage />);
    expect(screen.getByText("Kapsam belgesine ulaşılamıyor")).toBeInTheDocument();
  });

  it("boş: goal + in_scope + non_goals üçü de boşsa dürüst boş durum", () => {
    mockUseScope.mockReturnValue({
      ...doluScope,
      data: { ...scopeVerisi, goal: "", in_scope: [], non_goals: [] },
    });
    render(<ScopePage />);
    expect(screen.getByText("Dondurulmuş kapsam boş")).toBeInTheDocument();
  });

  it("dolu: amaç + kapsam içi/dışı maddeler listelenir", () => {
    render(<ScopePage />);
    expect(screen.getByText(/Sprint 3 amacı/)).toBeInTheDocument();
    expect(screen.getByText(/Go-live mekanigi kurulur/)).toBeInTheDocument();
    expect(screen.getByText(/MCP write-back yapilmaz/)).toBeInTheDocument();
  });

  it("kapsam kararları paneli: henüz karar yoksa ucun gerçek boş cevabı basılır", () => {
    render(<ScopePage />);
    expect(screen.getByText("Henüz kapsam kararı yok.")).toBeInTheDocument();
  });
});

describe("ScopePage — künye şeridi (#318 tasarım paritesi)", () => {
  // Mutasyon kanıtı: `KunyeSeridi`'yi eski hâline (✓ Dondurulmuş + "sürüm: N" +
  // ayrı "Donduruldu: <tam tarih>" satırı, kilit emoji yok) geri alınca bu 3
  // test KIRMIZI görüldü (screen.getByText("DONMUŞ") bulunamadı hatası) — sonra
  // geri alındı, yeşile döndü. Kırmızı görülmeden bırakılan bir test burada yok.
  it("kompakt rozet: kilit + DONMUŞ + v{sürüm} + kısa tarih görünür", () => {
    render(<ScopePage />);
    const rozet = screen.getByText("DONMUŞ").closest("span")!;
    expect(rozet).toHaveTextContent("🔒");
    expect(rozet).toHaveTextContent("v1");
    // frozen_at 6 Temmuz — kısa biçim gün+kısaltılmış ay ("6 Tem")
    expect(rozet).toHaveTextContent("6 Tem");
  });

  it("eski tam-genişlik biçimi ('Dondurulmuş', 'sürüm:') artık BASILMAZ", () => {
    render(<ScopePage />);
    expect(screen.queryByText("Dondurulmuş")).not.toBeInTheDocument();
    expect(screen.queryByText(/sürüm:/)).not.toBeInTheDocument();
  });

  it("kanıt bağlantısı (ref + tam commit_sha) SİLİNMEDİ — sadece rozetten sonra durur", () => {
    render(<ScopePage />);
    expect(screen.getByText(".harness/scope/sprint-3.md")).toBeInTheDocument();
    const commitKisa = screen.getByText("18f846f");
    expect(commitKisa).toHaveAttribute("title", scopeVerisi.commit_sha);
  });

  it("bozuk frozen_at: kısa rozet de 'Invalid Date' basmaz, ham metni gösterir", () => {
    mockUseScope.mockReturnValue({
      ...doluScope,
      data: { ...scopeVerisi, frozen_at: "bozuk-tarih" },
    });
    render(<ScopePage />);
    const rozet = screen.getByText("DONMUŞ").closest("span")!;
    expect(rozet).toHaveTextContent("bozuk-tarih");
    expect(rozet).not.toHaveTextContent("Invalid Date");
  });
});
