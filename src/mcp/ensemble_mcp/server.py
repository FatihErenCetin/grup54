"""FastMCP server (#32) — READ-ONLY MCP tool'ları.

Kontrat: docs/sprint3-kontratlar.md Ek D. Mantık engine'e delege eder,
yeniden yazılmaz:
  - who_is_touching -> HarnessPort.read_active() projeksiyonu (HTTP /presence,
    Ek B2 ile aynı veri).
  - check_scope     -> ScopeService.check_scope() (engine/scope.py) delegasyonu
    — HTTP /scope/check (Ek B4) ikizi, TEK motor iki yüz.

Kapsam sınırı: declare_work (yazma) S3 write-back/stretch — burada YOK,
yalnız read tool'lar.

Not: `who_is_touching_impl`/`check_scope_impl` port'ları enjekte edilebilir
tutar (testte fixture harness/fake judge) — FastMCP `@mcp.tool()` imzasından
Pydantic şeması türettiği için Protocol tipli (harness_port/scope_service)
parametreler MCP-tool imzasında OLAMAZ; bu yüzden tool wrapper'ları temiz
public imzayla (yalnız module/ref) `_impl` fonksiyonlarına delege eder.
"""

from datetime import datetime

from mcp.server.fastmcp import FastMCP

from ensemble.config import Settings, get_settings
from ensemble.engine.scope import ScopeService
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.models import ActorRef, PresenceEntry, ScopeVerdict
from ensemble.ports import JudgePort
from ensemble_shared.harness import FileHarnessPort, HarnessPort

mcp = FastMCP("ensemble")


def _build_judge_port(settings: Settings) -> JudgePort:
    # app.py::_build_judge_port ile aynı seçim (GEMINI_API_KEY yoksa fake) -
    # HTTP/MCP aynı motoru paylaşır ilkesi burada da geçerli.
    if settings.GEMINI_API_KEY:
        return GeminiJudgeAdapter(settings)
    return FakeJudgeAdapter()


def _presence_entry(decl: dict) -> PresenceEntry:
    # active.schema.json'da human/agent ayrımı yok (yalnız front-matter
    # "type": "active" = belge tipi) - bilinen bir sinyal kaynağı olmadığı
    # için "human" varsayılır; agent-flag S3 write-back'te (declare_work)
    # eklenirse burası güncellenir.
    return PresenceEntry(
        actor=ActorRef(handle=decl.get("handle", ""), type="human"),
        module=decl.get("module") or "",
        task=decl.get("task_id"),
        branch=decl.get("branch"),
        since=datetime.fromisoformat(decl["updated_at"]),
    )


def who_is_touching_impl(
    module: str | None,
    harness_port: HarnessPort | None = None,
) -> list[PresenceEntry]:
    port = harness_port or FileHarnessPort()
    entries = [_presence_entry(decl) for decl in port.read_active()]
    if module is not None:
        entries = [e for e in entries if e.module == module]
    return entries


def check_scope_impl(
    ref: str,
    scope_service: ScopeService | None = None,
) -> ScopeVerdict:
    service = scope_service or ScopeService(
        harness_port=FileHarnessPort(), judge_port=_build_judge_port(get_settings())
    )
    return service.check_scope(ref)


@mcp.tool()
def who_is_touching(module: str | None = None) -> list[PresenceEntry]:
    """`.harness/active/*` beyanlarını döner; `module` verilirse o modüle filtrelenir."""
    return who_is_touching_impl(module)


@mcp.tool()
def check_scope(ref: str) -> ScopeVerdict:
    """Scope-drift verdict'i döner — ScopeService.check_scope()'a delege (#31 mantığı)."""
    return check_scope_impl(ref)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
