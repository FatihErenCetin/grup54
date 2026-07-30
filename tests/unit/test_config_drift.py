"""#349 — "imaj taze, yapilandirma bayat" sinifinin kilidi.

OLCULMUS OLAY (30 Tem 2026, uretim — bu testlerin varlik sebebi):
sunucudaki elle-operasyon checkout'u (`/home/fatih/grup54`) `origin/main`'den
73 commit geride kalmisti; CD yalnizca IMAJI tasidigi icin konteyneri YARATAN
compose dosyasi 3 gun eskiydi.

    main'deki compose:   RADAR_WINDOW_DAYS=14 · GITHUB_BACKFILL_LIMIT=150
    konteynerde efektif: RADAR_WINDOW_DAYS=2  · GITHUB_BACKFILL_LIMIT=10

#326'nin radar duzeltmesi prod'a HIC ulasmadi; radar 30 Tem'de tamamen
bosaldi (0 tespit). Ayni imajla, yalniz compose tazelenince 110 tespit.

BU DOSYA NEYI KILITLER
======================
1. `scripts/config_drift.py`in saf fonksiyonlari (compose parse · env parse ·
   fark bulma · ops-checkout karsilastirmasi).
2. Script'in UCTAN UCA davranisi — GERCEK bir alt surec olarak, PATH'e konan
   SAHTE bir `docker` ile (ag/gercek docker YOK): drift varsa 1, temizse 0,
   olculemiyorsa 2. Metnin taklidi degil, dosyanin KENDISI kosar.
3. `.github/workflows/deploy.yml`in iki yeni adimi (`ops_sync` + drift
   dogrulamasi) — YAML seviyesinde VE `ops_sync` govdesi GERCEK git
   depolariyla, gercek bash altinda kosturularak (test_deploy_workflow.py'nin
   `_run_ci_check` desenini izler).
4. `.github/workflows/config-drift.yml` nobeti (periyodik olcum) — bu sinifin
   ZARARI iki deploy ARASINDA olusur, deploy-anindaki kontrol tek basina
   yetmez.
5. `deploy/docker-compose.prod.yml`in olaya konu KRITIK anahtarlarinin hala
   `environment:` blogunda ve DUZ (interpolasyonsuz) oldugu — biri sunucudaki
   sir dosyasina geri tasinirsa kilit sessizce KONUSUZ kalirdi.
6. `docs/deploy-runbook.md`in elle komutlarinin `pull` adimini tasidigi ve
   sunucuda BULUNMAYAN `/opt/ensemble` yolunu artik onermedigi.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "config_drift.py"
COMPOSE_PATH = REPO_ROOT / "deploy" / "docker-compose.prod.yml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
RUNBOOK_PATH = REPO_ROOT / "docs" / "deploy-runbook.md"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import config_drift  # noqa: E402  (sys.path ayarindan SONRA import edilmeli)


def _load_workflow(ad: str) -> dict:
    return yaml.safe_load((WORKFLOWS_DIR / ad).read_text(encoding="utf-8"))


def _steps(job: dict) -> list[dict]:
    return job.get("steps", []) or []


DEPLOY = _load_workflow("deploy.yml")
NOBET = _load_workflow("config-drift.yml")


# ===========================================================================
# 1. Saf fonksiyonlar
# ===========================================================================


def test_compose_env_mapping_bicimini_okur():
    metin = """
name: ensemble
services:
  api:
    environment:
      ENSEMBLE_MODE: hosted
      RADAR_WINDOW_DAYS: "14"
      GITHUB_BACKFILL_LIMIT: "150"
"""
    karsilastirilabilir, atlanan = config_drift.compose_env_oku(metin)
    assert karsilastirilabilir == {
        "ENSEMBLE_MODE": "hosted",
        "RADAR_WINDOW_DAYS": "14",
        "GITHUB_BACKFILL_LIMIT": "150",
    }
    assert atlanan == {}


def test_compose_env_liste_bicimini_de_okur():
    """`environment:` mapping YERINE liste yazilabilir (`- K=V`). Yalniz
    mapping desteklenseydi bicim degisiminde kilit SESSIZCE konusuz kalirdi
    (bos sozluk -> hicbir fark -> hep yesil) — tam da bu testin engelledigi
    sey."""
    metin = """
