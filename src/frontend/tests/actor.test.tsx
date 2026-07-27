/** #129 testleri — kimlik bloğu (insan/ajan + pair zinciri) · presence beyan yaşı ·
 * 3 aktivite bloğunun client-side süzmesi · boş durumlar · falsy-error kilidi. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import ActivityPage from "../src/pages/ActivityPage";
import ActorPage from "../src/pages/ActorPage";

/* Dört uç da en dışından sahtelenir (ActivityPage testindeki kalıpla aynı):
   sayfanın kendi süzme/durum mantığını ölçüyoruz, HTTP katmanını değil. */
const bos = { data: undefined as unknown, error: null as unknown, isLoading: false, isFetching: false, dataUpdatedAt: 0 };

const durumlar = vi.hoisted(() => ({
  events: { data: undefined as unknown, error: null as unknown, isLoading: false, isFetching: false, dataUpdatedAt: 0 },
  board: { data: undefined as unknown, error: null as unknown, isLoading: false, isFetching: false, dataUpdatedAt: 0 },
  radar: { data: undefined as unknown, error: null as unknown, isLoading: false, isFetching: false, dataUpdatedAt: 0 },
  presence: { data: undefined as unknown, error: null as unknown, isLoading: false, isFetching: false, dataUpdatedAt: 0 },
}));

vi.mock("../src/lib/useEvents", () => ({ useEvents: () => durumlar.events }));
vi.mock("../src/lib/useBoard", () => ({ useBoard: () => durumlar.board }));
vi.mock("../src/lib/useRadar", () => ({ useRadar: () => durumlar.radar }));
vi.mock("../src/lib/usePresence", () => ({ usePresence: () => durumlar.presence }));

type Durum = typeof bos;

