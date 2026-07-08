import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import {
  ActivityPage,
  AskPage,
  BoardPage,
  GraphPage,
  RadarPage,
  ScopePage,
} from "./pages";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
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
    </BrowserRouter>
  </StrictMode>,
);
