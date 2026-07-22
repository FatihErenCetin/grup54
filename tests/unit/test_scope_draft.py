from ensemble.config import Settings
from ensemble.onboarding.scope_draft import FakeScopeDrafter, GeminiScopeDrafter, build_scope_drafter


def test_fake_drafter_deterministik():
    drafter = FakeScopeDrafter()
    d1 = drafter.draft(milestone="Sprint 3", context="x")
    d2 = drafter.draft(milestone="Sprint 3", context="x")
    assert d1 == d2
    assert "Sprint 3" in d1.goal


def test_build_scope_drafter_key_yoksa_fake():
    drafter = build_scope_drafter(Settings(_env_file=None))
    assert isinstance(drafter, FakeScopeDrafter)


def test_build_scope_drafter_key_varsa_gemini():
    drafter = build_scope_drafter(Settings(_env_file=None, GEMINI_API_KEY="fake-key"))
    assert isinstance(drafter, GeminiScopeDrafter)
