"""T-307 FAZ 3 — yerel modda `dist/` varsa backend'in KENDİSİ frontend'i
servis eder (`_mount_frontend_if_built`, `app.py`).

Üç kilit:
  1. API yolları (`/health` vb.) statik mount tarafından GÖLGELENMEZ.
  2. Bilinmeyen bir yol (SPA client-route) 404 DEĞİL, `index.html` (200) alır.
  3. Hosted modda VE `dist/` yokken mount hiç devreye GİRMEZ (regresyon yok).

Sahte bir `dist/` kullanılır (tmp_path) — gerçek `src/frontend/dist`'e
bağımlı olmadan izole test edilir.
"""

from fastapi.testclient import TestClient

from ensemble.app import _frontend_dist_dir, create_app
from ensemble.config import Settings
from ensemble.store.engine import get_engine
from ensemble.store.models import Base


def _write_fake_dist(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>spa-shell</body></html>", encoding="utf-8")
    (dist / "favicon.ico").write_bytes(b"\x00")
    return dist


def _make_app(tmp_path, monkeypatch, *, mode: str, dist_dir=None, **overrides):
    monkeypatch.setattr(
        "ensemble.app._frontend_dist_dir", lambda: dist_dir if mode == "local" else None
    )
    db_path = tmp_path / "e.db"
    # T-307 takip: mount artik ACIK bayrakla kontrol ediliyor ("dist/ var mi"
    # otomatik tespiti degil) — cunku o tespit uygulamanin davranisini
    # "birinin `npm run build` calistirip calistirmadigina" bagliyordu.
    overrides.setdefault("ENSEMBLE_SERVE_FRONTEND", dist_dir is not None)
    settings = Settings(
        _env_file=None, ENSEMBLE_MODE=mode, DATABASE_URL=f"sqlite:///{db_path}", **overrides
    )
    app = create_app(settings)
    Base.metadata.create_all(get_engine(settings))
    return app


def test_dist_yoksa_mount_hic_eklenmez_api_only_davranis_korunur(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch, mode="local", dist_dir=None)
    with TestClient(app) as client:
        resp = client.get("/bilinmeyen-bir-yol")
    assert resp.status_code == 404


def test_hosted_modda_dist_varsa_bile_mount_EKLENMEZ(tmp_path, monkeypatch):
    """D-23'ün ruhu: hosted davranışı bu FAZ'dan ETKİLENMEMELİ — Vercel
    frontend'i zaten servis ediyor."""
    dist = _write_fake_dist(tmp_path)
    app = _make_app(tmp_path, monkeypatch, mode="hosted", dist_dir=dist)
    with TestClient(app) as client:
        resp = client.get("/bilinmeyen-bir-yol")
    assert resp.status_code == 404


def test_local_dist_varken_bilinmeyen_yol_index_html_200_doner(tmp_path, monkeypatch):
    """Gerçek SPA fallback: 404 DEĞİL, `index.html` 200 ile döner (Starlette'in
    kendi `StaticFiles(html=True)`'ı YALNIZ dizin-index + 404.html bilir,
    bu davranışı VERMEZ — bkz. `_SPAStaticFiles.get_response`)."""
    dist = _write_fake_dist(tmp_path)
    app = _make_app(tmp_path, monkeypatch, mode="local", dist_dir=dist)
    with TestClient(app) as client:
        # TARAYICI gezinmesi: Accept HTML tasir. SPA fallback YALNIZ buna
        # verilir — API istemcisi (Accept: */*) durust 404 alir, yoksa
        # bulunamayan her yol 200+HTML olur ve istemci `response.ok` deyip
        # cagrinin BASARILI oldugunu sanar (fail-open, bkz. app.py
        # `_html_isteniyor`).
        resp = client.get("/ayarlar", headers={"Accept": "text/html"})
    assert resp.status_code == 200
    assert "spa-shell" in resp.text


def test_local_dist_varken_kok_index_html_doner(tmp_path, monkeypatch):
    dist = _write_fake_dist(tmp_path)
    app = _make_app(tmp_path, monkeypatch, mode="local", dist_dir=dist)
    with TestClient(app) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "spa-shell" in resp.text


def test_local_dist_varken_gercek_dosya_kendisi_donulur(tmp_path, monkeypatch):
    dist = _write_fake_dist(tmp_path)
    app = _make_app(tmp_path, monkeypatch, mode="local", dist_dir=dist)
    with TestClient(app) as client:
        resp = client.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.content == b"\x00"


def test_API_YOLLARI_STATIK_MOUNT_TARAFINDAN_GOLGELENMEZ(tmp_path, monkeypatch):
    """MUTASYON KİLİDİ: `create_app`'te `_mount_frontend_if_built(app, settings)`
    çağrısını `app.include_router(health.router, ...)`'DAN ÖNCEYE taşı →
    bu test KIRMIZI olur (`/health` artık JSON DEĞİL, `index.html` metni
    döner — görev brifinginin "statik mount'u API'den ÖNCE koy → API
    yolları gölgeleniyor → kırmızı" mutasyonunun BİREBİR kendisi)."""
    dist = _write_fake_dist(tmp_path)
    app = _make_app(tmp_path, monkeypatch, mode="local", dist_dir=dist)
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_settings_ucu_da_golgelenmez(tmp_path, monkeypatch):
    dist = _write_fake_dist(tmp_path)
    app = _make_app(tmp_path, monkeypatch, mode="local", dist_dir=dist)
    with TestClient(app) as client:
        resp = client.get("/settings/saglayici")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "local"


def test_frontend_dist_dir_gercek_repo_yapisina_gore_hesaplanir():
    """Sahte olmayan (gerçek) hesaplama — `src/frontend/dist` repoda VARSA
    (frontend ajanı build ettiyse) doğru yolu döner, yoksa `None`."""
    result = _frontend_dist_dir()
    assert result is None or (result.name == "dist" and (result / "index.html").is_file())


def test_API_istemcisi_bilinmeyen_yolda_DURUST_404_alir(tmp_path, monkeypatch):
    """FAIL-OPEN KİLİDİ: SPA fallback KOŞULSUZ olursa bulunamayan HER yol
    200 + HTML döner ve API istemcisi `response.ok` deyip çağrının BAŞARILI
    olduğunu sanar — hata bir başarıya dönüşür (D-53'ün dersi).

    Ayrım "kim soruyor": tarayıcı `Accept: text/html` gönderir, API istemcisi
    `*/*` ya da `application/json`.

    MUTASYON KİLİDİ: `_html_isteniyor` kontrolünü kaldır → bu test kırılır.
    """
    dist = _write_fake_dist(tmp_path)
    app = _make_app(tmp_path, monkeypatch, mode="local", dist_dir=dist)
    with TestClient(app) as client:
        for accept in ("*/*", "application/json"):
            resp = client.get("/boyle-bir-uc-yok", headers={"Accept": accept})
            assert resp.status_code == 404, (
                f"Accept={accept} ile 404 beklenirdi, {resp.status_code} geldi — "
                "SPA fallback API hatalarını yutuyor"
            )
            assert "spa-shell" not in resp.text, "API istemcisine HTML kabuğu dönmüş"
