"""#255 — FallbackJudge: birincil düşerse ikincil devralır.

Bu sınıf hiçbir sağlayıcıyı tanımaz; testler de tanımıyor. Sahte port'larla
YALNIZCA kompozisyon davranışı doğrulanır — Gemini/Groq'a hiç dokunulmaz.
"""

from datetime import datetime, timezone

import pytest

from ensemble.config import Settings
from ensemble.engine.fallback import FallbackJudge
from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import JudgeUnavailableError


def _event(id_: str, actor: str) -> NormalizedEvent:
    return NormalizedEvent(
        id=id_,
        type="commit",
        actor=actor,
        branch=f"T-{id_}",
        files=["src/x.py"],
        ts=datetime.now(timezone.utc),
        ref="abc",
    )


class _Calisan:
    def __init__(self, etiket: str):
        self.etiket = etiket
        self.calls = 0

    def judge_conflict(self, a, b, overlap, sim) -> Detection:
        self.calls += 1
        return Detection(
            id=f"{a.id}-{b.id}",
            actors=sorted({a.actor, b.actor}),
            branches=[],
            files=sorted(overlap),
            severity="high",
            confidence=0.9,
            rationale=self.etiket,
        )


class _Dusen:
    def __init__(self, mesaj: str = "kota bitti"):
        self.mesaj = mesaj
        self.calls = 0

    def judge_conflict(self, a, b, overlap, sim) -> Detection:
        self.calls += 1
        raise JudgeUnavailableError(self.mesaj)


class _Patlayan:
    def __init__(self):
        self.calls = 0

    def judge_conflict(self, a, b, overlap, sim) -> Detection:
        self.calls += 1
        raise ValueError("kod hatasi")


def _cift():
    return _event("1", "esma"), _event("2", "fatih")


def test_birincil_calisirken_yedek_hic_cagrilmaz():
    """Yedek pasif olmalı — aksi halde her istek iki sağlayıcıya gider."""
    birincil, yedek = _Calisan("birincil"), _Calisan("yedek")
    a, b = _cift()

    sonuc = FallbackJudge(birincil, yedek).judge_conflict(a, b, ["src/x.py"], 0.5)

    assert sonuc.rationale == "birincil"
    assert birincil.calls == 1
    assert yedek.calls == 0


def test_birincil_dusunce_yedek_devralir():
    """MUTASYON KİLİDİ: yedek çağrısını kaldır → yargı hiç üretilemez."""
    birincil, yedek = _Dusen(), _Calisan("yedek")
    a, b = _cift()

    sonuc = FallbackJudge(birincil, yedek).judge_conflict(a, b, ["src/x.py"], 0.5)

    assert sonuc.rationale == "yedek"
    assert birincil.calls == 1
    assert yedek.calls == 1


def test_ikisi_de_dusunce_sahte_tespit_uretilmez():
    """#252 sözleşmesi burada da geçerli — iki arıza bir tespit yapmaz."""
    birincil, yedek = _Dusen("birincil 429"), _Dusen("yedek 503")
    a, b = _cift()

    with pytest.raises(JudgeUnavailableError) as ei:
        FallbackJudge(birincil, yedek).judge_conflict(a, b, ["src/x.py"], 0.5)

    # Her iki sebep de mesajda: "hangisi neden düştü" yanıtlanabilsin.
    assert "birincil 429" in str(ei.value)
    assert "yedek 503" in str(ei.value)
    assert birincil.calls == 1
    assert yedek.calls == 1


def test_kok_neden_birincildir():
    """`raise ... from birincil` — zincirin kökü birincil sağlayıcı olmalı.

    Yedeğin hatası semptomdur; kök neden birincilin düşmesidir. Yanlış
    zincirleme, log okuyanı yedeği suçlamaya yönlendirirdi.
    """
    a, b = _cift()
    with pytest.raises(JudgeUnavailableError) as ei:
        FallbackJudge(_Dusen("birincil 429"), _Dusen("yedek 503")).judge_conflict(
            a, b, ["src/x.py"], 0.5
        )
    assert "birincil 429" in str(ei.value.__cause__)


