from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from ensemble.api.auth_session import SESSION_COOKIE_NAME, SessionSignatureError, verify_session
from ensemble.config import Settings
from ensemble.engine import BoardService, EventService, GraphService, RadarService, ScopeService
from ensemble.engine.query import QueryService
from ensemble.store.installation_store import list_watched_repos
from ensemble.store.models import DEFAULT_REPO_FULL_NAME
from ensemble.store.user_store import get_user_by_id
from ensemble.tenancy import ServiceTeam, Tenant, TenantRegistry


from ensemble.ports import VectorIndexPort


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """`/auth/register` + `/auth/login` (T-294) `users` tablosuna yazmak için
    kullanır. `lifespan` (app.py) bunu HER zaman kurar (DEMO_MODE/ENSEMBLE_MODE
    fark etmez) — `get_board_service`'in aksine burada savunmacı bir kurulum-
    zamanı fallback'i YOK, çünkü bu dependency yalnızca gerçek uygulama
    yaşam-döngüsü (TestClient dahil, `with` bloğu) üzerinden çağrılır."""
    return request.app.state.session_factory


def get_radar_service(request: Request) -> RadarService:
    return request.app.state.radar_service


def get_scope_service(request: Request) -> ScopeService:
    return request.app.state.scope_service


def get_query_service(request: Request) -> QueryService:
    return request.app.state.query_service


def get_vector_index(request: Request) -> VectorIndexPort:
    return request.app.state.vector_index


def get_board_service(request: Request) -> BoardService:
    if hasattr(request.app.state, "board_service"):
        return request.app.state.board_service
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        from ensemble.store.engine import get_engine, get_session_factory
        session_factory = get_session_factory(get_engine(request.app.state.settings))
    return BoardService(session_factory=session_factory)


def get_session_factory_or_build(request: Request) -> "sessionmaker[Session]":
    """`get_session_factory`in HOŞGÖRÜLÜ ikizi (#340).

    `get_session_factory` `app.state.session_factory`i ZORUNLU kılar; o da
    yalnız `lifespan` koştuğunda kurulur. Onboarding `/uygula` ucu ise
    `TestClient(app)` gibi lifespan'siz kurulumlarda ve masaüstü paketinde de
    çalışmalı — orada sert bir `AttributeError` kullanıcıya hiçbir şey
    anlatmaz.

    Geri düşüş `get_board_service`in ZATEN kullandığı desenin aynısı; burada
    yalnız ADLANDIRILDI ki iki yerde kopyalanmasın.
    """
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        from ensemble.store.engine import get_engine, get_session_factory as _kur

        session_factory = _kur(get_engine(request.app.state.settings))
    return session_factory


def get_graph_service(request: Request) -> GraphService:
    # #104 review bulgusu (Semih, blocker): eskiden Board/Scope ile ayni gecici
    # stub'du (session_factory=lambda: None) - override'siz istekte TypeError
    # veriyordu. Gercek DI app.py::lifespan'de kuruluyor (radar_service deseni).
    return request.app.state.graph_service


def get_event_service(request: Request) -> EventService:
    return request.app.state.event_service


# Annotated dependencies
SettingsDep = Annotated[Settings, Depends(get_settings)]
RadarServiceDep = Annotated[RadarService, Depends(get_radar_service)]
ScopeServiceDep = Annotated[ScopeService, Depends(get_scope_service)]
QueryServiceDep = Annotated[QueryService, Depends(get_query_service)]
VectorIndexDep = Annotated[VectorIndexPort, Depends(get_vector_index)]
BoardServiceDep = Annotated[BoardService, Depends(get_board_service)]
GraphServiceDep = Annotated[GraphService, Depends(get_graph_service)]
EventServiceDep = Annotated[EventService, Depends(get_event_service)]
SessionFactoryDep = Annotated[sessionmaker[Session], Depends(get_session_factory)]
SessionFactoryOrBuildDep = Annotated[
    sessionmaker[Session], Depends(get_session_factory_or_build)
]


# --- Çok-kiracılı repo seçimi (#79 kalan dilim, T-79) ---------------------
#
# `TenantDep`: kiracı SUNUCU tarafında çözülür — istemcinin gönderdiği
# `?repo=`e ASLA körlemesine güvenilmez, HER ZAMAN çağıranın (oturumdaki
# kullanıcının) izinli setine (`watched_repos`) karşı doğrulanır; izinsizse
# 403 (bkz. `_izinli_repo_mu`). Oturum yoksa (anonim) → demo repo — bugünkü
# public demo davranışı BİREBİR korunur (D-23).


def _demo_repo_full_name(settings: Settings) -> str:
    return settings.demo_repo_full_name or DEFAULT_REPO_FULL_NAME


