from ensemble.config import Settings
from ensemble.integrations.gemini.query_judge import (
    FakeQueryJudgeAdapter,
    GeminiQueryJudgeAdapter,
    build_query_judge,
)
from ensemble.models import QueryDocument


class _Client:
    def __init__(self) -> None:
        self.prompt = ""

    def generate_content(self, prompt: str, *, response_schema=None) -> str:
        self.prompt = prompt
        return '{"answer":"Yanıt [cite:T-58]","citation_refs":["T-58"],"confidence":"high"}'


def _document() -> QueryDocument:
    return QueryDocument(
        id="task:T-58",
        type="task",
        ref="T-58",
        quote="Ask endpoint'ini yaz",
        text="RAG ve citations",
    )


def test_fake_judge_yalniz_verilen_refleri_placeholderla_kullanir():
    judgement = FakeQueryJudgeAdapter().answer_query("Ask nedir?", [_document()])

    assert judgement.citation_refs == ["T-58"]
    assert "[cite:T-58]" in judgement.answer


def test_gemini_judge_yapilandirilmis_cevap_ister():
    client = _Client()
    judge = GeminiQueryJudgeAdapter(Settings(_env_file=None), client=client)

    judgement = judge.answer_query("Ask nedir?", [_document()])

    assert judgement.confidence == "high"
    assert '"ref": "T-58"' in client.prompt


def test_builder_key_yokken_fake_secer():
    assert isinstance(build_query_judge(Settings(_env_file=None)), FakeQueryJudgeAdapter)
