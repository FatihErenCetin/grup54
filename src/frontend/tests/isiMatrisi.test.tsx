/** #105 — Radar'a gömülü aktör×modül ısı matrisi paneli testleri.
 *
 * `useGraph`/`useEvents` -> `usePolling` -> `api.GET` zincirini en dışından
 * sahteliyoruz (Activity testleriyle aynı desen): panelin kendi durum
 * dallarını + hücre tıklaması → olay listesi eşlemesini ölçüyoruz, HTTP
 * katmanını değil.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IsiMatrisi } from "../src/components/IsiMatrisi";

const graphDurum = vi.hoisted(() => ({
  data: undefined as unknown,
  error: null as unknown,
  isLoading: false,
}));
const eventsDurum = vi.hoisted(() => ({
  data: undefined as unknown,
  error: null as unknown,
  isLoading: false,
}));

vi.mock("../src/lib/useGraph", () => ({ useGraph: () => graphDurum }));
vi.mock("../src/lib/useEvents", () => ({ useEvents: () => eventsDurum }));

function ayarlaGraph(yeni: Partial<typeof graphDurum>) {
  Object.assign(graphDurum, { data: undefined, error: null, isLoading: false, ...yeni });
}
function ayarlaEvents(yeni: Partial<typeof eventsDurum>) {
  Object.assign(eventsDurum, { data: undefined, error: null, isLoading: false, ...yeni });
}

function kenar(actor: string, module: string, count: number, opts: Partial<{ is_active_declared: boolean; last_ts: string }> = {}) {
  return {
    actor,
    module,
    count,
    last_ts: opts.last_ts ?? "2026-07-27T09:00:00",
    is_active_declared: opts.is_active_declared ?? false,
  };
}

function dugum(id: string, type: "actor" | "module", weight: number, actorVerified = true) {
  return { id, type, weight, actor_verified: actorVerified };
}

function ev(id: string, actor: string, files: string[], ts = "2026-07-27T09:00:00", type = "commit") {
  return { id, type, actor, branch: `T-${id}`, files, ts, ref: id };
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <IsiMatrisi />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("IsiMatrisi — katlanma (varsayılan kapalı)", () => {
  it("kapalıyken gövde mount olmaz — kapalı panel istek atmaz", () => {
    renderPanel();
    expect(
      screen.getByRole("button", { name: /Aktör × modül ısı matrisi/ }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("group", { name: /dokunma matrisi/ })).not.toBeInTheDocument();
  });

  it("tıklanınca açılır, tekrar tıklanınca kapanır", async () => {
    ayarlaGraph({ data: { window_days: 14, nodes: [], edges: [kenar("esma", "backend", 3)] } });
    const user = userEvent.setup();
    renderPanel();
    const toggle = screen.getByRole("button", { name: /Aktör × modül ısı matrisi/ });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("group", { name: /dokunma matrisi/ })).toBeInTheDocument();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("group", { name: /dokunma matrisi/ })).not.toBeInTheDocument();
  });
});

describe("IsiMatrisi — durum dalları", () => {
  async function ac() {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /Aktör × modül ısı matrisi/ }));
    return user;
  }

  it("yükleniyor: iskelet gösterir", async () => {
    ayarlaGraph({ isLoading: true });
    await ac();
    expect(screen.getByLabelText(/Isı matrisi yükleniyor/i)).toBeInTheDocument();
  });

  it('error="" (falsy) bile HATA sayılır — sessizce yutulmaz', async () => {
    // MUTASYON KİLİDİ: `error != null` -> `if (error)` yapılırsa bu test kırılır.
    ayarlaGraph({ error: "", data: undefined });
    await ac();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Isı matrisine ulaşılamıyor/)).toBeInTheDocument();
  });

  it("veri varken geçici poll hatası matrisi GİZLEMEZ", async () => {
    ayarlaGraph({ data: { window_days: 14, nodes: [], edges: [kenar("esma", "backend", 2)] }, error: "geçici" });
    await ac();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: /dokunma matrisi/ })).toBeInTheDocument();
  });

  it("boş sonuç HATA DEĞİL — dürüst boş durum gösterir", async () => {
    ayarlaGraph({ data: { window_days: 14, nodes: [], edges: [] } });
    await ac();
    expect(screen.getByText(/Bu pencerede dokunuş yok/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("tek aktör/tek modül: matris kırılmadan render olur", async () => {
    ayarlaGraph({ data: { window_days: 14, nodes: [], edges: [kenar("fatih", "backend", 5)] } });
    await ac();
    expect(screen.getByTitle("fatih")).toBeInTheDocument();
    expect(screen.getByTitle("backend")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /fatih, backend: 5 dokunuş/ }),
    ).toBeInTheDocument();
  });
});

describe("IsiMatrisi — hücre tıklaması → olay/PR listesi (#105 kabul kriteri)", () => {
  async function acVeMatrisiKur() {
    ayarlaGraph({
      data: {
        window_days: 14,
        nodes: [],
        edges: [
          kenar("esma", "backend", 2, { is_active_declared: true }),
          kenar("fatih-claude", "frontend", 1),
        ],
      },
    });
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /Aktör × modül ısı matrisi/ }));
    return user;
  }

  it("hücreye tıklanınca ilgili olaylar listelenir (actor+module eşlemesi)", async () => {
    ayarlaEvents({
      data: {
        events: [
          ev("e1", "esma", ["src/backend/ensemble/engine/graph.py"], "2026-07-27T09:00:00"),
          ev("e2", "esma", ["src/frontend/src/lib/api.ts"], "2026-07-27T08:00:00"), // farklı modül
          ev("e3", "fatih-claude", ["src/backend/ensemble/config.py"], "2026-07-27T07:00:00"), // farklı aktör
        ],
      },
    });
    const user = await acVeMatrisiKur();
    await user.click(screen.getByRole("button", { name: /esma, backend: 2 dokunuş/ }));
    const liste = screen.getByLabelText("esma → backend olayları");
    expect(within(liste).getAllByRole("listitem")).toHaveLength(1);
    expect(within(liste).getByText("T-e1")).toBeInTheDocument();
    // farklı modül/aktörün olayları bu listede GÖRÜNMEZ
    expect(within(liste).queryByText("T-e2")).not.toBeInTheDocument();
    expect(within(liste).queryByText("T-e3")).not.toBeInTheDocument();
  });

  it("eşleşen olay yoksa dürüst mesaj basar — 'dokunuş olmadı' YALANI söylemez", async () => {
    ayarlaEvents({ data: { events: [] } });
    const user = await acVeMatrisiKur();
    await user.click(screen.getByRole("button", { name: /esma, backend: 2 dokunuş/ }));
    // Dürüst mesaj: eksik bilgi ≠ "hiç dokunuş olmadı" iddiası (matristeki sayı gerçek kalır).
    expect(screen.getByText(/eşleşen olay bulunamadı/)).toBeInTheDocument();
  });

  it("aynı hücreye tekrar tıklamak listeyi kapatır", async () => {
    ayarlaEvents({ data: { events: [ev("e1", "esma", ["src/backend/x.py"])] } });
    const user = await acVeMatrisiKur();
    const hucre = screen.getByRole("button", { name: /esma, backend: 2 dokunuş/ });
    await user.click(hucre);
    expect(screen.getByLabelText("esma → backend olayları")).toBeInTheDocument();
    await user.click(hucre);
    expect(screen.queryByLabelText("esma → backend olayları")).not.toBeInTheDocument();
  });

  it("olay listesi hatası: sessizce yutulmaz, teknik ayrıntı basar", async () => {
    ayarlaEvents({ data: undefined, error: { message: "Failed to fetch" } });
    const user = await acVeMatrisiKur();
    await user.click(screen.getByRole("button", { name: /esma, backend: 2 dokunuş/ }));
    await waitFor(() => {
      expect(screen.getByText(/Olay listesine ulaşılamadı/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Failed to fetch/)).toBeInTheDocument();
  });

  it("✕ ile kapatılır", async () => {
    ayarlaEvents({ data: { events: [ev("e1", "esma", ["src/backend/x.py"])] } });
    const user = await acVeMatrisiKur();
    await user.click(screen.getByRole("button", { name: /esma, backend: 2 dokunuş/ }));
    await user.click(screen.getByLabelText("Olay listesini kapat"));
    expect(screen.queryByLabelText("esma → backend olayları")).not.toBeInTheDocument();
  });
});

describe("IsiMatrisi — derin inceleme linki (#104 /graph, ölü link değil)", () => {
  it("aktif Graf route'una link verir", async () => {
    ayarlaGraph({ data: { window_days: 14, nodes: [], edges: [kenar("esma", "backend", 1)] } });
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /Aktör × modül ısı matrisi/ }));
    const link = screen.getByRole("link", { name: "Dokunma grafı" });
    expect(link).toHaveAttribute("href", "/graph");
  });
});

describe("IsiMatrisi — GraphNode.actor_verified göstergesi (#296)", () => {
  async function acVeMatrisiKur() {
    ayarlaGraph({
      data: {
        window_days: 14,
        nodes: [
          dugum("esma6", "actor", 2, true),
          dugum("Merge Simulation", "actor", 1, false),
          dugum("backend", "module", 3, true),
        ],
        edges: [
          kenar("esma6", "backend", 2),
          kenar("Merge Simulation", "backend", 1),
        ],
      },
    });
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /Aktör × modül ısı matrisi/ }));
    return user;
  }

  it("satır başlığı: yalnız eşleşmeyen aktörde rozet var", async () => {
    await acVeMatrisiKur();
    const grup = screen.getByRole("group", { name: /dokunma matrisi/ });
    const merge = within(grup).getByText("Merge Simulation").closest("div");
    const esma = within(grup).getByText("esma6").closest("div");
    expect(merge?.querySelector('[data-testid="actor-unverified-badge"]')).not.toBeNull();
    expect(esma?.querySelector('[data-testid="actor-unverified-badge"]')).toBeNull();
  });

  it("olay listesi paneli açılınca (hücre tıklama) eşleşmeyen aktörde rozet görünür", async () => {
    ayarlaEvents({ data: { events: [ev("e1", "Merge Simulation", ["src/backend/x.py"])] } });
    const user = await acVeMatrisiKur();
    await user.click(screen.getByRole("button", { name: /Merge Simulation, backend: 1 dokunuş/ }));
    const panel = screen.getByLabelText("Merge Simulation → backend olayları").closest("div");
    expect(panel?.querySelector('[data-testid="actor-unverified-badge"]')).not.toBeNull();
  });

  it("actor_verified alanı hiç yoksa (eski/mock veri): doğrulanmış sayılır", async () => {
    ayarlaGraph({
      data: {
        window_days: 14,
        nodes: [],
        edges: [kenar("esma", "backend", 1)],
      },
    });
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /Aktör × modül ısı matrisi/ }));
    expect(screen.queryByTestId("actor-unverified-badge")).toBeNull();
  });
});
