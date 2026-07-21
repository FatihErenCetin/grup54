"""Backtest dataset builder (#27) — gecmis repo tarihinden etiketli cakisma korpusu.

Iki asamali determinizm modeli:
  1. SNAPSHOT (bir kez, insan kosar): `gh pr list --state merged` metadata'si
     `pr-snapshot.json`'a dokulur ve COMMIT'lenir — dataset'in zaman pini budur.
  2. BUILD (bu script): yalniz snapshot + yerel git objelerinden calisir; ag yok,
     rastgelelik yok → ayni snapshot + ayni git tarihi = bit-bit ayni cikti.

Ground-truth mantigi (retrospektif simulasyon):
  Iki PR'in aktif pencereleri (ilk commit → merge) ORTUSUYORSA, ikisi eszamanli
  "kor" calisiyordu demektir. `git merge-tree --write-tree headA headB` bu iki
  ucu bugun birlestirmeyi dener:
    - conflict cikti            → label = "conflict"      (net pozitif)
    - temiz merge + dosya kesisimi BOS → label = "no_conflict" (net negatif)
    - temiz merge + dosya kesisimi VAR → GRI BOLGE: git'e gore temiz ama
      potansiyel SEMANTIK cakisma — otomatik etiket YOK, insan etiketi bekler
      (ayri dosyaya yazilir; #28 runner'i v1'de bunu TUKETMEZ).
  Bir uc digerinin atasiysa cift atlanir: sonraki is oncekini GORMUS demektir,
  "kor cakisma" sorusu anlamsizlasir.
  BASE-SKEW korumasi: conflict etiketi ancak conflictli dosyaya iki tarafin
  KENDI isi de dokunduysa gecerlidir — fork noktalari farkliysa aradaki main
  commit'leri simulasyona sizar ve conflict ucuncu bir isin eseri olabilir.

Cikti satirlari tests/fixtures/conflict_corpus.py'deki ConflictCase semasiyla
uyumludur (kontrat: docs/sprint2-kontratlar.md Ek C). `sim` bilincli olarak
null'dur: benzerligi dataset degil DEDEKTOR hesaplar (veri sizintisi olmasin).

Kullanim:  python3 eval/backtest/build_dataset.py  (repo kokunden ya da her yerden)
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from itertools import combinations
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SNAPSHOT = _HERE / "pr-snapshot.json"
_OUT_MAIN = _REPO_ROOT / "eval" / "datasets" / "backtest-grup54.jsonl"
_OUT_GRAY = _REPO_ROOT / "eval" / "datasets" / "backtest-grup54-gri.jsonl"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        # quotePath=off: non-ASCII dosya adlari octal-escape'lenmesin (tutarli ham yol)
        ["git", "-C", str(_REPO_ROOT), "-c", "core.quotePath=off", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        # determinizm: git mesajlari makine yereline gore cevriliyor (ör. "ÇAKIŞMA (içerik)");
        # C locale sabitlemezsek ayni komut farkli makinede farkli metin dondurur.
        # PATH vs. miras kalir (Windows/homebrew kurulumlarini kirmamak icin).
        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    )


def _branch_files(merge_oid: str, head_oid: str) -> list[str]:
    """PR'in kendi degisiklikleri: merge-base(main-oncesi, head)..head dosya listesi."""
    out = _git("diff", "--name-only", f"{merge_oid}^1...{head_oid}")
    return sorted(line for line in out.stdout.splitlines() if line.strip())


def _first_commit_ts(merge_oid: str, head_oid: str) -> str | None:
    """Dala ozgu ilk commit'in author tarihi (ISO) — aktif pencerenin baslangici."""
    out = _git("log", "--format=%aI", "--reverse", f"{merge_oid}^1..{head_oid}")
    lines = out.stdout.splitlines()
    return lines[0] if lines else None


def _is_ancestor(a: str, b: str) -> bool:
    return _git("merge-base", "--is-ancestor", a, b).returncode == 0


def _ts(iso: str) -> datetime:
    """ISO-8601 → TZ-bilincli datetime (git +03:00 ile GitHub Z karisik gelir)."""
    return datetime.fromisoformat(iso)


