"""`TenantRegistry.update_shared_ports` (T-307 FAZ 2 KURAL 5) testleri.

Kapsam: `api/routers/settings.py::update_provider_settings`'in çağırdığı
`ensemble.app.rebuild_llm_services` demo-DIŞI (T-79) kiracılar için BU
metodu kullanır — burada doğrudan, `ServiceTeam`'in ağır bağımlılıklarından
(gerçek GitHub App/DB verisi) bağımsız test edilir.
"""

from __future__ import annotations

from ensemble.config import Settings
from ensemble.engine.embeddings import HashEmbeddings
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.query_judge import FakeQueryJudgeAdapter
from ensemble.integrations.gemini.scope_judge import FakeScopeJudgeAdapter
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.tenancy import ServiceTeam, Tenant, TenantRegistry


def _dummy_demo_team() -> ServiceTeam:
    # Demo takımı bu testte HİÇ dokunulmuyor (`get_team(is_demo=True)` bunu
    # olduğu gibi döner) — yalnızca `TenantRegistry.__init__`'in gerektirdiği
    # bir yer tutucu; gerçek servis sınıfları OLMASINA gerek yok (Python
    # dataclass alanları çalışma zamanında tip DOĞRULAMAZ).
    return ServiceTeam(
        radar_service=object(),
        board_service=object(),
        scope_service=object(),
        query_service=object(),
        graph_service=object(),
        event_service=object(),
    )


def _registry(tmp_path) -> TenantRegistry:
    settings = Settings(
        _env_file=None, ENSEMBLE_MODE="local", DATABASE_URL=f"sqlite:///{tmp_path / 'e.db'}"
    )
    session_factory = get_session_factory(get_engine(settings))
    return TenantRegistry(
        settings,
        demo_team=_dummy_demo_team(),
        session_factory=session_factory,
        judge_port=FakeJudgeAdapter(),
        embeddings_port=HashEmbeddings(),
        query_judge_port=FakeQueryJudgeAdapter(),
        scope_judge_port=FakeScopeJudgeAdapter(),
    )


def test_update_shared_ports_yeni_kiracilarda_YENI_portlari_kullanir(tmp_path):
    registry = _registry(tmp_path)
    tenant = Tenant(repo_full_name="acme/once", installation_id=None, is_demo=False)

    yeni_judge = FakeJudgeAdapter()
    registry.update_shared_ports(
        judge_port=yeni_judge,
        embeddings_port=HashEmbeddings(),
        query_judge_port=FakeQueryJudgeAdapter(),
        scope_judge_port=FakeScopeJudgeAdapter(),
    )

    team = registry.get_team(tenant)
    assert team.radar_service.judge_port is yeni_judge


def test_update_shared_ports_ONCEDEN_cachelenmis_kiraciyi_TAHLIYE_eder(tmp_path):
    """MUTASYON KİLİDİ: `update_shared_ports`'taki `self._teams.clear()`
    satırını kaldır → bu test KIRMIZI olur (daha önce inşa edilmiş takım
    LRU'da kalır ve `get_team` aynı — ESKİ port'larla kurulmuş — nesneyi
    döner; kaydedilen yeni anahtar bu kiracı için hiç devreye girmez)."""
    registry = _registry(tmp_path)
    tenant = Tenant(repo_full_name="acme/once", installation_id=None, is_demo=False)

    eski_takim = registry.get_team(tenant)
    eski_judge = eski_takim.radar_service.judge_port

    yeni_judge = FakeJudgeAdapter()
    registry.update_shared_ports(
        judge_port=yeni_judge,
        embeddings_port=HashEmbeddings(),
        query_judge_port=FakeQueryJudgeAdapter(),
        scope_judge_port=FakeScopeJudgeAdapter(),
    )

    yeni_takim = registry.get_team(tenant)
    assert yeni_takim is not eski_takim
    assert yeni_takim.radar_service.judge_port is yeni_judge
    assert yeni_takim.radar_service.judge_port is not eski_judge


def test_update_shared_ports_demo_takimina_DOKUNMAZ(tmp_path):
    registry = _registry(tmp_path)
    demo_tenant = Tenant(repo_full_name="demo/demo", installation_id=None, is_demo=True)
    demo_team_before = registry.get_team(demo_tenant)

    registry.update_shared_ports(
        judge_port=FakeJudgeAdapter(),
        embeddings_port=HashEmbeddings(),
        query_judge_port=FakeQueryJudgeAdapter(),
        scope_judge_port=FakeScopeJudgeAdapter(),
    )

    assert registry.get_team(demo_tenant) is demo_team_before
