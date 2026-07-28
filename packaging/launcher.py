"""Ensemble masaüstü paketinin (.app) başlatıcısı (T-305).

Kullanıcı `Ensemble.app`'e çift tıkladığında PyInstaller'ın ürettiği tek
çalıştırılabilir dosya bunu import edip `main()`'i çağırır (bkz.
`packaging/ensemble.spec`). Yalnızca PAKETLENMİŞ (frozen) çalışma için
yazılmıştır — `src/backend/ensemble/**` içindeki gerçek uygulama koduna HİÇ
DOKUNMAZ; `create_app()` fabrikasını olduğu gibi çağırıp üstüne "masaüstü
paketi" kaygılarını (veri dizini · migration · port · tarayıcı) ekler.

Akış:
  1. Kullanıcı veri dizinini hazırla (`~/Library/Application Support/Ensemble/`)
     — `.app` paketinin İÇİNE yazmayız (salt-okunur sayılır + imzayı bozar).
  2. Paketlenmiş `.harness/` iskeletini (yalnızca ilk çalıştırmada) veri
     dizinine kopyala — `FileHarnessPort(root=".")` cwd'den okur, bu yüzden
     çalışma dizinini veri dizinine çeviriyoruz (bkz. `_chdir_to_data_dir`).
  3. `DATABASE_URL` vb. ortam değişkenlerini veri dizinini gösterecek şekilde
     ayarla (ensemble.config.Settings ilk okunmadan ÖNCE — `get_settings()`
     `lru_cache`'li, tek sefer okunur).
  4. Alembic migration'ı BAŞLIK OLARAK (programatik `Config`, ini dosyasız)
     bundled migration dizinine karşı koştur — koşmadan `/board` `/events`
     `/graph` 500 döner (ölçüldü, bkz. görev notu).
  5. `ensemble.app.create_app()`'i çağır; kök path'te (`/`) zaten bir route
     yoksa (bkz. `_frontend_already_served`) paketlenmiş frontend `dist/`'ini
     `StaticFiles(html=True)` ile aynı porta ekle — iki senaryoda da (backend
     kendisi frontend'i servis ediyor / etmiyor) TEK port sonucu.
  6. Boş olduğu doğrulanmış bir portta uvicorn'u ARKA PLAN THREAD'İNDE başlat,
     `/health`'i yoklayarak hazır olmasını bekle (sabit `sleep` YOK), sonra
     varsayılan tarayıcıyı aç.
  7. Ana thread uvicorn sunucusunu (foreground) çalıştırmaya devam eder;
     pencere kapanınca (macOS'ta Cmd+Q / Dock'tan çıkış) süreç düzgün sonlanır.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "Ensemble"
# Sabit tercih edilen port: frontend `dist/` build-time'da BU porta karşı
# derlenir (`VITE_API_BASE_URL`, bkz. build_macos.sh) — Vite ortam
# değişkenleri DERLEME ANINDA JS'e gömülür (runtime'da değiştirilemez,
# `src/frontend/src/lib/config.ts` buna göre yazılmış). Bu yüzden portu
# rastgele seçmiyoruz: sabit bir port + "zaten benim bir kopyam mı çalışıyor"
# kontrolü + "başka biri mi tutuyor" hata mesajı — `find_free_port()` yerine
# `_resolve_port()` (bkz. aşağı) tam bunu yapar.
PREFERRED_PORT = 8756
HEALTH_TIMEOUT_S = 30.0
HEALTH_POLL_INTERVAL_S = 0.2

logger = logging.getLogger("ensemble.launcher")


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_dir() -> Path:
    """PyInstaller'ın data dosyalarını açtığı kök (`sys._MEIPASS`).

    Frozen değilken (örn. `python packaging/launcher.py` ile elle test) repo
    kökünü döner — geliştirme sırasında da aynı script çalıştırılabilsin diye.
    """
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS"))  # noqa: B009 — PyInstaller runtime attr
    return Path(__file__).resolve().parents[1]


def _data_dir() -> Path:
    """Kullanıcı veri dizini — SQLite + kopyalanmış `.harness/` burada yaşar.

    `.app` paketinin İÇİNE yazmıyoruz: macOS Gatekeeper/codesign imzalı (ya da
    imzasız ama Gatekeeper'ın izlediği) bir `.app`'in içeriği DEĞİŞTİRİLİRSE
    imza bozulur ve sonraki her açılışta yeni bir uyarı/hata riski doğar; ayrıca
    `.app` içi genelde salt-okunur bir birim gibi ele alınmalı (App Translocation
    vb.). Bu yüzden tüm YAZILABİLİR durum `~/Library/Application Support/`
    altında, paket dizini dışındadır.
    """
    return Path.home() / "Library" / "Application Support" / APP_NAME


def _configure_logging(data_dir: Path) -> None:
    log_path = data_dir / "ensemble.log"
    handlers: list[logging.Handler] = [logging.FileHandler(log_path, encoding="utf-8")]
    if not _is_frozen():
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
    )
    logger.info("Ensemble başlatıcı başladı (frozen=%s, log=%s)", _is_frozen(), log_path)


def _seed_harness(data_dir: Path, bundle_dir: Path) -> None:
    """`.harness/` iskeletini yalnızca YOKSA veri dizinine kopyala.

    `ensemble.app.lifespan`'daki `_verify_harness_boot` açılışta
    `.harness/scope/sprint-<N>.md` + `.harness/tasks/` + `.harness/active/`
    dizinlerinin OKUNABİLİR olmasını ZORUNLU kılar (yoksa uygulama hiç
    ayağa kalkmaz — bkz. o fonksiyonun docstring'i). `FileHarnessPort()`
    varsayılan `root="."` kullanır, yani sürecin ÇALIŞMA DİZİNİNDEN okur —
    bu yüzden hem burada bir kopya tutuyoruz HEM DE `main()` içinde `cwd`'yi
    veri dizinine çeviriyoruz (bkz. `_chdir_to_data_dir`).

    Zaten varsa DOKUNMAZ (kullanıcı kendi `.harness/`'ini elle düzenlemiş
    olabilir — sürüm yükseltmesinde üzerine yazmak veri kaybı riski taşır).
    """
    dest = data_dir / ".harness"
    if dest.exists():
        logger.info(".harness/ zaten var (%s) — tohumlama atlandı.", dest)
        return
    src = bundle_dir / "harness_seed" / ".harness"
    if not src.is_dir():
        raise RuntimeError(
            f"Pakette .harness/ tohum dizini bulunamadı ({src}). "
            "packaging/ensemble.spec içindeki harness_seed veri girdisini kontrol et."
        )
    shutil.copytree(src, dest)
    logger.info(".harness/ tohumlandı: %s -> %s", src, dest)


def _migrations_dir(bundle_dir: Path) -> Path:
    path = bundle_dir / "ensemble" / "store" / "migrations"
    if not path.is_dir():
        raise RuntimeError(
            f"Pakette alembic migration dizini bulunamadı ({path}). PyInstaller "
            "--add-data ile migrations/ eklenmemiş olabilir (bkz. ensemble.spec)."
        )
    return path


def _run_migrations(migrations_dir: Path) -> None:
    """Alembic'i INI DOSYASI OLMADAN, programatik `Config` ile koştur.

    Alembic'in `ScriptDirectory` mekanizması `versions/*.py` dosyalarını
    DİSKTEN OKUYUP exec eder (normal `import` değil) — bu yüzden bu dosyaların
    PyInstaller'ın gömülü bytecode arşivinde değil, GERÇEK dosya olarak diskte
    (`--add-data` ile kopyalanmış) durması ZORUNLUDUR. `env.py` da aynı şekilde
    diskten okunup exec edilir ve KENDİSİ `ensemble.config.get_settings()`'ten
    `DATABASE_URL`'i okuyup `sqlalchemy.url`'in üzerine yazar (bkz.
    `src/backend/ensemble/store/migrations/env.py`) — o yüzden burada
    verdiğimiz `sqlalchemy.url` yalnızca bir yer tutucudur, gerçek karar
    ortam değişkenindedir (`main()`'de migration'dan ÖNCE ayarlanır).
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    logger.info("Alembic migration başlıyor (script_location=%s)", migrations_dir)
    command.upgrade(cfg, "head")
    logger.info("Alembic migration tamamlandı (head).")


def _frontend_already_served(app) -> bool:
    """`create_app()`'in DÖNDÜRDÜĞÜ app zaten `/`'de bir route/mount taşıyor mu?

    Paralel bir çalışma backend'e `dist/`'i `StaticFiles` ile aynı porttan
    servis etme işini ekliyor olabilir (bkz. görev notu — o işe GÜVENME,
    ama inerse çakışmayı da yaratma). `app.routes` üzerinde `/` ile eşleşen
    bir `Mount`/`Route` var mı diye bakıyoruz; varsa KENDİ mount'umuzu
    EKLEMEYİZ (aksi halde iki mount aynı path'te çakışıp belirsiz sonuç
    üretebilir).
    """
    for route in app.routes:
        path = getattr(route, "path", None)
        if path in ("/", ""):
            return True
    return False


def _mount_frontend_if_needed(app, bundle_dir: Path) -> None:
    if _frontend_already_served(app):
        logger.info("Backend zaten '/' rotasını servis ediyor — ayrı static mount eklenmedi.")
        return
    dist_dir = bundle_dir / "frontend_dist"
    if not dist_dir.is_dir():
        logger.warning(
            "Pakette frontend_dist/ bulunamadı (%s) — yalnızca API servis edilecek, "
            "tarayıcıda UI görünmeyecek.",
            dist_dir,
        )
        return
    from fastapi.staticfiles import StaticFiles

    # `/` sonuna eklenir (router'lardan SONRA) — Starlette route'ları eklendiği
    # sırayla dener; `/health`, `/board` vb. daha spesifik route'lar burada
    # zaten `create_app()` içinde eklenmiş olduğu için önce onlar eşleşir,
    # yalnızca eşleşmeyen (statik dosya/SPA) istekler bu mount'a düşer.
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend_dist")
    logger.info("Frontend static mount eklendi: %s", dist_dir)


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _is_our_instance(port: int) -> bool:
    """Bu porttaki sunucu zaten BİZİM Ensemble instance'ımız mı?

    Öyleyse ikinci bir kopya başlatmak yerine yalnızca tarayıcıyı açarız
    (tek-instance davranışı — çift tıklama iki backend süreci doğurmasın).
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status == 200 and isinstance(body, dict)
    except Exception:  # noqa: BLE001 — herhangi bir hata = "bizim değil/bilinmiyor"
        return False


def _resolve_port() -> tuple[int, bool]:
    """Sabit `PREFERRED_PORT`'un durumunu çözer.

    Döner: (port, already_running). `already_running=True` ise `main()`
    yeni bir uvicorn BAŞLATMAZ, doğrudan tarayıcıyı açar.

    Rastgele boş port ARAMIYORUZ: frontend `dist/`'i build-time'da TEK bir
    porta karşı derlendiği için (`VITE_API_BASE_URL`, bkz. build_macos.sh)
    runtime'da farklı bir port seçmek frontend'i backend'ten koparır. Bunun
    yerine: (a) port zaten BİZİM instance'ımız tarafından tutuluyorsa onu
    kullan, (b) BAŞKA bir şey tutuyorsa AÇIKÇA hata ver (sessizce başka porta
    kaymak yerine — kullanıcı hangi portu boşaltacağını bilsin).
    """
    if not _port_in_use(PREFERRED_PORT):
        return PREFERRED_PORT, False
    if _is_our_instance(PREFERRED_PORT):
        logger.info("Ensemble zaten çalışıyor (port %d) — yeni süreç başlatılmayacak.", PREFERRED_PORT)
        return PREFERRED_PORT, True
    raise RuntimeError(
        f"Port {PREFERRED_PORT} başka bir uygulama tarafından kullanılıyor. "
        "Ensemble bu portu bekliyor (frontend derlemesine gömülü) — o uygulamayı "
        "kapatıp tekrar dene."
    )


def _wait_until_ready(port: int, timeout_s: float = HEALTH_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(HEALTH_POLL_INTERVAL_S)
    return False


def _open_browser_when_ready(port: int) -> None:
    if _wait_until_ready(port):
        logger.info("Backend hazır — tarayıcı açılıyor (port %d).", port)
        webbrowser.open(f"http://127.0.0.1:{port}/")
    else:
        logger.error(
            "Backend %.0f sn içinde hazır olmadı (port %d) — tarayıcı açılmadı. "
            "Log dosyasına bak: %s",
            HEALTH_TIMEOUT_S,
            port,
            _data_dir() / "ensemble.log",
        )


def main() -> int:
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    _configure_logging(data_dir)

    try:
        port, already_running = _resolve_port()
    except RuntimeError as exc:
        logger.error(str(exc))
        print(str(exc), file=sys.stderr)
        return 1

    if already_running:
        webbrowser.open(f"http://127.0.0.1:{port}/")
        return 0

    bundle_dir = _bundle_dir()
    _seed_harness(data_dir, bundle_dir)

    # `.harness/` cwd'den okunur (`FileHarnessPort(root=".")`) — çalışma
    # dizinini veri dizinine çeviriyoruz ki paket İÇİNDEKİ değil, kopyalanmış
    # (yazılabilir) `.harness/` kullanılsın.
    os.chdir(data_dir)

    db_path = data_dir / "ensemble.db"
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{db_path}")
    os.environ.setdefault("ENSEMBLE_MODE", "local")
    # Anahtar yoksa backend zaten Fake adapter'lara düşer (ölçüldü — görev
    # notu); burada bilerek zorunlu kılmıyoruz.

    try:
        _run_migrations(_migrations_dir(bundle_dir))
    except Exception:
        logger.exception("Migration başarısız — uygulama başlatılmıyor.")
        return 1

    from ensemble.app import create_app

    app = create_app()
    _mount_frontend_if_needed(app, bundle_dir)

    threading.Thread(target=_open_browser_when_ready, args=(port,), daemon=True).start()

    import uvicorn

    logger.info("uvicorn başlıyor (127.0.0.1:%d)", port)
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    finally:
        logger.info("uvicorn durdu — çıkılıyor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