def _merge_tree_conflicts(head_a: str, head_b: str) -> tuple[bool, list[str]]:
    """3-yollu merge simulasyonu (dokunmadan). (conflict_var_mi, conflictli_dosyalar).

    --write-tree cikti bicimi: 1. satir tree oid, ardindan conflictli dosya adlari,
    BOS SATIR, sonra insan-okur bilgi mesajlari ("Auto-merging ..."). Dosya listesi
    yalniz bos satira KADAR okunur — bilgi mesajlari dosya adi degildir.
    """
    out = _git("merge-tree", "--write-tree", "--name-only", head_a, head_b)
    if out.returncode == 0:
        return False, []
    if out.returncode != 1:
        # git sozlesmesi: 0 = temiz, 1 = conflict, digeri = HATA (ör. cozulmeyen oid) —
        # hatayi conflict sanmak dataset'i sessizce zehirler
        raise RuntimeError(f"merge-tree hatasi ({out.returncode}): {out.stderr.strip()}")
    files: set[str] = set()
    for line in out.stdout.splitlines()[1:]:
        if not line.strip():
            break
        files.add(line)
    return True, sorted(files)


def _event(pr: dict, files: list[str], ts: str, ref: str | None = None) -> dict:
    """PR'i NormalizedEvent seklinde temsil et (type='pr', ref=head SHA)."""
    return {
        "id": f"pr-{pr['number']}",
        "type": "pr",
        "actor": pr["author"],
        "branch": pr["branch"],
        "files": files,
        "ts": ts,
        "ref": ref or pr["head_oid"],
    }


def _mine_internal_merges(enriched: list[dict]) -> tuple[list[dict], list[dict], int]:
    """Cozulup gomulmus conflict'leri geri kazan (retrospektif kanit madenciligi).

    Bir branch calisirken main'i icine merge ettiyse (conflict cozumu dahil), branch
    ucu karsi tarafi 'gormus' olur → ciftli asamada ata-filtresine takilir ve gercek
    pozitif KAYBOLUR. Ama kanit silinmemistir: branch-ici merge commit'i M'nin iki
    ebeveyni (P1 = branch'in o anki ucu, P2 = gelen main) bugun yeniden simule
    edilebilir. merge-tree(P1, P2) conflict veriyorsa, o an YASANMIS cakismayi
    aynen yeniden hesaplariz — cozum M'nin tree'sinde yasar, girdilerinde degil.

    Atif CIFT-BAZLIDIR (adversarial dogrulama bulgusu): ic-merge yalniz KESIF
    tetikleyicisidir; conflictli dosyaya "dokunmus olmak" suclamaya yetmez —
    ayni dosyanin farkli hunk'lari temiz birlesebilir. Bu yuzden her aday PA
    icin merge-tree(PA.head, P1) AYRICA kosulur: cift kendisi conflict veriyorsa
    → conflict; temiz ama ortak dosya varsa → gri (ciftli asamayla ayni taksonomi).
    """
    conflict_rows: list[dict] = []
    gray_rows: list[dict] = []
    skipped_base_skew = 0
    seen_pairs: set[tuple[int, int]] = set()  # ayni cift birden cok ic-merge'de gorunmesin

    for pb in sorted(enriched, key=lambda p: p["number"]):
        merges = _git(
            "rev-list", "--merges", f"{pb['merge_oid']}^1..{pb['head_oid']}"
        ).stdout.split()
        for m in sorted(merges):
            p1 = _git("rev-parse", f"{m}^1").stdout.strip()
            p2 = _git("rev-parse", f"{m}^2").stdout.strip()
            if not p1 or not p2:
                continue
            # branch'in M anindaki KENDI degisiklikleri (P2'de olmayan taraf)
            files_b = sorted(
                ln for ln in _git("diff", "--name-only", f"{p2}...{p1}").stdout.splitlines()
                if ln.strip()
            )
            ts_b_lines = _git("log", "--format=%aI", "--reverse", f"{p2}..{p1}").stdout.splitlines()
            ts_b = ts_b_lines[0] if ts_b_lines else pb["ts_start"]

            for pa in sorted(enriched, key=lambda p: p["number"]):
                if pa["number"] == pb["number"] or (pa["number"], pb["number"]) in seen_pairs:
                    continue
                # PA gelen tarafta var ama branch henuz gormemis olmali
                if not _is_ancestor(pa["head_oid"], p2) or _is_ancestor(pa["head_oid"], p1):
                    continue
                # KRITIK: etiket ciftin KENDI simulasyonundan gelir — M'nin toplu
                # conflict'ine dokunan her PR suclanamaz (farkli hunk temiz birlesir)
                pair_conflict, pair_files = _merge_tree_conflicts(pa["head_oid"], p1)
                overlap = sorted(set(pa["files"]) & set(files_b))
                # base-skew korumasi (ciftli asamayla ayni kural): conflict ancak
                # dosyaya iki tarafin KENDI isi de dokunduysa gecerli
                owned = [f for f in pair_files if f in set(pa["files"]) and f in set(files_b)]
                actor_tag = " [ayni-yazar]" if pa["author"] == pb["author"] else ""
                base_row = {
                    "case_id": f"backtest-pr{pa['number']}-pr{pb['number']}-icmerge",
                    "event_a": _event(pa, pa["files"], pa["ts_start"]),
                    "event_b": _event(pb, files_b, ts_b, ref=p1),
                    "overlap": overlap,
                    "sim": None,
                }
                if pair_conflict and not owned:
                    skipped_base_skew += 1
                    if overlap:
                        seen_pairs.add((pa["number"], pb["number"]))
                        gray_rows.append(
                            {
                                **base_row,
                                "label_beklemede": "insan-etiketi-gerekli",
                                "note": (
                                    f"PR #{pa['number']} + #{pb['number']}: simulasyon base "
                                    f"kaymasiyla kirli ama {len(overlap)} ortak dosya var — "
                                    f"elle incelenecek [ic-merge][base-skew]{actor_tag}"
                                ),
                            }
                        )
                    continue
                if pair_conflict:
                    seen_pairs.add((pa["number"], pb["number"]))
                    conflict_rows.append(
                        {
                            **base_row,
                            "label": "conflict",
                            "note": (
                                f"PR #{pa['number']} + #{pb['number']}: cift dogrudan yeniden "
                                f"simule edildi (kesif: ic-merge {m[:8]}) — conflict: "
                                f"{', '.join(owned)} [ic-merge]{actor_tag}"
                            ),
                        }
                    )
                elif overlap:
                    seen_pairs.add((pa["number"], pb["number"]))
                    gray_rows.append(
                        {
                            **base_row,
                            "label_beklemede": "insan-etiketi-gerekli",
                            "note": (
                                f"PR #{pa['number']} + #{pb['number']}: cift temiz birlesiyor "
                                f"AMA {len(overlap)} ortak dosya (kesif: ic-merge {m[:8]}) — "
                                f"potansiyel semantik cakisma [ic-merge]{actor_tag}"
                            ),
                        }
                    )

    return conflict_rows, gray_rows, skipped_base_skew


