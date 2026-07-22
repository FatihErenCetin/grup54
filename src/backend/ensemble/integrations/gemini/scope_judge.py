"""Scope-drift için deterministik fake + yapılandırılmış Gemini judge (#31)."""

from ensemble.config import Settings
from ensemble.integrations.gemini.client import ResilientGeminiClient
from ensemble.models import ScopeCandidate, ScopeJudgement
from ensemble.ports import ScopeJudgePort

# #31 scope korpusu: en düşük gerçek kapsam eşleşmesi 0.1667, en yüksek
# drift eşleşmesi 0.1429. Operasyon eşiği ölçülen boşluğun içinde.
_FAKE_MIN_SCORE = 0.16
_FAKE_MARGIN = 0.04


class FakeScopeJudgeAdapter:
    """Ağsız ve muhafazakâr scope judge; CI/backtest için deterministik."""

    def judge_scope(
        self, ref: str, subject: str, candidates: list[ScopeCandidate]
    ) -> ScopeJudgement:
        del ref, subject
        best_in = _best_candidate(candidates, {"goal", "in_scope"})
        best_non_goal = _best_candidate(candidates, {"non_goals"})

        if best_non_goal is not None and best_non_goal[1].similarity >= _FAKE_MIN_SCORE:
            in_score = best_in[1].similarity if best_in is not None else 0.0
            if best_non_goal[1].similarity >= in_score + _FAKE_MARGIN:
                return ScopeJudgement(
                    verdict="non_goal_violation",
                    confidence=round(best_non_goal[1].similarity, 4),
                    evidence_index=best_non_goal[0],
                )

        if best_in is not None and best_in[1].similarity >= _FAKE_MIN_SCORE:
            return ScopeJudgement(
                verdict="in_scope",
                confidence=round(best_in[1].similarity, 4),
                evidence_index=best_in[0],
            )

        return ScopeJudgement(verdict="drift", confidence=0.7, evidence_index=None)


class GeminiScopeJudgeAdapter:
    """Retrieval adaylarından alıntı seçen gerçek Gemini scope judge."""

    def __init__(
        self, settings: Settings, client: ResilientGeminiClient | None = None
    ) -> None:
        self._client = client or ResilientGeminiClient(settings)

    def judge_scope(
        self, ref: str, subject: str, candidates: list[ScopeCandidate]
    ) -> ScopeJudgement:
        prompt = _build_prompt(ref, subject, candidates)
        raw = self._client.generate_content(prompt, response_schema=ScopeJudgement)
        return ScopeJudgement.model_validate_json(raw)


def build_scope_judge(settings: Settings) -> ScopeJudgePort:
    if settings.GEMINI_API_KEY:
        return GeminiScopeJudgeAdapter(settings)
    return FakeScopeJudgeAdapter()


def _best_candidate(
    candidates: list[ScopeCandidate], sections: set[str]
) -> tuple[int, ScopeCandidate] | None:
    matches = [
        (index, candidate)
        for index, candidate in enumerate(candidates)
        if candidate.evidence.section in sections
    ]
    return max(matches, key=lambda item: item[1].similarity, default=None)


def _build_prompt(ref: str, subject: str, candidates: list[ScopeCandidate]) -> str:
    candidate_text = "\n".join(
        f"[{index}] section={candidate.evidence.section} "
        f"item_id={candidate.evidence.item_id or '-'} "
        f"similarity={candidate.similarity:.4f} quote={candidate.evidence.quote}"
        for index, candidate in enumerate(candidates)
    )
    return (
        "Bir değişikliğin donmuş sprint kapsamıyla ilişkisini muhafazakâr biçimde değerlendir.\n"
        "Karar sırası: açık non_goals ihlali => non_goal_violation; kapsam maddesiyle "
        "desteklenen iş => in_scope; güvenilir eşleşme yok => drift.\n"
        "Yalnız aşağıdaki retrieval adaylarını kanıt göster. in_scope/non_goal_violation için "
        "evidence_index zorunlu; drift için null bırak. Benzerlik skoru tek başına karar değildir.\n\n"
        f"Ref: {ref}\nDeğişiklik:\n{subject}\n\nAday scope maddeleri:\n{candidate_text}\n"
    )