name: ensemble
services:
  api:
    environment:
      - ENSEMBLE_MODE=hosted
      - RADAR_WINDOW_DAYS=14
"""
    karsilastirilabilir, atlanan = config_drift.compose_env_oku(metin)
    assert karsilastirilabilir == {"ENSEMBLE_MODE": "hosted", "RADAR_WINDOW_DAYS": "14"}
    assert atlanan == {}


def test_interpolasyonlu_degerler_karsilastirilmaz_ama_raporlanir():
    """`DATABASE_URL` degeri sunucudaki sir dosyasindan gelir — repo'dan
    BILINEMEZ, karsilastirilirsa HER kosuda yanlis kirmizi verir. Ama sessizce
    yok sayilmaz: ayri bir sozlukte doner ve rapora basilir."""
    metin = """
name: ensemble
services:
  api:
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/x
      PORT: "8000"
"""
    karsilastirilabilir, atlanan = config_drift.compose_env_oku(metin)
    assert karsilastirilabilir == {"PORT": "8000"}
    assert "DATABASE_URL" in atlanan


def test_tirnaksiz_sayi_ve_bool_konteyner_bicimine_cevrilir():
    """YAML `8000` -> int, `true` -> bool. Konteynerde ikisi de METINDIR
    ("8000" / "true"). Python'un `str(True)` == "True" ciktisi konteynerdeki
    "true" ile ESLESMEZ -> her kosuda yanlis kirmizi olurdu."""
    assert config_drift.deger_metni(8000) == "8000"
    assert config_drift.deger_metni(True) == "true"
    assert config_drift.deger_metni(False) == "false"
    assert config_drift.deger_metni(None) == ""


def test_konteyner_env_ayristirma_ve_son_deger_kazanir():
    env = config_drift.konteyner_env_ayristir(
        ["PATH=/usr/bin", "RADAR_WINDOW_DAYS=2", "RADAR_WINDOW_DAYS=14", "BOZUK_SATIR"]
    )
    assert env["PATH"] == "/usr/bin"
    assert env["RADAR_WINDOW_DAYS"] == "14"
    assert "BOZUK_SATIR" not in env


def test_farklari_bul_eksik_ve_ayrisan_anahtari_yakalar():
    farklar = config_drift.farklari_bul(
        {"A": "1", "B": "2", "C": "3"}, {"A": "1", "B": "99", "EKSTRA": "x"}
    )
    anahtarlar = {f.anahtar for f in farklar}
    assert anahtarlar == {"B", "C"}, farklar
    assert next(f for f in farklar if f.anahtar == "C").gercek is None


def test_farklari_bul_konteynerdeki_fazladan_anahtarlari_fark_saymaz():
    """Konteynerde sir dosyasindan gelen 30+ anahtar var (olculdu: 36).
    Karsilastirma TEK YONLUDUR — aksi halde her kosu kirmizi olurdu."""
    assert config_drift.farklari_bul({"A": "1"}, {"A": "1", "GEMINI_API_KEY": "gizli"}) == []


def test_ops_checkout_farki_ayni_dosyada_none_farkli_dosyada_aciklama_dondurur(tmp_path):
    repo_compose = tmp_path / "repo" / "deploy" / "docker-compose.prod.yml"
    repo_compose.parent.mkdir(parents=True)
    icerik = 'name: ensemble\nservices:\n  api:\n    environment:\n      RADAR_WINDOW_DAYS: "14"\n'
    repo_compose.write_text(icerik, encoding="utf-8")

    ops = tmp_path / "ops"
    (ops / "deploy").mkdir(parents=True)
    ops_compose = ops / "deploy" / "docker-compose.prod.yml"

    gorece = Path("deploy/docker-compose.prod.yml")

    ops_compose.write_text(icerik, encoding="utf-8")
    assert config_drift.ops_checkout_farki(ops, repo_compose, gorece) is None

    ops_compose.write_text(icerik.replace('"14"', '"2"'), encoding="utf-8")
    bulgu = config_drift.ops_checkout_farki(ops, repo_compose, gorece)
    assert bulgu is not None
    assert "RADAR_WINDOW_DAYS" in bulgu, bulgu

    ops_compose.unlink()
    assert "YOK" in (config_drift.ops_checkout_farki(ops, repo_compose, gorece) or "")


# ===========================================================================
# 2. Uctan uca: GERCEK script + sahte `docker` (mutasyona acik)
# ===========================================================================

_SAHTE_DOCKER = """#!/usr/bin/env bash
set -u
case "${1:-}" in
  ps)
    # Bos FAKE_CONTAINER_ID -> "kosan konteyner yok" (olculemedi) yolu.
    [ -n "${FAKE_CONTAINER_ID:-}" ] && printf '%s\\n' "$FAKE_CONTAINER_ID"
    exit 0
    ;;
  inspect)
    printf '%s\\n' "${FAKE_CONFIG_JSON:?FAKE_CONFIG_JSON verilmedi}"
    exit 0
    ;;
