# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Ensemble masaüstü paketi (T-305).

Çalıştırma: repo kökünden
    uv run --with-requirements packaging/requirements-build.txt \
        pyinstaller packaging/ensemble.spec --noconfirm \
        --distpath packaging/dist-macos --workpath packaging/build-macos

(`packaging/build_macos.sh` bunu sarmalar; bkz. o script + `make paket-macos`.)

Neyi neden topluyoruz:
  - `ensemble` + `ensemble_shared` paketleri: proje kodu, workspace'te editable
    kurulu (`uv sync`) — PyInstaller import analiziyle otomatik bulur.
  - `store/migrations/**`, VERİ olarak (`--add-data`): alembic `versions/*.py`
    ve `env.py`'yi NORMAL import ile değil, `ScriptDirectory`'nin diskten
    okuyup exec ettiği dosyalar olarak kullanır — bytecode arşivine
    gömülseler alembic onları BULAMAZ (görev notundaki ölçülen risklerden
    biri buydu; gerçek çözüm burada: gerçek dosya olarak diskte durmaları).
  - `.harness/` (repo kökünden), VERİ olarak `harness_seed/.harness` adı
    altında: `ensemble.app`'in açılış kontrolü (`_verify_harness_boot`)
    `.harness/scope|tasks|active`'in OKUNABİLİR olmasını zorunlu kılar;
    `launcher.py` bunu ilk çalıştırmada kullanıcı veri dizinine kopyalar.
  - `src/shared/openapi.json` gerekmiyor (yalnızca TS client üretimi için,
    runtime'da kullanılmıyor) — DAHİL EDİLMEDİ (paket boyutu).
  - `collect_all` — google-genai (grpc/protobuf içerir), uvicorn (üvicorn
    [standard] uvloop/httptools/websockets gibi opsiyonel C-eklentileri
    hidden-import olarak KAÇIRABİLİR), alembic (kendi `templates/` veri
    dizinini import-time'da kullanır), pydantic/pydantic_settings (dynamic
    model rebuild), jsonschema (validator plugin kayıtları), argon2_cffi
    (cffi backend'i runtime'da derlenmiş .so arar).
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# NOT: PyInstaller spec dosyalarını `exec()` ile çalıştırır, `__file__`
# TANIMLI DEĞİLDİR (bkz. PyInstaller building/build_main.py) — bu yüzden
# `Path.cwd()` kullanıyoruz. `build_macos.sh` pyinstaller'ı DAİMA repo
# kökünden çağırır (`cd "$REPO_ROOT"` sonrası) — elle çalıştırırken de
# repo kökünden çağır: `pyinstaller packaging/ensemble.spec`.
REPO_ROOT = Path.cwd()
BACKEND_SRC = REPO_ROOT / "src" / "backend"
SHARED_SRC = REPO_ROOT / "src" / "shared"

block_cipher = None

datas = []
binaries = []
hiddenimports = [
    # sqlalchemy dialect'leri DATABASE_URL şemasına göre RUNTIME'da (plugin
    # sistemiyle) seçiliyor — statik import analizi bunları göremez.
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    "sqlalchemy.dialects.postgresql",
    "sqlalchemy.dialects.postgresql.psycopg",
    "psycopg",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]

# `collect_all` bu paketlerin kendi test/benchmark/mypy-plugin alt paketlerini
# de topluyor (ölçüldü: ilk deneme 75M .app / 37M .dmg üretti — google.genai.
# tests.*, jsonschema.tests.*/benchmarks.*, alembic.testing.* runtime'da HİÇ
# kullanılmıyor). `_is_test_noise` bunları datas/hiddenimports'tan ELER —
# gerçek paket verisini (schemas, templates, .so uzantıları) DOKUNMADAN bırakır.
_NOISE_MARKERS = (".tests.", ".test_", ".benchmarks.", ".testing.", ".mypy", "_hypothesis_plugin")


def _is_test_noise(dotted_or_path: str) -> bool:
    normalized = f".{dotted_or_path.replace('/', '.').replace(chr(92), '.')}."
    return any(marker in normalized for marker in _NOISE_MARKERS)


for pkg in (
    "uvicorn",
    "google.genai",
    "alembic",
    "pydantic",
    "pydantic_settings",
    "jsonschema",
    "argon2",
    "argon2_cffi_bindings",
):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    except Exception:  # noqa: BLE001 — opsiyonel paket build makinesinde yoksa atla
        continue
    datas += [d for d in pkg_datas if not _is_test_noise(d[1])]
    binaries += pkg_binaries
    hiddenimports += [h for h in pkg_hidden if not _is_test_noise(h)]

# --- Alembic migration dosyaları — GERÇEK DOSYA olarak (bkz. modül docstring'i) ---
datas.append((str(BACKEND_SRC / "ensemble" / "store" / "migrations"), "ensemble/store/migrations"))

# --- ensemble_shared JSON şemaları — `importlib.resources.files("ensemble_shared")
# .joinpath("schemas")` (bkz. src/shared/ensemble_shared/harness.py::_validator)
# paket VERİSİDİR, kod değil — normal Analysis import taraması bunları BULMAZ
# (yalnız .py/.pyc toplar). Eksik kalırsa açılış `.harness/scope/...`'u schema
# doğrularken "Harness schema not found" ile ÇÖKER (bu paketleme turunda
# GERÇEKTEN ölçülen hata — bkz. görev raporu).
datas.append((str(SHARED_SRC / "ensemble_shared" / "schemas"), "ensemble_shared/schemas"))

# --- .harness/ tohum kopyası — ilk çalıştırmada kullanıcı veri dizinine kopyalanır ---
#
# NEDEN `REPO_ROOT / ".harness"` DEĞİL (ölçüldü, 30 Tem — #340 doğrulama turu):
# paket eskiden GELİŞTİRİCİ REPOSUNUN kendi `.harness/`'ini tohumluyordu, yani
# grup54'ün donmuş `scope/sprint-3.md`'si, 22 görev dosyası ve karar kayıtları
# yeni kullanıcının başlangıç durumu oluyordu. İki somut zarar:
#   1) Kullanıcı BAŞKA bir projenin iç durumunu kendi projesi sanıyordu.
#   2) Onboarding sihirbazı 3 sprintlik plan yazmak istediğinde
#      `scope/sprint-3.md` zaten var olduğu için TÜM yazma 409 ile
#      reddediliyordu — sihirbaz paketlenmiş uygulamada hiç çalışamıyordu.
#      (Reddetmenin kendisi doğru: var olan kapsamı sessizce ezmek kullanıcının
#      işini kaybettirirdi. Yanlış olan tohumun DOLU olmasıydı.)
#
# `_verify_harness_boot`'un istediği tek şey klasörlerin OKUNABİLİR olması;
# boş `scope/tasks/active` meşru bir durumdur ve hata üretmez. Bu yüzden tohum
# artık `packaging/harness_seed/` altındaki BOŞ iskelet.
datas.append((str(REPO_ROOT / "packaging" / "harness_seed" / ".harness"), "harness_seed/.harness"))

# --- Frontend production build — build_macos.sh `npm run build` ile üretir ---
frontend_dist = REPO_ROOT / "src" / "frontend" / "dist"
if frontend_dist.is_dir():
    datas.append((str(frontend_dist), "frontend_dist"))

a = Analysis(
    [str(REPO_ROOT / "packaging" / "launcher.py")],
    pathex=[str(BACKEND_SRC), str(SHARED_SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "ruff"],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ensemble",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Ensemble",
)

app = BUNDLE(
    coll,
    name="Ensemble.app",
    icon=str(REPO_ROOT / "packaging" / "AppIcon.icns")
    if (REPO_ROOT / "packaging" / "AppIcon.icns").is_file()
    else None,
    bundle_identifier="com.grup54.ensemble",
    version="0.0.1",
    info_plist={
        "CFBundleName": "Ensemble",
        "CFBundleDisplayName": "Ensemble",
        "CFBundleShortVersionString": "0.0.1",
        "CFBundleVersion": "0.0.1",
        "NSHighResolutionCapable": True,
        # Uygulama menu bar'da görünsün istiyoruz (arkaplan-only ajan DEĞİL) —
        # kullanıcı Dock'tan/Cmd+Q ile kapatabilsin (LSUIElement=False, varsayılan).
        "LSUIElement": False,
        "NSHumanReadableCopyright": "grup54",
    },
)