function ayarla(partial: {
  events?: Partial<Durum>;
  board?: Partial<Durum>;
  radar?: Partial<Durum>;
  presence?: Partial<Durum>;
}) {
  durumlar.events = { ...bos, ...partial.events };
  durumlar.board = { ...bos, ...partial.board };
  durumlar.radar = { ...bos, ...partial.radar };
  durumlar.presence = { ...bos, ...partial.presence };
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderActor(handle: string) {
  return render(
    <MemoryRouter initialEntries={[`/actors/${handle}`]}>
      <Routes>
        <Route path="/actors/:handle" element={<ActorPage />} />
        <Route path="/activity" element={<ActivityPage />} />
      </Routes>
    </MemoryRouter>,
    { wrapper },
  );
}

function ev(id: string, actor: string, type = "commit") {
  return { id, type, actor, branch: `T-${id}`, files: ["src/x.py"], ts: "2026-07-27T09:00:00", ref: id };
}

type KartDurumu = "backlog" | "todo" | "in_progress" | "in_review" | "done";

function kart(taskId: string, assignee: string | null, status: KartDurumu = "in_progress") {
  return { task_id: taskId, title: `Başlık ${taskId}`, status, assignee, ref: null };
}

function tespit(id: string, actors: string[]) {
  return {
    id,
    kind: "conflict" as const,
    actors,
    branches: ["T-1"],
    files: ["src/backend/ensemble/engine/x.py"],
    severity: "med" as const,
    confidence: 0.7,
    rationale: `${id} gerekçesi`,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  ayarla({});
});

describe("ActorPage — kimlik bloğu", () => {
  it("insan varyantı: 'insan' etiketi, AI rozeti ve 'yapamaz' listesi YOK", () => {
    ayarla({
      events: { data: { events: [], latest_ts: null } },
      board: { data: { cards: [] } },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: { data: { entries: [], latest_ts: "x" } },
    });
    renderActor("asmarufoglu");
    expect(screen.getAllByText("asmarufoglu").length).toBeGreaterThan(0);
    expect(screen.getByText("insan")).toBeInTheDocument();
    expect(screen.queryByText("AI ajanı")).not.toBeInTheDocument();
    expect(screen.queryByText("Bu ajan yapamaz")).not.toBeInTheDocument();
  });

  it("ajan varyantı (presence aktif): kare rozet + gerçek pair zinciri (sezgi değil)", () => {
    ayarla({
      events: { data: { events: [], latest_ts: null } },
      board: { data: { cards: [] } },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: {
        data: {
          entries: [
            {
              actor: { handle: "fatih-claude", type: "agent", responsible: "FatihErenCetin" },
              module: "frontend",
              task: "T-129",
              branch: "T-129-aktor-gorunumu",
              since: "2026-07-27T08:55:00Z",
            },
          ],
          latest_ts: "x",
        },
        dataUpdatedAt: new Date("2026-07-27T09:00:00Z").getTime(),
      },
    });
    renderActor("fatih-claude");
    expect(screen.getByText("AI ajanı")).toBeInTheDocument();
    expect(screen.getByText(/eller: fatih-claude · sorumlu: FatihErenCetin/)).toBeInTheDocument();
    expect(screen.getByText("Bu ajan yapamaz")).toBeInTheDocument();
    // sezgi notu GÖRÜNMEZ — tip presence'tan GERÇEK geldi
    expect(screen.queryByText(/handle sonekinden sezildi/)).not.toBeInTheDocument();
    expect(screen.getByText(/beyan yaşı/)).toBeInTheDocument();
  });

  it("ajan varyantı (presence'ta AKTİF değil): sezgiyle tip + 'beyan yok' — uydurma responsible YAZILMAZ", () => {
    ayarla({
      events: { data: { events: [], latest_ts: null } },
      board: { data: { cards: [] } },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: { data: { entries: [], latest_ts: "x" } },
    });
    renderActor("fatih-claude"); // -claude soneki → sezgiyle ajan
    expect(screen.getByText("AI ajanı")).toBeInTheDocument();
    expect(screen.getByText(/handle sonekinden sezildi/)).toBeInTheDocument();
    // Pair zinciri boşken de GÖRÜNÜR (kabul kriteri) — uydurma isim değil, dürüst "beyan yok"
    expect(screen.getByText(/eller: fatih-claude · sorumlu: beyan yok/)).toBeInTheDocument();
  });

  it("presence hatası ('' dahil) sessizce yutulmaz — kimlik bloğu görünür kalır", () => {
    ayarla({
      events: { data: { events: [], latest_ts: null } },
      board: { data: { cards: [] } },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: { data: undefined, error: "" },
    });
    renderActor("asmarufoglu");
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Presence'a ulaşılamıyor/)).toBeInTheDocument();
  });
});

describe("ActorPage — 3 aktivite bloğu (client-side süzme, yeni endpoint yok)", () => {
  it("olaylar yalnız bu aktöre süzülür, diğer aktörün olayı görünmez", () => {
    ayarla({
      events: {
        data: {
          events: [ev("e1", "asmarufoglu"), ev("e2", "baskasi"), ev("e3", "asmarufoglu", "pr")],
          latest_ts: "x",
        },
      },
      board: { data: { cards: [] } },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: { data: { entries: [], latest_ts: "x" } },
    });
    renderActor("asmarufoglu");
    const olaylarBlok = screen.getByLabelText("asmarufoglu olayları");
    expect(within(olaylarBlok).getAllByText(/T-e/)).toHaveLength(2);
    // Başlık + sayaç ayrı text-node'larda (span iç içe) — getByText yalnız
    // DİREKT metin çocuklarına bakar, isim hesaplaması için heading rolü kullan.
    expect(screen.getByRole("heading", { name: "Olaylar (2)" })).toBeInTheDocument();
  });

  it("board kartları yalnız bu aktöre atananlar — durum rozeti görünür", () => {
    ayarla({
      events: { data: { events: [], latest_ts: null } },
      board: {
        data: {
          cards: [kart("T-1", "asmarufoglu", "in_review"), kart("T-2", "baskasi"), kart("T-3", null)],
        },
      },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: { data: { entries: [], latest_ts: "x" } },
    });
    renderActor("asmarufoglu");
    expect(screen.getByRole("heading", { name: "Board kartları (1)" })).toBeInTheDocument();
    expect(screen.getByText("T-1")).toBeInTheDocument();
    expect(screen.getByText("İncelemede")).toBeInTheDocument();
    expect(screen.queryByText("T-2")).not.toBeInTheDocument();
  });

  it("tespitler bu aktörün geçtiği çiftlere süzülür; diğer aktör çipi linkli görünür", () => {
    ayarla({
      events: { data: { events: [], latest_ts: null } },
      board: { data: { cards: [] } },
      radar: {
        data: {
          detections: [tespit("det-1", ["asmarufoglu", "fatih-claude"]), tespit("det-2", ["baskasi"])],
          updated_at: "x",
        },
      },
      presence: { data: { entries: [], latest_ts: "x" } },
    });
    renderActor("asmarufoglu");
    expect(screen.getByRole("heading", { name: "Tespitler (1)" })).toBeInTheDocument();
    expect(screen.getByText("det-1 gerekçesi")).toBeInTheDocument();
    expect(screen.queryByText("det-2 gerekçesi")).not.toBeInTheDocument();
    // diğer aktör (fatih-claude) linkli çip olarak görünür, kendisi (asmarufoglu) tekrar edilmez orada
    const link = screen.getByRole("link", { name: /fatih-claude/ });
    expect(link).toHaveAttribute("href", "/actors/fatih-claude");
  });

  it("her bloğun kendi 'ulaşılamıyor' hatası vardır — falsy error ('') bile yutulmaz", () => {
    ayarla({
      events: { data: undefined, error: "" },
      board: { data: { cards: [] } },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: { data: { entries: [], latest_ts: "x" } },
    });
    renderActor("asmarufoglu");
    expect(screen.getByText("Bu aktörün olaylarına ulaşılamıyor")).toBeInTheDocument();
  });

  it("kart/radar deep-link'leri handle'ı query-param olarak taşır", () => {
    ayarla({
      events: { data: { events: [], latest_ts: null } },
      board: { data: { cards: [] } },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: { data: { entries: [], latest_ts: "x" } },
    });
    renderActor("asmarufoglu");
    expect(screen.getByRole("link", { name: "Board'da gör →" })).toHaveAttribute(
      "href",
      "/board?assignee=asmarufoglu",
    );
    expect(screen.getByRole("link", { name: "Radar'da gör →" })).toHaveAttribute(
      "href",
      "/radar?actor=asmarufoglu",
    );
  });
});

describe("ActorPage — boş durum (dört uç da başarıyla döndü, hepsi boş)", () => {
  it("insan: dürüst 3-adım davet — 404 gibi davranmaz", () => {
    ayarla({
      events: { data: { events: [], latest_ts: null } },
      board: { data: { cards: [] } },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: { data: { entries: [], latest_ts: "x" } },
    });
    renderActor("hicKimse");
    expect(screen.getByText("Henüz aktivite yok")).toBeInTheDocument();
    expect(screen.getByText(/3\) PR aç/)).toBeInTheDocument();
  });

  it("herhangi bir uç henüz dönmediyse (isLoading) sahte 'boş' denmez", () => {
    ayarla({
      events: { isLoading: true, data: undefined },
      board: { data: { cards: [] } },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: { data: { entries: [], latest_ts: "x" } },
    });
    renderActor("hicKimse");
    expect(screen.queryByText("Henüz aktivite yok")).not.toBeInTheDocument();
  });
});

describe("ActorPage — ActorChip navigasyonu (#129 kabul kriteri: çip tıklanabilir)", () => {
  it("Activity'deki aktör çipine tıklamak /actors/:handle'a götürür", async () => {
    const user = userEvent.setup();
    ayarla({
      events: { data: { events: [ev("e1", "esma")], latest_ts: null } },
      board: { data: { cards: [] } },
      radar: { data: { detections: [], updated_at: "x" } },
      presence: { data: { entries: [], latest_ts: "x" } },
    });
    render(
      <MemoryRouter initialEntries={["/activity"]}>
        <Routes>
          <Route path="/activity" element={<ActivityPage />} />
          <Route path="/actors/:handle" element={<ActorPage />} />
        </Routes>
      </MemoryRouter>,
      { wrapper },
    );
    await user.click(screen.getByText("esma"));
    expect(screen.getByText("Aktör")).toBeInTheDocument();
    expect(screen.getAllByText("esma").length).toBeGreaterThan(0);
  });
});
