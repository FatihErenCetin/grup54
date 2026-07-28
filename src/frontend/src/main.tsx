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
const LandingPage = lazy(() => import("./pages/LandingPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const RegisterPage = lazy(() => import("./pages/RegisterPage"));
const RadarPage = lazy(() => import("./pages/RadarPage"));
const BoardPage = lazy(() => import("./pages/BoardPage"));
const ScopePage = lazy(() => import("./pages/ScopePage"));
const GraphPage = lazy(() => import("./pages/GraphPage"));
const ActivityPage = lazy(() => import("./pages/ActivityPage"));
const AskPage = lazy(() => import("./pages/AskPage"));
const ActorPage = lazy(() => import("./pages/ActorPage"));
const RepoSeciciPage = lazy(() => import("./pages/RepoSeciciPage"));

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
            {/* Landing + Login + Kayıt: AppLayout DIŞINDA (#260 — tasarım
                paketi: "app dışında yaşar, sidebar'a girmez"). Statik/kimliksiz
                sayfalar (T-294: /kayit email+parola üyeliğinin giriş noktası). */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/kayit" element={<RegisterPage />} />
            <Route element={<AppLayout />}>
              <Route path="radar" element={<RadarPage />} />
              <Route path="board" element={<BoardPage />} />
              <Route path="scope" element={<ScopePage />} />
              <Route path="graph" element={<GraphPage />} />
              <Route path="activity" element={<ActivityPage />} />
              <Route path="ask" element={<AskPage />} />
              {/* #129 — aktör hub'ı; sidebar'da YOK (ActorChip'lerden linklenir) */}
              <Route path="actors/:handle" element={<ActorPage />} />
              {/* #79/T-79 — repo seçici; sidebar'da YOK (topbar'daki aktif
                  kiracı göstergesinden linklenir, ActorPage kalıbının aynısı) */}
              <Route path="repolar" element={<RepoSeciciPage />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