esac
echo "sahte docker: beklenmeyen alt komut ${1:-}" >&2
exit 1
"""


def _sahte_docker_kur(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    sahte = bin_dir / "docker"
    sahte.write_text(_SAHTE_DOCKER)
    sahte.chmod(sahte.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _script_kos(
    tmp_path: Path,
    *,
    compose: Path,
    konteyner_env: dict[str, str] | None,
    ops_checkout: str = "",
) -> subprocess.CompletedProcess:
    """`scripts/config_drift.py`i GERCEKTEN calistirir (metnin taklidi DEGIL).

    `konteyner_env=None` -> kosan konteyner YOK (olculemedi yolu)."""
    bin_dir = _sahte_docker_kur(tmp_path)
    config_json = json.dumps(
        {
            "Env": [f"{k}={v}" for k, v in (konteyner_env or {}).items()],
            "Labels": {config_drift.ETIKET_CONFIG_FILES: "/home/fatih/grup54/deploy/x.yml"},
        }
    )
    env = {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "FAKE_CONTAINER_ID": "" if konteyner_env is None else "abc123",
        "FAKE_CONFIG_JSON": config_json,
        "HOME": os.environ.get("HOME", str(tmp_path)),
    }
    arg = ["--compose", str(compose)]
    if ops_checkout:
        arg += ["--ops-checkout", ops_checkout]
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *arg],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _gercek_compose_env() -> dict[str, str]:
    karsilastirilabilir, _ = config_drift.compose_env_oku(
        COMPOSE_PATH.read_text(encoding="utf-8")
    )
    return karsilastirilabilir


def test_script_konteyner_main_ile_ayniysa_temiz_biter(tmp_path):
    """GERCEK `deploy/docker-compose.prod.yml` + ayni degerleri tasiyan bir
    konteyner -> cikis 0."""
    res = _script_kos(tmp_path, compose=COMPOSE_PATH, konteyner_env=_gercek_compose_env())
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Yapilandirma drifti YOK" in res.stdout


def test_script_349_olayini_aynen_yeniden_uretince_kirmizi_olur(tmp_path):
    """30 Tem'in TAM olcumu: konteynerde RADAR_WINDOW_DAYS=2 ·
    GITHUB_BACKFILL_LIMIT=10 iken main 14 · 150 diyor -> cikis 1 ve iki
    anahtar da ADIYLA raporlanir. Bu test kirmizi vermiyorsa kilit yoktur."""
    env = _gercek_compose_env()
    env["RADAR_WINDOW_DAYS"] = "2"
    env["GITHUB_BACKFILL_LIMIT"] = "10"
    res = _script_kos(tmp_path, compose=COMPOSE_PATH, konteyner_env=env)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "::error::" in res.stdout
    assert "RADAR_WINDOW_DAYS" in res.stdout
    assert "GITHUB_BACKFILL_LIMIT" in res.stdout


def test_script_konteyner_kosmuyorsa_olculemedi_ile_biter_yesil_degil(tmp_path):
    """FAIL-OPEN YASAK: olcum yapilamadiginda "drift yok" DEMEZ, 2 ile
    (sifir-disi = kirmizi) biter."""
    res = _script_kos(tmp_path, compose=COMPOSE_PATH, konteyner_env=None)
    assert res.returncode == 2, res.stdout + res.stderr
    assert "OLCULEMEDI" in res.stdout


def test_script_ops_checkout_bayatsa_konteyner_dogru_olsa_bile_kirmizi(tmp_path):
    """B kontrolu — A'dan BAGIMSIZ deger: konteyner bugun DOGRU kosuyor
    (A yesil) ama elle-operasyon checkout'undaki compose bayat; bir sonraki
    ELLE `up -d` prod'u yeniden bozar. Tek bir "her sey yolunda" bunu
    goremezdi."""
    ops = tmp_path / "ops"
    (ops / "deploy").mkdir(parents=True)
    bayat = COMPOSE_PATH.read_text(encoding="utf-8").replace(
        'RADAR_WINDOW_DAYS: "14"', 'RADAR_WINDOW_DAYS: "2"'
    )
    assert 'RADAR_WINDOW_DAYS: "2"' in bayat, "test kurulumu: compose metni beklenen satiri tasimiyor"
    (ops / "deploy" / "docker-compose.prod.yml").write_text(bayat, encoding="utf-8")

    res = _script_kos(
        tmp_path,
        compose=COMPOSE_PATH,
        konteyner_env=_gercek_compose_env(),  # A: konteyner main ile AYNI
        ops_checkout=str(ops),
    )
    assert res.returncode == 1, res.stdout + res.stderr
    assert "elle-operasyon checkout" in res.stdout


def test_script_ops_checkout_verilmezse_sessiz_gecmez(tmp_path):
    """Kosmayan bir kontrol SESSIZ kalamaz — gorunur `::warning::` basar."""
    res = _script_kos(tmp_path, compose=COMPOSE_PATH, konteyner_env=_gercek_compose_env())
    assert res.returncode == 0
    assert "::warning::" in res.stdout, res.stdout


# ===========================================================================
# 3. `deploy/docker-compose.prod.yml` — kilidin KONUSU kaybolmasin
# ===========================================================================


def test_olaya_konu_kritik_anahtarlar_compose_environment_blogunda_ve_duz():
    """#324/#326'nin radar ayarlari `services.api.environment` icinde VE
    interpolasyonsuz olmali.

    Neden test: bu anahtarlar sunucudaki `/etc/ensemble/ensemble.env`e geri
    tasinirsa (ya da `${RADAR_WINDOW_DAYS}` bicimine cevrilirse) drift kilidi
    hicbir sey KIRMAZ — sessizce KONUSUZ kalir ve #349 aynen geri doner. Bu,
    compose dosyasinin kendi yorumundaki "bunlar sir degil, AYAR; commit'li
    olmalilar" gerekcesinin makine-okunur hali."""
    karsilastirilabilir, atlanan = config_drift.compose_env_oku(
        COMPOSE_PATH.read_text(encoding="utf-8")
    )
    for anahtar in ("RADAR_WINDOW_DAYS", "GITHUB_BACKFILL_LIMIT", "RADAR_JUDGE_CONCURRENCY"):
        assert anahtar in karsilastirilabilir, (
            f"{anahtar} artik compose `api.environment` blogunda DUZ bir deger degil "
            f"(atlananlar: {sorted(atlanan)}) -- drift kilidi bu anahtari artik "
            "olcemez, #349 sessizce geri doner."
        )
    assert "ENSEMBLE_MODE" in karsilastirilabilir


