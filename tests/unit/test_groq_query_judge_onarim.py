"""Groq Ask judge'inin eksik-alan onarimi (#355).

Canlida olculdu (30 Tem 2026): Gemini'nin gunluk generate kotasi (flash icin
20) bitince yedek devreye giriyor ama llama-3.3-70b yalniz `answer` donduryor,
`citation_refs`/`confidence` atliyordu -> yedek de "uretemedi" sayiliyor ve
`/query` 503 veriyordu. Yani kotanin bittigi an calisan TEK yol biçimsel bir
eksik yuzunden cope gidiyordu.
"""

from __future__ import annotations

import json

import pytest

from ensemble.config import Settings
from ensemble.engine.query import _CITATION_RE as ENGINE_CITATION_RE
from ensemble.integrations.groq.errors import GroqError
from ensemble.integrations.groq.query_judge import _CITATION_RE, GroqQueryJudgeAdapter
from ensemble.models import QueryDocument


class _Client:
    def __init__(self, raw: str) -> None:
        self.raw = raw

    def generate_content(self, prompt: str, *, response_schema) -> str:  # noqa: ANN001
        self.prompt = prompt
        return self.raw


BELGELER = [
    QueryDocument(id="task:T-34", type="task", ref="T-34", quote="Hosted demo", text="Hosted demo"),
]


def _judge(raw: str) -> GroqQueryJudgeAdapter:
    return GroqQueryJudgeAdapter(Settings(GROQ_API_KEY="x"), client=_Client(raw))


def test_yalniz_answer_donen_cevap_metinden_onarilir():
    """MUTASYON KİLİDİ: `_eksik_alanlari_onar` cagrisini sil -> GroqError firlar."""
    raw = json.dumps({"answer": "Hosted demo VDS'te [cite:T-34]."})
    sonuc = _judge(raw).answer_query("soru", BELGELER)
    assert sonuc.citation_refs == ["T-34"]
    assert sonuc.confidence == "low"


def test_atif_UYDURULMAZ_isaret_yoksa_saglayici_dusmus_sayilir():
    """Cevapta hic [cite:] yoksa onarim YAPILMAZ — kaynaksiz cevap uretmiyoruz.

    MUTASYON KİLİDİ: `if not refs: return None` satirini sil -> bos atifli
    bir cevap uretilir, bu test kirilir.
    """
    raw = json.dumps({"answer": "Bilmiyorum ama tahminim su."})
    with pytest.raises(GroqError):
        _judge(raw).answer_query("soru", BELGELER)


def test_confidence_uydurulmaz_EN_DUSUK_kademe_verilir():
    """Model guvenini soylemediyse 'medium' varsaymak olmayan bir kesinlik satardi.

    MUTASYON KİLİDİ: varsayilani "high" yap -> bu test kirilir.
    """
    raw = json.dumps({"answer": "x [cite:T-34]", "citation_refs": ["T-34"]})
    assert _judge(raw).answer_query("soru", BELGELER).confidence == "low"


def test_modelin_KENDI_verdigi_confidence_korunur():
    raw = json.dumps({"answer": "x [cite:T-34]", "citation_refs": ["T-34"], "confidence": "high"})
    assert _judge(raw).answer_query("soru", BELGELER).confidence == "high"


def test_tekrar_eden_atiflar_duser_sira_korunur():
    raw = json.dumps({"answer": "a [cite:B] b [cite:A] c [cite:B]"})
    assert _judge(raw).answer_query("soru", BELGELER).citation_refs == ["B", "A"]


def test_bozuk_json_onarilmaz():
    with pytest.raises(GroqError):
        _judge("bu json degil").answer_query("soru", BELGELER)


def test_atif_regexi_engine_ile_AYNI_kalir():
    """Kopya bilincli (katman disiplini) ama sessizce ayrismamali.

    MUTASYON KİLİDİ: groq/query_judge.py'deki regex'i degistir -> bu test kirilir.
    """
    assert _CITATION_RE.pattern == ENGINE_CITATION_RE.pattern


def test_prompt_UC_alani_da_adiyla_istiyor():
    """Groq semayi ZORLAMIYOR; alanlar prompt'ta adiyla istenmezse atlaniyor.

    MUTASYON KİLİDİ: _build_prompt'tan uc-alan cumlesini sil -> bu test kirilir.
    """
    j = _judge(json.dumps({"answer": "x [cite:T-34]"}))
    j.answer_query("soru", BELGELER)
    prompt = j._client.prompt  # type: ignore[attr-defined]
    for alan in ("answer", "citation_refs", "confidence"):
        assert f'"{alan}"' in prompt
