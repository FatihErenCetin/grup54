/** #316/A5 — sayfa başlıkları Title Case olsun (Pencil karşılaştırması).
 *
 * Radar/Graph/Activity'nin kendi test dosyaları zaten VAR (radar.test.tsx,
 * graph.test.tsx, activity.test.tsx) — başlık kilidi oraya eklendi. Scope ve
 * Ask'ın henüz kendi test dosyası yoktu; burada yalnız başlık + gerekli
 * minimum render iskeleti var (mevcut sayfa davranışını yeniden test ETMİYOR).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { components } from "../src/api/schema.d.ts";
import AskPage from "../src/pages/AskPage";
import ScopePage from "../src/pages/ScopePage";

type ScopeCurrent = components["schemas"]["ScopeCurrent"];

const scopeDolu: ScopeCurrent = {
  goal: "Sprint hedefi — test amaçlı kısa cümle.",
  in_scope: ["madde 1"],
  non_goals: [],
  version: "v1",
  ref: "sprint-3",
  commit_sha: "abcdef1234567890",
  frozen_at: "2026-07-20T09:00:00Z",
};

const mockUseScope = vi.fn();
const mockUseScopeVerdicts = vi.fn();
vi.mock("../src/lib/useScope", () => ({
  useScope: () => mockUseScope(),
  useScopeVerdicts: () => mockUseScopeVerdicts(),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ScopePage — başlık Title Case (#316/A5)", () => {
  it("'Kapsam Bekçisi' basar, 'Kapsam bekçisi' DEĞİL", () => {
    // MUTASYON KİLİDİ: h1'i eski "Kapsam bekçisi"ya geri çevir -> bu test kırılır.
    mockUseScope.mockReturnValue({
      data: scopeDolu,
      error: null,
      isLoading: false,
      isFetching: false,
      dataUpdatedAt: Date.now(),
    });
    mockUseScopeVerdicts.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: false,
      isFetching: false,
      dataUpdatedAt: 0,
    });
    render(<ScopePage />, { wrapper });
    expect(screen.getByRole("heading", { name: "Kapsam Bekçisi" })).toBeInTheDocument();
  });
});

describe("AskPage — başlık Title Case (#316/A5)", () => {
  it("'Projeye Sor' basar, 'Projeye sor' DEĞİL — soru boşken hiç istek atılmadan da görünür", () => {
    // MUTASYON KİLİDİ: h1'i eski "Projeye sor"a geri çevir -> bu test kırılır.
    // Soru boşken useAsk enabled=false döner (bkz. lib/useAsk.ts) — gerçek hook
    // güvenle kullanılabilir, mock GEREKMEZ.
    render(<AskPage />, { wrapper });
    expect(screen.getByRole("heading", { name: "Projeye Sor" })).toBeInTheDocument();
  });
});
