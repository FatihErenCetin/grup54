/** #316/H2 — main.tsx'te catch-all rota YOKTU: `/graf` gibi yanlış bir yol
 * (doğrusu `/graph`) hiçbir route'a eşleşmiyordu; `<Route element={<AppLayout
 * />}>` pathless layout route'unun HİÇBİR çocuğu eşleşmeyince React Router
 * o dalın TAMAMINI atlıyor — kabuk (sidebar/topbar) bile render olmadan
 * TAMAMEN boş ekran (canlıda doğrulandı, 2026-07-28, browse ile bir daha
 * doğrulandı: http://localhost:5183/graf).
 *
 * Test main.tsx'in KENDİSİNİ import etmez (o modül `createRoot(...).render()`
 * yan etkisiyle bootstrap eder, jsdom'da `#root` yok — import patlar). Bunun
 * yerine main.tsx'teki GERÇEK route şeklini (layout route + içinde `path="*"`
 * en sonda) burada birebir aynalıyoruz — `shell.test.tsx`'in zaten kullandığı
 * kalıp (kendi route ağacını MemoryRouter'la kurar).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import AppLayout from "../src/components/AppLayout";
import NotFoundPage from "../src/pages/NotFoundPage";
import { RadarPage } from "../src/pages";

function renderApp(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="radar" element={<RadarPage />} />
            {/* main.tsx'teki SIRAYLA aynı: catch-all EN SONDA */}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("catch-all rota (#316/H2)", () => {
  it("yanlış bir yolda (/graf) kabuk YİNE render olur, boş ekran YOK", () => {
    // MUTASYON KİLİDİ: `<Route path=\"*\" .../>` satırını sil -> bu test kırılır
    // (React Router hiçbir dalı eşleştiremez, <Routes> hiçbir şey render etmez).
    renderApp("/graf");
    // Kabuk: sidebar kalemleri hâlâ görünür (main.tsx'teki H2 öncesi bulgu
    // tam buydu — "kabuk bile çizilmiyor").
    expect(screen.getByText("Radar")).toBeInTheDocument();
    expect(screen.getByText("Ensemble")).toBeInTheDocument();
  });

  it("404 içeriği + 'Radar'a dön' bağlantısı görünür", () => {
    renderApp("/boyle-bir-yol-yok");
    expect(screen.getByRole("heading", { name: "Böyle bir sayfa yok" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Radar'a dön/ })).toHaveAttribute("href", "/radar");
  });

  it("'Radar'a dön' tıklanınca gerçekten Radar sayfasına gider", async () => {
    const user = userEvent.setup();
    renderApp("/graf");
    await user.click(screen.getByRole("link", { name: /Radar'a dön/ }));
    // jsdom'da backend yok → Radar ilk karede yükleme iskeleti basar; asıl
    // kanıt navigasyonun GERÇEKLEŞTİĞİ (404 metni kalkmış olmalı).
    expect(screen.queryByRole("heading", { name: "Böyle bir sayfa yok" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Radar yükleniyor")).toBeInTheDocument();
  });

  it("bilinen bir yol (/radar) hâlâ normal çalışır — catch-all onu YUTMAZ", () => {
    renderApp("/radar");
    expect(screen.queryByRole("heading", { name: "Böyle bir sayfa yok" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Radar yükleniyor")).toBeInTheDocument();
  });
});
