"""#259 (GÖREV 2/2) — `PersistentJudge`: `CachedConflictJudge` (bellek) ile
`FallbackJudge` (Gemini→Groq) ARASINDA DB-kalıcı katman.

Bu sınıf hiçbir sağlayıcıyı tanımaz; testler de tanımıyor — `FallbackJudge`
testleri (`test_fallback_judge.py`) ile AYNI disiplin: sahte bir `JudgePort`
ile YALNIZCA kompozisyon/kalıcılık davranışı doğrulanır, Gemini/Groq'a hiç
dokunulmaz. DB tarafı gerçek (in-memory SQLite) — `verdict_store.py`'nin
KENDİSİ (`get_verdict`/`put_verdict`) `test_verdict_store.py`'de ayrıca
doğrulanmış durumda; burada onun ARKASINDAKİ sarmalama mantığı test edilir.
"""

import logging

import pytest

from ensemble.config import Settings
from ensemble.engine.cache import CachedConflictJudge, _digest
from ensemble.engine.fallback import FallbackJudge
from ensemble.engine.persistence import PersistentJudge
from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import JudgeUnavailableError
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import Base
from ensemble.store.verdict_store import get_verdict, put_verdict


def _event(id_: str, actor: str) -> NormalizedEvent:
    from datetime import datetime, timezone

    return NormalizedEvent(
        id=id_,
        type="commit",
        actor=actor,
        branch=f"T-{id_}",
        files=["src/x.py"],
        ts=datetime.now(timezone.utc),
        ref="abc",
    )


def _cift():
    return _event("1", "esma"), _event("2", "fatih")


def _detection(rationale: str = "yargi") -> Detection:
    return Detection(
        id="1-2",
        actors=["esma", "fatih"],
        branches=[],
        files=["src/x.py"],
        severity="high",
        confidence=0.9,
        rationale=rationale,
    )


def _cache_key(a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim, model: str) -> str:
    """`PersistentJudge.judge_conflict`'in KENDİ hesapladığı anahtarla AYNI
    payload — test, sarmalayıcının içine bakmadan (kara kutu) doğru satırı
    okuyup/yazdığını bu anahtar üzerinden kontrol eder."""
    return _digest(
        {
            "a": a.model_dump(mode="json"),
            "b": b.model_dump(mode="json"),
            "overlap": sorted(overlap),
            "sim": sim,
            "model": model,
        }
    )


class _IcPort:
    """Sahte `JudgePort` — çağrı sayısı sayar, sabit bir `Detection` döner."""

    def __init__(self, rationale: str = "ic-port"):
        self.rationale = rationale
        self.calls = 0

    def judge_conflict(self, a, b, overlap, sim) -> Detection:
        self.calls += 1
        return _detection(self.rationale)


class _DusenPort:
    """Sahte `JudgePort` — her çağrıda `JudgeUnavailableError` fırlatır."""

    def __init__(self, mesaj: str = "kota bitti"):
        self.mesaj = mesaj
        self.calls = 0

    def judge_conflict(self, a, b, overlap, sim) -> Detection:
        self.calls += 1
        raise JudgeUnavailableError(self.mesaj)


