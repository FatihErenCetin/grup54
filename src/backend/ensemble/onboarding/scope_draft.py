"""Kapsam taslağı üretici (#57) — onboarding sihirbazının TEK gerçek AI adımı.

`tasks/` mirror'ı (wizard.py) deterministiktir (gh -> md, AI DEĞİL — bkz.
wizard.py docstring); `scope/sprint-N.md` ise sentez gerektirir (hedef/
kapsam-dışı hiçbir GitHub issue'sından birebir kopyalanamaz). Bu yüzden
gerçek bir Gemini çağrısı burada — `FakeScopeDrafter` diğer Fake* adapterlerle
(FakeJudgeAdapter, FakeGitHubAdapter) aynı offline/CI deseni.

Çıktı her zaman TASLAK'tır (status="draft") — PO gözden geçirip düzenler,
commit etmesi onay/"dondurma" sayılır (dizin_yapisi.md §3: "PO yazar ve dondurur").
"""

from typing import Protocol

from pydantic import BaseModel

from ensemble.config import Settings
from ensemble.integrations.gemini.client import ResilientGeminiClient


class ScopeDraft(BaseModel):
    goal: str
    in_scope: list[str]
    non_goals: list[str]


class ScopeDrafter(Protocol):
    def draft(self, *, milestone: str, context: str) -> ScopeDraft: ...


class FakeScopeDrafter:
    """Deterministik, ağ çağrısı yok — offline/CI (FakeJudgeAdapter deseni)."""

    def draft(self, *, milestone: str, context: str) -> ScopeDraft:
        return ScopeDraft(
            goal=f"[TASLAK] {milestone} hedefi — PO doldursun.",
            in_scope=["[TASLAK] madde 1 — PO doldursun"],
            non_goals=["[TASLAK] madde 1 — PO doldursun"],
        )


class GeminiScopeDrafter:
    """Gerçek Gemini çağrısı — README/ROADMAP/issue başlıklarından taslak sentezler."""

    def __init__(self, settings: Settings):
        self._client = ResilientGeminiClient(settings)

    def draft(self, *, milestone: str, context: str) -> ScopeDraft:
        prompt = (
            f"Aşağıdaki proje bağlamına göre '{milestone}' için bir KAPSAM TASLAĞI üret. "
            "Türkçe yaz. 'goal' tek cümle, 'in_scope' 3-7 madde, 'non_goals' "
            "(kapsam dışı) 2-5 madde. Bu bir TASLAKTIR — insan onayı gerekir; "
            "belirsizsen genel ve temkinli kal, uydurma detay ekleme.\n\n"
            f"Proje bağlamı:\n{context}\n"
        )
        raw = self._client.generate_content(prompt, response_schema=ScopeDraft)
        return ScopeDraft.model_validate_json(raw)


def build_scope_drafter(settings: Settings) -> ScopeDrafter:
    if settings.GEMINI_API_KEY:
        return GeminiScopeDrafter(settings)
    return FakeScopeDrafter()
