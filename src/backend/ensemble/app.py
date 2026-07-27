import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from ensemble.api.errors import ERROR_RESPONSES, ErrorEnvelope, register_exception_handlers
from ensemble.api.rate_limit import DemoRateLimitMiddleware
from ensemble.api.routers import board, events, graph, health, query, radar, scope, webhook
from ensemble.config import Settings, get_settings
from ensemble.engine.board import BoardService
from ensemble.engine.cache import CachedConflictJudge, CachedQueryJudge, CachedScopeJudge
from ensemble.engine.embeddings import (
    DEFAULT_EMBEDDING_CACHE_MAX_ENTRIES,
    CachedEmbeddings,
    HashEmbeddings,
)
from ensemble.engine.events import EventService
from ensemble.engine.graph import GraphService
from ensemble.engine.query import QueryService
from ensemble.engine.radar import RadarService
from ensemble.engine.scope import ScopeService
from ensemble.integrations.gemini.client import RETRY_WAIT_CAP_S
from ensemble.integrations.gemini.embeddings import GeminiEmbeddingsAdapter
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.gemini.query_judge import build_query_judge
from ensemble.integrations.gemini.scope_judge import build_scope_judge
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.errors import GitHubConfigError
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.engine.fallback import FallbackJudge
from ensemble.engine.persistence import PersistentJudge
from ensemble.integrations.groq.client import RETRY_WAIT_CAP_S as GROQ_RETRY_WAIT_CAP_S
from ensemble.integrations.groq.judge import GroqJudgeAdapter
from ensemble.integrations.ollama.adapter import OllamaAdapter
from ensemble.integrations.ollama.client import RETRY_WAIT_CAP_S as OLLAMA_RETRY_WAIT_CAP_S
from ensemble.integrations.query_source import HarnessEventQuerySource
from ensemble.ports import EmbeddingsPort, GitHubPort, JudgePort, VectorIndexPort
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.vector_store import LocalVectorIndex, build_vector_index
from ensemble_shared.harness import FileHarnessPort, HarnessError

logger = logging.getLogger("ensemble.wiring")


def _gemini_single_flight_wait_s(settings: Settings) -> float:
    """`engine/cache.py::TtlLruCache.get_or_compute` (ve `CachedEmbeddings.
    embed`'in kendi çok-anahtarlı tekil-uçuş turu) tek bir anahtarın kilidini
    en çok BU KADAR bekler; süre dolunca kilitsiz devam eder (bkz. o
    modüllerin docstring'i - "zarif düşüş"). Sabit `30.0` (engine katmanının
    modül-seviyesi VARSAYILANI) tek bir Gemini çağrısının GERÇEK en-kötü-durum
    süresiyle uyumsuzdu (#63 takip, ISTENEN 2): Gemini yavaşladığında -
    tam da faturanın patlayacağı an - bekleyenler süre dolunca pes edip HER
    BİRİ kendi çağrısını tekrarlıyordu (tekil-uçuş katmanının tüm amacını
    delen boşluk).

    Türetme formülü: `ResilientGeminiClient` bir çağrıyı `GEMINI_MAX_RETRIES`
    kez dener (`tenacity.stop_after_attempt`); her deneme kendi
    `GEMINI_TIMEOUT_S` HTTP timeout'una kadar sürebilir. N deneme arasında
    N-1 bekleme olur (ilk denemeden ÖNCE bekleme yok), her bekleme
    `wait_random_exponential(..., max=RETRY_WAIT_CAP_S)` ile üstten sınırlı.
    En kötü durum = N*timeout + (N-1)*bekleme_tavanı. Varsayılan ayarlarla
    (10.0 x 3 + 8.0 x 2 = 46.0 sn) tek bir çağrı gerçekten bu kadar
    sürebiliyordu - sabit 30 sn bu senaryoda HER ZAMAN erken zaman aşımına
    uğrardı. `engine katmanı ensemble.config'e bağımlı kalmaz (katman
    disiplini) - bu türetme yalnız BURADA, wiring noktasında yapılır.
    """
    attempts = settings.GEMINI_MAX_RETRIES
    waits_between_attempts = max(attempts - 1, 0)
    return attempts * settings.GEMINI_TIMEOUT_S + waits_between_attempts * RETRY_WAIT_CAP_S