# ===========================================================================
# 4. deploy.yml — iki yeni adim (YAML seviyesi)
# ===========================================================================


def _deploy_steps() -> list[dict]:
    return _steps(DEPLOY["jobs"]["deploy"])


def _ops_sync_step() -> dict:
    step = next((s for s in _deploy_steps() if s.get("id") == "ops_sync"), None)
    assert step is not None, (
        "deploy.yml deploy job'inda `id: ops_sync` adimi YOK -- elle-operasyon "
        "checkout'unu tazeleyen adim silinmis (#349 aynen geri doner)."
    )
    return step


def test_ops_sync_adimi_deploy_edilen_shaya_baglanir_ve_yol_sabit_kodlu_degil():
    step = _ops_sync_step()
    env = step.get("env") or {}
    assert "OPS_CHECKOUT_DIR" in env, f"ops_sync env: {env!r}"
    assert "vars.OPS_CHECKOUT_DIR" in str(env["OPS_CHECKOUT_DIR"]), (
        f"OPS_CHECKOUT_DIR={env['OPS_CHECKOUT_DIR']!r} -- yol repo variable'indan "
        "GELMIYOR (sabit kodlanmis olabilir); farkli bir sunucu topolojisinde "
        "sessizce yanlis dizini tazeler."
    )
    assert "needs.preflight.outputs.sha" in str(env.get("SHA", "")), (
        "ops_sync hedefi deploy edilen TAM SHA'ya bagli degil -- main'in hareketli "
        "ucuna cekerse iki checkout farkli commit'lerde kalabilir."
    )
    govde = step["run"]
    assert "/home/fatih/grup54" not in govde.split("gh variable set")[0], (
        "ops_sync govdesinde sabit kodlu bir sunucu yolu var (yalniz ornek/oneri "
        "metninde gecmeli)."
    )


