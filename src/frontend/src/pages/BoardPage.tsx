import { useMemo } from "react";
import type { components } from "../api/schema.d.ts";
import {
  ActorChip,
  EmptyState,
  HataDurumu,
  SonGuncelleme,
  YuklemeIskeleti,
} from "../components/ui";
import { useBoard } from "../lib/useBoard";

type BoardCard = components["schemas"]["BoardCard"];
type Status = BoardCard["status"];

/* Board sayfası (#111) — "kendiliğinden dolan pano".
   Sürükleme YOK ve olmayacak: durumu yalnız ingest yazar (projector.py MVP
   kuralı — T-<id> dalına commit → in_progress, PR → in_review, done terminal).
   Bu bir eksiklik değil, ürünün iddiası; arayüz bunu SÖYLEMEK zorunda, yoksa
   "sürükleyemiyorum" bug gibi okunur (tasarım paketi /board notu).
   Gate'li (bilinçli, eksik DEĞİL): assignee/modül filtresi + aktör swimlane
   toggle'ı (tasarım paketi) · kart detayına gidiş (/actors/:handle, S3-stretch)
   · yeniden sıralama/atama (yazma ucu yok — CRUD yasağı, D-23). */

/* Kolon sırası = akış sırası; ikon + TR etiket + renk BİRLİKTE taşınır
   (renk tek başına anlam taşımaz — D-34). Sınıflar tam literal yazılır:
   Tailwind kaynak taraması dinamik `bg-status-${x}` üretimini göremez. */
const KOLONLAR: {
  key: Status;
  etiket: string;
  ikon: string;
  cip: string;
  nokta: string;
}[] = [
  {
    key: "backlog",
    etiket: "Backlog",
    ikon: "○",
    cip: "bg-status-backlog/15 text-status-backlog",
    nokta: "bg-status-backlog",
  },
  {
    key: "todo",
    etiket: "Yapılacak",
    ikon: "◔",
    cip: "bg-status-todo/15 text-status-todo",
    nokta: "bg-status-todo",
  },
  {
    key: "in_progress",
    etiket: "Devam ediyor",
    ikon: "◑",
    cip: "bg-status-in-progress/15 text-status-in-progress",
    nokta: "bg-status-in-progress",
  },
  {
    key: "in_review",
    etiket: "İncelemede",
    ikon: "◕",
    cip: "bg-status-in-review/15 text-status-in-review",
    nokta: "bg-status-in-review",
  },
  {
    key: "done",
    etiket: "Bitti",
    ikon: "●",
    cip: "bg-status-done/15 text-status-done",
    nokta: "bg-status-done",
  },
];

/** "T-9" < "T-111" — düz string sıralaması bunu ters çevirirdi. */
function taskNo(id: string): number | null {
  const m = id.match(/\d+/);
  return m ? Number(m[0]) : null;
}

/* Backend kart sırası GARANTİLİ DEĞİL (`session.query(...).all()` — ORDER BY yok),
   yani 10 sn'lik her poll kartları yeniden dizebilir. Deterministik sıralama
   olmadan kullanıcı okurken satırlar yer değiştirir; sıralamayı UI sabitler. */
function kartSirasi(a: BoardCard, b: BoardCard): number {
  const na = taskNo(a.task_id);
  const nb = taskNo(b.task_id);
  if (na !== null && nb !== null && na !== nb) return na - nb;
  return a.task_id.localeCompare(b.task_id, "tr");
}

function DurumCipi({ kolon }: { kolon: (typeof KOLONLAR)[number] }) {
  return (
    <span
      // Rozet ölçeği ev standardı: text-xs (SeverityBadge · ScopePage karar
      // rozeti · "Kendini günceller" çipi) — text-[10px] yalnız dipnot ölçüsü.
      className={`inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${kolon.cip}`}
    >
      <span aria-hidden>{kolon.ikon}</span>
      {kolon.etiket}
    </span>
  );
}

/* Kart TIKLANABİLİR DEĞİL ve sürüklenebilir değil — bilinçli: buton/hover-lift
   vermek "buradan oynatabilirim" sözü verirdi, karşılığı yok. */
function KartOgesi({ kart, kolon }: { kart: BoardCard; kolon: (typeof KOLONLAR)[number] }) {
  return (
    <li className="rounded-lg border border-border bg-card px-3 py-2">
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-xs text-muted-foreground">{kart.task_id}</span>
        {/* Durum kartın ÜSTÜNDE de yazılı: dar ekranda kolonlar yatay kayar,
            kart başlığından koparsa ekran okuyucu durumu kaybederdi. */}
        <DurumCipi kolon={kolon} />
      </div>
      <p className="mt-1 text-sm" title={kart.title}>
        {kart.title}
      </p>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        {kart.assignee ? (
          <ActorChip handle={kart.assignee} />
        ) : (
          // Boş atama gizlenmez: "kimse almamış" gerçek bir board sinyali
          <span className="text-[11px] text-muted-foreground">Atanmamış</span>
        )}
        {kart.ref && (
          <span
            className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
            title="Kaynak referansı (.harness/tasks kaydından)"
          >
            {kart.ref}
          </span>
        )}
      </div>
    </li>
  );
}

