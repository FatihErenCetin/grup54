"""Bağımlılık haritası üretici (#124) testleri.

Kabul kriteri odağı: script S2 verisinden EŞDEĞER graf üretiyor (fixture),
döngü tespiti çalışıyor, sahipsizler raporlanıyor.
"""

import json
from pathlib import Path

from scripts.bagimlilik_uret import (
    build_graph,
    detect_cycles,
    find_orphans,
    parse_prereqs,
    render_block,
    replace_block,
    topological_waves,
)

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "bagimlilik_issues.json"


def _issues() -> list[dict]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


# --- ayrıştırma ---

def test_parse_hard_and_soft():
    hard, soft = parse_prereqs("**Ön-koşul:** #26, #27\n**Yumuşak ön-koşul:** #17")
    assert hard == [26, 27]
    assert soft == [17]


def test_soft_line_not_double_counted_as_hard():
    """'Yumuşak ön-koşul' metni 'ön-koşul'u içerir → sert'e SIZMAMALI."""
    hard, soft = parse_prereqs("**Yumuşak ön-koşul:** #17")
    assert hard == []
    assert soft == [17]


def test_parse_dash_means_none():
    hard, soft = parse_prereqs("**Ön-koşul:** — (backfill tamam)")
    assert hard == []
    assert soft == []


def test_prose_mention_not_a_prereq():
    """Narrative/olumsuzlama satırı sahte HARD kenar üretmemeli (adversarial bulgu)."""
    assert parse_prereqs("bu bir ön-koşul değildir ama #42 ilgilidir") == ([], [])
    assert parse_prereqs("Ön-koşul yoktur; sadece #42 referansı") == ([], [])
    assert parse_prereqs("Not: bunun #1 ile bir ön-koşul ilişkisi YOKTUR") == ([], [])


def test_structured_field_still_parses():
    """Anchor'lı alan (opsiyonel ** ve çoklu değer) hâlâ doğru çıkar."""
    assert parse_prereqs("**Ön-koşul:** #28") == ([28], [])
    assert parse_prereqs("Ön-koşul: #1, #2, #3") == ([1, 2, 3], [])


def test_prose_negation_does_not_fabricate_cycle():
    """Gerçek kenar + prose-olumsuzlama → sahte döngü/kenar olmamalı."""
    issues = [
        {"number": 1, "title": "a", "state": "open",
         "assignees": [], "labels": [], "body": "**Ön-koşul:** #2"},
        {"number": 2, "title": "b", "state": "open",
         "assignees": [], "labels": [],
         "body": "Burada #1 için bir ön-koşul söz konusu değildir."},
    ]
    graph = build_graph(issues)
    assert graph.cycles == []
    assert any(e.src == 2 and e.dst == 1 for e in graph.edges)
    assert not any(e.src == 1 and e.dst == 2 for e in graph.edges)


# --- graf inşası ---

def test_edges_hard_and_soft():
    graph = build_graph(_issues())
    assert any(e.src == 28 and e.dst == 30 and not e.soft for e in graph.edges)
    assert any(e.src == 17 and e.dst == 28 and e.soft for e in graph.edges)


def test_unknown_prereq_dropped():
    """#124'ün yumuşak ön-koşulu #117 fixture'da yok → kenar çizilmez."""
    graph = build_graph(_issues())
    assert all(e.src in graph.nodes and e.dst in graph.nodes for e in graph.edges)
    assert not any(e.src == 117 for e in graph.edges)


def test_owner_login_mapped_to_handle():
    graph = build_graph(_issues())
    assert graph.nodes[30].owner == "fatih"
    assert graph.nodes[28].owner == "enes"


def test_theme_from_label():
    graph = build_graph(_issues())
    assert graph.nodes[30].theme == "eval"
    assert graph.nodes[124].theme == "süreç"
    assert graph.nodes[99].theme == "Diğer"


# --- döngü / sahipsiz / dalga ---

def test_no_cycles_in_fixture():
    graph = build_graph(_issues())
    assert graph.cycles == []


def test_cycle_detected():
    issues = [
        {"number": 1, "title": "a", "state": "open",
         "assignees": [{"login": "esma6"}], "labels": [{"name": "task"}],
         "body": "**Ön-koşul:** #2"},
        {"number": 2, "title": "b", "state": "open",
         "assignees": [{"login": "esma6"}], "labels": [{"name": "task"}],
         "body": "**Ön-koşul:** #1"},
    ]
    graph = build_graph(issues)
    assert graph.cycles, "A->B->A döngüsü yakalanmalı"


def test_soft_edge_does_not_make_cycle():
    """Yumuşak kenar döngü saymamalı (mock ile başlanabilir)."""
    issues = [
        {"number": 1, "title": "a", "state": "open",
         "assignees": [], "labels": [], "body": "**Yumuşak ön-koşul:** #2"},
        {"number": 2, "title": "b", "state": "open",
         "assignees": [], "labels": [], "body": "**Yumuşak ön-koşul:** #1"},
    ]
    assert detect_cycles(build_graph(issues).nodes, build_graph(issues).edges) == []


def test_orphans_ownerless_or_labelless():
    graph = build_graph(_issues())
    orphans = find_orphans(graph.nodes)
    assert 99 in orphans          # sahipsiz + label'sız
    assert 30 not in orphans      # sahibi + label'ı var
    assert 28 not in orphans      # kapalı (açık değil)


def test_waves_closed_prereq_not_blocking():
    """#30 sert olarak #28'e bağlı ama #28 kapalı → #30 D0'da."""
    graph = build_graph(_issues())
    waves = topological_waves(graph.nodes, graph.edges)
    order = {n: i for i, wave in enumerate(waves) for n in wave}
    assert order.get(30) == 0
    assert order.get(28) is None  # kapalı düğüm dalgalarda yok


# --- render / birleştirme ---

def test_render_deterministic():
    graph = build_graph(_issues())
    assert render_block(graph, "Sprint 2") == render_block(graph, "Sprint 2")


def test_render_has_nodes_and_mermaid():
    block = render_block(build_graph(_issues()), "Sprint 2")
    assert "```mermaid" in block
    assert "I30" in block and "I124" in block


def test_replace_block_preserves_human_text():
    existing = (
        "# Başlık\n\nİnsan notu üstte.\n\n"
        "<!-- BOT-BLOK:baslangic -->\nESKI\n<!-- BOT-BLOK:bitis -->\n\nİnsan notu altta.\n"
    )
    out = replace_block(existing, "YENI")
    assert "İnsan notu üstte." in out
    assert "İnsan notu altta." in out
    assert "YENI" in out
    assert "ESKI" not in out


def test_replace_block_appends_when_no_markers():
    out = replace_block("# Sadece insan metni\n", "BLOK")
    assert "# Sadece insan metni" in out
    assert "<!-- BOT-BLOK:baslangic -->" in out
    assert "BLOK" in out
