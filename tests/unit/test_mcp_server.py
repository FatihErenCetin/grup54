"""FastMCP read tool'ları (#32) testleri — kontrat: docs/sprint3-kontratlar.md Ek D.

who_is_touching -> HarnessPort.read_active() projeksiyonu; check_scope ->
ScopeService.check_scope() delegasyonu (mantık YENİDEN YAZILMAZ, o yüzden
#31 henüz implemente değilken NotImplementedError'ın MCP'den de aynen
geçtiğini doğruluyoruz - delegasyonun kanıtı).
"""

from pathlib import Path
from textwrap import dedent

import pytest

from ensemble.engine.scope import ScopeService
from ensemble.models import PresenceEntry, ScopeVerdict
from ensemble_mcp.server import check_scope, check_scope_impl, mcp, who_is_touching, who_is_touching_impl
from ensemble_shared.harness import FileHarnessPort


def write_active(path: Path, frontmatter: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{dedent(frontmatter).strip()}\n---\n", encoding="utf-8")


class _FakeScopeService(ScopeService):
    def __init__(self, verdict: ScopeVerdict):
        self._verdict = verdict

    def check_scope(self, ref: str) -> ScopeVerdict:
        return self._verdict


# --- who_is_touching ---


def test_who_is_touching_bos_harness_bos_liste(tmp_path):
    port = FileHarnessPort(tmp_path)
    assert who_is_touching_impl(None, harness_port=port) == []


def test_who_is_touching_active_beyanlarini_presence_entrye_cevirir(tmp_path):
    write_active(
        tmp_path / ".harness/active/enes.md",
        """
        type: active
        handle: enes
        task_id: T-104
        branch: T-104-graph-endpoint
        module: backend
        paths:
          - src/backend/ensemble/engine/graph.py
        updated_at: "2026-07-20T09:00:00+03:00"
        """,
    )
    port = FileHarnessPort(tmp_path)

    entries = who_is_touching_impl(None, harness_port=port)

    assert len(entries) == 1
    entry = entries[0]
    assert isinstance(entry, PresenceEntry)
    assert entry.actor.handle == "enes"
    assert entry.actor.type == "human"
    assert entry.module == "backend"
    assert entry.task == "T-104"
    assert entry.branch == "T-104-graph-endpoint"


def test_who_is_touching_module_filtresi(tmp_path):
    write_active(
        tmp_path / ".harness/active/enes.md",
        """
        type: active
        handle: enes
        task_id: T-104
        branch: b1
        module: backend
        paths: []
        updated_at: "2026-07-20T09:00:00+03:00"
        """,
    )
    write_active(
        tmp_path / ".harness/active/fatih.md",
        """
        type: active
        handle: fatih
        task_id: T-61
        branch: b2
        module: frontend
        paths: []
        updated_at: "2026-07-20T09:05:00+03:00"
        """,
    )
    port = FileHarnessPort(tmp_path)

    backend_only = who_is_touching_impl("backend", harness_port=port)

    assert [e.actor.handle for e in backend_only] == ["enes"]


def test_who_is_touching_modulsuz_beyan_bos_string_module(tmp_path):
    write_active(
        tmp_path / ".harness/active/esma.md",
        """
        type: active
        handle: esma
        task_id: T-32
        branch: T-32-mcp-read-tools
        paths: []
        updated_at: "2026-07-20T10:00:00+03:00"
        """,
    )
    port = FileHarnessPort(tmp_path)

    entries = who_is_touching_impl(None, harness_port=port)

    assert entries[0].module == ""


# --- check_scope ---


def test_check_scope_delege_eder_fake_service():
    verdict = ScopeVerdict(ref="PR-1", verdict="in_scope", confidence=0.9, evidence="test")
    result = check_scope_impl("PR-1", scope_service=_FakeScopeService(verdict))
    assert result == verdict


def test_check_scope_gercek_scopeservice_henuz_implemente_degil():
    """#31 henuz yazilmadigi icin delegasyon ayni NotImplementedError'i verir
    (mantik burada YENIDEN YAZILMADIGININ kaniti)."""
    with pytest.raises(NotImplementedError):
        check_scope_impl("PR-1")


def test_check_scope_tool_wrapper_de_ayni_sekilde_delege_eder():
    """Tool wrapper (check_scope) de impl ile ayni yoldan gecer - #31 tamamlanana
    kadar ikisi de NotImplementedError verir."""
    with pytest.raises(NotImplementedError):
        check_scope("PR-1")


# --- MCP tool kaydı ---


def test_tools_dogru_kayitli():
    import asyncio

    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"who_is_touching", "check_scope"}


def test_who_is_touching_tool_wrapper_impl_ile_ayni(tmp_path, monkeypatch):
    write_active(
        tmp_path / ".harness/active/enes.md",
        """
        type: active
        handle: enes
        task_id: T-104
        branch: b1
        module: backend
        paths: []
        updated_at: "2026-07-20T09:00:00+03:00"
        """,
    )
    monkeypatch.chdir(tmp_path)
    assert who_is_touching(None) == who_is_touching_impl(None)