def test_judge_disi_istisna_yedege_dusmez():
    """Gerçek bir bug, "sağlayıcı arızası" gibi gösterilmemeli.

    Her istisnayı yakalayıp yedeğe düşmek, kod hatalarını sessizce maskeler:
    birincil her seferinde patlar, yedek her seferinde kurtarır ve kimse
    birincilin bozuk olduğunu fark etmez.
    """
    birincil, yedek = _Patlayan(), _Calisan("yedek")
    a, b = _cift()

    with pytest.raises(ValueError, match="kod hatasi"):
        FallbackJudge(birincil, yedek).judge_conflict(a, b, ["src/x.py"], 0.5)

    assert yedek.calls == 0  # yedek HİÇ denenmedi


# --- kablolama (#255): ayar -> kompozisyon ---------------------------------


def test_groq_anahtari_yoksa_yedek_kurulmaz():
    """Yedek OPSİYONEL — anahtar yoksa kurulum hiç değişmemeli."""
    from ensemble.app import _build_judge_port

    judge = _build_judge_port(Settings(_env_file=None, GEMINI_API_KEY="g", GROQ_API_KEY=""))
    assert not isinstance(judge, FallbackJudge)


def test_groq_anahtari_varsa_yedek_kurulur():
    """MUTASYON KİLİDİ: app.py'deki sarmayı kaldır → bu test kırılır."""
    from ensemble.app import _build_judge_port
    from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
    from ensemble.integrations.groq.judge import GroqJudgeAdapter

    judge = _build_judge_port(Settings(_env_file=None, GEMINI_API_KEY="g", GROQ_API_KEY="q"))

    assert isinstance(judge, FallbackJudge)
    # #288: her sağlayıcı KENDİ devre kesicisiyle sarılır. Sarma bilerek
    # İÇERİDE (her dalda ayrı) — dıştan tek kesici, Gemini'nin günlük kotası
    # bitince ÇALIŞAN Groq'a gitmeyi de keserdi (bkz.
    # test_devre_kesici.py::test_devre_kesici_YEDEGI_kesmez).
    from ensemble.engine.devre_kesici import DevreKesiciJudge

    assert isinstance(judge.primary, DevreKesiciJudge)
    assert isinstance(judge.secondary, DevreKesiciJudge)
    # Kesicinin ARDINDA doğru sağlayıcılar duruyor — asıl iddia bu, ve
    # gevşetilmedi: hangi sağlayıcının hangi dalda olduğu hâlâ kilitli.
    assert isinstance(judge.primary.inner, GeminiJudgeAdapter)
    assert isinstance(judge.secondary.inner, GroqJudgeAdapter)


def test_yedek_cache_in_ICINDE_kalir():
    """Sarma sırası: CachedConflictJudge(FallbackJudge(...)).

    Tersi (iki ayrı cache) aynı çifti iki kez saklardı ve birincil geri
    döndüğünde yedeğin bayat yargısı ayrı bir kayıtta yaşamaya devam ederdi.
    """
    from ensemble.app import _build_judge_port
    from ensemble.engine.cache import CachedConflictJudge

    judge = _build_judge_port(
        Settings(
            _env_file=None,
            GEMINI_API_KEY="g",
            GROQ_API_KEY="q",
            DEMO_MODE=True,
            # #63 tek-repo pin: DEMO_MODE repo sabitlenmeden açılamaz.
            GITHUB_REPO_OWNER="FatihErenCetin",
            GITHUB_REPO_NAME="grup54",
        )
    )

    assert isinstance(judge, CachedConflictJudge)
    assert isinstance(judge.inner, FallbackJudge)


def test_birincil_sahteyken_yedek_kurulmaz():
    """FakeJudgeAdapter hiç düşmez — yedek anlamsız olurdu."""
    from ensemble.app import _build_judge_port
    from ensemble.integrations.gemini.fake import FakeJudgeAdapter

    judge = _build_judge_port(Settings(_env_file=None, GEMINI_API_KEY="", GROQ_API_KEY="q"))
    assert isinstance(judge, FakeJudgeAdapter)
