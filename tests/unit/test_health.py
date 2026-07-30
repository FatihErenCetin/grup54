from fastapi.testclient import TestClient

from ensemble.api.routers.health import health_check
from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.engine.embeddings import HashEmbeddings
from ensemble.engine.radar import RadarService
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.fake import FakeGitHubAdapter


def _radar_service(*, github_port, judge_port) -> RadarService:
    return RadarService(
        github_port=github_port,
        judge_port=judge_port,
        embeddings_port=HashEmbeddings(),
    )


def test_health_check_fake_adapterlerde_missing_raporlar():
    # sozlesme §3: {status, mode, github_auth, gemini} (#53 zenginlestirmesi)
    settings = Settings(ENSEMBLE_MODE="local")
    radar_service = _radar_service(github_port=FakeGitHubAdapter(), judge_port=FakeJudgeAdapter())
    result = health_check(settings=settings, radar_service=radar_service)
    assert result.model_dump() == {
        "status": "ok",
        "mode": "local",
        "github_auth": "missing",
        "gemini": "missing",
        "fallback": "missing",
    }


def test_health_check_gercek_adapterlerde_configured_raporlar(tmp_path):
    pem = tmp_path / "app.pem"
    pem.write_text("fake-pem-icerigi")
    github_settings = Settings(
        _env_file=None,
        GITHUB_APP_ID="123",
        GITHUB_APP_PRIVATE_KEY_PATH=str(pem),
        GITHUB_APP_INSTALLATION_ID="456",
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
    )
    gemini_settings = Settings(_env_file=None, GEMINI_API_KEY="fake-key")
    radar_service = _radar_service(
        github_port=GitHubAdapter(github_settings),
        judge_port=GeminiJudgeAdapter(gemini_settings),
    )
    result = health_check(settings=Settings(ENSEMBLE_MODE="hosted"), radar_service=radar_service)
    assert result.github_auth == "configured"
    assert result.gemini == "configured"
    assert result.mode == "hosted"


def test_health_check_gecersiz_pem_de_configured_doner_dogrulanmis_degil(tmp_path):
    """Semih'in review bulgusu: 'configured' yalnizca kimlik bilgisi SET
    EDILMIS demektir, GECERLI demek DEGILDIR - GitHubAdapter construction'i
    PEM icerigini parse etmez (yalniz token yenilenirken okunur, #159).
    Bu test o sinirin BILEREK boyle kaldigini belgeler (canli dogrulama
    #58/spot-check kapsami)."""
    pem = tmp_path / "gecersiz.pem"
    pem.write_text("bu-gecerli-bir-pem-degil")
    github_settings = Settings(
        _env_file=None,
        GITHUB_APP_ID="123",
        GITHUB_APP_PRIVATE_KEY_PATH=str(pem),
        GITHUB_APP_INSTALLATION_ID="456",
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
    )
    radar_service = _radar_service(
        github_port=GitHubAdapter(github_settings), judge_port=FakeJudgeAdapter()
    )
    result = health_check(settings=Settings(ENSEMBLE_MODE="hosted"), radar_service=radar_service)
    assert result.github_auth == "configured"