def _ollama_single_flight_wait_s(settings: Settings) -> float:
    """`_gemini_single_flight_wait_s` ile AYNI formül, Ollama'nın KENDİ
    ayarlarından (#63 sertleştirme turu — dogrulayici bulgusu):
    `_build_embeddings_port` daha önce Ollama dalına da Gemini'den türetilen
    değeri enjekte ediyordu ("Ollama/Fake provider'da hiç kullanılmaz"
    yorumu YANLIŞTI — `CachedEmbeddings` DEMO_MODE'dan bağımsız, LLM_PROVIDER
    ollama/gemini olduğu SÜRECE her zaman devrededir). Varsayılan ayarlarla
    (OLLAMA_TIMEOUT_S=60.0, OLLAMA_MAX_RETRIES=2, OLLAMA_RETRY_WAIT_CAP_S=2.0)
    Ollama'nın gerçek en-kötü-durumu 2*60 + 1*2 = 122 sn'dir - Gemini'den
    türetilen 46 sn bu senaryoda ERKEN zaman aşımına uğrardı (tekil-uçuş
    katmanının amacını deler)."""
    attempts = settings.OLLAMA_MAX_RETRIES
    waits_between_attempts = max(attempts - 1, 0)
    return attempts * settings.OLLAMA_TIMEOUT_S + waits_between_attempts * OLLAMA_RETRY_WAIT_CAP_S


def _groq_single_flight_wait_s(settings: Settings) -> float:
    """`_gemini_single_flight_wait_s` ile AYNI formül, Groq'un KENDİ ayarlarından.

    `FallbackJudge` sarmasında tek bir `judge_conflict()` çağrısının en-kötü
    süresi **toplamsaldır**: birincil tüm retry'larını tüketir (bu süre boyunca
    bekler), ardından yedek kendi retry'larını tüketir. Cache'e yalnız birincilin
    bütçesini vermek, tekil-uçuş kilidini tam da yedeğin devreye girdiği anda —
    yani kotanın bittiği anda — süre aşımına uğratır; bekleyen thread'ler
    kilitsiz devam edip HER BİRİ kendi çağrısını yapar (`cache.py` "zarif
    düşüş"). #63'ün Ollama ikizinde aynı hata yakalanmıştı
    (`test_judge_ollama_dalinda_kendi_single_flight_degerini_kullanir`).
    """
    attempts = settings.GROQ_MAX_RETRIES
    waits_between_attempts = max(attempts - 1, 0)
    return attempts * settings.GROQ_TIMEOUT_S + waits_between_attempts * GROQ_RETRY_WAIT_CAP_S


def _build_github_port(settings: Settings) -> GitHubPort:
    # pem dosyası yoksa GitHubAdapter bunu hemen fark etmez (yalnız token
    # yenilenirken okunur) - istek-anı 500'e düşmeden acilis-anı degradasyona
    # ceviriyoruz (Fatih review notu, PR #159).
    if (
        settings.GITHUB_APP_PRIVATE_KEY_PATH
        and not Path(settings.GITHUB_APP_PRIVATE_KEY_PATH).is_file()
    ):
        logger.warning(
            "GITHUB_APP_PRIVATE_KEY_PATH (%s) bulunamadı — FakeGitHubAdapter kullanılıyor.",
            settings.GITHUB_APP_PRIVATE_KEY_PATH,
        )
        return FakeGitHubAdapter()
    try:
        return GitHubAdapter(settings)
    except GitHubConfigError as exc:
        logger.warning(
            "GitHub App yapılandırması eksik (%s) — FakeGitHubAdapter kullanılıyor.", exc
        )
        return FakeGitHubAdapter()


