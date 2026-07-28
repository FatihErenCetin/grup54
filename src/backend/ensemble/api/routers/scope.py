from fastapi import APIRouter

from ensemble.api.deps import TenantScopeServiceDep
from ensemble.api.errors import ErrorEnvelope
from ensemble.api.schemas import ScopeVerdictCounts, ScopeVerdictsResponse
from ensemble.models import ScopeCurrent, ScopeVerdict

router = APIRouter(prefix="/scope", tags=["scope"])


@router.get(
    "/check",
    responses={
        404: {"model": ErrorEnvelope, "description": "Scope referansı bulunamadı"},
    },
)
def check_scope(ref: str, scope_service: TenantScopeServiceDep) -> ScopeVerdict:
    return scope_service.check_scope(ref)


@router.get("/current")
def current_scope(scope_service: TenantScopeServiceDep) -> ScopeCurrent:
    return scope_service.get_current_scope()


@router.get("/verdicts")
def scope_verdicts(scope_service: TenantScopeServiceDep) -> ScopeVerdictsResponse:
    verdicts = scope_service.list_verdicts()
    return ScopeVerdictsResponse(
        verdicts=verdicts,
        counts=ScopeVerdictCounts.model_validate(scope_service.verdict_counts()),
        judged_at=verdicts[0].judged_at if verdicts else None,
    )