export default function BoardPage() {
  const { data, error, isLoading, isFetching, dataUpdatedAt } = useBoard();

  // Erken-return'lerden ÖNCE (hook kuralı). `data.cards` referansı poll'lar
  // arasında sabit → memo gerçekten iş görür.
  const cards = data?.cards;
  const gruplar = useMemo(() => {
    const m = new Map<string, BoardCard[]>();
    for (const kart of cards ?? []) {
      const liste = m.get(kart.status);
      if (liste) liste.push(kart);
      else m.set(kart.status, [kart]);
    }
    for (const liste of m.values()) liste.sort(kartSirasi);
    return m;
  }, [cards]);

  // Beş kolondan hiçbirine düşmeyen durum = SESSİZCE kaybolan kart olurdu.
  // Kontrat (Literal enum) bunu yasaklıyor ama sözleşme kayarsa kullanıcı
  // eksik pano görüp fark etmez → sayıyı görünür kılıyoruz (fail-open yok).
  const bilinmeyen = useMemo(
    () =>
      [...gruplar.entries()].filter(
        ([durum]) => !KOLONLAR.some((k) => k.key === durum),
      ),
    [gruplar],
  );

  if (isLoading) {
    return <YuklemeIskeleti label="Board yükleniyor" />;
  }

  // != null: openapi-fetch boş-gövdeli non-ok cevapta error="" (falsy!) verebilir —
  // truthiness kontrolü onu yutup sahte "pano boş" basardı. data===undefined:
  // geçici tek poll hatası eldeki panoyu GİZLEMESİN (polling zaten sürüyor).
  if (error != null && data === undefined) {
    return <HataDurumu baslik="Board'a ulaşılamıyor" hata={error} />;
  }

  const toplam = cards?.length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-base font-semibold">Görev panosu</h1>
        <SonGuncelleme dataUpdatedAt={dataUpdatedAt} isFetching={isFetching} />
      </div>

      {/* Ürünün iddiası, boş panoda bile görünür kalır */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-border bg-card px-4 py-3">
        <span className="rounded bg-primary/15 px-1.5 py-0.5 text-xs font-medium text-primary">
          <span aria-hidden>⟳ </span>Kendini günceller
        </span>
        <p className="text-xs text-muted-foreground">
          Kartlar sürüklenmez — durumu ingest yazar:{" "}
          <span className="font-mono">T-&lt;id&gt;</span> dalına commit düşünce
          “Devam ediyor”, PR açılınca “İncelemede”. Kaynak:{" "}
          <span className="font-mono">.harness/tasks/</span> + GitHub olayları.
        </p>
      </div>

      {toplam === 0 ? (
        <EmptyState
          title="Pano henüz dolmadı"
          description="Bu boşluk “veri alınamadı” demek değil: uç canlı ve boş liste döndü. Burada elle kart açılmaz — her kart bir .harness/tasks/T-<id> kaydıdır; projeksiyon kurulup GitHub olayları işlendiğinde beş kolon kendiliğinden dolar."
          items={[
            "○ Backlog — task dosyası var, sıraya girmedi",
            "◔ Yapılacak — sprint kapsamına alındı",
            "◑ Devam ediyor — T-<id> dalına commit düştü",
            "◕ İncelemede — task için PR açıldı",
            "● Bitti — kapandı; ingest bu durumu geri almaz",
          ]}
          eta="Sürükleme bu panoya hiç gelmeyecek — kart oynatmak PR/issue akışının işi."
        />
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            <span className="tabular-nums">{toplam}</span> kart · beş kolon
          </p>

          {/* Yatay kaydırma Kanban'ın doğal davranışı: kolonlar 14rem altına
              inip okunmaz hâle gelmez, dar ekranda sayfa yerine ŞERİT kayar. */}
          <div className="flex gap-3 overflow-x-auto pb-2">
            {KOLONLAR.map((kolon) => {
              const kolonKartlari = gruplar.get(kolon.key) ?? [];
              return (
                <section
                  key={kolon.key}
                  aria-label={`${kolon.etiket} — ${kolonKartlari.length} kart`}
                  className="flex min-w-56 flex-1 flex-col gap-2"
                >
                  <div className="flex items-center gap-2 px-1">
                    <span aria-hidden className={`size-2 rounded-full ${kolon.nokta}`} />
                    <h2 className="text-xs font-medium">{kolon.etiket}</h2>
                    <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                      {kolonKartlari.length}
                    </span>
                  </div>

                  {kolonKartlari.length === 0 ? (
                    <p className="rounded-lg border border-dashed border-border px-3 py-2 text-[11px] text-muted-foreground">
                      Kart yok
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {kolonKartlari.map((kart) => (
                        <KartOgesi key={kart.task_id} kart={kart} kolon={kolon} />
                      ))}
                    </ul>
                  )}
                </section>
              );
            })}
          </div>

          {/* Ev kalıbı: RadarPage'in "eksik sonuç" şeridiyle aynı — ⚠ ikon +
              severity-med tonlu blok. Muted tek satır olarak basmak, "sessizce
              kaybolan kart" uyarısını görünmez kılıyordu (fail-open görünüm). */}
          {bilinmeyen.length > 0 && (
            <div
              role="alert"
              className="flex items-start gap-3 rounded-lg border border-severity-med/40 bg-severity-med/10 p-4"
            >
              <span aria-hidden className="mt-0.5 shrink-0 text-severity-med">
                ⚠
              </span>
              <div className="min-w-0 space-y-1">
                <p className="text-sm font-medium">
                  Tanınmayan durumdaki{" "}
                  <span className="tabular-nums">
                    {bilinmeyen.reduce((n, [, liste]) => n + liste.length, 0)}
                  </span>{" "}
                  kart hiçbir kolona düşmedi
                </p>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Bilinmeyen durum:{" "}
                  <span className="font-mono">
                    {bilinmeyen.map(([durum]) => durum).join(", ")}
                  </span>{" "}
                  — kontrat kaymış olabilir. Yukarıdaki pano bu kartları
                  göstermiyor; beş kolonun toplamını eksiksiz sayma.
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