def test_ops_sync_hicbir_dalda_sessizce_gecmez():
    """Tanimsizsa `::warning::`, bozuksa `::error::` + `exit 1`. Hicbir dal
    sessiz DEGIL (SESSIZ DUSUS YASAK)."""
    govde = _ops_sync_step()["run"]
    assert "::warning::" in govde, "Degisken tanimsiz dalinda gorunur bir uyari yok."
    assert "::error::" in govde, "Hata dallarinda gorunur bir ::error:: yok."
    assert "exit 1" in govde, "Fail-CLOSED dal yok -- bozuk bir yol sessizce tolere ediliyor."
    assert "--ff-only" in govde, (
        "`--ff-only` yok -- merge commit'i uretilebilir ya da yerel commit sessizce "
        "ezilebilir; ikisi de bu kilidin anlamini bozar."
    )
    assert "reset --hard" not in govde, (
        "`reset --hard` operatorun yerel dosyalarini yok eder; CD'nin isi kirmizi "
        "verip insani cagirmaktir."
    )


def _up_index() -> int:
    """`docker compose ... up -d` KOSAN adimin sirasi (mesaj metninde 'up -d'
    gecen adimlar degil -- ikisi de ayni kelimeyi tasiyabilir)."""
    return next(
        i
        for i, s in enumerate(_deploy_steps())
        if "docker compose" in (s.get("run") or "") and "up -d" in s["run"]
    )


def test_ops_sync_deploy_eden_adimlardan_ONCE_kosar():
    adlar = [s.get("name", "") for s in _deploy_steps()]
    idler = [s.get("id") for s in _deploy_steps()]
    ops_index = idler.index("ops_sync")
    up_index = _up_index()
    assert ops_index < up_index, (
        f"ops_sync (#{ops_index}) `up -d` adimindan (#{up_index}) SONRA -- elle "
        f"komut penceresi acik kalir. Adimlar: {adlar}"
    )


def _drift_step() -> dict:
    step = next(
        (s for s in _deploy_steps() if "config_drift.py" in (s.get("run") or "")), None
    )
    assert step is not None, (
        "deploy.yml deploy job'inda `scripts/config_drift.py` cagiran adim YOK -- "
        "deploy 'basarili' derken calisan yapilandirmanin main'den farkli olmasi "
        "yine sessiz kalir."
    )
    return step


def test_drift_dogrulamasi_up_dden_SONRA_kosar_ve_hata_bastirmaz():
    steps = _deploy_steps()
    up_index = _up_index()
    drift_index = steps.index(_drift_step())
    assert drift_index > up_index, (
        "Drift dogrulamasi `up -d`den ONCE kosuyor -- deploy'un uyguladigi degil, "
        "uygulanmadan onceki durumu olcerdi."
    )
    step = _drift_step()
    assert "continue-on-error" not in step
    assert "|| true" not in step["run"], "Cikis kodu yutuluyor -- kirmizi hic gorunmez."
    assert "if" not in step, "Step-level `if` sessiz atlamaya kapi acar."
    env = step.get("env") or {}
    assert "vars.OPS_CHECKOUT_DIR" in str(env.get("OPS_CHECKOUT_DIR", "")), (
        "Drift adimi OPS_CHECKOUT_DIR'i almiyor -- B kontrolu (elle-operasyon "
        "checkout'u) CD'de hic kosmaz."
    )


def test_cd_uv_kullanmaz_cunku_sunucuda_uv_yok():
    """Olculdu (30 Tem, VDS): `which uv` -> bos; `python3` -> 3.10.12 + PyYAML
    5.4.1. `uv run` yazilsaydi adim ilk kosuda "command not found" ile
    patlardi."""
    govde = _drift_step()["run"]
    assert govde.strip().startswith("python3 "), f"Drift adimi govdesi: {govde!r}"
    assert "uv run" not in govde


