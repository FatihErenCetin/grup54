"""Aga dokunmayan, deterministik JudgePort-benzeri GitHubPort fake'i.

Diger moduller (radar/board/frontend) gercek GitHub App/.pem olmadan buna
karsi yazar - docs/sprint2-kontratlar.md'nin "fake adapter" ilkesi.
"""

from datetime import datetime, timezone

from ensemble.models import NormalizedEvent
from ensemble.ports import BackfillResources

_DEFAULT_EVENTS: list[NormalizedEvent] = [
    NormalizedEvent(
        id="commit:aaa1111",
        type="commit",
        actor="esma",
        branch=None,
        files=["src/backend/ensemble/integrations/gemini/judge.py"],
        ts=datetime(2026, 7, 10, 9, 0, 0),
        ref="aaa1111",
    ),
    NormalizedEvent(
        id="pr:99:2026-07-10T10:00:00",
        type="pr",
        actor="fatih",
        branch="T-99-ornek-ozellik",
        files=[],
        ts=datetime(2026, 7, 10, 10, 0, 0),
        ref="99",
    ),
    NormalizedEvent(
        id="issue:50:2026-07-10T08:00:00",
        type="issue",
        actor="enes",
        branch=None,
        files=[],
        ts=datetime(2026, 7, 10, 8, 0, 0),
        ref="50",
    ),
]


class FakeGitHubAdapter:
    """`GitHubPort` kontratinin ag-cagrisi yapmayan, deterministik sahte implementasyonu."""

    def __init__(
        self,
        events: list[NormalizedEvent] | None = None,
        compare_files: dict[tuple[str, str], list[str]] | None = None,
        diffs: dict[tuple[str, str], dict[str, str]] | None = None,
        backfill_resources: BackfillResources | None = None,
    ) -> None:
        self._events = events if events is not None else _DEFAULT_EVENTS
        self._compare_files = compare_files or {}
        self._diffs = diffs or {}
        self._seen_backfill_ids: set[str] = set()
        # Varsayılan BOŞ (uydurma PR/issue yok): fake'in ürettiği
        # `_DEFAULT_EVENTS` durum türetmeye yetecek alanları (state/merged_at/
        # body/head.ref) zaten taşımıyor. Testler gerçek şekilli ham sözlükleri
        # açıkça verir.
        self._backfill_resources = backfill_resources or BackfillResources()
        # --- YAZMA yuzeyi (#339) — kurucu parametresi BILEREK eklenmedi:
        # testler bu sozlukleri kurulumdan SONRA doldurur (fake'in imzasi
        # buyudukce her cagiran etkilenirdi). Ayrintili gerekce ve "bilinmeyen
        # PR ACIK sayilir" secimi `pull_request_open` docstring'inde.
        self.acik_prler: dict[int, bool] = {}
        self.pr_yorumlari: dict[int, list[str]] = {}
        self.yazma_cagrilari: list[tuple[int, str]] = []

    def fetch_events(self, since: datetime) -> list[NormalizedEvent]:
        since_key = _datetime_key(since)
        return [e for e in self._events if _datetime_key(e.ts) >= since_key]

    def fetch_backfill_events(self, limit_per_type: int = 50) -> list[NormalizedEvent]:
        if limit_per_type <= 0:
            return []

        selected: list[NormalizedEvent] = []
        for event_type in ("commit", "pr", "issue"):
            candidates = [event for event in self._events if event.type == event_type]
            candidates = sorted(candidates, key=lambda event: (_datetime_key(event.ts), event.id), reverse=True)
            selected.extend(candidates[:limit_per_type])

        fresh = [event for event in selected if event.id not in self._seen_backfill_ids]
        self._seen_backfill_ids.update(event.id for event in fresh)
        return fresh

    def fetch_backfill_resources(self, limit_per_type: int = 50) -> BackfillResources:
        if limit_per_type <= 0:
            return BackfillResources()
        return BackfillResources(
            prs=self._backfill_resources.prs[:limit_per_type],
            issues=self._backfill_resources.issues[:limit_per_type],
        )

    def compare(self, base: str, head: str) -> list[str]:
        return self._compare_files.get((base, head), [])

    def get_diff(self, base: str, head: str) -> dict[str, str]:
        return self._diffs.get((base, head), {})

    # --- YAZMA yuzeyi (#339) — aga CIKMAYAN, bellekte biriken ikiz ----------

    def pull_request_open(self, number: int) -> bool:
        """Bilinmeyen PR **ACIK** sayilir.

        Neden fail-closed (`False`) degil: bu bir TEST IKIZI; varsayilan
        `False` olsaydi her test yazma yolunu once `acik_prler` doldurarak
        acmak zorunda kalir, unutan test SESSIZCE "yazmadi" diye yesil
        gecerdi — yani guard'i degil, kurulum eksigini olcerdi. Gercek
        fail-closed davranis uretimin kendisindedir: `GitHubAdapter`
        durumu GitHub'dan okur ve `agentic_cli` GERCEK yazmada
        `FakeGitHubAdapter`i zaten REDDEDER (bkz. o dosyadaki kapi).
        """
        return self.acik_prler.get(number, True)

    def list_pull_request_comment_bodies(self, number: int) -> list[str]:
        return list(self.pr_yorumlari.get(number, []))

    def create_pull_request_comment(self, number: int, body: str) -> str:
        self.yazma_cagrilari.append((number, body))
        self.pr_yorumlari.setdefault(number, []).append(body)
        return f"https://github.com/fake/fake/pull/{number}#issuecomment-{len(self.yazma_cagrilari)}"


def _datetime_key(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
