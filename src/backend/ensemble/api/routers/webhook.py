"""GitHub webhook receiver (#62) — hosted modda polling yerine push-tabanlı ingest.

`X-Hub-Signature-256` HMAC-SHA256 doğrulaması ZORUNLU (`GITHUB_WEBHOOK_SECRET`,
D-35). Timing-safe karşılaştırma (`hmac.compare_digest`). Local mod = polling
(bu endpoint local'de de kayıtlıdır ama trafik almaz — smee/GitHub yalnız
hosted URL'e bağlanır, D-35).

Desteklenen event'ler: `push` · `pull_request` · `issues` (docs/github-app-kurulum.md).
`pull_request`/`issues` payload'ları GitHub'da REST kaynağını AYNEN içerir →
mevcut `pr_to_event`/`issue_to_event` (REST şekli) doğrudan yeniden kullanılır.
`push` şekli REST commits API'den farklı → ayrı `webhook_push_to_events`.
Tanınmayan event'ler (örn. `ping`) imza doğrulandıktan sonra sessizce "ignored"
olarak 202 döner — GitHub'ın webhook'u "bozuk" sanmaması için.
"""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from ensemble.api.deps import SettingsDep
from ensemble.config import Settings
from ensemble.engine.projector import Projector
from ensemble.integrations.github.normalize import (
    issue_to_event,
    pr_to_event,
    webhook_push_to_events,
)
from ensemble.models import NormalizedEvent
from ensemble_shared.harness import FileHarnessPort

logger = logging.getLogger("ensemble.webhook")

router = APIRouter(tags=["webhook"])


def verify_signature(settings: Settings, body: bytes, signature_header: str | None) -> None:
    if not settings.GITHUB_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="GITHUB_WEBHOOK_SECRET yapılandırılmamış")
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="X-Hub-Signature-256 eksik/hatalı biçimde")

    expected = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    try:
        # compare_digest ASCII-dışı str'de TypeError atar (Fatih review nit,
        # #62) - HTTP header'lar latin-1 tasiyabilir; gecersiz imza zaten
        # fail-closed 401'e gidiyor, TypeError'i de ayni sonuca cevirmek
        # 500 sizintisini onler (guvenlik degil, tutarlilik).
        signatures_match = hmac.compare_digest(expected, provided)
    except TypeError:
        signatures_match = False
    if not signatures_match:
        raise HTTPException(status_code=401, detail="Geçersiz webhook imzası")


def parse_events(event_type: str | None, payload: dict) -> list[NormalizedEvent]:
    if event_type == "pull_request":
        return [pr_to_event(payload["pull_request"])]
    if event_type == "issues":
        return [issue_to_event(payload["issue"])]
    if event_type == "push":
        return webhook_push_to_events(payload)
    return []


@router.post("/webhooks/github", status_code=202)
async def github_webhook(
    request: Request,
    settings: SettingsDep,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict:
    body = await request.body()
    verify_signature(settings, body, x_hub_signature_256)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz JSON gövdesi") from exc

    events = parse_events(x_github_event, payload)
    if not events:
        logger.info("İşlenmeyen/boş webhook event'i: %s", x_github_event)
        return {"status": "ignored", "event": x_github_event}

    session_factory = request.app.state.session_factory
    with session_factory() as session:
        result = Projector(session, FileHarnessPort()).project_events(events)

    return {"status": "accepted", "event": x_github_event, **result}
