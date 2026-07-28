"""GET /graph (#104) testleri - sözleşme: docs/sprint2-kontratlar.md Ek A.

Odak: fixture NormalizedEvent'lerle deterministik TouchGraph (kabul kriteri 1),
active/ beyanı is_active_declared'ı işaretliyor mu (kriter 2), sıfır LLM
(kriter 4 - kod incelemesi: bu dosyada hiçbir Gemini import'u yok).
"""

from datetime import datetime, timezone

from ensemble.engine.graph import _module_of, build_touch_graph
from ensemble.models import NormalizedEvent


def _event(
    id: str,
    actor: str,
    files: list[str],
    ts: datetime,
    actor_verified: bool = True,
) -> NormalizedEvent:
    return NormalizedEvent(
        id=id,
        type="commit",
        actor=actor,
        branch="main",
        files=files,
        ts=ts,
        ref="abc123",
        actor_verified=actor_verified,
    )


def test_module_of_src_ikinci_segment():
    """Kontrat örneği: src/backend/... -> backend."""
    assert _module_of("src/backend/ensemble/engine/radar.py") == "backend"
    assert _module_of("src/frontend/src/App.tsx") == "frontend"


def test_module_of_src_disi_ilk_segment():
    assert _module_of("docs/sprint2-kontratlar.md") == "docs"
    assert _module_of("eval/gate.py") == "eval"
    assert _module_of("README.md") == "README.md"


def test_deterministik_ayni_girdi_ayni_cikti():
    events = [
        _event("e1", "enes", ["src/backend/a.py"], datetime(2026, 7, 10, tzinfo=timezone.utc)),
        _event("e2", "esma", ["src/frontend/b.tsx"], datetime(2026, 7, 11, tzinfo=timezone.utc)),
    ]
    g1 = build_touch_graph(events, set(), window_days=14)
    g2 = build_touch_graph(events, set(), window_days=14)
    assert g1.model_dump() == g2.model_dump()


def test_nodes_ve_edges_dogru_agregasyon():
    events = [
        _event("e1", "enes", ["src/backend/a.py", "src/backend/b.py"], datetime(2026, 7, 10, tzinfo=timezone.utc)),
        _event("e2", "enes", ["src/backend/a.py"], datetime(2026, 7, 12, tzinfo=timezone.utc)),
        _event("e3", "esma", ["src/frontend/x.tsx"], datetime(2026, 7, 11, tzinfo=timezone.utc)),
    ]
    graph = build_touch_graph(events, set(), window_days=14)

    actor_nodes = {n.id: n.weight for n in graph.nodes if n.type == "actor"}
    module_nodes = {n.id: n.weight for n in graph.nodes if n.type == "module"}
    # enes: e1 (backend, tekil modul kumesi) + e2 (backend) = 2 dokunus
    assert actor_nodes == {"enes": 2, "esma": 1}
    assert module_nodes == {"backend": 2, "frontend": 1}

    edge = next(e for e in graph.edges if e.actor == "enes" and e.module == "backend")
    assert edge.count == 2
    assert edge.last_ts == datetime(2026, 7, 12, tzinfo=timezone.utc)
    assert edge.is_active_declared is False


def test_ayni_eventte_tekrar_eden_modul_bir_kez_sayilir():
    """Bir event iki dosyayla ayni module dokunursa kenar count'u 1 artar (event-bazli)."""
    events = [
        _event(
            "e1", "enes",
            ["src/backend/a.py", "src/backend/b.py", "src/backend/c.py"],
            datetime(2026, 7, 10, tzinfo=timezone.utc),
        ),
    ]
    graph = build_touch_graph(events, set(), window_days=14)
    edge = next(e for e in graph.edges if e.actor == "enes" and e.module == "backend")
    assert edge.count == 1


def test_active_beyani_kenari_isaretler():
    events = [
        _event("e1", "enes", ["src/backend/a.py"], datetime(2026, 7, 10, tzinfo=timezone.utc)),
        _event("e2", "esma", ["src/frontend/x.tsx"], datetime(2026, 7, 10, tzinfo=timezone.utc)),
    ]
    graph = build_touch_graph(events, {("enes", "backend")}, window_days=14)

    by_key = {(e.actor, e.module): e.is_active_declared for e in graph.edges}
    assert by_key[("enes", "backend")] is True
    assert by_key[("esma", "frontend")] is False