# ===========================================================================
# 5. `ops_sync` govdesi — GERCEK git depolariyla, gercek bash altinda
# ===========================================================================


def _git(*argumanlar: str, cwd: Path) -> str:
    sonuc = subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "user.name=Test",
            "-c",
            "commit.gpgsign=false",
            *argumanlar,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert sonuc.returncode == 0, f"git {argumanlar}: {sonuc.stderr}"
    return sonuc.stdout.strip()


def _iki_commitli_depo(tmp_path: Path) -> tuple[Path, str, str]:
    """(ops_checkout, eski_sha, yeni_sha) -- ops checkout'u ESKI commit'te."""
    kaynak = tmp_path / "kaynak"
    kaynak.mkdir()
    _git("init", "-q", "-b", "main", ".", cwd=kaynak)
    hedef = kaynak / "deploy"
    hedef.mkdir()
    (hedef / "docker-compose.prod.yml").write_text('RADAR_WINDOW_DAYS: "2"\n')
    _git("add", "-A", cwd=kaynak)
    _git("commit", "-qm", "eski", cwd=kaynak)
    eski = _git("rev-parse", "HEAD", cwd=kaynak)
    (hedef / "docker-compose.prod.yml").write_text('RADAR_WINDOW_DAYS: "14"\n')
    _git("add", "-A", cwd=kaynak)
    _git("commit", "-qm", "yeni", cwd=kaynak)
    yeni = _git("rev-parse", "HEAD", cwd=kaynak)

    ops = tmp_path / "ops"
    _git("clone", "-q", str(kaynak), str(ops), cwd=tmp_path)
    _git("checkout", "-q", "-B", "main", eski, cwd=ops)
    return ops, eski, yeni


def _ops_sync_kos(tmp_path: Path, *, ops_dir: str, sha: str) -> subprocess.CompletedProcess:
    """`ops_sync` adiminin run govdesini GERCEKTEN kosturur (GitHub'in Linux
    runner kabugu: `bash --noprofile --norc -eo pipefail`)."""
    betik = tmp_path / "ops_sync.sh"
    betik.write_text(_ops_sync_step()["run"])
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(betik)],
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", str(tmp_path)),
            "OPS_CHECKOUT_DIR": ops_dir,
            "SHA": sha,
        },
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_ops_sync_govdesi_bayat_checkoutu_gercekten_ileri_sarar(tmp_path):
    """EN DEGERLI TEST: govde gercek bir git deposunu GERCEKTEN tazeler.
    #349'un tam senaryosu — ops checkout'u eski commit'te (compose "2"),
    deploy edilen SHA yeni commit ("14")."""
    ops, eski, yeni = _iki_commitli_depo(tmp_path)
    assert 'RADAR_WINDOW_DAYS: "2"' in (ops / "deploy" / "docker-compose.prod.yml").read_text()

    res = _ops_sync_kos(tmp_path, ops_dir=str(ops), sha=yeni)

    assert res.returncode == 0, res.stdout + res.stderr
    assert _git("rev-parse", "HEAD", cwd=ops) == yeni, "checkout ileri sarilmadi"
    assert 'RADAR_WINDOW_DAYS: "14"' in (
        ops / "deploy" / "docker-compose.prod.yml"
    ).read_text(), "Dosya icerigi tazelenmedi -- bir sonraki elle komut hala bayat"
    assert "::notice::" in res.stdout and eski[:7] in res.stdout


def test_ops_sync_govdesi_degisken_bossa_gorunur_uyariyla_gecer(tmp_path):
    res = _ops_sync_kos(tmp_path, ops_dir="", sha="deadbeef")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "::warning::" in res.stdout, res.stdout


def test_ops_sync_govdesi_git_olmayan_dizinde_fail_closed(tmp_path):
    ciplak = tmp_path / "ciplak"
    ciplak.mkdir()
    res = _ops_sync_kos(tmp_path, ops_dir=str(ciplak), sha="deadbeef")
    assert res.returncode == 1, res.stdout + res.stderr
    assert "::error::" in res.stdout


