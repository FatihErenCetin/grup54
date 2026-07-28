"""Çok-kiracılı servis kaydı (#79 kalan dilim, T-79).

`TenantRegistry`: `repo_full_name -> memoize edilmiş servis takımı` (LRU ile
sınırlı — sınırsız büyümesin). Engine sınıfları (`RadarService`, `ScopeService`,
`QueryService`, `BoardService`, `EventService`, `GraphService`) port'ları
KURUCUDAN alır (bkz. AGENTS.md mimari ilkeleri) — bu modül onları FARKLI
port'larla (farklı owner/repo + kendi installation token'ı + kiracıya
filtrelenmiş DB sorguları) kurarak çok-kiracılığı sağlar. **Hiçbir engine
dosyası DEĞİŞTİRİLMEDİ** — yalnızca bu dosyanın kendisi + BoardService/
EventService/GraphService'in (DB'yi doğrudan sorgulayan, port almayan üç
servis) `repo_full_name` kurucu parametresi (bkz. o dosyaların kendi
gerekçesi).

Kiracı çözümü (hangi repo_full_name/installation_id kullanılacağı) BURADA
YAPILMAZ — o, `api/deps.py::TenantDep`'in işi (oturum + `?repo=` doğrulaması,
sunucu tarafında, istemciye güvenilmeden). Bu modül yalnızca ZATEN ÇÖZÜLMÜŞ
bir `Tenant`'a karşılık gelen servis takımını üretir/hatırlar.

Demo kiracı (`settings.demo_repo_full_name`) İSTİSNADIR: onun takımı zaten
`lifespan`de (app.py) kurulan `app.state.*_service` singleton'larıdır — bu
modül onu YENİDEN KURMAZ (davranış/performans bugünküyle BİREBİR aynı kalır —
D-23'ün korunan vaadi, "bugünkü public demo aynen çalışmaya devam etmeli").
Yalnız GERÇEK (installation'lı) kiracılar için yeni bir takım inşa edilir.

LLM'e giden port'lar (`judge_port`, `embeddings_port`, `query_judge_port`,
`scope_judge_port`) TÜM kiracılar arasında PAYLAŞILIR — bunlar içerik-adresli
(a+b+overlap+sim / soru+belge hash'i) cache'lerdir, kiracıdan HABERSİZDİR ve
hiçbir kiracıya-özel VERİ taşımazlar; iki farklı kiracıda metinsel olarak
BİREBİR aynı bir diff/soru varsa (nadir) cache isabeti paylaşılabilir — bu
zararsızdır (yargının kendisi içerikten türer, tekrar hesaplansa da AYNI
sonucu verir), veri SIZINTISI değildir. Yalnız GitHub port'u (hangi repo'ya
gidileceği) ve DB projeksiyon sorguları (hangi satırların görüneceği)
kiracıya göre GERÇEKTEN ayrışır — izolasyonun canlı olduğu yer burasıdır.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ensemble.config import Settings
from ensemble.engine.board import BoardService
from ensemble.engine.events import EventService
from ensemble.engine.graph import GraphService
from ensemble.engine.query import QueryService
from ensemble.engine.radar import RadarService
from ensemble.engine.scope import ScopeService
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.errors import GitHubConfigError
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.integrations.null_harness import NullHarnessPort
from ensemble.integrations.query_source import HarnessEventQuerySource
from ensemble.ports import (
    EmbeddingsPort,
    GitHubPort,
    JudgePort,
    QueryJudgePort,
    ScopeJudgePort,
    VectorIndexPort,
)
from ensemble.store.vector_store import build_vector_index
from ensemble_shared.harness import HarnessPort

logger = logging.getLogger("ensemble.tenancy")

DEFAULT_TENANT_CACHE_SIZE = 16


@dataclass(frozen=True)
class Tenant:
    """Sunucu tarafında ÇÖZÜLMÜŞ kiracı — `api/deps.py::TenantDep`'in ürettiği,
    `TenantRegistry`'nin tükettiği sözleşme. `installation_id` demo kiracı
    için `None`'dur (statik `.env` yapılandırması kullanılır, D-23)."""

    repo_full_name: str
    installation_id: str | None
    is_demo: bool


@dataclass
class ServiceTeam:
    """Bir kiracının kendi servis takımı — engine SINIFLARININ KENDİSİ
    değişmedi, yalnızca bu kiracının port'larıyla kurulmuş birer örnek."""

    radar_service: RadarService
    board_service: BoardService
    scope_service: ScopeService
    query_service: QueryService
    graph_service: GraphService
    event_service: EventService