def test_bos_events_bos_graf():
    graph = build_touch_graph([], set(), window_days=14)
    assert graph.nodes == []
    assert graph.edges == []
    assert graph.window_days == 14


def test_bos_dosya_listesi_kenar_uretmez():
    events = [_event("e1", "enes", [], datetime(2026, 7, 10, tzinfo=timezone.utc))]
    graph = build_touch_graph(events, set(), window_days=14)
    assert graph.nodes == []
    assert graph.edges == []


def test_sifir_llm_import_yok():
    """Kabul kriteri 4: sıfır LLM çağrısı - Gemini/judge import'u bu modülde YOK."""
    import ensemble.engine.graph as graph_module

    source = graph_module.__file__
    with open(source, encoding="utf-8") as f:
        content = f.read()
    assert "gemini" not in content.lower()
    assert "judge" not in content.lower()


# --- #296 (T-296, PO talebi): GraphNode.actor_verified — PO bu hatayı GRAFTA
# gördü ("Merge Simulation" 5. takım üyesi gibi göründü), o yüzden işaretleme
# Activity'den sonra buraya da taşındı. ---


def test_tum_olaylari_dogrulanmamis_aktor_dugumde_isaretlenir():
    """'Merge Simulation' vakası: bu aktörün BÜTÜN olayları eşleşmedi ->
    GraphNode.actor_verified False olmalı."""
    events = [
        _event(
            "e1", "Merge Simulation", ["src/backend/a.py"],
            datetime(2026, 7, 10, tzinfo=timezone.utc), actor_verified=False,
        ),
        _event(
            "e2", "Merge Simulation", ["src/backend/b.py"],
            datetime(2026, 7, 11, tzinfo=timezone.utc), actor_verified=False,
        ),
    ]
    graph = build_touch_graph(events, set(), window_days=14)
    node = next(n for n in graph.nodes if n.id == "Merge Simulation")
    assert node.actor_verified is False


def test_karisik_durum_bir_olay_dogrulanirsa_aktor_dogrulanmis_sayilir():
    """PO kararı: aynı kişi bazı commit'lerini doğru git config ile, bazılarını
    yanlışla atmış olabilir - o GERÇEK bir GitHub kullanıcısıdır, tek bir
    eşleşmeyen commit onu komple 'eşleşmedi' göstermemeli (yanlış alarm).

    MUTASYON KİLİDİ: toplama kuralı ters çevrilip "bir olay bile eşleşmediyse
    komple işaretle" yapılırsa bu test KIRMIZI olur (bkz. PR gövdesi tablosu)."""
    events = [
        _event(
            "e1", "esma6", ["src/backend/a.py"],
            datetime(2026, 7, 10, tzinfo=timezone.utc), actor_verified=True,
        ),
        _event(
            "e2", "esma6", ["src/backend/b.py"],
            datetime(2026, 7, 11, tzinfo=timezone.utc), actor_verified=False,
        ),
    ]
    graph = build_touch_graph(events, set(), window_days=14)
    node = next(n for n in graph.nodes if n.id == "esma6")
    assert node.actor_verified is True


def test_actor_verified_belirtilmemis_olaylar_dugumu_dogrulanmis_yapar():
    """Eski/mock fixture'lar `actor_verified` hiç vermez (additive+varsayılanlı
    alan, model default'u True) - düğüm sessizce 'eşleşmedi' görünmemeli."""
    events = [_event("e1", "enes", ["src/backend/a.py"], datetime(2026, 7, 10, tzinfo=timezone.utc))]
    graph = build_touch_graph(events, set(), window_days=14)
    node = next(n for n in graph.nodes if n.id == "enes")
    assert node.actor_verified is True


def test_modul_dugumu_actor_verified_alaninda_etkilenmez():
    """type='module' düğümlerinde alan ANLAMSIZ - varsayılanında (True) kalır,
    aktörün doğrulama durumundan hiç etkilenmez."""
    events = [
        _event(
            "e1", "Merge Simulation", ["src/backend/a.py"],
            datetime(2026, 7, 10, tzinfo=timezone.utc), actor_verified=False,
        ),
    ]
    graph = build_touch_graph(events, set(), window_days=14)
    module_node = next(n for n in graph.nodes if n.id == "backend")
    assert module_node.type == "module"
    assert module_node.actor_verified is True