def build() -> tuple[list[dict], list[dict], dict]:
    prs = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))

    # PR basina yerel-git turevleri (dosyalar + aktif pencere)
    enriched = []
    for pr in prs:
        ts_start = _first_commit_ts(pr["merge_oid"], pr["head_oid"])
        if ts_start is None:  # dala ozgu commit yok (bos PR) — veri degeri yok
            continue
        enriched.append(
            {
                **pr,
                "files": _branch_files(pr["merge_oid"], pr["head_oid"]),
                "ts_start": ts_start,
                "ts_end": pr["merged_at"],
            }
        )

    main_rows: list[dict] = []
    gray_rows: list[dict] = []
    skipped_ancestor = 0
    skipped_base_skew = 0

    for a, b in combinations(sorted(enriched, key=lambda p: p["number"]), 2):
        # pencere ortusmesi — DIKKAT: git %aI yerel ofset (+03:00), GitHub ise UTC (Z)
        # verir; string karsilastirmasi yanlis olur, datetime'a cevirip karsilastir
        if not (
            _ts(a["ts_start"]) < _ts(b["ts_end"]) and _ts(b["ts_start"]) < _ts(a["ts_end"])
        ):
            continue
        if _is_ancestor(a["head_oid"], b["head_oid"]) or _is_ancestor(b["head_oid"], a["head_oid"]):
            skipped_ancestor += 1  # biri digerini icermis → kor calisma degil
            continue

        overlap = sorted(set(a["files"]) & set(b["files"]))
        has_conflict, conflict_files = _merge_tree_conflicts(a["head_oid"], b["head_oid"])

        # ayni-yazar ciftleri DAHIL: cakisma fizigi yazar tanimaz, dedektor
        # siniflandirmasi icin gecerli veri — #29 sweep isterse nota gore katmanlar
        actor_tag = " [ayni-yazar]" if a["author"] == b["author"] else ""
        row = {
            "case_id": f"backtest-pr{a['number']}-pr{b['number']}",
            "event_a": _event(a, a["files"], a["ts_start"]),
            "event_b": _event(b, b["files"], b["ts_start"]),
            "overlap": overlap,
            "sim": None,  # dedektor hesaplar — dataset'e yazilmaz (Ek C)
        }

        # BASE-SKEW korumasi: farkli fork noktalari yuzunden merge-base kayarsa,
        # aradaki main commit'leri simulasyona sizar ve conflict aslinda ucuncu
        # bir isin eseridir. Etiket ancak conflictli dosyaya IKI TARAFIN KENDI
        # isi de dokunduysa gecerlidir (adversarial dogrulama bulgusu).
        owned = [f for f in conflict_files if f in set(a["files"]) and f in set(b["files"])]
        if has_conflict and not owned:
            skipped_base_skew += 1
            if overlap:  # kendi isleri yine de ayni dosyalara dokunuyor → suphe kalir
                row["label_beklemede"] = "insan-etiketi-gerekli"
                row["note"] = (
                    f"PR #{a['number']} + #{b['number']}: simulasyon base kaymasiyla kirli, "
                    f"ama {len(overlap)} ortak dosya var — elle incelenecek "
                    f"[base-skew]{actor_tag}"
                )
                gray_rows.append(row)
            continue
        if has_conflict:
            row["label"] = "conflict"
            row["note"] = (
                f"PR #{a['number']} + #{b['number']}: merge-tree conflict — "
                f"{', '.join(owned)}{actor_tag}"
            )
            main_rows.append(row)
        elif not overlap:
            row["label"] = "no_conflict"
            row["note"] = (
                f"PR #{a['number']} + #{b['number']}: ayrik dosyalar, "
                f"temiz merge simulasyonu{actor_tag}"
            )
            main_rows.append(row)
        else:
            # GRI: git'e gore temiz ama ayni dosyalara dokunulmus → semantik suphe
            row["label_beklemede"] = "insan-etiketi-gerekli"
            row["note"] = (
                f"PR #{a['number']} + #{b['number']}: temiz merge AMA {len(overlap)} "
                f"ortak dosya — potansiyel semantik cakisma, elle incelenecek{actor_tag}"
            )
            gray_rows.append(row)

    # ata-filtresine takilan ciftlerdeki gomulu kaniti geri kazan (docstring'e bak)
    mined_conflicts, mined_gray, mined_skew = _mine_internal_merges(enriched)
    main_rows.extend(mined_conflicts)
    gray_rows.extend(mined_gray)
    skipped_base_skew += mined_skew

    stats = {
        "pr_sayisi": len(enriched),
        "conflict": sum(1 for r in main_rows if r["label"] == "conflict"),
        "no_conflict": sum(1 for r in main_rows if r["label"] == "no_conflict"),
        "gri": len(gray_rows),
        "ic_merge_kazanimi": {"conflict": len(mined_conflicts), "gri": len(mined_gray)},
        "ayni_yazar": sum(
            1
            for r in main_rows + gray_rows
            if r["event_a"]["actor"] == r["event_b"]["actor"]
        ),
        "atlanan_ata_cifti": skipped_ancestor,
        "atlanan_base_skew": skipped_base_skew,
    }
    return main_rows, gray_rows, stats


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    main_rows, gray_rows, stats = build()
    _write_jsonl(_OUT_MAIN, main_rows)
    _write_jsonl(_OUT_GRAY, gray_rows)
    print(f"yazildi: {_OUT_MAIN.relative_to(_REPO_ROOT)} ({len(main_rows)} satir)")
    print(f"yazildi: {_OUT_GRAY.relative_to(_REPO_ROOT)} ({len(gray_rows)} satir)")
    print("istatistik:", json.dumps(stats, ensure_ascii=False))
    if stats["conflict"] < 5:
        print("UYARI: conflict ornegi az (<5) — recall olcumu zayif kalir")


if __name__ == "__main__":
    main()
