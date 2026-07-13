/** #20 testleri — polling konvansiyonu + SonGuncelleme (gerçek dataUpdatedAt). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { SonGuncelleme } from "../src/components/ui";
import { POLL_INTERVAL_MS, pollingOptions, usePolling } from "../src/lib/usePolling";

function wrapper({ children }: { children: ReactNode }) {
  // retry kapalı: hata yolu testi 3 deneme beklemesin
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("pollingOptions — konvansiyonun kendisi", () => {
  // Bu test konvansiyonu KİLİTLER: biri interval'i silerse/arka planı açarsa kırılır
  // (adversarial doğrulama bulgusu: çekirdek davranış hiçbir yerde assert edilmiyordu)
  it("10sn aralık + arka planda durur + odakta tazeler", () => {
    const opts = pollingOptions(["k"], async () => ({ data: 1 }));
    expect(opts.refetchInterval).toBe(POLL_INTERVAL_MS);
    expect(POLL_INTERVAL_MS).toBe(10_000);
    expect(opts.refetchIntervalInBackground).toBe(false);
    expect(opts.refetchOnWindowFocus).toBe(true);
  });

  it("boş cevabı (error da data da yok) sessizce yutmaz, fırlatır", async () => {
    const opts = pollingOptions(["k"], async () => ({}));
    await expect(opts.queryFn()).rejects.toThrow("Boş cevap");
  });
});

describe("usePolling", () => {
  it("başarılı fetch'te veriyi ve GERÇEK dataUpdatedAt'i verir", async () => {
    const before = Date.now();
    const { result } = renderHook(
      () => usePolling(["test-ok"], async () => ({ data: { answer: 42 } })),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toEqual({ answer: 42 }));
    expect(result.current.dataUpdatedAt).toBeGreaterThanOrEqual(before);
  });

  it("openapi-fetch tarzı {error} dönüşünü react-query hatasına çevirir", async () => {
    const { result } = renderHook(
      () => usePolling(["test-err"], async () => ({ error: { detail: "patladı" } })),
      { wrapper },
    );
    await waitFor(() => expect(result.current.error).toEqual({ detail: "patladı" }));
    expect(result.current.data).toBeUndefined();
  });
});

describe("SonGuncelleme", () => {
  it("veri yokken (0) dürüst boş durum basar", () => {
    render(<SonGuncelleme dataUpdatedAt={0} />);
    expect(screen.getByText("Henüz veri yok")).toBeInTheDocument();
  });

  it("gerçek zamanı yerel saat olarak basar (uydurma değil)", () => {
    const ts = new Date(2026, 6, 12, 15, 4, 5).getTime(); // yerel 15:04:05
    render(<SonGuncelleme dataUpdatedAt={ts} />);
    expect(screen.getByText(/Son güncelleme: 15:04:05/)).toBeInTheDocument();
  });
});