class TenantRegistry:
    def __init__(
        self,
        settings: Settings,
        *,
        demo_team: ServiceTeam,
        session_factory: Callable[[], Session],
        judge_port: JudgePort,
        embeddings_port: EmbeddingsPort,
        query_judge_port: QueryJudgePort,
        scope_judge_port: ScopeJudgePort,
        max_entries: int = DEFAULT_TENANT_CACHE_SIZE,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._settings = settings
        self._demo_repo = settings.demo_repo_full_name
        self._demo_team = demo_team
        self._session_factory = session_factory
        self._judge_port = judge_port
        self._embeddings_port = embeddings_port
        self._query_judge_port = query_judge_port
        self._scope_judge_port = scope_judge_port
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._teams: OrderedDict[str, ServiceTeam] = OrderedDict()

    def get_team(self, tenant: Tenant) -> ServiceTeam:
        """`tenant`'a karşılık gelen (memoize edilmiş) servis takımını döner.

        Demo kiracı için HER ZAMAN `lifespan`de kurulan singleton döner —
        LRU'ya hiç girmez, tahliye edilemez.
        """
        if tenant.is_demo or (self._demo_repo and tenant.repo_full_name == self._demo_repo):
            return self._demo_team

        with self._lock:
            team = self._teams.get(tenant.repo_full_name)
            if team is not None:
                self._teams.move_to_end(tenant.repo_full_name)
                return team

        team = self._build_team(tenant)

        with self._lock:
            self._teams[tenant.repo_full_name] = team
            self._teams.move_to_end(tenant.repo_full_name)
            while len(self._teams) > self._max_entries:
                evicted_repo, _ = self._teams.popitem(last=False)
                logger.info("TenantRegistry LRU tahliyesi: %s", evicted_repo)
        return team

    def _build_team(self, tenant: Tenant) -> ServiceTeam:
        owner, _, repo = tenant.repo_full_name.partition("/")
        if not owner or not repo:
            raise ValueError(
                f"repo_full_name 'owner/repo' bicimli olmali: {tenant.repo_full_name!r}"
            )

        # GitHubAdapter/InstallationTokenCache owner/repo/installation_id'yi
        # YALNIZCA verilen Settings nesnesinden okur (integrations/github/
        # adapter.py, auth.py) — bu yüzden onları DEĞİŞTİRMEDEN, klonlanmış
        # bir Settings ile kiracıya özel bir GitHubAdapter kurmak yeterli
        # (engine/integrations sıfır dokunuş).
        tenant_settings = self._settings.model_copy(
            update={
                "GITHUB_REPO_OWNER": owner,
                "GITHUB_REPO_NAME": repo,
                "GITHUB_APP_INSTALLATION_ID": tenant.installation_id,
            }
        )
        github_port: GitHubPort
        try:
            github_port = GitHubAdapter(tenant_settings)
        except GitHubConfigError as exc:
            logger.warning(
                "kiracı %s için GitHub App yapılandırması eksik (%s) — FakeGitHubAdapter kullanılıyor.",
                tenant.repo_full_name,
                exc,
            )
            github_port = FakeGitHubAdapter()

        vector_index: VectorIndexPort = build_vector_index(
            self._settings,
            session_factory=(
                self._session_factory if self._settings.ENSEMBLE_MODE == "hosted" else None
            ),
            repo_full_name=tenant.repo_full_name,
        )

        radar_service = RadarService(
            github_port=github_port,
            judge_port=self._judge_port,
            embeddings_port=self._embeddings_port,
            vector_index=vector_index,
            window_days=self._settings.RADAR_WINDOW_DAYS,
            min_jaccard=self._settings.RADAR_MIN_JACCARD,
            min_similarity=self._settings.RADAR_MIN_SIMILARITY,
            backfill_limit=self._settings.GITHUB_BACKFILL_LIMIT,
            default_base=self._settings.GITHUB_DEFAULT_BRANCH,
            judge_concurrency=self._settings.RADAR_JUDGE_CONCURRENCY,
        )

        # `.harness/` yalnız demo reponun git ağacında yaşar (yerel disk) —
        # gerçek kiracılar için dürüst-boş port (bkz. integrations/null_harness.py).
        harness_port: HarnessPort = NullHarnessPort()
        # `hasattr` (isinstance DEĞİL) BİLEREK: `FakeGitHubAdapter`
        # `resolve_scope_subject` taşımaz; gerçek `GitHubAdapter` taşır. Duck-
        # typing burada isinstance'tan daha sağlam — testler bu fabrikayı
        # (bkz. tests/unit/test_tenant_isolation.py) monkeypatch'leyip AYNI
        # arayüzü sağlayan başka bir sınıf verebilir.
        subject_port = github_port if hasattr(github_port, "resolve_scope_subject") else None
        scope_service = ScopeService(
            harness_port=harness_port,
            judge_port=self._scope_judge_port,
            embeddings_port=self._embeddings_port,
            subject_port=subject_port,
        )

        query_source = HarnessEventQuerySource(
            harness_port,
            session_factory=self._session_factory,
            github_owner=owner,
            github_repo=repo,
            repo_full_name=tenant.repo_full_name,
        )
        query_service = QueryService(
            source_port=query_source,
            embeddings_port=self._embeddings_port,
            vector_index=vector_index,
            judge_port=self._query_judge_port,
        )

        board_service = BoardService(self._session_factory, repo_full_name=tenant.repo_full_name)
        graph_service = GraphService(
            self._session_factory, harness_port=harness_port, repo_full_name=tenant.repo_full_name
        )
        event_service = EventService(
            harness_port=harness_port,
            github_port=github_port,
            session_factory=self._session_factory,
            repo_full_name=tenant.repo_full_name,
        )

        return ServiceTeam(
            radar_service=radar_service,
            board_service=board_service,
            scope_service=scope_service,
            query_service=query_service,
            graph_service=graph_service,
            event_service=event_service,
        )
