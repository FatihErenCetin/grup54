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


# ── #330: query + scope judge'lari da yedekli ───────────────────────────────
# D-53'un yedegi UC judge'dan yalniz radar'inkine baglanmisti; olcum (29 Tem):
# /query'nin uc ornek sorusu da 503, /scope/check de 503.


class _DusenPort:
    """Saglayici arizasi — cagrilan her metot patlar."""

    def __init__(self, hata: Exception) -> None:
        self.hata = hata
        self.calls = 0

    def answer_query(self, question, documents):  # noqa: ANN001, ANN201
        self.calls += 1
        raise self.hata

    def judge_scope(self, ref, subject, candidates):  # noqa: ANN001, ANN201
        self.calls += 1
        raise self.hata


class _CalisanQueryPort:
    def __init__(self, etiket: str) -> None:
        self.etiket = etiket
        self.calls = 0

    def answer_query(self, question, documents):  # noqa: ANN001, ANN201
        from ensemble.models import QueryJudgement

        self.calls += 1
        return QueryJudgement(answer=self.etiket, citation_refs=[], confidence="low")


def _gemini_hata(mesaj: str) -> Exception:
    from ensemble.integrations.gemini.errors import GeminiTransientError

    return GeminiTransientError(mesaj)


def _groq_hata(mesaj: str) -> Exception:
    from ensemble.integrations.groq.errors import GroqError

    return GroqError(mesaj)


def _query_yedek(primary, secondary):  # noqa: ANN001, ANN202
    from ensemble.engine.fallback import FallbackQueryJudge
    from ensemble.integrations.gemini.errors import GeminiError
    from ensemble.integrations.groq.errors import GroqError

    return FallbackQueryJudge(primary, secondary, unavailable=(GeminiError, GroqError))


def test_query_birincil_calisirken_yedek_hic_cagrilmaz():
    birincil = _CalisanQueryPort("gemini")
    yedek = _CalisanQueryPort("groq")

    sonuc = _query_yedek(birincil, yedek).answer_query("soru", [])

    assert sonuc.answer == "gemini"
    assert yedek.calls == 0


def test_query_birincil_dusunce_yedek_devralir():
    """MUTASYON KİLİDİ: app.py'deki FallbackQueryJudge sarması kaldırılırsa
    ya da `_cagir` yedeği denemezse kırılır — canlıda ölçülen 503 geri gelir."""
    birincil = _DusenPort(_gemini_hata("429 kota"))
    yedek = _CalisanQueryPort("groq")

    sonuc = _query_yedek(birincil, yedek).answer_query("soru", [])

    assert sonuc.answer == "groq"
    assert birincil.calls == 1
    assert yedek.calls == 1


def test_query_ikisi_de_dusunce_BIRINCILIN_hatasi_yayilir():
    """Donmuş hata sözleşmesi kilidi: `/query` ve `/scope/check` için API hata
    haritasında `GeminiError` var, `GroqError` YOK. Yedeğin hatasını yaymak,
    haritada karşılığı olmayan bir istisnayı router'a taşıyıp 500'e çevirirdi —
    yani yedek EKLEMEK hata sözleşmesini BOZARDI.
    MUTASYON KİLİDİ: `raise birincil` yerine `raise ikincil` yazılırsa kırılır."""
    from ensemble.integrations.gemini.errors import GeminiError

    birincil = _DusenPort(_gemini_hata("gemini kotasi"))
    yedek = _DusenPort(_groq_hata("groq TPD doldu"))

    with pytest.raises(GeminiError, match="gemini kotasi"):
        _query_yedek(birincil, yedek).answer_query("soru", [])


def test_query_saglayici_disi_istisna_yedege_dusmez():
    """`unavailable` listesinde OLMAYAN bir hata (ör. programlama hatası)
    yedeğe düşmez — gerçek bir bug'ı "sağlayıcı arızası" gibi göstermek yasak."""
    birincil = _DusenPort(TypeError("bug"))
    yedek = _CalisanQueryPort("groq")

    with pytest.raises(TypeError):
        _query_yedek(birincil, yedek).answer_query("soru", [])
    assert yedek.calls == 0


def test_query_groq_yoksa_yedek_kurulmaz():
    from ensemble.app import _build_query_judge_port
    from ensemble.engine.fallback import FallbackQueryJudge

    port = _build_query_judge_port(
        Settings(_env_file=None, GEMINI_API_KEY="g", GROQ_API_KEY="")
    )
    assert not isinstance(port, FallbackQueryJudge)


def test_query_groq_varsa_yedek_kurulur():
    """MUTASYON KİLİDİ: app.py'deki sarmayı kaldır → kırılır."""
    from ensemble.app import _build_query_judge_port
    from ensemble.engine.fallback import FallbackQueryJudge
    from ensemble.integrations.gemini.query_judge import GeminiQueryJudgeAdapter
    from ensemble.integrations.groq.query_judge import GroqQueryJudgeAdapter

    port = _build_query_judge_port(
        Settings(_env_file=None, GEMINI_API_KEY="g", GROQ_API_KEY="q")
    )

    assert isinstance(port, FallbackQueryJudge)
    assert isinstance(port.primary, GeminiQueryJudgeAdapter)
    assert isinstance(port.secondary, GroqQueryJudgeAdapter)


def test_query_birincil_sahteyken_yedek_kurulmaz():
    """FakeQueryJudge hiç düşmez — onu Groq'la yedeklemek anlamsız olurdu."""
    from ensemble.app import _build_query_judge_port
    from ensemble.engine.fallback import FallbackQueryJudge
    from ensemble.integrations.gemini.query_judge import FakeQueryJudgeAdapter

    port = _build_query_judge_port(
        Settings(_env_file=None, GEMINI_API_KEY="", GROQ_API_KEY="q")
    )

    assert isinstance(port, FakeQueryJudgeAdapter)
    assert not isinstance(port, FallbackQueryJudge)


