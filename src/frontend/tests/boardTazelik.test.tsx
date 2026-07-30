/** #331 (c) — board SAHTE tazelik sinyali basmayacak.
 *
 * Eski hâl: `<SonGuncelleme dataUpdatedAt={dataUpdatedAt} />` istemcinin fetch
 * saatini "Son güncelleme" diye basıyordu. O saat her poll'da tazelenir; board
 * günlerce bayat olsa bile kullanıcı "az önce güncellendi" görüyordu. Gerçek
 * veri yaşı (`last_transition_at`) ve kaynak (`source`) yanıtta ZATEN vardı.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import BoardPage, { BoardTazeligi, yasMetni } from "../src/pages/BoardPage";

/* Sayfanın KABLOLAMASINI de ölçmek için `useBoard` en dıştan sahtelenir —
   yalnız bileşeni izole test etmek, "bileşen doğru ama sayfa onu hiç
   çağırmıyor" hatasını (yani bu issue'nun ta kendisini) yakalayamazdı. */
const durum = vi.hoisted(() => ({
  data: undefined as unknown,
  error: null as unknown,
  isLoading: false,
  isFetching: false,
  dataUpdatedAt: 0,
}));

vi.mock("../src/lib/useBoard", () => ({ useBoard: () => durum }));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

// Canlıdan alınmış gerçek değer (29 Tem ölçümü): board'un en taze verisi
// 28 Tem 11:59 UTC idi — yani ~1 gün bayat, ama ekranda "az önce" yazıyordu.
const GERCEK_SON_GECIS = "2026-07-28T11:59:10";
const SIMDI = Date.parse("2026-07-29T12:00:00Z");

describe("BoardTazeligi", () => {
  it("İSTEMCİ fetch saatini değil GERÇEK veri yaşını basar", () => {
    render(
      <BoardTazeligi
        lastTransitionAt={GERCEK_SON_GECIS}
        source="ingest"
        // Fetch saati "şimdi": eski bileşen bunu "Son güncelleme" diye basardı.
        dataUpdatedAt={SIMDI}
        simdi={SIMDI}
      />,
    );

    // Veri yaşı gerçek: 1 gün önce. "az önce" ÇIKMAMALI.
    expect(screen.getByText(/1 gün önce/)).toBeTruthy();
    expect(screen.queryByText(/az önce/)).toBeNull();
    // Fetch saati SİLİNMEDİ ama artık "son çekim" diye DOĞRU adlandırılıyor;
    // "Son güncelleme" ifadesi veri yaşı sanılacağı için kalkmalı.
    expect(screen.getByText(/son çekim:/)).toBeTruthy();
    expect(screen.queryByText(/Son güncelleme/)).toBeNull();
  });

  it("kaynak (source) görünür: ingest", () => {
    render(
      <BoardTazeligi
        lastTransitionAt={GERCEK_SON_GECIS}
        source="ingest"
        dataUpdatedAt={SIMDI}
        simdi={SIMDI}
      />,
    );
    expect(screen.getByText(/kaynak: ingest/)).toBeTruthy();
  });

  it("hiç geçiş işlenmemişse SESSİZ KALMAZ: 'yalnız tohum' der", () => {
    render(
      <BoardTazeligi lastTransitionAt={null} source="seed" dataUpdatedAt={SIMDI} simdi={SIMDI} />,
    );
    expect(screen.getByText(/kaynak: yalnız tohum/)).toBeTruthy();
    expect(screen.getByText(/hiç geçiş işlenmedi/)).toBeTruthy();
  });

  it("zone eki OLMAYAN damga UTC kabul edilir (yerel saat sanılıp yaş kaymaz)", () => {
    // Backend `last_transition_at`i naive-UTC olarak döner ("...T11:59:10").
    // `new Date(iso)` bunu YEREL saat sayar; TZ=+03'te yaş 3 saat KÜÇÜK çıkardı.
    render(
      <BoardTazeligi
        lastTransitionAt="2026-07-29T09:00:00"
        source="ingest"
        dataUpdatedAt={SIMDI}
        simdi={Date.parse("2026-07-29T12:00:00Z")}
      />,
    );
    expect(screen.getByText(/3 sa önce/)).toBeTruthy();
  });

  it("bozuk damgada 'Invalid Date' basmaz", () => {
    render(
      <BoardTazeligi
        lastTransitionAt="bozuk-damga"
        source="ingest"
        dataUpdatedAt={SIMDI}
        simdi={SIMDI}
      />,
    );
    expect(screen.getByText(/okunamadı/)).toBeTruthy();
    expect(screen.queryByText(/Invalid Date/)).toBeNull();
  });
});

describe("BoardPage kablolaması", () => {
  it("sayfa GERÇEK last_transition_at + source'u bileşene geçirir", () => {
    Object.assign(durum, {
      data: {
        cards: [
          { task_id: "T-1", title: "X", status: "done", assignee: null, ref: "#1" },
        ],
        last_transition_at: GERCEK_SON_GECIS,
        source: "ingest",
      },
      error: null,
      isLoading: false,
      isFetching: false,
      // İstemci fetch saati "şimdi" — eski kablolama bunu basıyordu.
      dataUpdatedAt: SIMDI,
    });

    render(<BoardPage />, { wrapper });

    expect(screen.getByText(/kaynak: ingest/)).toBeTruthy();
    // Yanıttaki 28 Tem damgası ekranda: fetch saati (29 Tem 12:00) DEĞİL.
    expect(screen.getByText(/28 Tem/)).toBeTruthy();
    expect(screen.queryByText(/Son güncelleme/)).toBeNull();
  });
});

describe("yasMetni", () => {
  it("gün eşiğini ayrı sayar (board bayatlığı saatle değil GÜNLE ölçülüyordu)", () => {
    expect(yasMetni(30_000)).toBe("az önce");
    expect(yasMetni(5 * 60_000)).toBe("5 dk önce");
    expect(yasMetni(3 * 3600_000)).toBe("3 sa önce");
    expect(yasMetni(50 * 3600_000)).toBe("2 gün önce");
  });
});
