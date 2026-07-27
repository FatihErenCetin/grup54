from fastapi import APIRouter

from ensemble.api.deps import RadarServiceDep, SettingsDep
from ensemble.api.schemas import HealthResponse
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.github.adapter import GitHubAdapter

router = APIRouter(tags=["health"])

# `JudgePort` sarmalayicilarinin alt-port'u tuttugu alan adlari.
# CachedConflictJudge -> .inner (#63) · FallbackJudge -> .primary/.secondary (#255)
_SARMALAYICI_ALANLARI = ("inner", "primary", "secondary")


def _judge_zinciri(port: object) -> list[object]:
    """Sarmalanmis judge zincirindeki TUM dugumleri dondurur (kok dahil).

    Neden tek kat acmak yetmiyor (#238 canli smoke bulgusu): bu fonksiyondan
    once kod `getattr(port, "inner", port)` ile YALNIZ BIR kat aciyordu. O
    duzeltme yazildiginda tek sarmalayici vardi (CachedConflictJudge) ve
    dogruydu. #255 ikinci bir kat ekleyince (FallbackJudge) zincir
    `Cached -> Fallback -> Gemini` oldu; bir kat acinca elde `FallbackJudge`
    kaliyor ve `isinstance(..., GeminiJudgeAdapter)` False donuyordu.

    Sonuc: canli `/health` `gemini="missing"` raporladi ve `make smoke`
    (#189) STRICT modda KIRMIZI kaldi — anahtar dogru ayarlanmis olmasina
    ragmen. Yani bu, "yapilandirma yok" diye yalan soyleyen bir saglik
    kontroluydu.

    Sabit sayida kat acmak yerine zinciri YURUYORUZ: yeni bir sarmalayici
    katmani eklendiginde (or. bir rate-limiter ya da metrik sarmalayicisi)
    bu kontrol kendiliginden dogru kalir. Dongulere karsi kimlik-bazli
    ziyaret kaydi tutulur.
    """
    yigin: list[object] = [port]
    gorulen: set[int] = set()
    dugumler: list[object] = []
    while yigin:
        dugum = yigin.pop()
        if id(dugum) in gorulen:
            continue
        gorulen.add(id(dugum))
        dugumler.append(dugum)
        for alan in _SARMALAYICI_ALANLARI:
            alt = getattr(dugum, alan, None)
            if alt is not None:
                yigin.append(alt)
    return dugumler


@router.get("/health")
def health_check(settings: SettingsDep, radar_service: RadarServiceDep) -> HealthResponse:
    # Acilis-anindaki WIRING sonucunu okur (#53) - canli ag cagrisi yok, Fly
    # health-check'i aglamaz. GitHubAdapter/GeminiJudgeAdapter kurulduysa
    # "configured", Fake*'e dusulduyse "missing" (app.py wiring, #159/#186).
    # "configured" DOGRULANMIS auth anlamina GELMEZ - yalniz kimlik bilgisi
    # SET EDILMIS (review bulgusu, Semih: gecersiz PEM/anahtarla da ayni
    # sonuc doner, gercek dogrulama ilk API cagrisina kadar bilinmez).
    #
    # DEMO_MODE=true iken app.py::_build_judge_port judge'i CachedConflictJudge
    # (#63, engine/cache.py) ile SARMALAR - port artik GeminiJudgeAdapter degil,
    # CachedConflictJudge oluyor ve isinstance dogrudan hep "missing" derdi
    # (gercek regresyon: hosted demo /health hep gemini=missing raporlardi,
    # #189 make smoke kapisi kalici kirmizi kalirdi). Sarmalayicinin GERCEK
    # ic port'una in - CachedConflictJudge.inner (bkz. engine/cache.py) - sonra
    # isinstance uygula. Sarmalanmamis port'ta getattr fallback kendi degerine
    # doner (no-op).
    github_auth = "configured" if isinstance(radar_service.github_port, GitHubAdapter) else "missing"
    # Zincirin HERHANGI bir yerinde gercek Gemini adapteri varsa "configured".
    # Alan anlami degismedi ("Gemini kimlik bilgisi set edilmis ve adapter
    # kuruldu"); degisen tek sey, sarmalayici sayisindan BAGIMSIZ olmasi.
    gemini = (
        "configured"
        if any(isinstance(d, GeminiJudgeAdapter) for d in _judge_zinciri(radar_service.judge_port))
        else "missing"
    )
    return HealthResponse(
        status="ok",
        mode=settings.ENSEMBLE_MODE,
        github_auth=github_auth,
        gemini=gemini,
    )