def _session_user_id(request: Request, settings: Settings) -> str | None:
    """Oturum çerezinden `sub` (users.id) — yalnız email VEYA GitHub OAuth
    (T-79 sonrası her ikisi de get-or-create ile `users` satırı açar)
    oturumlarında dolu olur. Çerez yok/bozuk/imza tutmuyor → `None` (401
    DEĞİL — anonim istekler demo repoyu görmeye devam eder, giriş duvarı
    YOK)."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie or not settings.AUTH_SESSION_SECRET:
        return None
    try:
        payload = verify_session(settings.AUTH_SESSION_SECRET, cookie)
    except SessionSignatureError:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


def get_tenant(
    request: Request,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
) -> Tenant:
    """Bu isteğin kiracısını çözer — radar/board/scope/query/graph/events
    router'larının HEPSİNİN kullandığı TEK kapı.

    Sıra:
      1) Oturum yoksa → demo repo (`?repo=` demo'dan BAŞKA bir şey istiyorsa 403).
      2) Oturum var → `watched_repos` izinli set. `?repo=` verilmişse bu
         sette (veya demo) OLMALI, yoksa 403. Verilmemişse kullanıcının
         `active_repo_full_name`'i kullanılır; o da sette değilse (silinmiş/
         tutarsız) fail-closed demo'ya düşülür — uydurma veri YOK.
    """
    demo_repo = _demo_repo_full_name(settings)
    demo_tenant = Tenant(repo_full_name=demo_repo, installation_id=None, is_demo=True)
    requested_repo = request.query_params.get("repo")

    user_id = _session_user_id(request, settings)
    if user_id is None:
        if requested_repo and requested_repo != demo_repo:
            raise HTTPException(status_code=403, detail="Bu repoya erişim izniniz yok.")
        return demo_tenant

    with session_factory() as session:
        user = get_user_by_id(session, user_id)
        watched = (
            {row.repo_full_name: row.installation_id for row in list_watched_repos(session, user_id)}
            if user is not None
            else {}
        )

    if requested_repo is not None:
        if requested_repo == demo_repo:
            return demo_tenant
        installation_id = watched.get(requested_repo)
        if installation_id is None:
            raise HTTPException(status_code=403, detail="Bu repoya erişim izniniz yok.")
        return Tenant(repo_full_name=requested_repo, installation_id=installation_id, is_demo=False)

    active = user.active_repo_full_name if user is not None else None
    if active and active == demo_repo:
        return demo_tenant
    if active and active in watched:
        return Tenant(repo_full_name=active, installation_id=watched[active], is_demo=False)
    return demo_tenant


def get_tenant_registry(request: Request) -> TenantRegistry:
    return request.app.state.tenant_registry


TenantDep = Annotated[Tenant, Depends(get_tenant)]
TenantRegistryDep = Annotated[TenantRegistry, Depends(get_tenant_registry)]


def get_service_team(tenant: TenantDep, registry: TenantRegistryDep) -> ServiceTeam:
    return registry.get_team(tenant)


ServiceTeamDep = Annotated[ServiceTeam, Depends(get_service_team)]


# Takımdan tek servis türeten küçük dependency'ler — router fonksiyonlarının
# PARAMETRE ADI/İMZASI DEĞİŞMEDEN (mevcut router-doğrudan-çağıran testler
# kırılmasın) yalnız DI KAYNAĞI demo singleton'dan kiracıya-göre-çözülen
# takıma kayar.
def get_tenant_radar_service(team: ServiceTeamDep) -> RadarService:
    return team.radar_service


def get_tenant_board_service(team: ServiceTeamDep) -> BoardService:
    return team.board_service


def get_tenant_scope_service(team: ServiceTeamDep) -> ScopeService:
    return team.scope_service


def get_tenant_query_service(team: ServiceTeamDep) -> QueryService:
    return team.query_service


def get_tenant_graph_service(team: ServiceTeamDep) -> GraphService:
    return team.graph_service


def get_tenant_event_service(team: ServiceTeamDep) -> EventService:
    return team.event_service


TenantRadarServiceDep = Annotated[RadarService, Depends(get_tenant_radar_service)]
TenantBoardServiceDep = Annotated[BoardService, Depends(get_tenant_board_service)]
TenantScopeServiceDep = Annotated[ScopeService, Depends(get_tenant_scope_service)]
TenantQueryServiceDep = Annotated[QueryService, Depends(get_tenant_query_service)]
TenantGraphServiceDep = Annotated[GraphService, Depends(get_tenant_graph_service)]
TenantEventServiceDep = Annotated[EventService, Depends(get_tenant_event_service)]
