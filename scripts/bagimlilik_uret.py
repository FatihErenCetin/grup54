"""Bağımlılık haritası üretici (#124) — deterministik, AI'sız.

GitHub issue verisinden (`gh`) bağımlılık grafını çıkarır ve
`docs/<milestone-slug>-bagimlilik.md` içindeki BOT-BLOK'unu (Mermaid graf +
dalga tablosu + kişi kuyrukları + sahipsiz/döngü uyarıları + düz liste)
yeniden üretir. İnsan yorumları (dalga notları vb.) blok DIŞINDA korunur.

Kaynak/format: docs/bagimlilik-harita-rehberi.md + docs/sprint2-bagimlilik.md.
Kanonik durum GitHub'dadır (issue/atama/milestone); bu belge sıralama rehberidir.

Bağımlılık kaynağı — gövdedeki makine-okur satırlar:
  "Ön-koşul: #16, #41"     → SERT kenar (A --> B: B, A bitmeden canlıya çıkamaz)
  "Yumuşak ön-koşul: #17"  → YUMUŞAK kenar (A -.-> B: mock ile beklemeden başlar)

Kapsam notu: subgraph ekseni (tema) `tema:<ad>` etiketinden türetilir. Board'ın
Projects-v2 "Tema" alanı daha zengin kaynaktır (GraphQL) — belgelenmiş uzatma
noktası; bu sürüm etiket + gövde ile deterministik ve test-edilebilir çalışır.

Kullanım:
    python scripts/bagimlilik_uret.py --milestone "Sprint 2"
    python scripts/bagimlilik_uret.py --milestone "Sprint 2" --issues-json fixture.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# assignee login -> harita rengi/handle (proje-özgü; rehber: "adlar uyarlanır")
LOGIN_TO_HANDLE = {
    "asmarufoglu": "semih",
    "esma6": "esma",
    "EnesErdemT": "enes",
    "FatihErenCetin": "fatih",
}
HANDLE_STYLE = {
    "semih": "fill:#5b8def,color:#fff,stroke:#2f5bb7",
    "esma": "fill:#9d5bde,color:#fff,stroke:#6b2fb7",
    "enes": "fill:#2e9e6b,color:#fff,stroke:#1d6b47",
    "fatih": "fill:#de8f3c,color:#fff,stroke:#a8641d",
    "done": "fill:#3a3f45,color:#9aa3ad,stroke:#565e66",
    "orphan": "fill:#2a1f1f,color:#e0a0a0,stroke:#a05252,stroke-dasharray:4 3",
}

_BLOK_BASI = "<!-- BOT-BLOK:baslangic -->"
_BLOK_SONU = "<!-- BOT-BLOK:bitis -->"

# Ön-koşul YAPILANDIRILMIŞ alan satırından okunur (rehber kaynak-1): satır
# başında (opsiyonel ** / boşluk) 'Ön-koşul:' ya da 'Yumuşak ön-koşul:', ardından
# ':'. Anchor + zorunlu iki nokta → prose/olumsuzlama ("bu bir ön-koşul değildir
# ama #42") EŞLEŞMEZ, sahte kenar üretilmez. #N yalnız ':' SONRASINDAN toplanır.
_FIELD_RE = re.compile(
    r"^\s*\**\s*(?P<soft>yumu[şs]ak\s+)?[öo]n-ko[şs]ul\b[^:\n]*:(?P<rest>.*)$",
    re.IGNORECASE,
)
_ISSUE_REF_RE = re.compile(r"#(\d+)")


# ---------------------------------------------------------------------------
# Veri yapıları
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Node:
    number: int
    title: str
    state: str            # "open" | "closed"
    owner: str | None     # handle (semih/esma/...) veya None
    labels: tuple[str, ...]
    theme: str            # subgraph ekseni

    @property
    def done(self) -> bool:
        return self.state.lower() == "closed"


@dataclass(frozen=True)
class Edge:
    src: int              # ön-koşul (önce biten)
    dst: int              # bağımlı (sonra)
    soft: bool


@dataclass
class Graph:
    nodes: dict[int, Node]
    edges: list[Edge]
    cycles: list[list[int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ayrıştırma + graf inşası
# ---------------------------------------------------------------------------

def parse_prereqs(body: str) -> tuple[list[int], list[int]]:
    """Gövdedeki yapılandırılmış alan satırlarından (sert, yumuşak) çıkarır.

    Yalnız satır başındaki 'Ön-koşul:' / 'Yumuşak ön-koşul:' alanları sayılır;
    #N referansları YALNIZ ':' sonrasından toplanır → narrative/olumsuzlama
    ("... ön-koşul değildir ama #42") sahte bağımlılık ÜRETMEZ.
    """
    hard: list[int] = []
    soft: list[int] = []
    for line in (body or "").splitlines():
        match = _FIELD_RE.match(line)
        if not match:
            continue
        refs = [int(n) for n in _ISSUE_REF_RE.findall(match.group("rest"))]
        if match.group("soft"):
            soft.extend(refs)
        else:
            hard.extend(refs)
    return (sorted(set(hard)), sorted(set(soft)))


def _theme_of(labels: list[str]) -> str:
    """Subgraph eksenini `tema:<ad>` etiketinden türetir; yoksa 'Diğer'."""
    for label in sorted(labels):
        if label.lower().startswith("tema:"):
            return label.split(":", 1)[1].strip() or "Diğer"
    return "Diğer"


def build_nodes(issues: list[dict]) -> dict[int, Node]:
    nodes: dict[int, Node] = {}
    for issue in issues:
        labels = [lbl["name"] for lbl in issue.get("labels", [])]
        assignees = [a["login"] for a in issue.get("assignees", [])]
        owner = None
        if assignees:
            login = sorted(assignees)[0]
            owner = LOGIN_TO_HANDLE.get(login, login)
        nodes[issue["number"]] = Node(
            number=issue["number"],
            title=issue["title"],
            state=str(issue.get("state", "open")).lower(),
            owner=owner,
            labels=tuple(sorted(labels)),
            theme=_theme_of(labels),
        )
    return nodes


def build_edges(issues: list[dict], known: set[int]) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[tuple[int, int, bool]] = set()
    for issue in issues:
        dst = issue["number"]
        hard, soft = parse_prereqs(issue.get("body", ""))
        for src in hard:
            key = (src, dst, False)
            if src in known and src != dst and key not in seen:
                edges.append(Edge(src=src, dst=dst, soft=False))
                seen.add(key)
        for src in soft:
            key = (src, dst, True)
            if src in known and src != dst and key not in seen:
                edges.append(Edge(src=src, dst=dst, soft=True))
                seen.add(key)
    return sorted(edges, key=lambda e: (e.dst, e.src, e.soft))


def detect_cycles(nodes: dict[int, Node], edges: list[Edge]) -> list[list[int]]:
    """Sert kenarlar üzerinde döngü arar (yumuşak = mock, bloklamaz)."""
    adj: dict[int, list[int]] = {n: [] for n in nodes}
    for edge in edges:
        if not edge.soft:
            adj[edge.src].append(edge.dst)

    white, gray, black = 0, 1, 2
    color = dict.fromkeys(nodes, white)
    cycles: list[list[int]] = []

    def visit(start: int) -> None:
        stack: list[tuple[int, int]] = [(start, 0)]
        path: list[int] = []
        color[start] = gray
        path.append(start)
        while stack:
            node, idx = stack[-1]
            neighbors = sorted(adj[node])
            if idx < len(neighbors):
                stack[-1] = (node, idx + 1)
                nxt = neighbors[idx]
                if color[nxt] == gray:
                    cut = path.index(nxt)
                    cycles.append(path[cut:] + [nxt])
                elif color[nxt] == white:
                    color[nxt] = gray
                    path.append(nxt)
                    stack.append((nxt, 0))
            else:
                color[node] = black
                path.pop()
                stack.pop()

    for node in sorted(nodes):
        if color[node] == white:
            visit(node)
    return cycles


def build_graph(issues: list[dict]) -> Graph:
    nodes = build_nodes(issues)
    edges = build_edges(issues, set(nodes))
    return Graph(nodes=nodes, edges=edges, cycles=detect_cycles(nodes, edges))


def topological_waves(nodes: dict[int, Node], edges: list[Edge]) -> list[list[int]]:
    """Açık düğümleri sert-kenar topolojik seviyelere böler.

    Kapalı ön-koşul = tamamlanmış (bloklamaz). Döngüdeki düğümler yerleşemez
    ve dışarıda kalır (döngü ayrıca detect_cycles ile raporlanır).
    """
    open_nodes = {n for n, node in nodes.items() if not node.done}
    deps: dict[int, set[int]] = {n: set() for n in open_nodes}
    for edge in edges:
        if not edge.soft and edge.dst in open_nodes and edge.src in open_nodes:
            deps[edge.dst].add(edge.src)

    waves: list[list[int]] = []
    placed: set[int] = set()
    remaining = set(open_nodes)
    while remaining:
        ready = sorted(n for n in remaining if deps[n] <= placed)
        if not ready:
            break
        waves.append(ready)
        placed.update(ready)
        remaining.difference_update(ready)
    return waves


def find_orphans(nodes: dict[int, Node]) -> list[int]:
    """Açık ama sahipsiz VEYA label'sız issue'lar (rehber QC kriteri)."""
    return sorted(
        n for n, node in nodes.items()
        if not node.done and (node.owner is None or not node.labels)
    )


# ---------------------------------------------------------------------------
# Render (BOT-BLOK içeriği)
# ---------------------------------------------------------------------------

def _ident(theme: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", theme) or "grup"


def _node_label(node: Node) -> str:
    title = node.title.replace('"', "'")
    if len(title) > 34:
        title = title[:33].rstrip() + "…"
    mark = " ✓" if node.done else ""
    return f"#{node.number} {title}{mark}"


def _mermaid(graph: Graph) -> str:
    lines = ["```mermaid", "graph LR"]
    present = sorted(
        {n.owner for n in graph.nodes.values() if n.owner in HANDLE_STYLE}
    )
    for handle in present:
        lines.append(f"  classDef {handle} {HANDLE_STYLE[handle]}")
    lines.append(f"  classDef done {HANDLE_STYLE['done']}")
    lines.append(f"  classDef orphan {HANDLE_STYLE['orphan']}")

    themes: dict[str, list[int]] = {}
    for node in graph.nodes.values():
        themes.setdefault(node.theme, []).append(node.number)
    for theme in sorted(themes):
        lines.append(f'  subgraph T_{_ident(theme)}["{theme}"]')
        for num in sorted(themes[theme]):
            node = graph.nodes[num]
            if node.done:
                cls = "done"
            elif node.owner in HANDLE_STYLE:
                cls = node.owner
            else:
                cls = "orphan"
            lines.append(f'    I{num}["{_node_label(node)}"]:::{cls}')
        lines.append("  end")

    for edge in graph.edges:
        arrow = "-.->" if edge.soft else "-->"
        lines.append(f"  I{edge.src} {arrow} I{edge.dst}")
    lines.append("```")
    return "\n".join(lines)


def _wave_table(graph: Graph) -> str:
    waves = topological_waves(graph.nodes, graph.edges)
    rows = ["| Dalga | Issue'lar (sahip) |", "|---|---|"]
    for i, wave in enumerate(waves):
        items = " · ".join(
            f"#{n} ({graph.nodes[n].owner or 'sahipsiz'})" for n in wave
        )
        rows.append(f"| D{i} | {items} |")
    if len(rows) == 2:
        rows.append("| — | (açık iş yok) |")
    return "\n".join(rows)


def _queues(graph: Graph) -> str:
    waves = topological_waves(graph.nodes, graph.edges)
    order = {n: i for i, wave in enumerate(waves) for n in wave}
    by_owner: dict[str, list[int]] = {}
    for num, node in graph.nodes.items():
        if node.done:
            continue
        by_owner.setdefault(node.owner or "sahipsiz", []).append(num)
    rows = ["| Kişi | Sıra (dalga içi # artan) |", "|---|---|"]
    for owner in sorted(by_owner):
        seq = " → ".join(
            f"#{n}"
            for n in sorted(by_owner[owner], key=lambda x: (order.get(x, 99), x))
        )
        rows.append(f"| {owner} | {seq} |")
    return "\n".join(rows)


def _flat_list(graph: Graph) -> str:
    rows = ["| # | Sahip | Bağımlı olduğu | Kilitlediği |", "|---|---|---|---|"]
    for num in sorted(graph.nodes):
        node = graph.nodes[num]
        deps = sorted(
            f"#{e.src}{'~' if e.soft else ''}" for e in graph.edges if e.dst == num
        )
        blocks = sorted(f"#{e.dst}" for e in graph.edges if e.src == num)
        state = " ✓" if node.done else ""
        rows.append(
            f"| {num}{state} | {node.owner or 'sahipsiz'} | "
            f"{' '.join(deps) or '—'} | {' '.join(blocks) or '—'} |"
        )
    return "\n".join(rows)


def _warnings(graph: Graph) -> str:
    parts: list[str] = []
    orphans = find_orphans(graph.nodes)
    if orphans:
        parts.append(
            "**⚠️ Sahipsiz/label'sız (açık):** "
            + " ".join(f"#{n}" for n in orphans)
        )
    if graph.cycles:
        formatted = "; ".join(
            " → ".join(f"#{n}" for n in cycle) for cycle in graph.cycles
        )
        parts.append(f"**❗ DÖNGÜ (bağımlılık yanlış çıkarılmış olabilir):** {formatted}")
    if not parts:
        parts.append("Döngü yok · sahipsiz/label'sız açık iş yok.")
    return "\n\n".join(parts)


def render_block(graph: Graph, milestone: str) -> str:
    """BOT-BLOK içeriğini üretir (deterministik; markerlar hariç)."""
    return "\n\n".join([
        f"### {milestone} — bağımlılık grafı (otomatik üretildi · #124)",
        "> Kanonik durum GitHub'da. Düz ok = sert (canlı ön-koşul) · "
        "kesik ok = yumuşak (mock ile beklemeden başlar). `~` = yumuşak bağımlılık.",
        "#### Görsel harita",
        _mermaid(graph),
        "#### Dalgalar (sert-kenar topolojik seviyeler)",
        _wave_table(graph),
        "#### Kişi kuyrukları",
        _queues(graph),
        "#### Uyarılar",
        _warnings(graph),
        "#### Düz liste",
        _flat_list(graph),
    ])


# ---------------------------------------------------------------------------
# Dosya birleştirme
# ---------------------------------------------------------------------------

def replace_block(existing: str, block: str) -> str:
    """BOT-BLOK markerları arasını değiştirir; yoksa sona ekler (insan metni korunur)."""
    wrapped = f"{_BLOK_BASI}\n{block}\n{_BLOK_SONU}"
    if _BLOK_BASI in existing and _BLOK_SONU in existing:
        before = existing.split(_BLOK_BASI, 1)[0]
        after = existing.split(_BLOK_SONU, 1)[1]
        return f"{before}{wrapped}{after}"
    sep = "" if existing.endswith("\n") or not existing else "\n\n"
    return f"{existing}{sep}{wrapped}\n"


def _slug(milestone: str) -> str:
    return re.sub(r"[^a-z0-9]", "", milestone.lower())


def _skeleton(milestone: str) -> str:
    return (
        f"# {milestone} — Bağımlılık Haritası & Yürütme Sırası\n\n"
        "> Bu dosyanın BOT-BLOK'u `scripts/bagimlilik_uret.py` ile otomatik "
        "üretilir (#124). Blok DIŞINA yazılan insan notları korunur.\n\n"
    )


# ---------------------------------------------------------------------------
# Veri çekme + CLI
# ---------------------------------------------------------------------------

def fetch_issues(milestone: str) -> list[dict]:
    """gh ile milestone'un tüm issue'larını çeker (--limit 200 zorunlu, rehber §1)."""
    result = subprocess.run(
        [
            "gh", "issue", "list", "--milestone", milestone,
            "--state", "all", "--limit", "200",
            "--json", "number,title,state,assignees,labels,body",
        ],
        capture_output=True, text=True, check=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bağımlılık haritası üretici (#124)")
    parser.add_argument("--milestone", required=True)
    parser.add_argument(
        "--issues-json", help="offline: gh yerine bu JSON dosyasından oku"
    )
    parser.add_argument("--output", help="çıktı .md yolu (varsayılan docs/<slug>-bagimlilik.md)")
    args = parser.parse_args()

    if args.issues_json:
        issues = json.loads(Path(args.issues_json).read_text(encoding="utf-8"))
    else:
        issues = fetch_issues(args.milestone)

    graph = build_graph(issues)
    block = render_block(graph, args.milestone)

    out_path = (
        Path(args.output) if args.output
        else _REPO_ROOT / "docs" / f"{_slug(args.milestone)}-bagimlilik.md"
    )
    existing = (
        out_path.read_text(encoding="utf-8") if out_path.exists()
        else _skeleton(args.milestone)
    )
    out_path.write_text(replace_block(existing, block), encoding="utf-8")

    print(f"yazildi: {out_path}")
    if graph.cycles:
        print(f"UYARI: {len(graph.cycles)} dongu bulundu", file=sys.stderr)


if __name__ == "__main__":
    main()
