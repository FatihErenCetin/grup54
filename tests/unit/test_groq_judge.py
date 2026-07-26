"""#255 — Groq yedek sağlayıcı: istemci + JudgePort adaptörü.

Gerçek ağ çağrısı YOK; `httpx.MockTransport` ile HTTP katmanı taklit edilir.
"""

import json
from datetime import datetime, timezone

import httpx
import pytest
from pydantic import BaseModel

from ensemble.config import Settings
from ensemble.integrations.groq.client import GroqClient
from ensemble.integrations.groq.errors import GroqPermanentError, GroqTransientError
from ensemble.integrations.groq.judge import GroqJudgeAdapter
from ensemble.models import NormalizedEvent
from ensemble.ports import JudgeUnavailableError


class _Sema(BaseModel):
    """İstemci testleri için asgari şema — judge'ın kendi `_JudgeVerdict`'i
    ayrı; burada istemcinin şemayı prompt'a gömdüğünü doğruluyoruz."""

    severity: str
    confidence: float
    rationale: str


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, GROQ_API_KEY="test-key", GROQ_MAX_RETRIES=2, **overrides)


def _client(handler) -> GroqClient:
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.groq.com")
    return GroqClient(_settings(), http_client=http)


def _event(id_: str, actor: str, files: list[str] | None = None) -> NormalizedEvent:
    return NormalizedEvent(
        id=id_,
        type="commit",
        actor=actor,
        branch=f"T-{id_}",
        files=files or ["src/core.py"],
        ts=datetime.now(timezone.utc),
        ref=id_,
    )


def _verdict_response(severity="high", confidence=0.9, rationale="ayni fonksiyon"):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "severity": severity,
                                "confidence": confidence,
                                "rationale": rationale,
                            }
                        )
                    }
                }
            ]
        },
    )


# --- istemci ---------------------------------------------------------------


def test_istek_openai_uyumlu_uca_gider_ve_json_modu_ister():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return _verdict_response()

    _client(handler).generate_content("soru", response_schema=_Sema)

    assert seen["url"].endswith("/openai/v1/chat/completions")
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["temperature"] == 0
    # Sema prompt'a da gomulur: response_format yalnizca "gecerli JSON" garanti
    # eder, alan adlarini ZORLAMAZ.
    assert "severity" in seen["body"]["messages"][0]["content"]


def test_gecici_hata_retry_edilir():
    denemeler = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        denemeler["n"] += 1
        if denemeler["n"] == 1:
            return httpx.Response(429, json={"error": "rate limit"})
        return _verdict_response()

    icerik = _client(handler).generate_content("soru", response_schema=_Sema)

    assert denemeler["n"] == 2  # 429 sonrasi yeniden denendi
    assert "high" in icerik


def test_kalici_hata_retry_edilmez():
    denemeler = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        denemeler["n"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(GroqPermanentError):
        _client(handler).generate_content("soru", response_schema=_Sema)

    assert denemeler["n"] == 1  # 401 icin bosuna tekrar YOK


def test_kota_tukenmesi_gecici_sayilir():
    """429 = GroqTransientError; retry tukenirse yukari yayilir."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "quota"})

    with pytest.raises(GroqTransientError):
        _client(handler).generate_content("soru", response_schema=_Sema)


# --- adaptör ---------------------------------------------------------------


def test_basarili_yanit_detection_uretir():
    adapter = GroqJudgeAdapter(_settings(), client=_client(lambda _r: _verdict_response()))
    a, b = _event("1", "esma"), _event("2", "fatih")

    d = adapter.judge_conflict(a, b, ["src/core.py"], 0.8)

    assert d.severity == "high"
    assert d.confidence == 0.9
    assert d.rationale == "ayni fonksiyon"
    assert d.actors == ["esma", "fatih"]


def test_groq_hatasi_sahte_tespit_uretmez():
    """#252 sözleşmesi Groq'ta da geçerli — yedek de yalan söylemez."""
    adapter = GroqJudgeAdapter(
        _settings(), client=_client(lambda _r: httpx.Response(500, json={"e": "down"}))
    )
    a, b = _event("1", "esma"), _event("2", "fatih")

    with pytest.raises(JudgeUnavailableError):
        adapter.judge_conflict(a, b, ["src/core.py"], 0.8)


def test_semaya_uymayan_yanit_sahte_tespit_uretmez():
    """Groq JSON modu gecerli JSON garanti eder ama ALANLARI zorlamaz.

    Yani "gecerli JSON ama yanlis sema" gercekci bir yol — ve o da tespit
    uretmemeli.
    """
    bozuk = httpx.Response(200, json={"choices": [{"message": {"content": '{"foo": 1}'}}]})
    adapter = GroqJudgeAdapter(_settings(), client=_client(lambda _r: bozuk))
    a, b = _event("1", "esma"), _event("2", "fatih")

    with pytest.raises(JudgeUnavailableError, match="semaya uymuyor"):
        adapter.judge_conflict(a, b, ["src/core.py"], 0.8)


def test_ucuz_gecit_yedek_kotasini_da_korur():
    """`cheap_prejudge` Groq'a da uygulanir — gurultu dosyasi aga cikmaz."""
    cagrildi = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        cagrildi["n"] += 1
        return _verdict_response()

    adapter = GroqJudgeAdapter(_settings(), client=_client(handler))
    a = _event("1", "esma", ["uv.lock"])
    b = _event("2", "fatih", ["uv.lock"])

    adapter.judge_conflict(a, b, ["uv.lock"], 1.0)

    assert cagrildi["n"] == 0  # gurultu dosyasi -> saglayiciya HIC gidilmedi


