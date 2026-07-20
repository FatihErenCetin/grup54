"""Onboarding sihirbazı (#57) — ilk çalıştırma `.harness/` iskeletini yazar.

Kaynak: internal/grup54_dizin_yapisi.md §3 (.harness/ şeması) +
internal/grup54_vizyon_ve_karar_kaydi.md §8.2/8.3 — küçültülmüş (S3
`docs/kapsam-sinirlari.md`: onboarding = KABUK, "ince yeter").

Tek seferlik; `.harness/` zaten varsa DOKUNMAZ (fail-safe — takımın gerçek
verisini asla ezmez).

İki mod:
  - **Brownfield** (açık GitHub issue'ları var — bu repo gibi): `tasks/`
    issue'lardan DETERMİNİSTİK üretilir (AI DEĞİL — `bagimlilik_uret.py` ile
    aynı dürüstlük: "süs AI" değil, gh->md mekanik dönüşüm). `scope/` ise
    gerçek bir AI adımı (`scope_draft.py`) — hedef/kapsam-dışı hiçbir
    issue'dan birebir kopyalanamaz, sentezlenir; `status: draft` ile yazılır,
    PO gözden geçirip commit etmesi onay/"dondurma" sayılır.
  - **Greenfield** (açık issue yok): yalnız şablon dosyalar — GitHub/Gemini'ye
    hiç bağlanmaz (boş bağlamdan AI'ya taslak yazdırmak "uydurma" riski taşır).

`active/`, `locks/`, `decisions/` her modda boş başlar (.gitkeep) +
`.harness/README.md` şema haritası.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ensemble.config import Settings, get_settings
from ensemble.onboarding.scope_draft import ScopeDrafter, build_scope_drafter
from ensemble_shared.harness import FileHarnessPort, HarnessPort

_SPRINT_DIGIT_RE = re.compile(r"(\d+)")

_HARNESS_README = """\
# .harness/ — Ensemble'ın ortak beyni

Bu klasör **kanoniktir** (git ile senkron, audit bedava) — DB yalnız
projeksiyondur; çelişkide `.harness/` kazanır.

| Klasör | Ne tutar | Kim yazar |
|---|---|---|
| `scope/sprint-N.md` | Kararlaştırılan kapsam (hedef, kapsam-dışı) | PO yazar/dondurur |
| `tasks/T-<id>-*.md` | Her story/task = 1 dosya — board'ın tek kaynağı | Onboarding taslaklar, ekip onaylar |
| `active/<handle>.md` | "Şu an neye dokunuyorum" (yazar başına 1 dosya) | Herkes kendi dosyasını günceller |
| `locks/modules.md` | Yumuşak (advisory) modül kilidi | Uzun süren iş için elle eklenir |
| `decisions/D-NN-*.md` | Operasyonel karar günlüğü (append-only) | SM/PO/dev önemli kararda ekler |

Döngü (düzenlemeden önce): **oku** `active/*` (çakışma riski?) → **beyan et**
kendi `active/<handle>.md`'ni → **kontrol et** `scope/sprint-N.md` (kapsam
içi mi?). Detay: kök `AGENTS.md`.

