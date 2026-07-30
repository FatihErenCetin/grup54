#!/usr/bin/env python3
"""#349 — Yapilandirma drifti kilidi: `main`'deki compose ile CALISAN sistem
ayrisirsa GORUNUR (kirmizi) olsun.

NEDEN VAR (olculmus olay, 30 Tem 2026 — tahmin degil)
=====================================================
CD (`.github/workflows/deploy.yml`) **imaji** tasiyor (`ensemble-api:<sha>`),
ama konteyneri YARATAN compose dosyasinin `environment:` blogu sunucudaki
ELLE-OPERASYON checkout'undan (`/home/fatih/grup54`) okunuyordu ve o checkout
73 commit bayatti. Sonuc:

    main'deki compose:   RADAR_WINDOW_DAYS=14 · GITHUB_BACKFILL_LIMIT=150
    konteynerde efektif: RADAR_WINDOW_DAYS=2  · GITHUB_BACKFILL_LIMIT=10

#326'nin olcumle bulunmus radar duzeltmesi (29 Tem merge) production'a HIC
ulasmadi; radar uc gun kisitli ayarla kostu ve 30 Tem'de tamamen bosaldi
(0 tespit). Ayni imajla, yalniz compose tazelenerek: 110 tespit.

"Merge edildi = canlida gecerli" varsayimi tam burada kirildi: **imaj taze,
yapilandirma bayat** — ve bunu SOYLEYEN hicbir sinyal yoktu.

NEDEN `/health` UZERINDEN DEGIL (olculdu, 30 Tem)
=================================================
    curl -s http://127.0.0.1:8001/health
    {"status":"ok","mode":"hosted","github_auth":"configured","gemini":"configured"}

`/health` hicbir AYAR degeri dondurmuyor -> disaridan (GitHub-hosted smoke)
bu drift SINIFI OLCULEMEZ. Ayrica `scripts/smoke.py` bu repoda `main`'de
YOK (#189 / PR #238 hala acik; `Makefile`'da `smoke:` hedefi de yok) — yani
"smoke'a bir kontrol ekle" yolu bugun mevcut DEGIL.

Uygulanabilir tek olcum noktasi SUNUCUNUN KENDISI: self-hosted runner prod
kutusunda kosar ve `docker` erisimi vardir -> `docker inspect` konteynerin
GERCEK, efektif ortamini verir. Bu script tam olarak orada kosar.

NE OLCER (iki bagimsiz kontrol, ikisi de FAIL-CLOSED)
=====================================================
A) EFEKTIF ENV: repo'daki `deploy/docker-compose.prod.yml` -> `services.api.
   environment:` blogundaki DUZ (interpolasyonsuz) anahtarlar ile CALISAN
   konteynerin `Config.Env`'i karsilastirilir. Ayrisma -> kirmizi.
   `${...}` iceren degerler (orn. `DATABASE_URL`) BILINCLI olarak
   karsilastirilmaz — degerleri sunucudaki sir dosyasindan gelir, repo'dan
   bilinemez. Atlananlar SESSIZ degil: raporda acikca listelenir.

B) ELLE-OPERASYON CHECKOUT'U: `--ops-checkout` (ya da `OPS_CHECKOUT_DIR`
   ortam degiskeni) verilirse, o dizindeki `deploy/docker-compose.prod.yml`
   ile repo'daki AYNI dosya bayt-bayt karsilastirilir. Ayrisma -> kirmizi.
   Bu, olayin KOK NEDENIDIR: bir sonraki ELLE `docker compose ... up -d`
   komutu prod'u yeniden o bayat dosyayla zehirler. A yesilken B kirmizi
   olabilir (bugun dogru calisiyor ama yarinki elle komut bozacak) — bu
   yuzden iki AYRI kontrol, tek bir "her sey yolunda" degil.

CIKIS KODLARI
=============
    0  drift yok
    1  drift VAR (A ve/veya B)
    2  olculemedi (docker yok, konteyner kosmuyor, compose okunamadi)

Iki sifir-disi kod da KIRMIZIDIR — "olcemedim" ile "temiz" birbirinden
ayrilir ama ikisi de sessizce yesil DONMEZ (fail-open yasak).

KULLANIM
========
    python3 scripts/config_drift.py                      # repo kokunden
    python3 scripts/config_drift.py --ops-checkout /home/fatih/grup54
    make config-drift                                    # yerel (uv ile)

NOT: bu script sunucuda `python3` (Ubuntu 22.04 / 3.10.12, PyYAML 5.4.1 —
olculdu) ile kosar; VDS'te `uv` KURULU DEGIL (olculdu: `which uv` -> bos).
Bu yuzden CD adimi `uv run` DEGIL, dogrudan `python3` cagirir. Yerel
gelistiricide ayni script `make config-drift` ile uv ortaminda kosar.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - ortam hatasi
    # SESSIZ DUSUS YASAK: PyYAML yoksa "drift yok" DEMEYIZ, olcemedigimizi
    # soyleyip 2 ile cikariz.
    print(f"::error::PyYAML yuklu degil ({exc}) — yapilandirma drifti OLCULEMEDI.", flush=True)
    raise SystemExit(2) from exc

VARSAYILAN_COMPOSE = Path("deploy/docker-compose.prod.yml")
VARSAYILAN_SERVIS = "api"

# Compose'un konteyner etiketleri (drift'in KAYNAGINI teshis icin — hangi
# dosyadan yaratilmis?). Sadece raporlanir, kapi DEGILDIR: CD kendi
# checkout'undan yaratirsa yol runner dizinidir, elle komut yaratirsa
# elle-operasyon dizinidir; ikisi de mesru.
ETIKET_CONFIG_FILES = "com.docker.compose.project.config_files"


class OlcumHatasi(RuntimeError):
    """Olcum YAPILAMADI (docker yok, konteyner kosmuyor, dosya okunamadi).

    "Drift yok" ile KARISTIRILMAZ — cagiran taraf bunu 2 ile disari verir."""


@dataclass(frozen=True)
class Fark:
    anahtar: str
    beklenen: str
    gercek: str | None  # None -> anahtar konteynerde HIC yok

    def __str__(self) -> str:
        gercek = "(YOK)" if self.gercek is None else repr(self.gercek)
        return f"{self.anahtar}: compose={self.beklenen!r} · konteyner={gercek}"


def deger_metni(ham: object) -> str:
    """YAML degerini Compose'un konteynere GERCEKTEN yazacagi metne cevirir.

    `RADAR_WINDOW_DAYS: "14"` -> "14" · `PORT: 8000` (tirnaksiz) -> "8000" ·
    `X: true` -> "true" (Python'un "True"su DEGIL — konteynerde "true" olur).
    """
    if isinstance(ham, bool):
        return "true" if ham else "false"
    if ham is None:
        return ""
    return str(ham)


def compose_env_oku(metin: str, servis: str = VARSAYILAN_SERVIS) -> tuple[dict[str, str], dict[str, str]]:
    """Compose metninden `services.<servis>.environment` blogunu okur.

    Donen: (karsilastirilabilir, atlanan)
      * karsilastirilabilir -> deger DUZ (repo'dan bilinebilir)
      * atlanan             -> deger `${...}` interpolasyonu iceriyor
                               (sunucudaki sir dosyasindan gelir)

    `environment` hem mapping (`K: V`) hem liste (`- K=V`) yazilabilir;
    ikisi de desteklenir — biri digerine cevrilirse kontrol SESSIZCE
    kapanmasin diye.
    """
    doc = yaml.safe_load(metin)
    if not isinstance(doc, dict):
        raise OlcumHatasi("compose dosyasi gecerli bir YAML mapping'i degil")
    servisler = doc.get("services") or {}
    if servis not in servisler:
        raise OlcumHatasi(f"compose dosyasinda '{servis}' servisi yok (mevcut: {sorted(servisler)})")
    ham = servisler[servis].get("environment") or {}

    ciftler: list[tuple[str, object]] = []
    if isinstance(ham, dict):
        ciftler = list(ham.items())
    elif isinstance(ham, list):
        for girdi in ham:
            metin_girdi = deger_metni(girdi)
            if "=" not in metin_girdi:
                # `- KEY` bicimi: degeri host ortamindan devralinir -> repo'dan
                # bilinemez, karsilastirilamaz (atlanan olarak raporlanir).
                ciftler.append((metin_girdi, "${" + metin_girdi + "}"))
                continue
            anahtar, deger = metin_girdi.split("=", 1)
            ciftler.append((anahtar, deger))
    else:
        raise OlcumHatasi(f"'{servis}.environment' beklenmeyen tipte: {type(ham).__name__}")

    karsilastirilabilir: dict[str, str] = {}
    atlanan: dict[str, str] = {}
    for anahtar, ham_deger in ciftler:
        deger = deger_metni(ham_deger)
        if "${" in deger:
            atlanan[str(anahtar)] = deger
        else:
            karsilastirilabilir[str(anahtar)] = deger
    return karsilastirilabilir, atlanan


def konteyner_env_ayristir(satirlar: list[str]) -> dict[str, str]:
    """Docker `Config.Env` listesini (`["K=V", ...]`) sozluge cevirir.

    Ayni anahtar birden fazla gecerse SON deger kazanir (Docker'in calisma
    zamani davranisi)."""
    sonuc: dict[str, str] = {}
    for satir in satirlar:
        if "=" not in satir:
            continue
        anahtar, deger = satir.split("=", 1)
        sonuc[anahtar] = deger
    return sonuc


def farklari_bul(beklenen: dict[str, str], gercek: dict[str, str]) -> list[Fark]:
    """compose'un SOYLEDIGI ile konteynerde OLAN arasindaki ayrismalar.

    Yon TEK TARAFLI ve bilincli: konteynerde compose'da olmayan fazladan
    anahtarlar (sir dosyasindan gelen 30+ anahtar) fark SAYILMAZ."""
    return [
        Fark(anahtar, deger, gercek.get(anahtar))
        for anahtar, deger in sorted(beklenen.items())
        if gercek.get(anahtar) != deger
    ]


# --------------------------------------------------------------------------
# Docker tarafi (yan etkili — unit testler yukaridaki saf fonksiyonlari kosar)
# --------------------------------------------------------------------------


def _docker(argumanlar: list[str]) -> str:
    try:
        sonuc = subprocess.run(
            ["docker", *argumanlar], capture_output=True, text=True, timeout=60, check=False
        )
    except FileNotFoundError as exc:
        raise OlcumHatasi("`docker` PATH'te yok — bu script prod kutusunda kosmali") from exc
    except subprocess.TimeoutExpired as exc:
        raise OlcumHatasi("`docker` komutu zaman asimina ugradi") from exc
    if sonuc.returncode != 0:
        raise OlcumHatasi(
            f"`docker {' '.join(argumanlar)}` {sonuc.returncode} ile bitti: {sonuc.stderr.strip()}"
        )
    return sonuc.stdout


def konteyner_bul(proje: str, servis: str) -> str:
    """Compose etiketlerinden KOSAN konteyneri bulur (ad tahmin ETMEZ).

    `--filter label=com.docker.compose.project=<proje>` — proje adi compose
    dosyasinin kendi `name:` alanindan gelir, sabit kodlanmaz."""
    cikti = _docker(
        [
            "ps",
            "--filter",
            f"label=com.docker.compose.project={proje}",
            "--filter",
            f"label=com.docker.compose.service={servis}",
            "--format",
            "{{.ID}}",
        ]
    )
    kimlikler = [s for s in cikti.split() if s]
    if not kimlikler:
        raise OlcumHatasi(
            f"'{proje}/{servis}' etiketli KOSAN bir konteyner yok — "
            "servis ayakta degil (bu da kirmizidir, sessiz gecilmez)"
        )
    return kimlikler[0]


def konteyner_bilgisi(kimlik: str) -> tuple[dict[str, str], str]:
    """(efektif env, konteyneri yaratan compose dosyasinin yolu)."""
    ham = _docker(["inspect", kimlik, "--format", "{{json .Config}}"])
    config = json.loads(ham)
    env = konteyner_env_ayristir(list(config.get("Env") or []))
    etiketler = config.get("Labels") or {}
    return env, str(etiketler.get(ETIKET_CONFIG_FILES, "(bilinmiyor)"))


def ops_checkout_farki(ops_dizin: Path, repo_compose: Path, gorece_yol: Path) -> str | None:
    """Elle-operasyon checkout'undaki compose ile repo'dakini karsilastirir.

    Donen: None (ayni) ya da insan-okunur fark aciklamasi."""
    aday = ops_dizin / gorece_yol
    if not aday.is_file():
        return f"{aday} YOK — elle-operasyon checkout'u bozuk ya da yol yanlis"
    ops_metin = aday.read_text(encoding="utf-8")
    repo_metin = repo_compose.read_text(encoding="utf-8")
    if ops_metin == repo_metin:
        return None
    ops_env, _ = compose_env_oku(ops_metin)
    repo_env, _ = compose_env_oku(repo_metin)
    env_farklari = [
        f"{k}: repo={v!r} · ops={ops_env.get(k, '(YOK)')!r}"
        for k, v in sorted(repo_env.items())
        if ops_env.get(k) != v
    ]
    ayrinti = "; ".join(env_farklari) if env_farklari else "(environment ayni, dosyanin gerisi farkli)"
    return f"{aday} repo'daki surumden FARKLI — bir sonraki ELLE `up -d` prod'u bozar. {ayrinti}"


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Prod yapilandirma drifti kilidi (#349)")
    ayristirici.add_argument("--compose", default=str(VARSAYILAN_COMPOSE), type=Path)
    ayristirici.add_argument("--servis", default=VARSAYILAN_SERVIS)
    ayristirici.add_argument(
        "--ops-checkout",
        default=os.environ.get("OPS_CHECKOUT_DIR", ""),
        help="Elle `docker compose` komutlarinin kostugu checkout dizini "
        "(vars.OPS_CHECKOUT_DIR). Bos ise B kontrolu ATLANIR — ama sessizce degil.",
    )
    args = ayristirici.parse_args(argv)

    compose_yolu: Path = args.compose
    if not compose_yolu.is_file():
        print(f"::error::Compose dosyasi bulunamadi: {compose_yolu}", flush=True)
        return 2

    try:
        compose_metin = compose_yolu.read_text(encoding="utf-8")
        beklenen, atlanan = compose_env_oku(compose_metin, args.servis)
        proje = (yaml.safe_load(compose_metin) or {}).get("name") or ""
        if not proje:
            raise OlcumHatasi("compose dosyasinda `name:` yok — proje adi turetilemez")
        kimlik = konteyner_bul(proje, args.servis)
        gercek, kaynak_dosya = konteyner_bilgisi(kimlik)
    except OlcumHatasi as exc:
        print(f"::error::Yapilandirma drifti OLCULEMEDI: {exc}", flush=True)
        return 2

    print(f"Compose      : {compose_yolu}")
    print(f"Proje/servis : {proje}/{args.servis} (konteyner {kimlik})")
    print(f"Konteyneri yaratan compose dosyasi (teshis): {kaynak_dosya}")
    print(f"Karsilastirilan anahtarlar: {', '.join(sorted(beklenen)) or '(yok)'}")
    if atlanan:
        print(f"Karsilastirilmayan (interpolasyonlu, degeri repo'dan bilinemez): {', '.join(sorted(atlanan))}")

    bulgular: list[str] = []

    farklar = farklari_bul(beklenen, gercek)
    for fark in farklar:
        bulgular.append(f"[A efektif-env] {fark}")

    if args.ops_checkout:
        ops_bulgu = ops_checkout_farki(Path(args.ops_checkout), compose_yolu, VARSAYILAN_COMPOSE)
        if ops_bulgu:
            bulgular.append(f"[B elle-operasyon checkout'u] {ops_bulgu}")
        else:
            print(f"Elle-operasyon checkout'u ({args.ops_checkout}) repo ile AYNI.")
    else:
        # SESSIZ ATLAMA YASAK: kontrolun kosmadigi acikca gorunur.
        print(
            "::warning::--ops-checkout / OPS_CHECKOUT_DIR bos — B kontrolu (elle-operasyon "
            "checkout'u) KOSMADI. Elle `docker compose` komutlarinin kostugu dizin "
            "dogrulanmamis durumda (#349'un kok nedeni).",
            flush=True,
        )

    if not bulgular:
        print("Yapilandirma drifti YOK.")
        return 0

    for bulgu in bulgular:
        print(f"::error::Yapilandirma DRIFTI: {bulgu}", flush=True)
    print(
        "::error::main'deki compose ile CALISAN sistem ayristi (#349). Duzeltme: "
        "elle-operasyon checkout'unda `git pull --ff-only`, ardindan "
        "`docker compose -f docker-compose.prod.yml --env-file .env.production up -d`.",
        flush=True,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