def test_ops_sync_govdesi_yerel_degisiklikte_sessizce_ezmez_kirmizi_verir(tmp_path):
    """Calisma agacinda ELLE degistirilmis bir compose varsa ff-merge o
    dosyanin uzerine yazamaz. Dogru davranis: SESSIZCE ezmek de degil,
    yesil donmek de degil -- gorunur bir hata."""
    ops, _eski, yeni = _iki_commitli_depo(tmp_path)
    (ops / "deploy" / "docker-compose.prod.yml").write_text('RADAR_WINDOW_DAYS: "999"\n')

    res = _ops_sync_kos(tmp_path, ops_dir=str(ops), sha=yeni)

    assert res.returncode == 1, res.stdout + res.stderr
    assert "::error::" in res.stdout
    assert (
        'RADAR_WINDOW_DAYS: "999"' in (ops / "deploy" / "docker-compose.prod.yml").read_text()
    ), "Operatorun yerel dosyasi sessizce ezilmis (reset --hard davranisi)."


# ===========================================================================
# 6. Nobet workflow'u — zarar iki deploy ARASINDA olusur
# ===========================================================================


def test_nobet_periyodik_ve_elle_tetiklenebilir():
    tetikleyiciler = NOBET.get("on", NOBET.get(True, {}))
    assert "schedule" in tetikleyiciler, (
        "config-drift.yml periyodik DEGIL -- #349'un zarari iki deploy ARASINDA "
        "olustu (uc gun kimse gormedi); yalniz deploy-anindaki kontrol yetmez."
    )
    assert "workflow_dispatch" in tetikleyiciler


def test_nobet_prod_kutusunda_kosar_ve_ayni_scripti_cagirir():
    job = NOBET["jobs"]["drift"]
    runs_on = [str(x).lower() for x in job["runs-on"]]
    assert "self-hosted" in runs_on and "ensemble-prod" in runs_on, (
        f"runs-on={job['runs-on']!r} -- /health hicbir AYAR degeri dondurmuyor "
        "(olculdu), bu drift sinifi DISARIDAN olculemez."
    )
    govdeler = " ".join(s.get("run", "") for s in _steps(job))
    assert "scripts/config_drift.py" in govdeler, (
        "Nobet, deploy.yml ile AYNI script'i cagirmiyor -- iki ayri olcum tanimi "
        "birbirinden kayar."
    )


def test_nobet_deploy_enabled_kapisina_bagli_ve_deploy_ile_ayni_kuyrukta():
    job = NOBET["jobs"]["drift"]
    assert "needs.preflight.outputs.has_target" in str(job.get("if", "")), (
        "Nobet `vars.DEPLOY_ENABLED` kapisina bagli degil."
    )
    hedef_govde = " ".join(s.get("run", "") for s in _steps(NOBET["jobs"]["preflight"]))
    assert "DEPLOY_ENABLED" in hedef_govde
    assert NOBET.get("concurrency", {}).get("group") == DEPLOY.get("concurrency", {}).get(
        "group"
    ), (
        "Nobet, deploy ile AYNI concurrency grubunda degil -- suren bir deploy'un "
        "ortasinda olcum yapip yanlis kirmizi verebilir."
    )


def test_nobet_hicbir_sey_degistirmez():
    """Nobet DOGRULAYICIDIR: prod'a hicbir sey uygulamaz."""
    govdeler = " ".join(s.get("run", "") for s in _steps(NOBET["jobs"]["drift"]))
    for yasak in ("up -d", "docker tag", "docker rmi", "git merge", "git pull"):
        assert yasak not in govdeler, f"Nobet govdesinde durum degistiren komut: {yasak!r}"


# ===========================================================================
# 7. Runbook — elle komutlar `pull` tasir, olmayan yolu onermez
# ===========================================================================


def _runbook_kod_bloklari() -> list[str]:
    """Runbook'un ``` ile cevrili kod bloklarini dondurur."""
    metin = RUNBOOK_PATH.read_text(encoding="utf-8")
    parcalar = metin.split("```")
    # 1., 3., 5., ... parcalar cit ICI (acilis dili satiri dahil).
    return parcalar[1::2]


