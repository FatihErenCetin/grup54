"""T-307 FAZ 1 — kök `docker-compose.yml`'in (yerel TEK-KOMUT kurulumu)
yapısal değişmezlerini kilitler.

`tests/unit/test_deploy_compose.py` (`deploy/docker-compose.prod.yml`,
hosted üretim yığını) ile AYNI desen — buradaki dosya FARKLI bir amaca
(kurulum kolaylığı, anahtarsız local mod) hizmet eder, birbirinin yerini
TUTMAZ.
"""

from pathlib import Path

import yaml

COMPOSE_PATH = Path(__file__).parent.parent.parent / "docker-compose.yml"


def _load_compose() -> dict:
    assert COMPOSE_PATH.exists(), f"Compose dosyası bulunamadı: {COMPOSE_PATH}"
    doc = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "docker-compose.yml geçerli bir YAML mapping'i değil"
    return doc


def test_gecerli_yaml_ve_uc_servis():
    doc = _load_compose()
    services = doc.get("services", {})
    assert set(services) == {"migrate", "api", "frontend"}, (
        f"beklenen {{'migrate','api','frontend'}}, gerçek: {set(services)}"
    )


def test_frontend_servisi_var_bu_PRnin_asil_eksigiydi():
    """Ölçülen önceki durum: kök compose'ta yalnız db+api vardı, frontend
    YOKTU — `docker compose up` tarayıcıda hiçbir şey açmıyordu."""
    doc = _load_compose()
    frontend = doc["services"]["frontend"]
    assert frontend.get("build", {}).get("context") == "./src/frontend"
    assert any("5173" in str(p) for p in frontend.get("ports", []))


def test_ensemble_mode_local_hicbir_anahtar_ZORUNLU_DEGIL():
    """`api`/`migrate` servislerinin `environment:`sinde GEMINI_API_KEY vb.
    hiçbir sağlayıcı anahtarı ZORUNLU kılınmamış olmalı (Fake adapter'lar
    zaten anahtarsız çalışır) — yalnız `ENSEMBLE_MODE`, `DATABASE_URL` gibi
    yapılandırma anahtarları serbest."""
    doc = _load_compose()
    yasakli_anahtarlar = {"GEMINI_API_KEY", "GROQ_API_KEY", "GITHUB_APP_PRIVATE_KEY"}
    for ad in ("migrate", "api"):
        env = doc["services"][ad].get("environment", {})
        assert not (set(env) & yasakli_anahtarlar), (
            f"{ad}.environment zorunlu bir sağlayıcı anahtarı içeriyor: {env}"
        )
        assert env.get("ENSEMBLE_MODE") == "local", f"{ad}.environment.ENSEMBLE_MODE 'local' olmalı"


def test_migrate_tek_atimlik_restart_no():
    """`deploy/docker-compose.prod.yml`'deki AYNI fail-closed disiplin: bir
    kez koşup başarıyla/başarısız bitmeli, sürekli yeniden denenmemeli."""
    doc = _load_compose()
    assert doc["services"]["migrate"].get("restart") == "no"


def test_api_migrate_basarmadan_baslamaz_fail_closed():
    """MUTASYON KİLİDİ: `condition: service_completed_successfully` satırını
    sil/`service_started`'a çevir → bu test kırmızı olur — migration
    henüz koşmadan `api` trafiğe açılabilir (ölçülen bu PR'ın asıl bulgusu:
    `/board`/`/events`/`/graph` "no such table" ile 500 dönüyordu)."""
    doc = _load_compose()
    depends_on = doc["services"]["api"].get("depends_on", {})
    assert "migrate" in depends_on, "api.depends_on içinde 'migrate' yok"
    assert depends_on["migrate"].get("condition") == "service_completed_successfully"


def test_migrate_ve_api_ayni_sqlite_dosyasini_PAYLASIR():
    """İkisi FARKLI dosyaya yazarsa migration'ın kurduğu tablolar api'nin
    gördüğü DB'de hiç olmaz — aynı `ensemble-local-data` volume'u + aynı
    `DATABASE_URL` şart."""
    doc = _load_compose()
    migrate_url = doc["services"]["migrate"]["environment"]["DATABASE_URL"]
    api_url = doc["services"]["api"]["environment"]["DATABASE_URL"]
    assert migrate_url == api_url
    migrate_volumes = {str(v) for v in doc["services"]["migrate"].get("volumes", [])}
    api_volumes = {str(v) for v in doc["services"]["api"].get("volumes", [])}
    shared = {v.split(":")[0] for v in migrate_volumes} & {v.split(":")[0] for v in api_volumes}
    assert shared, "migrate ve api arasında paylaşılan bir volume yok"


def test_ayarlar_volume_kalicidir():
    """T-307 FAZ 2 (`~/.ensemble/ayarlar.json`) — konteyner yeniden
    oluşturulsa (`docker compose up` tekrar) bile kullanıcının kaydettiği
    sağlayıcı anahtarı KORUNMALI; bu yalnızca `.ensemble/` bir named
    volume'a mount edilirse mümkündür."""
    doc = _load_compose()
    api_volumes = [str(v) for v in doc["services"]["api"].get("volumes", [])]
    assert any(".ensemble" in v for v in api_volumes), (
        f"api.volumes içinde '.ensemble' hedefli bir mount yok: {api_volumes}"
    )
    named_volumes = doc.get("volumes", {})
    assert len(named_volumes) >= 2, "en az iki named volume (db + ayarlar) bekleniyor"


def test_api_portu_yayinlanir():
    doc = _load_compose()
    ports = doc["services"]["api"].get("ports", [])
    assert any("8000" in str(p) for p in ports)