def test_query_yedek_cache_in_ICINDE_kalir():
    from ensemble.app import _build_query_judge_port
    from ensemble.engine.cache import CachedQueryJudge
    from ensemble.engine.fallback import FallbackQueryJudge

    port = _build_query_judge_port(
        Settings(
            _env_file=None,
            GEMINI_API_KEY="g",
            GROQ_API_KEY="q",
            DEMO_MODE=True,
            GITHUB_REPO_OWNER="FatihErenCetin",
            GITHUB_REPO_NAME="grup54",
        )
    )

    assert isinstance(port, CachedQueryJudge)
    assert isinstance(port.inner, FallbackQueryJudge)


def test_scope_groq_varsa_yedek_kurulur_ve_dususte_devralir():
    """Scope tarafının aynası — `/scope/check` de 503 dönüyordu."""
    from ensemble.app import _build_scope_judge_port
    from ensemble.engine.fallback import FallbackScopeJudge
    from ensemble.integrations.gemini.scope_judge import GeminiScopeJudgeAdapter
    from ensemble.integrations.groq.scope_judge import GroqScopeJudgeAdapter
    from ensemble.models import ScopeJudgement

    port = _build_scope_judge_port(
        Settings(_env_file=None, GEMINI_API_KEY="g", GROQ_API_KEY="q")
    )
    assert isinstance(port, FallbackScopeJudge)
    assert isinstance(port.primary, GeminiScopeJudgeAdapter)
    assert isinstance(port.secondary, GroqScopeJudgeAdapter)

    class _CalisanScope:
        def judge_scope(self, ref, subject, candidates):  # noqa: ANN001, ANN201
            return ScopeJudgement(verdict="in_scope", confidence=0.9, evidence_index=0)

    from ensemble.engine.fallback import FallbackScopeJudge as _FSJ
    from ensemble.integrations.gemini.errors import GeminiError
    from ensemble.integrations.groq.errors import GroqError

    yedekli = _FSJ(
        _DusenPort(_gemini_hata("kota")),
        _CalisanScope(),
        unavailable=(GeminiError, GroqError),
    )
    assert yedekli.judge_scope("T-1", "konu", []).verdict == "in_scope"


def test_scope_birincil_sahteyken_yedek_kurulmaz():
    from ensemble.app import _build_scope_judge_port
    from ensemble.engine.fallback import FallbackScopeJudge
    from ensemble.integrations.gemini.scope_judge import FakeScopeJudgeAdapter

    port = _build_scope_judge_port(
        Settings(_env_file=None, GEMINI_API_KEY="", GROQ_API_KEY="q")
    )
    assert isinstance(port, FakeScopeJudgeAdapter)
    assert not isinstance(port, FallbackScopeJudge)


def test_query_UCUNCU_saglayici_dalinda_yedek_KAPALI_kalir(monkeypatch):
    """DAHİL ETME listesinin ASIL kilidi (mutasyonla kanıtlandı).

    İlk denemem totolojikti: `GEMINI_API_KEY=""` ile üretilen Fake üzerinde
    dahil-etme ve hariç-tutma listeleri AYNI sonucu veriyor, çünkü ayırt edecek
    üçüncü bir dal yok. Ayrımı görünür kılmak için üçüncü bir sağlayıcı dalını
    ENJEKTE ediyoruz — conflict judge'da bunun gerçeği `OllamaAdapter`'dır ve
    hariç-tutma listesi orada "tam-yerel" taahhüdünü SESSİZCE kırmıştı
    (app.py ~satır 225'teki gerekçe yorumu).

    MUTASYON KİLİDİ: `isinstance(port, GeminiQueryJudgeAdapter)` yerine
    `not isinstance(port, FakeQueryJudgeAdapter)` yazılırsa bu test kırılır —
    yani yeni bir sağlayıcı dalı eklendiğinde yedek KAPALI kalmalı, sessizce
    açılmamalı.
    """
    import ensemble.app as app_modulu
    from ensemble.engine.fallback import FallbackQueryJudge

    class _UcuncuSaglayiciQueryJudge:
        """Ne Gemini ne Fake — ileride eklenecek bir dalın (ör. Ollama) yerine."""

        def answer_query(self, question, documents):  # noqa: ANN001, ANN201
            raise AssertionError("cagrilmamali")

    monkeypatch.setattr(
        app_modulu, "build_query_judge", lambda _s: _UcuncuSaglayiciQueryJudge()
    )

    port = app_modulu._build_query_judge_port(
        Settings(_env_file=None, GEMINI_API_KEY="g", GROQ_API_KEY="q")
    )

    assert isinstance(port, _UcuncuSaglayiciQueryJudge)
    assert not isinstance(port, FallbackQueryJudge)


def test_scope_UCUNCU_saglayici_dalinda_yedek_KAPALI_kalir(monkeypatch):
    """Scope tarafının aynası — aynı dahil-etme disiplini."""
    import ensemble.app as app_modulu
    from ensemble.engine.fallback import FallbackScopeJudge

    class _UcuncuSaglayiciScopeJudge:
        def judge_scope(self, ref, subject, candidates):  # noqa: ANN001, ANN201
            raise AssertionError("cagrilmamali")

    monkeypatch.setattr(
        app_modulu, "build_scope_judge", lambda _s: _UcuncuSaglayiciScopeJudge()
    )

    port = app_modulu._build_scope_judge_port(
        Settings(_env_file=None, GEMINI_API_KEY="g", GROQ_API_KEY="q")
    )

    assert isinstance(port, _UcuncuSaglayiciScopeJudge)
    assert not isinstance(port, FallbackScopeJudge)
