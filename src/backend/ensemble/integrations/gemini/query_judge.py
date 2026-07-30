"""Ask için deterministik fake ve yapılandırılmış Gemini judge (#58)."""

from __future__ import annotations

import json

from pydantic import ValidationError

from ensemble.config import Settings
from ensemble.engine.query import QueryJudgeError
from ensemble.integrations.gemini.client import ResilientGeminiClient
from ensemble.models import QueryDocument, QueryJudgement
from ensemble.ports import QueryJudgePort


class FakeQueryJudgeAdapter:
    """Ağsız yerel geliştirmede yalnız retrieval kanıtını özetler."""

    def answer_query(
        self,
        question: str,
        documents: list[QueryDocument],
    ) -> QueryJudgement:
        del question
        selected: list[QueryDocument] = []
        seen_refs: set[str] = set()
        for document in documents:
            if document.ref in seen_refs:
                continue
            selected.append(document)
            seen_refs.add(document.ref)
            if len(selected) == 2:
                break
        answer = " ".join(f"{document.quote} [cite:{document.ref}]" for document in selected)
        return QueryJudgement(
            answer=answer,
            citation_refs=[document.ref for document in selected],
            confidence="medium" if len(selected) > 1 else "low",
        )


class GeminiQueryJudgeAdapter:
    """Retrieval corpus'u dışına çıkmadan gerekçeli Ask cevabı üretir."""

    def __init__(
        self,
        settings: Settings,
        client: ResilientGeminiClient | None = None,
    ) -> None:
        self._client = client or ResilientGeminiClient(settings)

    def answer_query(
        self,
        question: str,
        documents: list[QueryDocument],
    ) -> QueryJudgement:
        prompt = _build_prompt(question, documents)
        raw = self._client.generate_content(prompt, response_schema=QueryJudgement)
        try:
            return QueryJudgement.model_validate_json(raw)
        except ValidationError as exc:
            raise QueryJudgeError("Gemini Ask cevabı yapılandırılmış kontrata uymadı") from exc


def build_query_judge(settings: Settings) -> QueryJudgePort:
    if settings.GEMINI_API_KEY:
        return GeminiQueryJudgeAdapter(settings)
    return FakeQueryJudgeAdapter()


def _build_prompt(question: str, documents: list[QueryDocument]) -> str:
    evidence = [
        {
            "ref": document.ref,
            "type": document.type,
            "quote": document.quote,
            "context": document.text,
        }
        for document in documents
    ]
    return (
        "Soruyu yalnız verilen kanonik proje kanıtlarıyla Türkçe yanıtla. "
        "Her iddianın hemen arkasına birebir [cite:<ref>] placeholder'ı koy. "
        "citation_refs yalnız aşağıdaki ref değerlerinden oluşmalı; yeni ref, kişi, karar "
        "veya proje olgusu uydurma. Kanıt yetmiyorsa bunu açıkça söyle.\n"
        # ÜÇ alanın da adıyla istenmesi (#355): Gemini şemayı sunucu tarafında
        # ZORLUYOR, Groq ise `response_format: json_object` ile yalnız "geçerli
        # JSON" garanti ediyor — şemayı zorlamıyor. Canlıda ölçüldü (30 Tem):
        # llama-3.3-70b yalnız `answer` döndürüp `citation_refs`/`confidence`'ı
        # atlıyordu, yani Gemini kotası bitince yedek de üretemiyordu.
        # Prompt ORTAK kalmalı (iki sağlayıcı aynı ölçüte göre cevaplasın), o
        # yüzden düzeltme Groq'a özel değil buraya yazıldı; Gemini'ye zararsız.
        "Cevabın JSON nesnesi ŞU ÜÇ alanı da taşımalı: "
        '"answer" (metin), "citation_refs" (kullandığın ref listesi), '
        '"confidence" ("low" | "medium" | "high"). Üçü de zorunludur.\n\n'
        f"Soru: {question}\n"
        f"Kanıtlar: {json.dumps(evidence, ensure_ascii=False)}"
    )
