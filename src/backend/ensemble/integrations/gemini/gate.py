"""Ucuz on-yargi kisayolu (#24) — Gemini'ye hic sormadan karar verilebilecek
durumlari eler (maliyet kontrolu: "yalniz iki esik arasindaki adaylarda cagrilir").

`#22`'nin (engine/radar.py) Jaccard geciditinden farkli/ek: o gecit ayni-actor
ve overlap-yok ciftlerini path-kor bicimde eler ama uv.lock/openapi.json gibi
gurultu dosyalarini YAKALAMAZ (tam overlap, Jaccard=1.0). Bu modul o bosluqu
kapatir + ayni-actor kontrolunu savunma-derinligi olarak burada da tutar
(JudgePort baska baglamlardan da dogrudan cagrilabilir).
"""

from ensemble.models import Detection, NormalizedEvent

_NOISE_BASENAMES = {
    "uv.lock",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Cargo.lock",
}
_NOISE_PATHS = {"src/shared/openapi.json"}


def _is_noise_file(path: str) -> bool:
    return path in _NOISE_PATHS or path.rsplit("/", 1)[-1] in _NOISE_BASENAMES


def _low_confidence(
    a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], reason: str
) -> Detection:
    return Detection(
        id=f"{a.id}-{b.id}",
        actors=sorted({a.actor, b.actor}),
        branches=sorted({x for x in (a.branch, b.branch) if x}),
        files=sorted(overlap),
        severity="low",
        confidence=0.05,
        rationale=f"Ucuz on-gecit: {reason}.",
    )


def cheap_prejudge(
    a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
) -> Detection | None:
    """Gemini'ye hic sormadan karar verilebiliyorsa Detection doner; belirsizse None."""
    if a.actor == b.actor:
        return _low_confidence(a, b, overlap, "ayni actor - kendisiyle cakismaz")
    if overlap and all(_is_noise_file(f) for f in overlap):
        return _low_confidence(
            a, b, overlap, "yalnizca uretilmis/kilit dosyasi overlap'i - gurultu"
        )
    return None
