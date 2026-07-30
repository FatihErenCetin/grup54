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

D-55 (İş 3, GOREV 3/4): event audit/presence (`parse_events` -> `NormalizedEvent`)
ile durum geçişi (`transitions_from_webhook` -> `StatusTransition`, İş 1) İKİ
BAĞIMSIZ sinyaldir — biri boş dönse bile diğeri dolu olabilir (örn. bir PR
`synchronize` action'ı her zaman bir `NormalizedEvent` üretir ama hiçbir zaman
bir `StatusTransition` üretmez; tersi de mümkün olsun diye ikisi AYRI AYRI
kontrol edilir, biri diğerini sessizce yutmaz).

#331 (D-60): `issues` event'inde ÜÇÜNCÜ bir iş daha yapılır —
`Projector.upsert_issue_cards`. Kart kümesi artık `.harness/tasks/` ile
sınırlı DEĞİL: hiç görülmemiş bir issue geldiğinde kartı ANINDA açılır
(eskiden yalnız geçişi üretilir, o da "unmatched" diye loglanıp panoya hiç
düşmezdi). Sıra önemli: kart açma, geçiş uygulamasından ÖNCE.
"""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from ensemble.api.deps import SettingsDep
from ensemble.config import Settings
from ensemble.engine.projector import Projector
from ensemble.engine.status_rules import transitions_from_webhook
from ensemble.integrations.github.normalize import (
    issue_to_event,
    pr_to_event,
    webhook_push_to_events,
)
from ensemble.integrations.null_harness import NullHarnessPort
from ensemble.models import NormalizedEvent
from ensemble.store.models import DEFAULT_REPO_FULL_NAME
from ensemble_shared.harness import FileHarnessPort, HarnessPort

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

    # Hosted demo tek-repo sabitlemesi (#63): DEMO_MODE'da yalnız yapılandırılmış
    # repo'nun webhook'u işlenir - imzası geçerli ama başka bir repodan gelen
    # event (App birden fazla repoya kuruluysa) DB'ye tek satır bile yazmadan
    # yok sayılır. 202+"ignored" (hata değil) - mevcut `ping` davranışıyla aynı;
    # 4xx dönmek GitHub'ın webhook'u devre dışı bırakmasına yol açar. Bilerek
    # imza doğrulamasından SONRA (fail-closed sıra bozulmaz).
    pinned_repo = settings.demo_repo_full_name
    if settings.DEMO_MODE and pinned_repo:
        repo_full_name = str((payload.get("repository") or {}).get("full_name") or "")
        if repo_full_name.casefold() != pinned_repo.casefold():
            logger.warning("DEMO_MODE: sabit olmayan repo webhook'u yok sayıldı: %s", repo_full_name)
            return {"status": "ignored", "reason": "repo_not_pinned", "event": x_github_event}

    events = parse_events(x_github_event, payload)
    # D-55 (İş 3): durum geçişi artık event audit'inden BAĞIMSIZ, saf bir
    # türetimden (status_rules.transitions_from_webhook, İş 1) gelir —
    # `events` boş diye burada erken dönülürse ve `transitions` dolu olursa
    # geçiş sessizce kaybolur; bu yüzden ikisi AYRI kontrol edilir.
    transitions = transitions_from_webhook(x_github_event, payload)

    if not events and not transitions:
        logger.info("İşlenmeyen/boş webhook event'i: %s", x_github_event)
        return {"status": "ignored", "event": x_github_event}

    # T-79 (çok-kiracılık): projeksiyon satırları artık repo_full_name'e göre
    # scoped (bkz. store/models.py) — webhook payload'ının KENDİ
    # `repository.full_name`'i kullanılır (payload zaten HMAC ile doğrulandı,
    # ayrıca bir "bilinen kiracı" kontrolüne gerek yok; gerçek GitHub push/
    # pull_request/issues payload'ları HER ZAMAN `repository` taşır). Payload'da
    # (sentetik/eksik test payload'ı gibi) hiç repo bağlamı yoksa demo repoya,
    # o da yapılandırılmamışsa `DEFAULT_REPO_FULL_NAME`'e düşülür — bugüne
    # kadar zaten TEK örtük kiracı vardı, davranış değişmez.
    repo_full_name = (
        str((payload.get("repository") or {}).get("full_name") or "")
        or settings.demo_repo_full_name
        or DEFAULT_REPO_FULL_NAME
    )

    # `.harness/` yalnız demo reponun git ağacında yaşar (yerel disk) — başka
    # bir kiracının presence senkronu için FileHarnessPort kullanmak GRUP54'ÜN
    # KENDİ `.harness/active/`'ını o kiracıya sızdırırdı. NullHarnessPort
    # dürüst-boş presence döner (bkz. integrations/null_harness.py).
    harness_port: HarnessPort = (
        FileHarnessPort() if repo_full_name == settings.demo_repo_full_name else NullHarnessPort()
    )

    session_factory = request.app.state.session_factory
    with session_factory() as session:
        projector = Projector(session, harness_port, repo_full_name=repo_full_name)

        # #331 — "kendiliğinden DOLAN board": yeni bir GitHub issue'su artık
        # `.harness/tasks/` dosyası beklemeden kart üretir. Geçişten ÖNCE
        # çalışmalı; aksi halde `apply_transitions` aynı payload'ın kapanış
        # geçişini "unmatched" sayardı (bugüne kadarki davranış).
        issue_payload = payload.get("issue") if x_github_event == "issues" else None
        card_result = (
            projector.upsert_issue_cards([issue_payload])
            if isinstance(issue_payload, dict)
            else {"created": 0, "existing": 0}
        )

        result = (
            projector.project_events(events)
            if events
            else {"events_processed": 0, "presence_synced": 0}
        )
        transition_result = (
            projector.apply_transitions(transitions)
            if transitions
            else {"applied": 0, "unchanged": 0, "unmatched": 0}
        )
        # `upsert_issue_cards` bilerek commit etmez (bkz. docstring). Yukarıdaki
        # iki metod kendi içinde commit eder ama İKİSİ DE atlanabilir (events ve
        # transitions birlikte boşsa) — o durumda yeni kart oturumda ASILI kalıp
        # sessizce kaybolurdu. Bu commit o deliği kapatır; bekleyen bir şey
        # yoksa no-op.
        session.commit()

    return {
        "status": "accepted",
        "event": x_github_event,
        **result,
        **transition_result,
        "cards_created": card_result["created"],
    }
