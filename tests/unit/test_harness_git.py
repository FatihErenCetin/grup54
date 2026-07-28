"""`.harness/` GERÇEKTEN git'e alınmış mı? (#242)

Ölçülen boşluk: `.harness/` repoda HİÇ yoktu (git'te 0 dosya, diskte de yok) —
ama `test_harness.py`/`test_harness_validate.py`'deki testlerin TAMAMI kendi
`tmp_path` fixture'ını `FileHarnessPort(tmp_path)` ile enjekte ediyordu; hiçbiri
gerçek repo köküne bakmıyordu. Sonuç: gerçek `.harness/` silinse/hiç
eklenmese bile mevcut test suite'i yeşil kalırdı (`scripts/harness_validate.py`
da `.harness/` yoksa no-op → CI de yeşildi). Bu dosya, gerçek repo köküne
karşı (fixture/temp-root DEĞİL) çalışarak o boşluğu kapatır: `.harness/`
eksikse ya da şemayla uyuşmuyorsa CI KIRMIZI olur.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ensemble.app import create_app
from ensemble.config import Settings
from ensemble.store.models import DEFAULT_REPO_FULL_NAME, Base, TaskProjectionRow
from ensemble_shared.harness import FileHarnessPort
from scripts.harness_validate import validate_harness

# tests/unit/test_harness_git.py -> parents[2] = repo kökü (bkz. test_config.py'deki aynı desen).
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_tracked_harness_files() -> list[str]:
    """`.harness/` altında GERÇEKTEN commit'lenmiş (git-tracked) dosyaları döner.

    `git ls-files` kullanır — diskte var ama .gitignore'da/untracked kalan bir
    `.harness/` de aynı şekilde yakalanır (asıl ölçülen boşluk buydu: diskte
    onboarding sihirbazının bıraktığı dosyalar olabilir ama git'te 0 dosya).
    """
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-files", "--", ".harness"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def test_harness_dir_exists_on_disk():
    """`.harness/` gerçek repo kökünde bir dizin olarak var olmalı."""
    assert (_REPO_ROOT / ".harness").is_dir(), (
        ".harness/ repo kökünde yok — onboarding/backfill hiç çalışmamış ya da silinmiş."
    )


def test_harness_is_tracked_in_git_not_just_on_disk():
    """Asıl ölçülen boşluk: diskte olması yetmez, GIT'TE de olmalı (#242).

    `.gitignore`'a `.harness/` eklenip dosyalar yerelde bırakılırsa bu test
    kırmızı verir (tracked-file sayısı 0 kalır) — tam da bugünkü hatanın
    sessizce geri gelme yolu.
    """
    tracked = _git_tracked_harness_files()
    assert tracked, ".harness/ diskte olsa bile git'e hiç eklenmemiş (git ls-files boş döndü)."
    assert any(name.endswith("scope/sprint-3.md") for name in tracked)
    assert any(name.startswith(".harness/tasks/") for name in tracked)


def test_read_scope_sprint_3_does_not_raise_against_real_repo_root():
    """Ölçülen başlangıç durumu: `read_scope('sprint-3')` HarnessError fırlatıyordu."""
    port = FileHarnessPort(_REPO_ROOT)
    scope = port.read_scope("sprint-3")
    assert scope["type"] == "scope"
    assert scope["sprint"] == "3"
    assert scope["title"]


def test_read_tasks_is_not_empty_against_real_repo_root():
    """Ölçülen başlangıç durumu: `read_tasks()` boş liste dönüyordu."""
    port = FileHarnessPort(_REPO_ROOT)
    tasks = port.read_tasks()
    assert tasks, "tasks/ altında hiç dosya okunamadı — .harness/tasks/ boş ya da eksik."
    assert all(task["type"] == "task" for task in tasks)


def test_real_harness_front_matter_validates_clean():
    """`scripts/harness_validate.py` (CI'ın koştuğu AYNI fonksiyon) gerçek
    repo köküne karşı sıfır hata dönmeli — front-matter/şema drift'i burada
    yakalanır (bkz. `.github/workflows/harness-validate.yml`)."""
    errors = validate_harness(_REPO_ROOT)
    assert errors == []


# ---------------------------------------------------------------------------
# Tüketici-seviyesi kilit (#242 review turu 2)
#
# Yukarıdaki testler yalnız "type/sprint/title truthy" diye bakıyordu — scope
# dosyası şema-geçerli ama `status: draft`'a düşse, `goals` boşalsa ya da
# dosyanın kendisi silinse bile YEŞİL kalırlardı (front-matter hâlâ
# `type=scope, sprint='3', title=...` taşır). Bu üç sinyal gerçek TÜKETİCİYİ
# (HTTP üzerinden `ScopeService`/uygulama açılışı) hiç kırmaz. Aşağıdaki
# testler GERÇEK repo köküne karşı gerçek `TestClient` ile uçtan uca çalışır
# ve dört mutasyonun HEPSİNİN gerçekten bir şeyi kırdığını kanıtlar (PR
# gövdesinde gerçek pytest çıktısıyla raporlanır):
#   M1 status: frozen -> draft         -> GET /scope/current 503 döner
#   M2 goals listesi boşaltılır         -> GET /scope/current 503 döner
#   M3 .harness/scope/sprint-3.md silinir -> uygulama AÇILAMAZ (RuntimeError)
#   M4 Dockerfile'daki `.harness` COPY satırı silinir -> Dockerfile kilidi kırılır
#
# M1-M3 gerçek COMMIT'LENMİŞ dosyayı BOZMAZ: `.harness/scope/sprint-3.md`
# tmp bir köke KOPYALANIR, mutasyon o kopyada uygulanır, `monkeypatch.chdir`
# ile süreç o kökten çalışır (`FileHarnessPort()` varsayılan kökü "." —
# yani cwd — olduğu için bu, gerçek dosyayı hiç değiştirmeden gerçek
# içerikle başlayıp mutasyona uğratmayı sağlar).
# ---------------------------------------------------------------------------


def _tmp_root_with_real_scope_copy(tmp_path: Path) -> Path:
    dest_dir = tmp_path / ".harness" / "scope"
    dest_dir.mkdir(parents=True)
    shutil.copy(_REPO_ROOT / ".harness" / "scope" / "sprint-3.md", dest_dir / "sprint-3.md")
    # #242 review turu 3: `_verify_harness_boot` artık `tasks/`/`active/`
    # dizinlerinin VARLIĞINI da kontrol ediyor (bkz. aşağıdaki N1-N3 testleri).
    # M1-M3 yalnız scope mutasyonlarını ölçtüğü için bu iki dizin BOŞ ama VAR
    # olmalı - yoksa açılış, ölçülmek istenen scope hatasından ÖNCE
    # tasks/active eksikliğinden patlar (yanlış nedenden kırmızı test).
    (tmp_path / ".harness" / "tasks").mkdir(parents=True)
    (tmp_path / ".harness" / "active").mkdir(parents=True)
    return tmp_path


def _tmp_root_with_full_real_harness_copy(tmp_path: Path) -> Path:
    """M1-M3'ün aksine (yalnız `scope/sprint-3.md` kopyalar) BÜTÜN gerçek
    `.harness/` ağacını (tasks/, active/ dahil) tmp köke kopyalar — aşağıdaki
    N1-N3 mutasyonları `tasks/`/`active/` dizinlerinin kendisini hedef aldığı
    için gerçek içerikle başlamaları gerekir."""
    shutil.copytree(_REPO_ROOT / ".harness", tmp_path / ".harness")
    return tmp_path


def test_scope_current_e2e_gercek_repo_kokunde_200_ve_anlamli_govde_doner(tmp_path, monkeypatch):
    """Gerçek `.harness/scope/sprint-3.md`'ye karşı, gerçek `TestClient` ile:
    `GET /scope/current` 200 dönmeli ve gövde anlamlı olmalı (boş/placeholder
    değil).

    `monkeypatch.chdir(_REPO_ROOT)` KASITLI: `_build_scope_service` ->
    `FileHarnessPort()` varsayılan kökü `"."` (yani CWD) kullanır — bu test
    "gerçek repo kökü" dediği şeyi CWD üzerinden ölçer, `_REPO_ROOT`'u hesaba
    katar ama pin'lemezse pytest nereden çağrıldığına göre (örn. `cd tests &&
    pytest ...`) 500/RuntimeError ile YANLIŞ yerden kırılır (#242 review turu
    3 — testin kendi docstring'i "gerçek repo kökü" diyordu ama bunu
    GARANTİLEMİYORDU, CI'nin repo kökünden koşması yüzünden gizliden yeşildi)."""
    monkeypatch.chdir(_REPO_ROOT)
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{tmp_path / 'scope-e2e.db'}")
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/scope/current")

    assert response.status_code == 200
    body = response.json()
    assert body["goal"]
    assert body["in_scope"]
    assert body["commit_sha"]
    assert body["version"]


def test_board_e2e_on_kosullari_kendisi_kurup_200_doner(tmp_path, monkeypatch):
    """`GET /board` — ön koşul (DB tabloları) TESTİN KENDİSİ tarafından
    kurulur (`Base.metadata.create_all`, `test_board_router.py` ile aynı
    desen). Belgelenmemiş ön koşul için bkz. `.harness/README.md` §9.

    `monkeypatch.chdir(_REPO_ROOT)` KASITLI (yukarıdaki scope e2e testiyle
    AYNI gerekçe): `create_app` lifespan'ı içinde `_verify_harness_boot` HER
    ZAMAN çalışır — CWD repo kökü olmazsa bu test `/board`'a hiç ulaşmadan
    açılışta patlar (#242 review turu 3)."""
    monkeypatch.chdir(_REPO_ROOT)
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{tmp_path / 'board-e2e.db'}")
    app = create_app(settings)

    with TestClient(app) as client:
        engine = app.state.session_factory.kw["bind"]
        Base.metadata.create_all(engine)
        with app.state.session_factory() as session:
            session.add(
                TaskProjectionRow(
                    task_id="T-242",
                    repo_full_name=DEFAULT_REPO_FULL_NAME,
                    title="e2e board",
                    status="todo",
                )
            )
            session.commit()

        response = client.get("/board")

    assert response.status_code == 200
    assert len(response.json()["cards"]) == 1
    assert response.json()["cards"][0]["task_id"] == "T-242"


def test_m1_scope_status_draft_kirar_scope_current_503(tmp_path, monkeypatch):
    """MUTASYON M1: `status: frozen` -> `status: draft`. Dosya hâlâ
    okunabilir/şema-geçerli (yalnız `type/sprint/title` bakan eski kilit bunu
    YAKALAMAZDI) ama `ScopeService.get_current_scope` artık 503 döner."""
    root = _tmp_root_with_real_scope_copy(tmp_path)
    port = FileHarnessPort(root)
    scope = port.read_scope("3")
    assert scope["status"] == "frozen", "beklenmeyen başlangıç durumu — mutasyon anlamsız olur"
    scope.pop("path", None)
    scope["status"] = "draft"
    port.write_scope("3", scope)

    monkeypatch.chdir(root)
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{root / 'm1.db'}")
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/scope/current")

    assert response.status_code == 503
    assert response.json()["error"] == "scope_unavailable"


def test_m2_scope_goals_bosaltilinca_scope_current_503(tmp_path, monkeypatch):
    """MUTASYON M2: `goals: []`. `in_scope` boşalır — `ScopeCurrent` şeması
    (`min_length=1`) ve `get_current_scope`'un açık kontrolü 503 üretir.
    Eski kilit (`type/sprint/title` truthy) `goals` alanına hiç bakmadığı
    için bunu YAKALAMAZDI."""
    root = _tmp_root_with_real_scope_copy(tmp_path)
    port = FileHarnessPort(root)
    scope = port.read_scope("3")
    assert scope["goals"], "beklenmeyen başlangıç durumu — mutasyon anlamsız olur"
    scope.pop("path", None)
    scope["goals"] = []
    port.write_scope("3", scope)

    monkeypatch.chdir(root)
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{root / 'm2.db'}")
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/scope/current")

    assert response.status_code == 503
    assert response.json()["error"] == "scope_unavailable"


def test_m3_scope_dosyasi_silinince_acilis_fail_closed_coker(tmp_path, monkeypatch):
    """MUTASYON M3: `.harness/scope/sprint-3.md` tamamen silinir — tam da
    üretimde bind-mount'un boş dizin maskelemesiyle aynı belirti
    (`read_scope` `HarnessError` fırlatır). Fail-closed açılış kontrolü
    (`ensemble.app._verify_harness_boot`, #242 BLOCKER 1b) bunu 503'e
    DEĞİL, uygulamanın hiç ayağa kalkmamasına çevirir."""
    root = _tmp_root_with_real_scope_copy(tmp_path)
    (root / ".harness" / "scope" / "sprint-3.md").unlink()

    monkeypatch.chdir(root)
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{root / 'm3.db'}")
    app = create_app(settings)

    with pytest.raises(RuntimeError, match="ACILIS DURDURULDU"):
        with TestClient(app):
            pass


# ---------------------------------------------------------------------------
# ACIK 1 (#242 review turu 3) — `_verify_harness_boot` yalnız `scope/`
# okuyordu; `tasks/`/`active/` dizinlerinin KENDİSİ host bind-mount'un
# maskelemesiyle yok olsa bile `read_tasks()`/`read_active()` bunu "0 açık
# task/aktif beyan var" ile ayırt edilemez şekilde sessizce `[]` döndürüyordu
# (#242'nin asıl semptomu — BOŞ BOARD — daha dar bir biçimde HAYATTA
# kalıyordu). Aşağıdaki üç mutasyon bu ayrımın (dizin-yok vs dizin-var-ama-
# boş) doğru tarafta çalıştığını kanıtlar; dördüncü mutasyon (N4) kalıcı bir
# test DEĞİL — bütünlük kontrolünün kendisinin LOAD-BEARING olduğunu (N1'i o
# olmadan KIRAMAYACAĞINI) kanıtlamak için `_verify_harness_boot`'taki
# tasks/active döngüsü GEÇİCİ olarak kaldırılıp N1 tekrar koşturuldu, gerçek
# pytest çıktısı PR gövdesinde raporlandı, sonra kod geri alındı.
#   N1 tasks/ dizini tamamen kaldırılır  -> açılış DURMALI
#   N2 active/ dizini tamamen kaldırılır -> açılış DURMALI
#   N3 tasks/ dizini VAR ama içi boşaltılır -> açılış DURMAMALI (yanlış pozitif kontrolü)
# ---------------------------------------------------------------------------


def test_n1_tasks_dizini_yok_olunca_acilis_fail_closed_coker(tmp_path, monkeypatch):
    """MUTASYON N1: `.harness/tasks/` dizininin KENDİSİ tamamen kaldırılır —
    host bind-mount'un onu hiç kopyalamadığı senaryo. `read_tasks()` bunu
    SESSİZCE `[]` döner (dizin-yok ile dizin-var-ama-boş ayrımını yapmaz) —
    #242'nin asıl semptomu (BOŞ BOARD) bu dar biçimde hayattaydı.
    `_verify_harness_boot`'un `verify_dir_readable("tasks")` çağrısı bunu artık
    açılışta yakalayıp süreci hiç ayağa kaldırmamalı."""
    root = _tmp_root_with_full_real_harness_copy(tmp_path)
    shutil.rmtree(root / ".harness" / "tasks")

    monkeypatch.chdir(root)
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{root / 'n1.db'}")
    app = create_app(settings)

    with pytest.raises(RuntimeError, match="ACILIS DURDURULDU"):
        with TestClient(app):
            pass


def test_n2_active_dizini_yok_olunca_acilis_fail_closed_coker(tmp_path, monkeypatch):
    """MUTASYON N2: `.harness/active/` dizininin KENDİSİ tamamen kaldırılır —
    N1 ile AYNI bind-mount maskeleme senaryosu, `active/` için. `read_active()`
    de aynı şekilde sessizce `[]` döner; bütünlük kontrolü bunu da ayrı ayrı
    yakalamalı (N1'i geçmek N2'yi garanti etmez — iki ayrı `verify_dir_readable`
    çağrısı var, biri diğerini maskeleyebilirdi)."""
    root = _tmp_root_with_full_real_harness_copy(tmp_path)
    shutil.rmtree(root / ".harness" / "active")

    monkeypatch.chdir(root)
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{root / 'n2.db'}")
    app = create_app(settings)

    with pytest.raises(RuntimeError, match="ACILIS DURDURULDU"):
        with TestClient(app):
            pass


def test_n3_tasks_dizini_bos_ama_var_acilis_durmaz_yanlis_pozitif_olmaz(tmp_path, monkeypatch):
    """MUTASYON N3: `.harness/tasks/` dizini VAR ama içindeki TÜM dosyalar
    silinir (hiç açık task olmama durumu — MEŞRU). N1'in tam tersi: dizin
    var-ama-boş olduğunda açılış DURMAMALI (yanlış pozitif kontrolü — N1/N2
    testlerinin gerçekten "dizin yok" durumunu ölçtüğünü, "dizin boş"
    durumuyla karıştırmadığını kanıtlar)."""
    root = _tmp_root_with_full_real_harness_copy(tmp_path)
    tasks_dir = root / ".harness" / "tasks"
    for path in tasks_dir.glob("*.md"):
        path.unlink()
    assert list(tasks_dir.iterdir()) == [], (
        "beklenmeyen başlangıç durumu — dizin hâlâ dosya taşıyor, mutasyon anlamsız olur"
    )

    monkeypatch.chdir(root)
    settings = Settings(_env_file=None, DATABASE_URL=f"sqlite:///{root / 'n3.db'}")
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/scope/current")

    assert response.status_code == 200


# --- M4: Dockerfile kilidi (statik — gerçek `docker build` PR gövdesinde
# ayrıca elle doğrulandı, bkz. rapor) ---


def test_dockerfile_harness_klasorunu_builder_asamasina_copy_eder():
    """MUTASYON M4: bu satır (`COPY .harness/ .harness/`) Dockerfile'dan
    silinirse üretim imajında `/app/.harness` HİÇ olmaz — `read_scope`/
    `read_tasks` konteynerde her zaman başarısız olur, fail-closed açılış
    kontrolü HER açılışta patlar (#242 BLOCKER 1a). Gerçek `docker build` ile
    doğrulandı: satır varken `/app/.harness/tasks` 22 dosya taşıyor, satır
    silinince `/app/.harness` hiç oluşmuyor."""
    dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    builder_stage, _, runtime_stage = dockerfile.partition("FROM python:3.12-slim AS runtime")

    assert "COPY .harness/ .harness/" in builder_stage, (
        ".harness/ builder aşamasına COPY edilmiyor — üretim imajında "
        "/app/.harness eksik kalır (#242 BLOCKER 1a)."
    )
    # Runtime aşaması builder'daki DERLENMİŞ /app'i olduğu gibi taşır — ayrı
    # bir .harness COPY'sine gerek yok, ama bu satır kaza ile silinip runtime
    # aşamasına yanlışlıkla eklenmiş olabilir; asıl kaynak builder'da olmalı.
    assert "COPY --from=builder" in runtime_stage


def test_dockerignore_harness_i_dislamaz():
    """`.dockerignore`'a `.harness/` (ya da `.harness`) eklenirse yukarıdaki
    COPY satırı no-op'a düşer (build context'te dosya hiç yok) — bu da aynı
    BLOCKER 1a semptomunu üretir, sessizce."""
    dockerignore = (_REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    active_lines = [
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert not any(line in (".harness", ".harness/") for line in active_lines), (
        ".dockerignore artık .harness/'i dışlıyor — Dockerfile'daki COPY "
        "satırı sessizce no-op'a düşer (build context'e .harness hiç girmez)."
    )