def test_runbook_up_d_koşan_HER_blok_checkoutu_tazeleyen_bir_git_komutu_tasir():
    """MUTASYON-DIRENCLI kilit: "dokumanin bir yerinde `pull` geciyor" YETMEZ
    (o test totolojiktir -- bir bloktan silinse bile digerleri yuzunden yesil
    kalir). Burada `docker compose ... up -d` KOSAN HER kod blogunun, AYNI
    blok icinde checkout'u tazeleyen bir git komutu (`pull --ff-only` ya da
    rollback yolundaki `fetch` + `checkout <sha>`) tasidigi dogrulanir.

    #349'un teslim yolu tam olarak buydu: komut dogruydu, KOSTUGU AGAC
    bayatti."""
    def _up_d_kosuyor(blok: str) -> bool:
        """Yorum satirlari elenir -- `# ... up -d ...` diye ANLATAN bir blok
        prod'u yeniden YARATMAZ."""
        return any(
            "docker compose" in satir and "up -d" in satir and not satir.strip().startswith("#")
            for satir in blok.splitlines()
        )

    bloklar = [b for b in _runbook_kod_bloklari() if _up_d_kosuyor(b)]
    assert bloklar, "Runbook'ta `up -d` KOSAN hic kod blogu yok (test kurulumu bozuk)."
    for blok in bloklar:
        assert "pull --ff-only" in blok or ("git fetch" in blok and "git checkout" in blok), (
            "Bu kod blogu prod'u yeniden yaratiyor ama checkout'u tazeleyen bir git "
            f"komutu TASIMIYOR -- #349 aynen tekrarlanir:\n{blok.strip()[:400]}"
        )


def test_runbook_elle_komut_oncesi_pull_adimini_ve_gerekcesini_tasir():
    metin = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "pull --ff-only" in metin, (
        "Runbook elle compose komutlarindan once `pull --ff-only` demiyor -- "
        "#349'un teslim yolu hala belgesiz."
    )
    assert "#349" in metin, "Runbook'ta gerekce (issue referansi) yok."
    assert "73 commit" in metin, (
        "Runbook olculmus zarari anlatmiyor -- gerekcesiz bir adim ilk aceleci "
        "operator tarafindan atlanir."
    )
    assert "config_drift.py" in metin, "Runbook drift kilidini hic anlatmiyor."


def test_runbook_sunucuda_bulunmayan_opt_ensemble_yolunu_onermez():
    """Olculdu (30 Tem): `ls -ld /opt/ensemble` -> "No such file or directory".
    Runbook'un `cd /opt/ensemble && ...` satirlari KOPYALANINCA patliyordu --
    "elle komut yanlis dizinde kosuyor" ayni hastaligin baska bir yuzu."""
    metin = RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "/opt/ensemble" not in metin, (
        "Runbook hala /opt/ensemble diyor -- o dizin sunucuda YOK."
    )


def test_runbook_exec_komutlari_prod_manifestine_sabitlenir():
    """`docker compose exec` bir manifeste SABITLENMEZSE Compose cwd'den
    yukari yuruyup KOK `docker-compose.yml`i bulur (Postgres'i 0.0.0.0:5432'de
    ensemble/ensemble ile YAYINLAYAN gelistirme dosyasi) -- yanlis proje,
    "no such service". Runbook `-f` ya da `COMPOSE_FILE` ile sabitlemeli.

    NOT: mevcut kilitler (`test_deploy_runbook.py` / `test_agentic_action.py`)
    `docker compose exec api python -m ...` dizgisini AYNEN arar; bu yuzden
    sabitleme `-f` ile degil `COMPOSE_FILE` ile yapilir -- iki kilit birbirini
    disarlamaz."""
    metin = RUNBOOK_PATH.read_text(encoding="utf-8")
    exec_satirlari = [
        satir.strip() for satir in metin.splitlines() if "docker compose exec" in satir
    ]
    assert exec_satirlari, "Runbook'ta hic `docker compose exec` satiri yok (test kurulumu bozuk)."
    assert "COMPOSE_FILE=docker-compose.prod.yml" in metin, (
        "Runbook'taki `docker compose exec` satirlari prod manifestine sabitlenmemis "
        f"(ne -f ne COMPOSE_FILE): {exec_satirlari}"
    )


@pytest.mark.parametrize("hedef", ["config-drift"])
def test_makefile_hedefi_ayni_scripti_cagirir(hedef):
    metin = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert f"\n{hedef}:\n" in metin, f"Makefile'da `{hedef}` hedefi yok."
    assert "scripts/config_drift.py" in metin, (
        "Makefile hedefi CD ile AYNI script'i cagirmiyor -- iki ayri olcum tanimi kayar."
    )
