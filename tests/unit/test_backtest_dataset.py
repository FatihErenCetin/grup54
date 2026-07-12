"""Backtest dataset (#27) testleri — sema, sizinti korumasi, determinizm.

Iki katman:
  - Commit'li dataset uzerinde HER ZAMAN kosan testler (CI dahil): sema
    validasyonu, sim=None sizinti korumasi, bilinen-vaka sanity, dedup.
  - Builder'i YENIDEN kosan determinizm testi: shallow clone'da (CI fetch-depth=1)
    PR head objeleri bulunmayabilir → o ortamda skip edilir, yerelde kosar.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from tests.fixtures.conflict_corpus import ConflictCase, load_conflict_corpus

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DATASET = _REPO_ROOT / "eval" / "datasets" / "backtest-grup54.jsonl"
_GRAY = _REPO_ROOT / "eval" / "datasets" / "backtest-grup54-gri.jsonl"
_BUILDER = _REPO_ROOT / "eval" / "backtest" / "build_dataset.py"


def _load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_dataset", _BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git_objects_available() -> bool:
    """PR head objeleri yerel clone'da mi? (CI shallow checkout'ta olmayabilir)"""
    snapshot = json.loads((_REPO_ROOT / "eval" / "backtest" / "pr-snapshot.json").read_text())
    probe = snapshot[0]["head_oid"]
    r = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "cat-file", "-e", probe], capture_output=True
    )
    return r.returncode == 0


def test_her_satir_conflictcase_semasindan_gecer():
    cases = [ConflictCase.model_validate(r) for r in _load_rows(_DATASET)]
    assert len(cases) > 0


def test_sim_hep_none_veri_sizintisi_yok():
    # backtest verisinde benzerligi dedektor hesaplar; dataset cevabi tasiyamaz (Ek C)
    assert all(r["sim"] is None for r in _load_rows(_DATASET))


def test_korpus_geriye_uyumlu_sim_float_kaldi():
    # sim: float | None gevsemesi #26'nin kuratorlu float'larini bozmamali
    corpus = load_conflict_corpus()
    assert len(corpus) >= 12
    assert all(isinstance(c.sim, float) for c in corpus)


def test_bilinen_tarihsel_conflict_yakalanmis():
    # 10-11 Tem'de gercekten yasandi: #135 (Gemini adapter) ile #137 (GitHub ingest)
    # ikisi de config.py/pyproject/test_config'e dokundu; cozum ic-merge'e gomuldu.
    # Madenci bunu geri kazanamiyorsa dataset kordur.
    rows = {r["case_id"]: r for r in _load_rows(_DATASET)}
    case = rows.get("backtest-pr135-pr137-icmerge")
    assert case is not None, "bilinen #135+#137 conflict'i dataset'te yok"
    assert case["label"] == "conflict"
    assert "src/backend/ensemble/config.py" in case["note"]


def test_case_idler_tekil():
    ids = [r["case_id"] for r in _load_rows(_DATASET)]
    assert len(ids) == len(set(ids))


def test_iki_etiket_de_var():
    labels = {r["label"] for r in _load_rows(_DATASET)}
    assert labels == {"conflict", "no_conflict"}


def test_gri_dosya_ana_semada_degil():
    # gri satirlar bilerek etiketsiz — #28 v1 bunlari TUKETMEZ (Ek C)
    for row in _load_rows(_GRAY):
        assert "label" not in row
        assert row["label_beklemede"] == "insan-etiketi-gerekli"


@pytest.mark.skipif(
    not _git_objects_available(),
    reason="PR head objeleri yok (shallow clone) — determinizm testi yalniz tam clone'da",
)
def test_builder_deterministik_ve_commitli_dataset_guncel():
    # ayni snapshot + ayni git tarihi → bit-bit ayni cikti; ayrica commit'li
    # dataset ile builder ciktisi arasinda drift olmadigini da kanitlar
    mod = _load_builder()
    main_rows, gray_rows, _stats = mod.build()
    expected_main = [json.dumps(r, ensure_ascii=False) for r in main_rows]
    expected_gray = [json.dumps(r, ensure_ascii=False) for r in gray_rows]
    assert _DATASET.read_text(encoding="utf-8").splitlines() == expected_main
    assert _GRAY.read_text(encoding="utf-8").splitlines() == expected_gray
