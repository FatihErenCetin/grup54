import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import "./index.css";

// Polling konvansiyonu (#20): aralık/odak davranışı usePolling'de — burada
// yalnız tek paylaşılan client (cache tüm sayfalar için ortak).
const queryClient = new QueryClient();

/* Lazy route'lar (#19 kabul kriteri): her sayfa kendi chunk'ında —
   gerçek sayfalar büyüdükçe (#21+) ilk yükleme küçük kalır. */
const RadarPage = lazy(() => import("./pages/RadarPage"));
const BoardPage = lazy(() => import("./pages/BoardPage"));
const ScopePage = lazy(() => import("./pages/ScopePage"));
const GraphPage = lazy(() => import("./pages/GraphPage"));
const ActivityPage = lazy(() => import("./pages/ActivityPage"));
const AskPage = lazy(() => import("./pages/AskPage"));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense
          fallback={
            <div className="p-8 text-sm text-muted-foreground">Yükleniyor…</div>
          }
        >
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<RadarPage />} />
              <Route path="board" element={<BoardPage />} />
              <Route path="scope" element={<ScopePage />} />
              <Route path="graph" element={<GraphPage />} />
              <Route path="activity" element={<ActivityPage />} />
              <Route path="ask" element={<AskPage />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