@pytest.fixture
def session_factory():
    """`test_verdict_store.py` ile AYNI kalıp — in-memory SQLite +
    `Base.metadata.create_all`. Farkla: burada session_factory'nin KENDİSİ
    döndürülür (tek bir açık session değil) — `PersistentJudge` gerçek
    kullanımda her çağrıda YENİ bir session açar (bkz. modülün kendisi)."""
    settings = Settings(_env_file=None, DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    return get_session_factory(engine)


MODEL = "gemini:test-model"


def test_db_hit_inner_hic_cagrilmaz(session_factory):
    a, b = _cift()
    overlap = ["src/x.py"]
    sim = 0.5
    onceden_yazilmis = _detection("onceden-yazilmis-yargi")
    key = _cache_key(a, b, overlap, sim, MODEL)

    with session_factory() as session:
        put_verdict(session, key, MODEL, onceden_yazilmis)
        session.commit()

    inner = _IcPort("inner-hic-cagrilmamali")
    judge = PersistentJudge(inner, session_factory=session_factory, model=MODEL)

    sonuc = judge.judge_conflict(a, b, overlap, sim)

    assert sonuc == onceden_yazilmis
    assert inner.calls == 0


def test_db_miss_inner_cagrilir_ve_sonuc_yazilir(session_factory):
    a, b = _cift()
    overlap = ["src/x.py"]
    sim = 0.5
    inner = _IcPort("inner-cevabi")
    judge = PersistentJudge(inner, session_factory=session_factory, model=MODEL)

    sonuc = judge.judge_conflict(a, b, overlap, sim)

    assert sonuc.rationale == "inner-cevabi"
    assert inner.calls == 1

    key = _cache_key(a, b, overlap, sim, MODEL)
    with session_factory() as session:
        yazilan = get_verdict(session, key)
    assert yazilan == sonuc


def test_ayni_cift_ikinci_cagrida_artik_dbden_gelir_inner_tekrar_cagrilmaz(session_factory):
    """DB MISS + yazma testinin doğal devamı: aynı sarmalayıcı örneği ile
    İKİNCİ kez sorulunca artık DB'den (bellek cache olmadan bile) gelmeli."""
    a, b = _cift()
    overlap = ["src/x.py"]
    sim = 0.5
    inner = _IcPort("inner-cevabi")
    judge = PersistentJudge(inner, session_factory=session_factory, model=MODEL)

    ilk = judge.judge_conflict(a, b, overlap, sim)
    ikinci = judge.judge_conflict(a, b, overlap, sim)

    assert ikinci == ilk
    assert inner.calls == 1  # ikinci çağrıda inner'a HİÇ gidilmedi


def test_judge_unavailable_dbye_yazilmaz_istisna_yayilir(session_factory):
    """#252 sözleşmesi: hata bir sonuç değildir, kalıcılaştırılmaz.

    MUTASYON KİLİDİ: `inner.judge_conflict()` çağrısını `put_verdict`'i de
    kapsayan geniş bir try/except'in İÇİNE al (ya da istisnayı yutup normal
    bir Detection'a çevir) -> bu test KIRILIR (ya `pytest.raises` hiç
    tetiklenmez, ya da `get_verdict` artık `None` DEĞİL bir satır döner).
    """
    a, b = _cift()
    overlap = ["src/x.py"]
    sim = 0.5
    inner = _DusenPort("kota bitti")
    judge = PersistentJudge(inner, session_factory=session_factory, model=MODEL)

    with pytest.raises(JudgeUnavailableError, match="kota bitti"):
        judge.judge_conflict(a, b, overlap, sim)

    assert inner.calls == 1

    key = _cache_key(a, b, overlap, sim, MODEL)
    with session_factory() as session:
        assert get_verdict(session, key) is None


def test_session_factory_yoksa_delege_eder_patlamaz():
    """MUTLAK KURAL 3: `session_factory=None` -> sarmalayıcı hiç kurulmamış
    gibi davranır, DB'ye hiç dokunmadan doğrudan `inner`'a delege eder."""
    inner = _IcPort("delege-cevabi")
    judge = PersistentJudge(inner, session_factory=None, model=MODEL)
    a, b = _cift()

    sonuc = judge.judge_conflict(a, b, ["src/x.py"], 0.5)

    assert sonuc.rationale == "delege-cevabi"
    assert inner.calls == 1


def test_db_yazma_hatasi_judge_yolunu_bozmaz_ama_gorunur_kalir(
    session_factory, monkeypatch, caplog
):
    """MUTLAK KURAL 2: DB yazımı patlarsa (ör. bağlantı koptu) GERÇEK yargı
    yine de döner (fail-open DEĞİL — dönen değer sahte değil) ama SESSİZ
    değildir: sayaç + log görünür kalır (repodaki altıncı fail-open'ı
    eklememek için)."""
    import ensemble.engine.persistence as persistence_module

    def _patlayan_put_verdict(session, cache_key, model, detection):
        raise RuntimeError("db baglantisi koptu")

    monkeypatch.setattr(persistence_module, "put_verdict", _patlayan_put_verdict)

    a, b = _cift()
    inner = _IcPort("gercek-yargi-yine-de-doner")
    judge = PersistentJudge(inner, session_factory=session_factory, model=MODEL)

    with caplog.at_level(logging.ERROR, logger="ensemble.judge.persistence"):
        sonuc = judge.judge_conflict(a, b, ["src/x.py"], 0.5)

    assert sonuc.rationale == "gercek-yargi-yine-de-doner"
    assert judge.write_failures == 1
    assert "yazımı başarısız" in caplog.text


def test_farkli_model_ayni_cifti_ayri_satirda_tutar(session_factory):
    """`model`in anahtara katılması: aynı çift farklı bir model tarafından
    yargılanırsa DB'de ayrı satır olarak tutulur — biri diğerinin üzerine
    yazılmaz (bkz. `cache_key` payload'ına `model`in katılması gerekçesi)."""
    a, b = _cift()
    overlap = ["src/x.py"]
    sim = 0.5

    gemini_judge = PersistentJudge(
        _IcPort("gemini-cevabi"), session_factory=session_factory, model="gemini:v1"
    )
    groq_judge = PersistentJudge(
        _IcPort("groq-cevabi"), session_factory=session_factory, model="groq:v1"
    )

    gemini_sonuc = gemini_judge.judge_conflict(a, b, overlap, sim)
    groq_sonuc = groq_judge.judge_conflict(a, b, overlap, sim)

    assert gemini_sonuc.rationale == "gemini-cevabi"
    assert groq_sonuc.rationale == "groq-cevabi"

    # Model değişince ikinci judge DB'de kendi satırını bulamaz - inner'a
    # gitti (yukarıdaki assert'ler zaten bunu kanıtlıyor); burada ayrıca iki
    # AYRI satırın var olduğunu (biri diğerinin üzerine YAZILMADIĞINI) da
    # doğrudan kontrol ediyoruz.
    key_gemini = _cache_key(a, b, overlap, sim, "gemini:v1")
    key_groq = _cache_key(a, b, overlap, sim, "groq:v1")
    assert key_gemini != key_groq
    with session_factory() as session:
        assert get_verdict(session, key_gemini).rationale == "gemini-cevabi"
        assert get_verdict(session, key_groq).rationale == "groq-cevabi"


# ---------------------------------------------------------------------------
# Kablolama (#259 GÖREV 2/2): app.py::_build_judge_port zinciri
# (`tests/unit/test_app_wiring.py` kalıbını izler)
# ---------------------------------------------------------------------------

_ENV_KEYS = [
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "LLM_PROVIDER",
    "GITHUB_APP_ID",
    "GITHUB_APP_PRIVATE_KEY_PATH",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_REPO_OWNER",
    "GITHUB_REPO_NAME",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # bkz. test_app_wiring.py::_clean_env - gelistiricinin makinesindeki
    # gercek export'lar testi yanıltmasın.
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _hosted_settings(tmp_path, **overrides) -> Settings:
    db_path = tmp_path / "persistent-judge-wiring.db"
    return Settings(
        _env_file=None,
        ENSEMBLE_MODE="hosted",
        DATABASE_URL=f"sqlite:///{db_path}",
        **overrides,
    )


def test_hosted_modda_session_factory_ile_persistentjudge_zincire_girer(tmp_path):
    from ensemble.app import _build_judge_port
    from ensemble.integrations.gemini.judge import GeminiJudgeAdapter

    settings = _hosted_settings(tmp_path, GEMINI_API_KEY="fake-key")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    sf = get_session_factory(engine)

    judge = _build_judge_port(settings, session_factory=sf)

    assert isinstance(judge, PersistentJudge)
    assert isinstance(judge.inner, GeminiJudgeAdapter)
    assert judge.model == f"gemini:{settings.GEMINI_MODEL}"


def test_local_modda_persistentjudge_KURULMAZ_session_factory_olsa_bile(tmp_path):
    """MUTLAK KURAL 3: ENSEMBLE_MODE=local iken (SQLite session_factory
    teknik olarak var olsa bile) katman devreye girmez — mevcut davranış
    aynen korunur."""
    from ensemble.app import _build_judge_port
    from ensemble.integrations.gemini.judge import GeminiJudgeAdapter

    settings = Settings(
        _env_file=None,
        ENSEMBLE_MODE="local",
        GEMINI_API_KEY="fake-key",
        DATABASE_URL=f"sqlite:///{tmp_path / 'local.db'}",
    )
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    sf = get_session_factory(engine)

    judge = _build_judge_port(settings, session_factory=sf)

    assert isinstance(judge, GeminiJudgeAdapter)
    assert not isinstance(judge, PersistentJudge)


def test_hosted_modda_session_factory_verilmezse_yine_de_kurulmaz(tmp_path):
    """Savunmacı sınır: `ENSEMBLE_MODE=hosted` ama `session_factory`
    verilmemiş (varsayılan `None`) -> katman yine kurulmaz, patlamaz."""
    from ensemble.app import _build_judge_port
    from ensemble.integrations.gemini.judge import GeminiJudgeAdapter

    settings = _hosted_settings(tmp_path, GEMINI_API_KEY="fake-key")

    judge = _build_judge_port(settings)  # session_factory verilmedi

    assert isinstance(judge, GeminiJudgeAdapter)
    assert not isinstance(judge, PersistentJudge)


def test_hosted_ve_demo_modda_tam_zincir_cached_persistent_fallback_sirasiyla(tmp_path):
    """Tam sarma sırası: `CachedConflictJudge(PersistentJudge(FallbackJudge(...)))`.

    `DEMO_MODE=True` + `GROQ_API_KEY` dolu iken en dış katman bellek
    cache'i, onun ALTINDA DB katmanı, en içte yedekli sağlayıcı zinciri
    olmalı."""
    from ensemble.app import create_app
    from fastapi.testclient import TestClient

    settings = _hosted_settings(
        tmp_path,
        DEMO_MODE=True,
        GEMINI_API_KEY="fake-key",
        GROQ_API_KEY="fake-groq-key",
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
    )

    app = create_app(settings)
    with TestClient(app):
        judge_port = app.state.radar_service.judge_port

        assert isinstance(judge_port, CachedConflictJudge)
        assert isinstance(judge_port.inner, PersistentJudge)
        assert isinstance(judge_port.inner.inner, FallbackJudge)
        assert (
            judge_port.inner.model == f"gemini:{settings.GEMINI_MODEL}+groq:{settings.GROQ_MODEL}"
        )


def test_hosted_modda_demo_kapaliyken_persistentjudge_en_dista_kalir(tmp_path):
    """`DEMO_MODE=False` iken bellek cache katmanı hiç kurulmaz —
    `PersistentJudge` doğrudan en dış katman olur."""
    from ensemble.app import create_app
    from fastapi.testclient import TestClient
    from ensemble.integrations.gemini.judge import GeminiJudgeAdapter

    settings = _hosted_settings(tmp_path, GEMINI_API_KEY="fake-key")

    app = create_app(settings)
    with TestClient(app):
        judge_port = app.state.radar_service.judge_port

        assert isinstance(judge_port, PersistentJudge)
        assert isinstance(judge_port.inner, GeminiJudgeAdapter)