def test_health_demo_modda_gercek_wiring_uzerinden_gemini_configured_raporlar(tmp_path):
    """E1/B1 regresyon kilidi: yukaridaki testler RadarService'i ELLE kurar,
    yani app.py::_build_judge_port'un DEMO_MODE=true iken judge'i
    CachedConflictJudge (#63) ile SARMALADIGI gercek wiring'i hic gormez - bu
    delik oradan sizdi (hosted demoda /health hep gemini=missing derdi).

    Bu test GERCEK create_app + lifespan yolundan geciyor: fix geri alinirsa
    (health.py'de getattr(...,"inner",...) unwrap'i kaldirilirsa) kirilir,
    cunku radar_service.judge_port artik dogrudan GeminiJudgeAdapter DEGIL,
    CachedConflictJudge olur ve isinstance dogrudan False doner."""
    db_path = tmp_path / "health-demo.db"
    settings = Settings(
        _env_file=None,
        DEMO_MODE=True,
        GEMINI_API_KEY="fake-key",
        GITHUB_REPO_OWNER="FatihErenCetin",
        GITHUB_REPO_NAME="grup54",
        DATABASE_URL=f"sqlite:///{db_path}",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["gemini"] == "configured"
    assert body["mode"] == "local"


# ---------------------------------------------------------------------------
# #238 canlı smoke bulgusu — sarmalayıcı ZİNCİRİ, tek kat değil
#
# Regresyon: `getattr(port, "inner", port)` YALNIZ BİR kat açıyordu. O düzeltme
# yazıldığında tek sarmalayıcı vardı (CachedConflictJudge) ve doğruydu. #255
# ikinci katı ekleyince (FallbackJudge) zincir `Cached -> Fallback -> Gemini`
# oldu; bir kat açınca elde FallbackJudge kalıyor ve isinstance False dönüyordu.
#
# Sonuç canlıda ölçüldü: /health `gemini="missing"` raporladı ve STRICT modda
# `make smoke` (#189) KIRMIZI kaldı — anahtar doğru ayarlı olmasına rağmen.
# Yani sağlık kontrolü "yapılandırma yok" diye YALAN söylüyordu.
# ---------------------------------------------------------------------------


def _gemini_judge() -> GeminiJudgeAdapter:
    return GeminiJudgeAdapter(Settings(_env_file=None, GEMINI_API_KEY="fake-key"))


def test_health_tek_sarmalayicida_gemini_bulur():
    from ensemble.engine.cache import CachedConflictJudge

    sarmalanmis = CachedConflictJudge(_gemini_judge(), ttl_s=60, max_entries=8)
    sonuc = health_check(
        settings=Settings(ENSEMBLE_MODE="hosted"),
        radar_service=_radar_service(github_port=FakeGitHubAdapter(), judge_port=sarmalanmis),
    )
    assert sonuc.gemini == "configured"


def test_health_IKI_sarmalayicida_da_gemini_bulur():
    """MUTASYON KİLİDİ: zincir yürüyüşünü tek-kat `getattr(...,"inner",...)`'a
    geri çevir → bu test kırılır (canlıda olan tam olarak buydu)."""
    from ensemble.engine.cache import CachedConflictJudge
    from ensemble.engine.fallback import FallbackJudge
    from ensemble.integrations.gemini.fake import FakeJudgeAdapter as _Yedek

    zincir = CachedConflictJudge(
        FallbackJudge(primary=_gemini_judge(), secondary=_Yedek()),
        ttl_s=60,
        max_entries=8,
    )
    sonuc = health_check(
        settings=Settings(ENSEMBLE_MODE="hosted"),
        radar_service=_radar_service(github_port=FakeGitHubAdapter(), judge_port=zincir),
    )
    assert sonuc.gemini == "configured"


def test_health_gemini_YEDEKTEYKEN_de_bulur():
    """Gemini zincirin ikincil dalındaysa da bulunmalı — `secondary` de gezilir."""
    from ensemble.engine.fallback import FallbackJudge

    zincir = FallbackJudge(primary=FakeJudgeAdapter(), secondary=_gemini_judge())
    sonuc = health_check(
        settings=Settings(ENSEMBLE_MODE="hosted"),
        radar_service=_radar_service(github_port=FakeGitHubAdapter(), judge_port=zincir),
    )
    assert sonuc.gemini == "configured"


def test_health_zincirde_gemini_YOKSA_missing():
    """Simetrik kilit: zincir yürüyüşü her şeye 'configured' DEMEMELİ."""
    from ensemble.engine.cache import CachedConflictJudge
    from ensemble.engine.fallback import FallbackJudge

    zincir = CachedConflictJudge(
        FallbackJudge(primary=FakeJudgeAdapter(), secondary=FakeJudgeAdapter()),
        ttl_s=60,
        max_entries=8,
    )
    sonuc = health_check(
        settings=Settings(ENSEMBLE_MODE="hosted"),
        radar_service=_radar_service(github_port=FakeGitHubAdapter(), judge_port=zincir),
    )
    assert sonuc.gemini == "missing"


# ── #359: yedek saglayici gorunurlugu ────────────────────────────────────────


def _groq_judge():
    """Gercek `GroqJudgeAdapter` — ag cagrisi YOK, yalniz kurulum."""
    from ensemble.integrations.groq.judge import GroqJudgeAdapter

    return GroqJudgeAdapter(Settings(GROQ_API_KEY="test-anahtari"))


def test_health_yedek_zincirde_VARSA_configured():
    """#359 — Groq zincirin ikincil dalindaysa `fallback: configured`.

    30 Tem olcumu: Gemini'nin gunluk generate kotasi (flash: 20/gun) bitip
    `/query` 503 donerken "yedek var mi" sorusunun cevabi ancak sunucuya
    SSH'lenip `ensemble.env` sayilarak bulunabildi — `/health` o sirada
    `status: ok` diyordu ve yedekten hic bahsetmiyordu.

    MUTASYON KILIDI: `fallback=fallback` alanini `"missing"` sabitine cevir
    -> bu test kirilir.
    """
    from ensemble.engine.fallback import FallbackJudge

    zincir = FallbackJudge(primary=_gemini_judge(), secondary=_groq_judge())
    sonuc = health_check(
        settings=Settings(ENSEMBLE_MODE="hosted"),
        radar_service=_radar_service(github_port=FakeGitHubAdapter(), judge_port=zincir),
    )
    assert sonuc.fallback == "configured"
    assert sonuc.gemini == "configured"  # iki alan birbirini bozmuyor


def test_health_ANAHTAR_dolu_ama_yedek_SARILMAMISSA_missing():
    """Bu alanin ASIL varlik sebebi — `settings.GROQ_API_KEY`'e bakmak YETMEZ.

    `app.py` yedegi yalnizca birincil GERCEK bir Gemini adapteri iken sarar
    (dahil-etme listesi). Anahtar dolu ama birincil baska bir sey ise yedek
    DEVREDE DEGILDIR; bugun bu yalnizca bir `logger.warning`'e dusuyor.
    `/health` bu hali "configured" diye raporlarsa operatore yalan soyler.

    MUTASYON KILIDI: `fallback`i zincir yerine `settings.GROQ_API_KEY`'den
    turet -> bu test kirilir (anahtar dolu ama zincirde Groq yok).
    """
    sonuc = health_check(
        settings=Settings(ENSEMBLE_MODE="hosted", GROQ_API_KEY="dolu-ama-sarilmadi"),
        radar_service=_radar_service(
            github_port=FakeGitHubAdapter(), judge_port=FakeJudgeAdapter()
        ),
    )
    assert sonuc.fallback == "missing"


def test_health_yedek_SARMALAYICI_ALTINDA_da_bulunur():
    """Cache/devre-kesici gibi katmanlar yedegi gizlememeli — zincir yurunur."""
    from ensemble.engine.cache import CachedConflictJudge
    from ensemble.engine.fallback import FallbackJudge

    zincir = CachedConflictJudge(
        FallbackJudge(primary=_gemini_judge(), secondary=_groq_judge()),
        ttl_s=60,
        max_entries=8,
    )
    sonuc = health_check(
        settings=Settings(ENSEMBLE_MODE="hosted"),
        radar_service=_radar_service(github_port=FakeGitHubAdapter(), judge_port=zincir),
    )
    assert sonuc.fallback == "configured"


def test_health_yanit_govdesi_SIR_sizdirmaz():
    """Yalniz var/yok — anahtarin kendisi ya da bir parcasi ASLA."""
    from ensemble.engine.fallback import FallbackJudge

    sir = "gsk-cok-gizli-anahtar-degeri"
    from ensemble.integrations.groq.judge import GroqJudgeAdapter

    zincir = FallbackJudge(
        primary=_gemini_judge(), secondary=GroqJudgeAdapter(Settings(GROQ_API_KEY=sir))
    )
    sonuc = health_check(
        settings=Settings(ENSEMBLE_MODE="hosted", GROQ_API_KEY=sir),
        radar_service=_radar_service(github_port=FakeGitHubAdapter(), judge_port=zincir),
    )
    govde = str(sonuc.model_dump())
    assert sir not in govde
    assert "gsk" not in govde
    assert sonuc.fallback == "configured"