Bu dosya `scripts` ile değil, onboarding sihirbazıyla (#57) üretildi —
`src/backend/ensemble/onboarding/wizard.py`.
"""


@dataclass
class OnboardingResult:
    mode: str  # "greenfield" | "brownfield" | "skipped"
    created: list[str] = field(default_factory=list)
    reason: str | None = None


def fetch_open_issues(limit: int = 200) -> list[dict]:
    """`gh` ile açık issue'ları çeker (board'ın tam kaydı, milestone'a göre süzülmez)."""
    result = subprocess.run(
        [
            "gh", "issue", "list", "--state", "open", "--limit", str(limit),
            "--json", "number,title,assignees",
        ],
        capture_output=True, text=True, check=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def _sprint_slug(milestone: str) -> str:
    match = _SPRINT_DIGIT_RE.search(milestone)
    return match.group(1) if match else re.sub(r"[^a-z0-9]+", "-", milestone.lower()).strip("-")


def _gather_context(root: Path, issues: list[dict]) -> str:
    parts: list[str] = []
    readme = root / "README.md"
    if readme.exists():
        parts.append(readme.read_text(encoding="utf-8")[:3000])
    roadmap = root / "ROADMAP.md"
    if roadmap.exists():
        parts.append(roadmap.read_text(encoding="utf-8")[:1500])
    if issues:
        titles = "\n".join(f"- #{issue['number']}: {issue['title']}" for issue in issues[:30])
        parts.append(f"Açık issue başlıkları:\n{titles}")
    return "\n\n---\n\n".join(parts)


def _write_tasks(port: HarnessPort, issues: list[dict]) -> list[str]:
    created = []
    for issue in issues:
        task_id = f"T-{issue['number']}"
        assignees = issue.get("assignees") or []
        assignee = assignees[0]["login"] if assignees else None
        port.write_task(
            task_id,
            {
                "title": issue["title"],
                "status": "backlog",
                "assignee": assignee,
                "paths": [],
            },
        )
        created.append(f"tasks/{task_id}-*.md")
    return created


def _write_brownfield_scope(
    port: HarnessPort, settings: Settings, milestone: str, context: str,
    scope_drafter: ScopeDrafter | None,
) -> str:
    drafter = scope_drafter or build_scope_drafter(settings)
    draft = drafter.draft(milestone=milestone, context=context)
    sprint = _sprint_slug(milestone)
    port.write_scope(
        sprint,
        {
            "title": milestone,
            "status": "draft",
            "goals": draft.in_scope,
            "non_goals": draft.non_goals,
            "body": f"[TASLAK — insan onayı bekliyor, PO düzenleyip dondurur]\n\n{draft.goal}\n",
        },
    )
    return f"scope/sprint-{sprint}.md"


def _write_greenfield_templates(port: HarnessPort, milestone: str) -> list[str]:
    sprint = _sprint_slug(milestone)
    port.write_scope(
        sprint,
        {
            "title": milestone,
            "status": "draft",
            "goals": ["[TASLAK] Bu sprintin hedeflerini buraya yaz"],
            "non_goals": ["[TASLAK] Kapsam dışını buraya yaz"],
            "body": (
                "[TASLAK — açık GitHub issue'sı yok, sihirbaz AI çağırmadı; "
                "PO doldurup dondurur.]\n"
            ),
        },
    )
    port.write_task(
        "T-1",
        {
            "title": "[ÖRNEK] ilk görevini buraya yaz",
            "status": "backlog",
            "assignee": None,
            "paths": [],
            "body": "[ÖRNEK — bu dosyayı silip kendi görevlerini ekle.]\n",
        },
    )
    return [f"scope/sprint-{sprint}.md", "tasks/T-1-*.md"]


def _write_empty_categories(root: Path) -> list[str]:
    created = []
    for name in ("active", "locks", "decisions"):
        directory = root / ".harness" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".gitkeep").touch(exist_ok=True)
        created.append(f"{name}/.gitkeep")
    return created


def init_harness(
    root: Path | str,
    *,
    milestone: str,
    settings: Settings | None = None,
    issues: list[dict] | None = None,
    harness_port: HarnessPort | None = None,
    scope_drafter: ScopeDrafter | None = None,
) -> OnboardingResult:
    root = Path(root)
    if (root / ".harness").exists():
        return OnboardingResult(
            mode="skipped", reason=".harness/ zaten var — dokunulmadı (fail-safe)"
        )

    settings = settings or get_settings()
    port = harness_port or FileHarnessPort(root)
    if issues is None:
        issues = fetch_open_issues()

    created: list[str] = []
    if issues:
        created += _write_tasks(port, issues)
        context = _gather_context(root, issues)
        created.append(_write_brownfield_scope(port, settings, milestone, context, scope_drafter))
        mode = "brownfield"
    else:
        created += _write_greenfield_templates(port, milestone)
        mode = "greenfield"

    created += _write_empty_categories(root)
    (root / ".harness" / "README.md").write_text(_HARNESS_README, encoding="utf-8")
    created.append(".harness/README.md")

    return OnboardingResult(mode=mode, created=created)


def main() -> None:
    parser = argparse.ArgumentParser(description="Onboarding sihirbazı (#57) — ilk .harness/ iskeleti")
    parser.add_argument("--milestone", required=True, help="Sprint/milestone adı (ör. 'Sprint 3')")
    parser.add_argument("--root", default=".", help="Repo kökü (varsayılan: cwd)")
    parser.add_argument("--issues-json", help="offline: gh yerine bu JSON dosyasından oku")
    args = parser.parse_args()

    issues = None
    if args.issues_json:
        issues = json.loads(Path(args.issues_json).read_text(encoding="utf-8"))

    result = init_harness(args.root, milestone=args.milestone, issues=issues)
    if result.mode == "skipped":
        print(f"Atlandı: {result.reason}")
        return
    print(f"Mod: {result.mode}")
    for item in result.created:
        print(f"  yazildi: {item}")


if __name__ == "__main__":
    main()
