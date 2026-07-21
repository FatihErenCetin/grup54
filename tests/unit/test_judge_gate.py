from datetime import datetime

from ensemble.integrations.gemini.gate import cheap_prejudge
from ensemble.models import NormalizedEvent


def _event(id_: str, actor: str, files: list[str]) -> NormalizedEvent:
    return NormalizedEvent(
        id=id_, type="commit", actor=actor, branch="main", files=files, ts=datetime.now(), ref="abc"
    )


def test_same_actor_returns_low_confidence_detection():
    a = _event("1", "esma", ["x.py"]).model_copy(update={"branch": "T-1"})
    b = _event("2", "esma", ["x.py"]).model_copy(update={"branch": "T-2"})
    d = cheap_prejudge(a, b, overlap=["x.py"], sim=0.95)
    assert d is not None
    assert d.severity == "low"
    assert d.branches == ["T-1", "T-2"]
    assert "kendi iki branch'in ayni bolgeye dokunuyor" in d.rationale


def test_lockfile_only_overlap_returns_low_confidence_detection():
    a, b = _event("1", "esma", ["uv.lock"]), _event("2", "fatih", ["uv.lock"])
    d = cheap_prejudge(a, b, overlap=["uv.lock"], sim=0.9)
    assert d is not None
    assert d.severity == "low"


def test_generated_artifact_only_overlap_returns_low_confidence_detection():
    a, b = _event("1", "semih", ["src/shared/openapi.json"]), _event(
        "2", "fatih", ["src/shared/openapi.json"]
    )
    d = cheap_prejudge(a, b, overlap=["src/shared/openapi.json"], sim=0.5)
    assert d is not None
    assert d.severity == "low"


def test_mixed_overlap_with_one_real_file_escalates():
    # overlap'in TAMAMI gurultu degilse (bir gercek dosya da varsa) escalate etmeli.
    a, b = _event("1", "esma", ["uv.lock", "src/x.py"]), _event(
        "2", "fatih", ["uv.lock", "src/x.py"]
    )
    d = cheap_prejudge(a, b, overlap=["uv.lock", "src/x.py"], sim=0.9)
    assert d is None


def test_normal_overlap_different_actors_escalates():
    a, b = _event("1", "esma", ["src/x.py"]), _event("2", "fatih", ["src/x.py"])
    d = cheap_prejudge(a, b, overlap=["src/x.py"], sim=0.7)
    assert d is None
