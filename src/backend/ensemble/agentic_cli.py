"""Agentic aksiyonu ELDE calistiran giris noktasi (#339, D-61).

    uv run python -m ensemble.agentic_cli            # yerel
    docker compose exec api python -m ensemble.agentic_cli   # uretim (VDS)

**Neden HTTP ucu degil, modul girisi:** ikisi arasinda secim yaparken belirleyici
olan "hangisi GERCEKTEN kosturulabilir" oldu.
  * Bir `POST /agentic/...` ucu `openapi.json` + `schema.d.ts` yeniden uretimi
    (`make contracts`) gerektirir ve bu isle es zamanli acik PR'larla ayni
    uretilmis dosyalari catistirir.
  * `python -m ...` yolu uretim IMAJINDA calisir: `Dockerfile` `src/backend/`i
    kopyalar ve `uv sync` ile `ensemble` paketini `/app/.venv`e KURAR; `PATH`
    zaten `/app/.venv/bin`. Yani ekstra bir dosya kopyalanmasi GEREKMEZ.
    (Bunun aksi bir tuzak daha once yasandi: bir runbook adimi `make` cagiriyordu
    ama `Makefile` imaja HIC kopyalanmiyordu — testler yesil, is canliya inemez.)

Bu giris FAIL-CLOSED bir kapi tasir: gercek bir GitHub App yoksa
(`FakeGitHubAdapter`e dusulmusse) GERCEK yazma REDDEDILIR. Aksi halde "3 yorum
yazildi" diye rapor eder ve hicbir sey olmamis olurdu — `store/rebuild.py`
`__main__` kapisinin (D-51) ayni ruhu.
"""

from __future__ import annotations

import argparse
import logging
import sys

from ensemble.engine.agentic import AgenticActionService, AgenticRunResult

logger = logging.getLogger("ensemble.agentic_cli")

_KAPI_HATASI = 2


def _ayristirici() -> argparse.ArgumentParser:
    ayristirici = argparse.ArgumentParser(
        prog="python -m ensemble.agentic_cli",
        description=(
            "Radar'in yuksek siddetli (severity=high) cakisma tespitleri icin "
            "ilgili ACIK PR'lara gerekceli uyari yorumu birakir. Varsayilan "
            "yapilandirmada (AGENTIC_ACTIONS_ENABLED=false) hicbir sey yapmaz."
        ),
    )
    ayristirici.add_argument(
        "--kuru-calisma",
        action="store_true",
        help=(
            "Yapilandirma ne olursa olsun KURU calis (yazma yok, yalniz log). "
            "Yalnizca guvenli yonde etki eder — bu bayrakla gercek yazma ACILAMAZ."
        ),
    )
    return ayristirici


def _rapor(sonuc: AgenticRunResult) -> str:
    satirlar = [
        "=== Ensemble agentic aksiyon raporu ===",
        f"enabled          : {sonuc.enabled}",
        f"dry_run          : {sonuc.dry_run}",
        f"yuksek tespit    : {sonuc.yuksek_tespit}",
        f"yazilan yorum    : {sonuc.yazilan}",
        f"kuru calisma     : {sonuc.kuru_calisma}",
        f"hata             : {len(sonuc.hatalar)}",
        f"sinir nedeniyle atlanan : {len(sonuc.sinir_asilanlar)}",
    ]
    for outcome in sonuc.outcomes:
        hedef = f"PR #{outcome.pr_number}" if outcome.pr_number is not None else "hedef yok"
        satirlar.append(f"  - {outcome.sonuc:<13} {hedef:<10} {outcome.detection_id} {outcome.detay}")
    return "\n".join(satirlar)


def main(argv: list[str] | None = None) -> int:
    args = _ayristirici().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Agir import'lar BILEREK fonksiyon icinde: `--help` (ve bu modulun sadece
    # import edilmesi) FastAPI/DB/vektor yigin kurulumunu tetiklemesin.
    from ensemble.app import _build_radar_service
    from ensemble.config import get_settings
    from ensemble.integrations.github.fake import FakeGitHubAdapter
    from ensemble.store.engine import get_engine, get_session_factory

    settings = get_settings()
    session_factory = get_session_factory(get_engine(settings))
    radar_service = _build_radar_service(settings, session_factory=session_factory)
    github_port = radar_service.github_port

    servis = AgenticActionService.from_settings(
        settings, github_port, dry_run_zorla=args.kuru_calisma
    )

    if servis.enabled and not servis.dry_run and isinstance(github_port, FakeGitHubAdapter):
        print(
            "REDDEDILDI: gercek GitHub App yapilandirmasi yok (FakeGitHubAdapter'e "
            "dusuldu) ama GERCEK yazma istendi. Sahte adapter'a yazmak 'yazildi' "
            "diye raporlanir ve hicbir sey olmaz. GITHUB_APP_* degerlerini "
            "tamamla ya da AGENTIC_ACTIONS_DRY_RUN=true birak.",
            file=sys.stderr,
        )
        return _KAPI_HATASI

    sonuc = servis.run(radar_service.collect())
    print(_rapor(sonuc))

    # Cikis kodu: hata varsa 1. Sessiz basari YOK — bir cron/systemd timer bu
    # kodu gorur, log'u kimse okumasa bile.
    return 1 if sonuc.hatalar else 0


if __name__ == "__main__":
    raise SystemExit(main())
