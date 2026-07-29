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


# ---------------------------------------------------------------------------
# #257 bulgu 3 — compose'un KENDİ "KRİTİK" dediği değişmezler kilitli değildi
# ---------------------------------------------------------------------------


def test_api_portu_YALNIZ_loopbacke_baglanir():
    """`127.0.0.1:` öneki silinirse API public IP'den TLS'siz erişilebilir olur.

    Compose dosyası bunu kendi yorumunda büyük harfle işaretliyor (satır ~214):
        "127.0.0.1:" on eki KRITIK — silinirse Docker portu 0.0.0.0'a acar
        ve ufw'yi ATLAR.

    Docker'ın DNAT kuralları ufw/iptables INPUT filtresini atlar — yani sunucuda
    ufw "kapalı" derken port yine de açık olur. Sessiz ve tehlikeli.

    Bu testten önce dosyadaki dört "kritik/bilerek" değişmezden yalnız İKİSİ
    kilitliydi (`migrate.restart`, `depends_on.condition`). Eşiği dosyanın
    KENDİSİ koymuş, test o eşiğin yarısını uyguluyordu (#257 bulgu 3).

    MUTASYON KİLİDİ: `- "8001:8000"` yaz → kırmızı.
    """
    api = _load_compose()["services"]["api"]
    portlar = api.get("ports")
    assert portlar, "api.ports yok — port yayını sessizce kaldırılmış olabilir"
    for p in portlar:
        metin = str(p)
        assert metin.startswith("127.0.0.1:"), (
            f"api portu '{metin}' loopback'e bağlı DEĞİL — Docker DNAT ufw'yi "
            "atlar ve API public IP'den TLS'siz erişilebilir olur"
        )


def test_harness_mounti_SALT_OKUNUR_ve_dizin_uydurmaz():
    """İki değişmez, ikisi de compose'un kendi yorumunda "BİLEREK" işaretli.

    `read_only: true`  — konteyner `.harness/`'i (kanonik ortak bağlam) yazamaz.
    `create_host_path: false` — host'ta dizin YOKSA Docker onu root'a ait BOŞ
    bir dizin olarak UYDURMAZ. Uydursaydı: board sessizce boş, `/scope` 503,
    yani demo "yarıya kadar çalışır" ve sebebi hiçbir yerde görünmez — tam da
    bu repoda avladığımız fail-open şekli, altyapı katmanında.

    MUTASYON KİLİDİ: kısa sözdizimine çevir (`- "../.harness:/app/.harness:ro"`)
    → `create_host_path` kaybolur → kırmızı.
    """
    api = _load_compose()["services"]["api"]
    mountlar = [m for m in api.get("volumes", []) if isinstance(m, dict)]
    harness = [m for m in mountlar if ".harness" in str(m.get("target", ""))]
    assert harness, (
        "api'de UZUN sözdizimli `.harness` mount'u yok — kısa sözdizimine "
        "dönülmüş olabilir; o zaman Docker eksik host dizinini kendisi yaratır"
    )
    m = harness[0]
    assert m.get("read_only") is True, f".harness mount'u salt-okunur değil: {m}"
    bind = m.get("bind") or {}
    assert bind.get("create_host_path") is False, (
        f".harness mount'unda create_host_path=false yok: {m} — Docker eksik "
        "dizini boş olarak yaratır ve board sessizce boş kalır"
    )


def test_radar_ayar_dugmeleri_compose_da_yasar():
    """#324 — radar'in uc ayar dugmesi compose `environment:`inde OLMALI.

    Neden kilitli: bu ayarlar 2026-07-29'a kadar SUNUCUDAKI
    `/etc/ensemble/ensemble.env` icinde yasiyordu ve orada kimse goremiyordu.
    Olculen sonuc: uretimde `RADAR_WINDOW_DAYS=2` + `GITHUB_BACKFILL_LIMIT=10`
    ile `GET /radar` 0 tespit donuyordu — `degraded: null` oldugu icin de
    "hata yok" gibi gorunuyordu. Aslinda judge'a hic cift gitmiyordu (DB:
    toplam 6 yargi, 6'si da "cakisma var" — dedektor calisiyor, ona soru
    sorulmuyordu).

    Sir olmayan bir AYARIN gitmeyen bir yerde yasamasi, "urun bozuk mu, ayar
    mi kisik" sorusunu cevaplanamaz kiliyordu. Bu test onlari commit'li
    dosyaya cakiyor: biri env dosyasina geri taşırsa CI kirmizi olur.

    Mutasyon kaniti: uc satiri da compose'dan gecici olarak sildim -> test
    kirmizi (KeyError yerine acik mesajla); geri alinca yesil.
    """
    api_env = _load_compose()["services"]["api"]["environment"]
    for anahtar in ("RADAR_WINDOW_DAYS", "GITHUB_BACKFILL_LIMIT", "RADAR_JUDGE_CONCURRENCY"):
        assert anahtar in api_env, (
            f"{anahtar} compose `api.environment` icinde yok. Sunucudaki env "
            "dosyasina geri tasindiysa geri al: sir degil, AYAR — commit'li "
            "olmali (bkz. #324 ve docs/deploy-runbook.md §env tablosu)."
        )
        # Deger STRING olmali: YAML `7`'yi int'e cevirir, Compose ise
        # `environment:` degerlerinde string bekler (int verilirse Compose
        # surumune gore uyari/hata). Tirnak kaybi sessizce kaymasin.
        assert isinstance(api_env[anahtar], str), (
            f"{anahtar} tirnak icinde (string) yazilmali — YAML tirnaksiz "
            f"sayiyi int yapar. Gercek tip: {type(api_env[anahtar]).__name__}"
        )

    # Pencere 2'de KALMAMALI: asil darbogaz oydu. Uste sinir kod
    # varsayilani (14) — asmak kotayi gereksiz yakar.
    pencere = int(api_env["RADAR_WINDOW_DAYS"])
    assert 3 <= pencere <= 14, (
        f"RADAR_WINDOW_DAYS={pencere}. 2 (eski deger) cift olusturmuyordu; "
        "14 kod varsayilani ve pratik ust sinir."
    )