def _build_judge_port(
    settings: Settings,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> JudgePort:
    # `single_flight_budget`, tek bir `judge_conflict()` çağrısının GERÇEK
    # en-kötü-durum süresi. Adapter seçilirken başlar, sarmalayıcılar eklendikçe
    # BÜYÜR (bkz. FallbackJudge dalı) ve DEMO_MODE'da cache'e enjekte edilir.
    # Tek noktada biriktirilmesinin sebebi: değer daha önce sarma yapısından
    # BAĞIMSIZ hesaplanıyordu ve yeni bir katman eklenince sessizce eksik kaldı.
    if settings.LLM_PROVIDER == "ollama":
        judge: JudgePort = OllamaAdapter(settings)
        single_flight_budget = _ollama_single_flight_wait_s(settings)
    elif settings.GEMINI_API_KEY:
        judge = GeminiJudgeAdapter(settings)
        single_flight_budget = _gemini_single_flight_wait_s(settings)
    else:
        logger.warning(
            "GEMINI_API_KEY tanımlı değil — FakeJudgeAdapter (kural-tabanlı) kullanılıyor."
        )
        judge = FakeJudgeAdapter()
        single_flight_budget = _gemini_single_flight_wait_s(settings)

    # #255: yedek sağlayıcı — YALNIZCA bulut-birincil (Gemini) dalında.
    #
    # Koşul bilerek bir DAHİL ETME listesi (`isinstance(..., GeminiJudgeAdapter)`),
    # hariç tutma listesi DEĞİL. İlk hâli `not isinstance(judge, FakeJudgeAdapter)`
    # idi ve Ollama dalını da yakalıyordu: README §"Tam-yerel gizlilik modu"
    # *"Gemini anahtarı tanımlı olsa bile buluta geri düşmez"* diye taahhüt
    # ederken, `LLM_PROVIDER=ollama` + `GROQ_API_KEY` kurulumu judge'ı sessizce
    # `FallbackJudge(Ollama, Groq)` yapıyordu — ve Groq prompt'u `actor=`
    # (GitHub kullanıcı adları) + `files=` (repo yolları) taşıyor. Hariç tutma
    # listeleri her yeni dalda sessizce yanlışa döner; dahil etme listeleri yeni
    # dal geldiğinde KAPALI kalır.
    #
    # Sarma sırası: yedek, cache'in İÇİNDE kalır (CachedConflictJudge(FallbackJudge)).
    # Cache "hangi sağlayıcı ürettiyse üretsin ortaya çıkan yargıyı" saklar; iki
    # ayrı cache aynı çifti iki kez saklar ve birincil dönünce yedeğin bayat
    # yargısı ayrı kayıtta yaşamaya devam ederdi. İki sağlayıcı da düşerse
    # JudgeUnavailableError yayılır → #252 gereği cache'e HİÇBİR ŞEY yazılmaz.
    if settings.GROQ_API_KEY and isinstance(judge, GeminiJudgeAdapter):
        judge = FallbackJudge(primary=judge, secondary=GroqJudgeAdapter(settings))
        # Tek çağrının en-kötü süresi TOPLAMSAL: birincil retry'larını tüketir,
        # sonra yedek kendi retry'larını tüketir.
        single_flight_budget += _groq_single_flight_wait_s(settings)
    elif settings.GROQ_API_KEY:
        logger.warning(
            "GROQ_API_KEY var ama birincil judge %s — yedek devrede DEĞİL "
            "(yalnız Gemini birincilde sarılır; yerel-kal modu korunur).",
            type(judge).__name__,
        )

    # #259 (GÖREV 2/2): DB-kalıcı judge katmanı (PersistentJudge) — bellek
    # cache (aşağıdaki CachedConflictJudge) MISS verince baktığı ikinci
    # katman. YALNIZCA hosted DI'da devreye girer: `ENSEMBLE_MODE=="hosted"`
    # VE `session_factory` verilmiş olmalı. local (SQLite gelişim DB'si)
    # mevcut davranış AYNEN korunur (MUTLAK KURAL 3) — bilerek bir DAHİL
    # ETME koşuludur (#255'teki isinstance dersiyle aynı disiplin): local'de
    # de teknik olarak bir session_factory kurulabilir (SQLite), ama bu
    # katmanın DB'si hosted Postgres için tasarlandı (konteyner-yeniden-
    # yaratma senaryosu, #236) — SQLite geliştirme DB'sini "judge_verdicts"
    # ile kirletmek istenmiyor.
    #
    # model_identity: DB anahtarına (`cache_key`) katılan kimlik etiketi
    # (bkz. persistence.py docstring'i — `engine/cache.py::_digest` ile aynı
    # desen). Zincirin TAMAMININ (birincil + varsa yedek) kimliğini taşır ki
    # sağlayıcı/model versiyonu değişince eski satırlar sessizce "doğru" gibi
    # kullanılmasın. Hangi ALT sağlayıcının (birincil mi yedek mi) belirli
    # bir çağrıyı yanıtladığını AYIRT ETMEZ — tıpkı aşağıdaki
    # CachedConflictJudge(FallbackJudge(...)) sarmasının da bunu ayırt
    # etmemesi gibi (bkz. o sarmanın gerekçe yorumu).
    if isinstance(judge, FallbackJudge):
        model_identity = f"gemini:{settings.GEMINI_MODEL}+groq:{settings.GROQ_MODEL}"
    elif settings.LLM_PROVIDER == "ollama":
        model_identity = f"ollama:{settings.OLLAMA_MODEL}"
    elif isinstance(judge, GeminiJudgeAdapter):
        model_identity = f"gemini:{settings.GEMINI_MODEL}"
    else:
        model_identity = "fake"

    if settings.ENSEMBLE_MODE == "hosted" and session_factory is not None:
        # Tekil-uçuş bütçesine (`single_flight_budget`) DB gidiş-dönüşü
        # BİLEREK eklenmiyor: (1) DB round-trip'i tek, kısa bir sorgu
        # (PK lookup / upsert) — Gemini/Groq'un N-deneme×timeout formülüyle
        # karşılaştırılabilir bir büyüklük mertebesinde değil; (2) Gemini/Groq
        # için bu bütçe GERÇEK, yapılandırılmış bir üst sınırdan (TIMEOUT_S×
        # MAX_RETRIES) türetiliyor — DB için böyle bir üst sınır yapılandırması
        # (bir "DATABASE_TIMEOUT_S" ayarı) yok; icat edilecek herhangi bir
        # sabit, tam da bu dosyanın başka yerlerinde kaçınılan türden keyfi bir
        # büyüklük olurdu; (3) bütçe eksik kalırsa sonuç bir doğruluk hatası
        # DEĞİL, `TtlLruCache.get_or_compute`'un zaten belgelenmiş "zarif
        # düşüşü"dür (kilit zaman aşımına uğrar, bekleyen thread kilitsiz
        # devam eder — en kötü ihtimalle DB sorgusu/az sayıda hesaplama
        # tekrarlanır, cache asla yanlış bir şey saklamaz).
        judge = PersistentJudge(judge, session_factory=session_factory, model=model_identity)

    if settings.DEMO_MODE:
        # #63: hosted public demo — Radar'ın 10 sn'lik poll'u aynı çifti
        # yeniden Gemini'ye sormasın (fatura kapağı). local/dev'de DEMO_MODE
        # kapalıyken bu sarmalayıcı hiç devreye girmez.
        # T-63 son tur: `_build_embeddings_port` ile AYNI disiplin - tekil-uçuş
        # bekleme süresi sağlayıcının GERÇEK en-kötü-durumundan türetilir
        # (Ollama'nın ~122 sn'si yerine sabit Gemini türetmesi ~46 sn kullanılınca
        # erken zaman aşımına uğruyordu - `_ollama_single_flight_wait_s`).
        # #255 sonrası bu değer artık yukarıda BİRİKTİRİLİYOR: FallbackJudge
        # sarması en-kötü süreyi toplamsal olarak büyütür, o yüzden burada
        # yeniden hesaplanmaz — hesaplansaydı yedeğin payı yine düşerdi.
        judge = CachedConflictJudge(
            judge,
            ttl_s=settings.DEMO_CACHE_TTL_S,
            max_entries=settings.DEMO_CACHE_MAX_ENTRIES,
            single_flight_wait_s=single_flight_budget,
        )
    return judge


def _build_embeddings_port(settings: Settings) -> EmbeddingsPort:
    # #170: local/dev cache'i 2048 girişle sınırlıdır; #63 hosted demo modu
    # serbest metin `q` yüküne karşı daha sıkı ayar değerini uygular.
    max_entries = (
        settings.DEMO_CACHE_MAX_ENTRIES
        if settings.DEMO_MODE
        else DEFAULT_EMBEDDING_CACHE_MAX_ENTRIES
    )
    # Tekil-uçuş bekleme süresi DEMO_MODE'dan BAĞIMSIZ hesaplanır - ama
    # `CachedEmbeddings` sarmalayıcısının KENDİSİ (dolayısıyla `_fill_misses`
    # tekil-uçuşu) LLM_PROVIDER ollama/gemini olduğu sürece HER ZAMAN
    # DEVREDEDİR (yalnız `max_entries` DEMO_MODE'a bağlıdır - #63
    # sertleştirme turu, dogrulayıcı bulgusu: eski yorum "Ollama/Fake
    # provider'da hiç kullanılmaz" diyordu, bu YANLIŞTI). Bu yüzden HER
    # provider KENDİ gerçek en-kötü-durum formülünü almalı - Gemini'nin
    # değerini Ollama dalına enjekte etmek, Ollama'nın (daha yavaş) gerçek
    # timeout'undan ERKEN vazgeçilmesine yol açardı (bkz.
    # `_ollama_single_flight_wait_s` docstring'i).
    if settings.LLM_PROVIDER == "ollama":
        return CachedEmbeddings(
            OllamaAdapter(settings),
            max_entries=max_entries,
            single_flight_wait_s=_ollama_single_flight_wait_s(settings),
        )
    if settings.GEMINI_API_KEY:
        return CachedEmbeddings(
            GeminiEmbeddingsAdapter(settings),
            max_entries=max_entries,
            single_flight_wait_s=_gemini_single_flight_wait_s(settings),
        )
    logger.warning("GEMINI_API_KEY tanımlı değil — HashEmbeddings kullanılıyor.")
    return HashEmbeddings()


def _build_radar_service(
    settings: Settings,
    *,
    session_factory: Callable[[], Session] | None = None,
    vector_index: VectorIndexPort | None = None,
) -> RadarService:
    return RadarService(
        github_port=_build_github_port(settings),
        judge_port=_build_judge_port(settings, session_factory=session_factory),
        embeddings_port=_build_embeddings_port(settings),
        vector_index=vector_index,
        window_days=settings.RADAR_WINDOW_DAYS,
        min_jaccard=settings.RADAR_MIN_JACCARD,
        min_similarity=settings.RADAR_MIN_SIMILARITY,
        backfill_limit=settings.GITHUB_BACKFILL_LIMIT,
        default_base=settings.GITHUB_DEFAULT_BRANCH,
        judge_concurrency=settings.RADAR_JUDGE_CONCURRENCY,
    )


def _build_query_service(
    settings: Settings,
    radar_service: RadarService,
    *,
    session_factory: Callable[[], Session] | None = None,
    vector_index: VectorIndexPort | None = None,
) -> QueryService:
    if session_factory is None and settings.ENSEMBLE_MODE == "local":
        session_factory = get_session_factory(get_engine(settings))
    if vector_index is None:
        if settings.ENSEMBLE_MODE == "local":
            vector_index = build_vector_index(settings)
        else:
            logger.warning("Hosted vector index henüz bağlı değil — local index kullanılıyor.")
            vector_index = LocalVectorIndex()
    source = HarnessEventQuerySource(
        FileHarnessPort(),
        session_factory=session_factory,
        github_owner=settings.GITHUB_REPO_OWNER,
        github_repo=settings.GITHUB_REPO_NAME,
    )
    query_judge_port = build_query_judge(settings)
    if settings.DEMO_MODE:
        # #63: aynı soru+belge çiftini Gemini'ye yeniden sormaz.
        query_judge_port = CachedQueryJudge(
            query_judge_port,
            ttl_s=settings.DEMO_CACHE_TTL_S,
            max_entries=settings.DEMO_CACHE_MAX_ENTRIES,
            single_flight_wait_s=_gemini_single_flight_wait_s(settings),
        )
    return QueryService(
        source_port=source,
        embeddings_port=radar_service.embeddings_port,
        vector_index=vector_index,
        judge_port=query_judge_port,
    )


def _build_scope_service(settings: Settings, radar_service: RadarService) -> ScopeService:
    subject_port = (
        radar_service.github_port if isinstance(radar_service.github_port, GitHubAdapter) else None
    )
    scope_judge_port = build_scope_judge(settings)
    if settings.DEMO_MODE:
        # #63: aynı ref+subject+aday üçlüsünü yeniden yargılamaz.
        scope_judge_port = CachedScopeJudge(
            scope_judge_port,
            ttl_s=settings.DEMO_CACHE_TTL_S,
            max_entries=settings.DEMO_CACHE_MAX_ENTRIES,
            single_flight_wait_s=_gemini_single_flight_wait_s(settings),
        )
    return ScopeService(
        harness_port=FileHarnessPort(),
        judge_port=scope_judge_port,
        embeddings_port=radar_service.embeddings_port,
        subject_port=subject_port,
    )


def _verify_harness_boot(scope_service: ScopeService) -> None:
    """#242 BLOCKER 1(b) — FAIL-CLOSED açılış kontrolü.

    Ölçülen üretim hatası: bir konteyner dağıtımında `deploy/docker-compose
    .prod.yml` (#246) `.harness/`i host'tan SALT-OKUNUR bind-mount ediyor.
    Host tarafında `.harness/` dizini yoksa Docker orada SESSİZCE **boş bir
    dizin** yaratır ve imaja gömülü (Dockerfile'daki `COPY .harness/`) kopyayı
    MASKELER — sonuç: `read_scope()` `HarnessError` fırlatır, `read_tasks()`
    sessizce `[]` döner, ürün "çalışıyor görünüp" boş board/scope sunar.

    Bu fonksiyon o senaryoyu SESSİZ bozulmadan GÜRÜLTÜLÜ açılış hatasına
    çevirir — ama yalnız TEK bir dosyaya (scope) bakmak yetmez: aynı
    bind-mount maskeleme senaryosu `tasks/`/`active/` dizinlerinin KENDİSİNİ
    de yok edebilir, ve o iki metod (`read_tasks`/`read_active`) "dizin yok"
    ile "dizin var ama boş" durumlarını ayırt etmeden ikisinde de sessizce
    `[]` döner — yani #242'nin asıl semptomu (BOŞ BOARD) daha dar bir biçimde
    HAYATTA kalırdı (bağımsız doğrulayıcı bulgusu, review turu 3). Bu yüzden
    burası `.harness/`'in BÜTÜNLÜĞÜNÜ doğrular: `scope/<sprint>` OKUNABİLİR mi
    + `tasks/` VE `active/` dizinleri VAR MI ve listelenebiliyor mu.
    `tasks/`/`active/` dizini VAR ama İÇİ BOŞ olması (hiç açık task/aktif
    beyan yok) MEŞRU bir durumdur — `verify_dir_readable` bunda RAISE ETMEZ,
    yalnız dizinin kendisi hiç yoksa (ya da listelenemiyorsa) fail-closed'a
    düşer. Bunlardan HERHANGİ biri okunamıyorsa süreç hiç ayağa kalkmaz, hata
    mesajı hangi parçanın eksik olduğunu ve ne yapılacağını söyler.

    KASITLI SINIR: yalnız `lifespan` (uygulama açılışı) içinden çağrılır —
    `FileHarnessPort`/`ScopeService` KURULUMUNA (constructor'a) taşınmadı;
    `tmp_path` köklü port kullanan birim testlerin (ör. `test_scope.py`)
    hiçbiri bu kontrolden geçmez ve etkilenmez (bkz. `.harness/README.md` §9).
    """
    harness_port = scope_service.harness_port
    try:
        harness_port.read_scope(scope_service.sprint)
    except HarnessError as exc:
        raise RuntimeError(
            f"ACILIS DURDURULDU: .harness/scope/sprint-{scope_service.sprint} "
            f"okunamadi ({exc}). Olasi sebep: .harness/ konteynerde yok ya da "
            "bos - host'ta .harness/ dizini bulunmadan bind-mount edilirse "
            "Docker orada bos bir dizin yaratip imaja gomulu kopyayi "
            "maskeler. COZUM: repo kokunde `.harness/` gercekten var mi ve "
            "git'e alinmis mi kontrol et (git ls-files -- .harness), "
            "bind-mount kullaniliyorsa host tarafinda ayni icerigi senkronla."
        ) from exc

    for folder in ("tasks", "active"):
        try:
            harness_port.verify_dir_readable(folder)
        except HarnessError as exc:
            raise RuntimeError(
                f"ACILIS DURDURULDU: .harness/{folder}/ dizini bulunamadi ya da "
                f"okunamiyor ({exc}). Bos bir .harness/{folder}/ (icinde hic "
                "dosya olmamasi) MESRUDUR ve bu hatayi TETIKLEMEZ - yalniz "
                "dizinin KENDISI hic yoksa (ya da izin hatasiyla listelenemiyorsa) "
                "buraya duser. Olasi sebep: .harness/ konteynerde eksik/kismi "
                "kopyalanmis - host'ta .harness/ dizini bulunmadan bind-mount "
                "edilirse Docker orada bos bir dizin yaratip imaja gomulu kopyayi "
                f"maskeler. COZUM: repo kokunde `.harness/{folder}/` gercekten "
                f"var mi ve git'e alinmis mi kontrol et (git ls-files -- "
                f".harness/{folder}), bind-mount kullaniliyorsa host tarafinda "
                "ayni icerigi senkronla."
            ) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    # #104 review bulgusu (Semih, blocker): stub session_factory=lambda: None
    # override'sız istekte TypeError veriyordu - store/engine.py'deki gercek
    # engine'e baglandi (radar_service ile ayni desen). Tablolar Alembic'le
    # onceden kurulu varsayilir (make migrate) - burasi sema kurmaz.
    # #62 webhook receiver: Projector'un yazacagi gercek DB session factory,
    # graph_service ile aynisi paylasilir.
    #
    # SIRA ÖNEMLİ (iki ayrı gereksinim, aynı zincirde):
    #   1) session_factory ÖNCE — #259: judge zincirindeki PersistentJudge
    #      (hosted DI) buna ihtiyaç duyar; eskiden yalnız query/board/graph
    #      servisleri için SONRADAN kuruluyordu.
    #   2) vector_index sonra — #183: kendisi de session_factory'yi alır
    #      (hosted'da pgvector, local'de FAISS).
    #   3) radar_service en son — ikisini birden tüketir.
    app.state.session_factory = get_session_factory(get_engine(settings))
    app.state.vector_index = build_vector_index(
        settings,
        session_factory=app.state.session_factory if settings.ENSEMBLE_MODE == "hosted" else None,
    )
    app.state.radar_service = _build_radar_service(
        settings,
        session_factory=app.state.session_factory,
        vector_index=app.state.vector_index,
    )
    app.state.graph_service = GraphService(app.state.session_factory)
    app.state.query_service = _build_query_service(
        settings,
        app.state.radar_service,
        session_factory=app.state.session_factory,
        vector_index=app.state.vector_index,
    )
    app.state.scope_service = _build_scope_service(settings, app.state.radar_service)
    _verify_harness_boot(app.state.scope_service)
    app.state.board_service = BoardService(session_factory=app.state.session_factory)
    app.state.event_service = EventService(
        harness_port=FileHarnessPort(),
        github_port=_build_github_port(settings),
    )
    yield
    # TODO: Kapanışta kaynakları temizle


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Ensemble",
        version="0.0.1",
        description="AI-çağı ekipleri için paylaşılan proje beyni",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Hosted demo IP/rate cap (#63) — CORS'TAN ÖNCE eklenmeli. Starlette
    # add_middleware'i başa ekler → SON eklenen middleware EN DIŞTA koşar.
    # Bu middleware CORS'tan SONRA eklenseydi, ürettiği 429 cevabı CORS
    # katmanının dışında kalır ve tarayıcı gerçek hatayı "CORS error" diye
    # gizlerdi (#45/#150 dersi — sıra test_demo_rate_limit.py ile kilitli).
    # Yalnız DEMO_MODE=true iken kurulur; local/dev'de hiç devreye girmez.
    if settings.DEMO_MODE:
        app.add_middleware(DemoRateLimitMiddleware, settings=settings)

    # CORS (#45): açık allowlist — asla "*". Kimlik bilgisi taşınmaz (D-23:
    # cookie/auth yok); kontrattaki tüm endpoint'ler GET.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # Global hata zarfı (#54): 500+stacktrace yerine tek tip JSON (Ek D)
    register_exception_handlers(app, settings)

    # Router'ları bağla — ERROR_RESPONSES tek kaynaktan yayılır (spec beyanı, #54)
    app.include_router(health.router, responses=ERROR_RESPONSES)
    app.include_router(radar.router, responses=ERROR_RESPONSES)
    app.include_router(scope.router, responses=ERROR_RESPONSES)
    app.include_router(board.router, responses=ERROR_RESPONSES)
    app.include_router(query.router, responses=ERROR_RESPONSES)
    app.include_router(graph.router, responses=ERROR_RESPONSES)
    app.include_router(events.router, responses=ERROR_RESPONSES)
    # #62 hata sözleşmesi: framework HTTPException'ları da Ek D zarfını taşır
    # (errors.py::http_exception) ama bunu ERROR_RESPONSES'a genel eklemedik -
    # 400/401 diğer (GET) router'lara uymuyor. Webhook'a özel bildiriliyor ki
    # üretilen client (#20 zinciri) gerçek hata gövdesini tipleyebilsin
    # (Semih review, #62: openapi 401'i gövdesiz ilan ediyordu).
    _webhook_responses = {
        **ERROR_RESPONSES,
        400: {"model": ErrorEnvelope, "description": "Geçersiz JSON gövdesi"},
        401: {"model": ErrorEnvelope, "description": "Eksik/geçersiz webhook imzası"},
    }
    app.include_router(webhook.router, responses=_webhook_responses)

    return app
