from fastapi import APIRouter

from ensemble.api.deps import ScopeServiceDep
from ensemble.models import ScopeVerdict

router = APIRouter(prefix="/scope", tags=["scope"])


@router.get("/check")
def check_scope(ref: str, scope_service: ScopeServiceDep) -> ScopeVerdict:
    return scope_service.check_scope(ref)
