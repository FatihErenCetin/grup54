import { Link } from "react-router-dom";

/* 404 (#316/H2) — eskiden `main.tsx`'te catch-all rota YOKTU: `/graf` gibi
   yanlış bir yol (doğrusu `/graph`) hiçbir route'a eşleşmiyordu, `<Routes>`
   HİÇBİR ŞEY render etmiyordu — kabuk (sidebar/topbar) bile çizilmeden
   TAMAMEN boş ekran (canlıda doğrulandı, 2026-07-28). Bu sayfa AppLayout'un
   İÇİNDEKİ layout route'un son çocuğu (`path="*"`, main.tsx) → sidebar/topbar
   HER ZAMAN görünür kalır, yalnız içerik "böyle bir sayfa yok" der. */
export default function NotFoundPage() {
  return (
    <div className="mx-auto mt-16 max-w-md text-center">
      <h1 className="text-base font-semibold">Böyle bir sayfa yok</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Aradığın adres bulunamadı ya da taşındı — yazım hatası olabilir mi?
      </p>
      <Link
        to="/radar"
        className="mt-6 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
      >
        Radar'a dön
      </Link>
    </div>
  );
}
