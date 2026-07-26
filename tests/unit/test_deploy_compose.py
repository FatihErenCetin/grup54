"""#246 — `deploy/docker-compose.prod.yml`'in gecerli YAML oldugunu VE
migration'in fail-closed zincirini (`#187`in elle karsiligi) kilitleyen test.

Neden var: bu dosyada `alembic upgrade head` calistiran `migrate` servisi bir
kez kosup biter (`restart: "no"`); `api` servisinin trafik acmadan once onun
BASARIYLA bittigini beklemesi (`depends_on.migrate.condition:
service_completed_successfully`) Fly'in `release_command`iyla ayni fail-closed
garantiyi verir — migration patlarsa api HIC ayaga kalkmaz. Bu iki alandan
BIRI yanlislikla silinirse/degistirilirse yigin "sessizce" migration'siz
trafik acabilir (fail-open) ve bu regresyon sinifi bu testler olmadan CI'da
YAKALANMAZ.

Mutasyon kanitiyla dogrulandi (PR govdesinde raporlanir): `condition:
service_completed_successfully` satirini gecici olarak silip test tekrar
calistirildi -> kirmizi oldu; geri alinca yesile dondu.
"""

from pathlib import Path

import yaml

COMPOSE_PATH = Path(__file__).parent.parent.parent / "deploy" / "docker-compose.prod.yml"


def _load_compose() -> dict:
    assert COMPOSE_PATH.exists(), f"Compose dosyasi bulunamadi: {COMPOSE_PATH}"
    doc = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "docker-compose.prod.yml gecerli bir YAML mapping'i degil"
    return doc


def test_gecerli_yaml_ve_beklenen_servisler():
    """Dosya gecerli YAML olarak parse edilir ve uc kanonik servisi (db,
    migrate, api) tasir — anchor/merge-key (`&api-imaj`, `<<: *api-imaj`)
    kullanimi `yaml.safe_load` ile de sorunsuz cozulur (PyYAML `<<` merge
    anahtarini SafeLoader'da da destekler)."""
    doc = _load_compose()
    assert doc.get("name") == "ensemble"
    services = doc.get("services", {})
    assert set(services) == {"db", "migrate", "api"}, (
        f"Beklenen servis kumesi {{'db','migrate','api'}}, gercek: {set(services)}"
    )


def test_migrate_tek_atimlik_restart_no():
    """`migrate` servisi `restart: unless-stopped`/`always` OLAMAZ — bir kez
    kosup basariyla/basarisiz bitmesi gerekir, aksi halde alembic surekli
    yeniden denenir (ve fail-closed zinciri anlamsizlasir)."""
    doc = _load_compose()
    migrate = doc["services"]["migrate"]
    assert migrate.get("restart") == "no", (
        f"migrate.restart {migrate.get('restart')!r} — 'no' olmali (tek atimlik, #187 elle karsiligi)"
    )


def test_api_migrate_basarmadan_baslamaz_fail_closed():
    """`api.depends_on.migrate.condition` == `service_completed_successfully`
    OLMALI: bu, `alembic upgrade head` sifir-disi bir kodla bitince Compose'un
    `api` konteynerini HIC baslatmamasini saglar (Fly `release_command`
    fail-closed davranisinin elle esdegeri, bkz. dosyanin basligindaki #187
    notu). Bu satir yanlislikla `service_started` ya da tamamen silinirse
    migration patlasa bile api trafige acilir — bu test tam da bunu yakalar."""
    doc = _load_compose()
    api = doc["services"]["api"]
    depends_on = api.get("depends_on", {})
    assert "migrate" in depends_on, "api.depends_on icinde 'migrate' anahtari yok"
    condition = depends_on["migrate"].get("condition")
    assert condition == "service_completed_successfully", (
        f"api.depends_on.migrate.condition {condition!r} — "
        "'service_completed_successfully' olmali (fail-closed zincir kilidi)"
    )
    # db icin de saglik kosulu bekleniyor (migrate/api ikisi de db hazir olmadan baslamamali).
    assert depends_on.get("db", {}).get("condition") == "service_healthy"


# ---------------------------------------------------------------------------
# Merge oncesi inceleme bulgulari (#246)
# ---------------------------------------------------------------------------

ENV_ORNEK_PATH = Path(__file__).parent.parent.parent / "deploy" / ".env.production.example"


def test_demo_sertlestirmesi_uretim_sablonunda_ACIK():
    """MUTASYON KILIDI: `DEMO_MODE=true` satirini yorumla -> bu test kirilir.

    Silinen `fly.toml` bu degeri PLATFORM MANIFESTINDE tasiyordu
    (`DEMO_MODE = "true"`) ve kendi yorumu suydu: "Bu satir olmadan ozellik
    canlida hic acilmaz (rate cap + cached verdict + repo-pin devre disi
    kalir)." Self-host'a gecerken (D-46) garanti kayboldu: deger operatorun
    hatirlamasina bagli bir secenege dondu.

    Regresyonun sessizligi tehlikeli — DEMO_MODE kapali acilirsa HICBIR SEY
    patlamaz, yalnizca public demo korumasiz kosar. Test bu yuzden var:
    kapali gitmesi bir kararsa, bu testi degistirmek o karari GORUNUR kilar.
    """
    satirlar = ENV_ORNEK_PATH.read_text(encoding="utf-8").splitlines()
    etkin = [s.strip() for s in satirlar if s.strip().startswith("DEMO_MODE=")]

    assert etkin, "deploy/.env.production.example icinde ETKIN bir DEMO_MODE satiri yok"
    assert etkin[0] == "DEMO_MODE=true", f"beklenen DEMO_MODE=true, bulunan: {etkin[0]}"


def test_env_file_degiskenle_yonlendirilebilir():
    """MUTASYON KILIDI: `${ENSEMBLE_ENV_FILE:-...}`'i sabit `.env.production`
    yap -> bu test kirilir.

    CD (#236) compose'u RUNNER'IN KENDI checkout'unda kosar; orada
    `deploy/.env.production` YOKTUR (gitignored, operator saglar). Sabit goreli
    yol, CD ilk calistiginda "env file not found" ile patlardi — ve bu ancak
    `vars.DEPLOY_ENABLED=true` yapildigi gun ortaya cikardi.

    Degisken hem elle kurulumun davranisini AYNEN korur (varsayilan
    `.env.production`) hem de CD'nin mutlak yol (/etc/ensemble/ensemble.env)
    vermesine izin verir — sir hicbir git agacinda yasamaz.
    """
    servisler = _load_compose()["services"]
    for ad in ("api", "migrate"):
        env_file = servisler[ad].get("env_file")
        assert env_file, f"{ad}: env_file yok"
        girdi = env_file[0] if isinstance(env_file, list) else env_file
        assert "ENSEMBLE_ENV_FILE" in str(girdi), (
            f"{ad}: env_file sabit ('{girdi}') — CD kendi checkout'unda bunu bulamaz"
        )
        assert ".env.production" in str(girdi), (
            f"{ad}: varsayilan kayboldu ('{girdi}') — elle kurulum bozulur"
        )
