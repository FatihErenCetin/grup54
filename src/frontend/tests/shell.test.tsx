/** #19 duman testleri — kabuk render oluyor mu, 6 kalem yerinde mi, config sağlam mı. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import AppLayout from "../src/components/AppLayout";
import { RadarPage } from "../src/pages";
import { config } from "../src/lib/config";

function renderShell(path = "/") {
  // #21'den beri RadarPage veri hook'u kullanıyor → gerçek uygulamadaki gibi provider şart
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<RadarPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("app shell", () => {
  it("sidebar 6 kalemle render olur", () => {
    renderShell();
    for (const label of ["Radar", "Board", "Scope", "Graf", "Activity", "Ask"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("Ensemble")).toBeInTheDocument();
  });

  it("açılış sayfası Radar'ı yükler (ölü link yok)", () => {
    renderShell();
    // jsdom'da backend yok → ilk kare loading iskeleti; sayfanın kendisi #21 testlerinde
    expect(screen.getByLabelText("Radar yükleniyor")).toBeInTheDocument();
  });
});

describe("config (tipli env — tek giriş noktası)", () => {
  it("varsayılan API adresi geçerli bir origin", () => {
    expect(config.apiBaseUrl).toBe("http://localhost:8000");
    expect(config.mode).toBe("local");
  });
});
