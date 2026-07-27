/** #33 · #272 — Activity sayfası: dört durum dalı + gruplama + UTC parse kilidi.
 *
 * Review bulgusu (Semih): 166 satırlık yeni UI'da tek test yoktu ve
 * `new Date(iso)` naive-UTC damgayı tarayıcı YEREL saati sanıyordu —
 * Europe/Istanbul'da 3 saat kayma ve yanlış GÜN başlığı.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ActivityPage from "../src/pages/ActivityPage";

/* `useEvents` -> `usePolling` -> `api.GET` zincirini en dışından sahteliyoruz:
   sayfanın kendi durum dallarını ölçmek istiyoruz, HTTP katmanını değil. */
const durum = vi.hoisted(() => ({
  data: undefined as unknown,
  error: null as unknown,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: 0,
}));

vi.mock("../src/lib/useEvents", () => ({
  useEvents: () => durum,
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function ayarla(yeni: Partial<typeof durum>) {
  Object.assign(durum, {
    data: undefined,
    error: null,
    isLoading: false,
    isFetching: false,
    dataUpdatedAt: 0,
    ...yeni,
  });
}

function ev(id: string, actor: string, ts: string, type = "commit") {
  return { id, type, actor, branch: `T-${id}`, files: ["src/x.py"], ts, ref: id };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ActivityPage — dört durum dalı", () => {
  it("yükleniyor: iskelet gösterir", () => {
    ayarla({ isLoading: true });
    render(<ActivityPage />, { wrapper });
    expect(screen.getByLabelText(/Olay akışı yükleniyor/i)).toBeTruthy();
  });

  it('error="" (falsy) bile HATA sayılır — sessizce yutulmaz', async () => {
    // MUTASYON KİLİDİ: `error != null` -> `if (error)` yapılırsa bu test kırılır.
    // openapi-fetch boş gövdeli non-ok yanıtta error olarak "" verebiliyor;
    // falsy olduğu için `if (error)` onu görmez ve sayfa "boş feed" gibi görünür.
    ayarla({ error: "", data: undefined });
    render(<ActivityPage />, { wrapper });
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
  });

  it("boş sonuç HATA DEĞİL — dürüst boş durum gösterir", () => {
    ayarla({ data: { events: [], latest_ts: null } });
    render(<ActivityPage />, { wrapper });
    expect(screen.getByText(/Henüz olay yok/i)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("veri varken geçici poll hatası listeyi GİZLEMEZ", () => {
    ayarla({ data: { events: [ev("e1", "esma", "2026-07-27T09:00:00")] }, error: "geçici" });
    render(<ActivityPage />, { wrapper });
    expect(screen.getByLabelText("esma olayları")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("ActivityPage — gruplama", () => {
  it("gün ve aktör bazında gruplar", () => {
    ayarla({
      data: {
        events: [
          ev("e1", "esma", "2026-07-27T09:00:00"),
          ev("e2", "esma", "2026-07-27T10:00:00"),
          ev("e3", "enes", "2026-07-27T11:00:00"),
        ],
      },
    });
    render(<ActivityPage />, { wrapper });
    // İki ayrı aktör kutusu; esma'nınkinde iki olay.
    expect(screen.getByLabelText("esma olayları").children.length).toBe(2);
    expect(screen.getByLabelText("enes olayları").children.length).toBe(1);
  });

  it("bozuk tarih ekrana 'Invalid Date' basmaz", () => {
    ayarla({ data: { events: [ev("e1", "esma", "bozuk-tarih")] } });
    render(<ActivityPage />, { wrapper });
    expect(screen.queryByText(/Invalid Date/i)).toBeNull();
    expect(screen.getByText(/Tarihi okunamayan olaylar/i)).toBeTruthy();
  });
});

describe("ActivityPage — naive-UTC parse (review blocker'ı)", () => {
  it("zone eki olmayan damgayı UTC sayar, yerel saat SANMAZ", () => {
    // Backend `"2026-07-27T22:30:00"` üretiyor (Z YOK).
    //   new Date(iso)      -> Europe/Istanbul'da 27 Tem 22:30  (YANLIŞ)
    //   new Date(iso+"Z")  -> Europe/Istanbul'da 28 Tem 01:30  (DOĞRU)
    // MUTASYON KİLİDİ: parseUtc'yi `new Date(iso)`'ya geri çevir -> kırılır.
    const naive = "2026-07-27T22:30:00";
    expect(new Date(`${naive}Z`).toISOString()).toBe("2026-07-27T22:30:00.000Z");

    ayarla({ data: { events: [ev("e1", "esma", naive)] } });
    render(<ActivityPage />, { wrapper });

    const beklenen = new Date(`${naive}Z`).toLocaleTimeString("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
    });
    expect(screen.getByText(beklenen)).toBeTruthy();

    // Naive parse edilseydi gösterilecek olan saat EKRANDA OLMAMALI.
    const yanlis = new Date(naive).toLocaleTimeString("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
    });
    if (yanlis !== beklenen) {
      expect(screen.queryByText(yanlis)).toBeNull();
    }
  });

  it("zone eki OLAN damgayı bozmaz (çift Z eklemez)", () => {
    ayarla({ data: { events: [ev("e1", "esma", "2026-07-27T22:30:00Z")] } });
    render(<ActivityPage />, { wrapper });
    expect(screen.queryByText(/Invalid Date/i)).toBeNull();
    expect(screen.getByLabelText("esma olayları")).toBeTruthy();
  });

  it("sıralama epoch üzerinden — naive/aware karışımı bozmaz", () => {
    // String karşılaştırması bu ikisini yanlış sıralardı ('Z' > rakam).
    ayarla({
      data: {
        events: [
          ev("eski", "esma", "2026-07-27T09:00:00Z"),
          ev("yeni", "esma", "2026-07-27T10:00:00"),
        ],
      },
    });
    render(<ActivityPage />, { wrapper });
    const liste = screen.getByLabelText("esma olayları");
    // En yeni önce: 10:00 satırı ilk sırada olmalı.
    expect(liste.children[0].textContent).toContain("T-yeni");
  });
});
