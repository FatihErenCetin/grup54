"""Deploy runbook (#190) drift kilidi — sozlesme: docs/sprint3-kontratlar.md Ek A.

Amac: `.env.example`'a yeni bir anahtar eklenip `docs/deploy-runbook.md`
guncellenmezse CI kirmizi olsun (issue #190'in asil derdi olan drift). Ag yok,
deterministik; stdlib + pathlib disinda bagimlilik yok (mevcut
`test_error_envelope.py` vb. deseni izler — ayri bir fixture/mock katmani
gerektirmiyor).

GUNCELLEME (D-46, self-host VDS donusumu): runbook Fly.io -> self-host
(BogaHost VDS + docker-compose.prod.yml + host Caddy) mimarisine gore
yeniden yazildi (`fly.toml`/`flyctl`/`FLY_API_TOKEN` main'de zaten kaldirildi,
#246). Buna paralel: eski "Fly secret" / "FLY_API_TOKEN" zorunlu-dizgi
kontrolleri kaldirildi/degistirildi (asagida
`test_platform_etiketleri_ve_zorunlu_notlar_var`); yerine self-host
gercekligini (`test_fly_operasyonel_komut_olarak_gecmiyor`) ve
`.env.example`'in `main`'de `#252/#254/#255` ile buyudugunu (GROQ_*,
RADAR_JUDGE_CONCURRENCY -> 38 degil 41 anahtar) kilitleyen testler eklendi.

Bilincli test EDILMEYEN:
- Tablo satirlarinin markdown yapisini parse edip "ayni anahtar iki
  sutunda" kuralini dogrulamak — kirilgan (bicim degisince yanlis
  kirmizi), degeri dusuk. Insan review'una birakilir (docs/review-rehberi.md).
- "runbook'ta `make smoke` Makefile'daki `smoke:` hedefiyle ayni" capraz-
  dosya kilidi — #189 (`scripts/smoke.py` + `make smoke`) hâlâ `main`'de
  degil (PR #238 acik, Makefile'da `smoke:` hedefi yok). Boyle bir testi
  simdi kosullu yazmak (var/yok'a gore dallanan bir assert) bu repoda #56 ve
  #189 review'larinda zaten bulgu olarak isaretlenen kosullu/fail-open test
  antikalibiydi tekrar eder. #189 `main`'e inince bu test ayri bir PR'da
  (ya da #189'un kendi PR'inda) eklenmelidir.
- Ayni gerekce ile `.github/workflows/deploy.yml` (#236, self-host CD) icin
  bir capraz-dosya testi de eklenmedi — o dal da hâlâ acik (PR #236).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_RUNBOOK = _REPO_ROOT / "docs" / "deploy-runbook.md"
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_DEPLOY_YML = _REPO_ROOT / ".github" / "workflows" / "deploy.yml"

# .env.example'daki duz "ANAHTAR=" satirlarini yakalar (yorum satirlari HARIC —
# CORS_ORIGINS bilerek bu regex'in disinda kaliyor, bkz. asagidaki ayri test).
_ENV_KEY_RE = re.compile(r"^([A-Z_][A-Z0-9_]*)=", re.MULTILINE)

# .env.example'da yalniz YORUM ornegi olarak gecen ama runbook'un yine de
# kapsamasi gereken anahtar (kabul kriteri: "her .env.example anahtari").
_COMMENT_ONLY_KEY = "CORS_ORIGINS"


def _env_example_keys() -> list[str]:
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    return _ENV_KEY_RE.findall(text)


def _runbook_text() -> str:
    return _RUNBOOK.read_text(encoding="utf-8")


def _bolum_1_topoloji() -> str:
    """'## 1. Topoloji' basligindan '## 2. Env' basligina kadarki metin —
    CD/deploy kapisi + PR/main required-check aciklamasi burada yasiyor."""
    runbook = _runbook_text()
    baslangic_baslik = "## 1. Topoloji"
    bitis_baslik = "## 2. Env"
    # runbook.index(...) ValueError firlatir ve bakimciya NE ARANDIGINI
    # soylemez ("substring not found") — baslik degisince (orn. numaralandirma
    # kayarsa) bakimci hangi basligin arandigini bulmak icin bu fonksiyona
    # bakmak zorunda kalir. Onceden acik assert mesajiyla ayni bilgiyi verir.
    assert baslangic_baslik in runbook, (
        f"docs/deploy-runbook.md'de {baslangic_baslik!r} basligi bulunamadi — "
        "baslik yeniden adlandirilmis/numaralandirilmis olabilir; "
        "_bolum_1_topoloji()'yi guncelle"
    )
    assert bitis_baslik in runbook, (
        f"docs/deploy-runbook.md'de {bitis_baslik!r} basligi bulunamadi — "
        "baslik yeniden adlandirilmis/numaralandirilmis olabilir; "
        "_bolum_1_topoloji()'yi guncelle"
    )
    baslangic = runbook.index(baslangic_baslik)
    bitis = runbook.index(bitis_baslik)
    return runbook[baslangic:bitis]


def _baglam_satiri(bolum: str, baglam_etiketi: str) -> str:
    """'- **<baglam_etiketi>**' ile BASLAYAN madde-satirini bulur (bu baglamin
    KUME-TANIMI ciddi anlamda yasadigi tek satir).

    Salt substring eslemesi ("baglam_etiketi in satir") YETERSIZ: ayni ifade
    runbook'ta ozet/capraz-referans cumlelerinde de geciyor — orn.
    "deploy kapısı" hem kume-tanimi satirinda ("- **deploy kapısı** (bu
    satır, ...): ...") HEM DE "Kesişim yalnız ..." ozet cumlesinde ("...deploy
    kapısında `gitleaks`, PR kapısında..."). Substring'e guvenen bir test bu
    ikinci baglamdan yanlislikla kume uyesi cikarabilir. Bu yuzden yalniz
    madde-basi bullet bicimiyle ("- **<etiket>**") baslayan satir aranir.
    """
    for satir in bolum.splitlines():
        if satir.strip().startswith(f"- **{baglam_etiketi}**"):
            return satir
    raise AssertionError(
        f"'- **{baglam_etiketi}**' ile baslayan bir madde-satiri bulunamadi — "
        "kume tanimi baska bir bicimde yazilmis olabilir, bu test yardimcisini "
        "guncelle"
    )


_KUME_UYE_RE = re.compile(r"`([a-zA-Z][a-zA-Z0-9_-]*)`")
_YOK_UYE_RE = re.compile(r"`([a-zA-Z][a-zA-Z0-9_-]*)`\s*bu kümede YOK")


def _kume_ve_yok_cumlesi(satir: str) -> tuple[str, str]:
    """Bir baglam satirini KUME-TANIMI cumlesinden YOK-IDDIASI cumlesine
    ayirir. Ayrim ilk '. ' (nokta+bosluk) sinirindan yapilir: ilk cumle uye
    listesini (': `a` + `b` + `c`.') tasir, ikinci cumle 'bu kümede YOK'
    iddiasini tasir.

    Bu ayrim ZORUNLU: aksi halde iki cumle tek bir 'satir' string'inde
    karisir ve "kumede X gecer mi" testi YOK-cumlesindeki bir ismi de kume
    uyesi sanabilir (#190 turunun asil kok nedeni — assert'ler kumenin UYESI
    olarak mi yoksa "bu kumede YOK" cumlesinde mi gectigini ayirt etmiyordu).
    """
    parcalar = satir.split(". ", 1)
    assert len(parcalar) == 2, (
        "baglam satirinda kume-cumlesi/YOK-cumlesi ayrimi (ilk '. ' siniri) "
        f"bulunamadi: {satir!r}"
    )
    return parcalar[0], parcalar[1]


def _kume_uyeleri(kume_cumlesi: str) -> set[str]:
    """Kume-tanimi cumlesinin ':' SONRASINDAKI kisminda gecen backtick'li
    isimleri doner. ':' oncesi (etiket + parantez aciklamasi, orn.
    "(bu satır, `workflow_run`)") KASTEN disarida birakilir — orada gecen
    backtick'li isimler (orn. `workflow_run`) kumenin UYESI degil."""
    assert ":" in kume_cumlesi, (
        f"kume cumlesinde ':' (uye listesi ayraci) bulunamadi: {kume_cumlesi!r}"
    )
    liste_kismi = kume_cumlesi.split(":", 1)[1]
    uyeler = set(_KUME_UYE_RE.findall(liste_kismi))
    assert uyeler, f"kume cumlesinin uye listesinde hic isim bulunamadi: {kume_cumlesi!r}"
    return uyeler


def _yok_uyesi(yok_cumlesi: str) -> str:
    """YOK-iddiasi cumlesinden '`isim` bu kümede YOK' desenindeki ismi cikarir."""
    eslesme = _YOK_UYE_RE.search(yok_cumlesi)
    assert eslesme, (
        f"YOK cumlesinde beklenen '`isim` bu kümede YOK' deseni bulunamadi: {yok_cumlesi!r}"
    )
    return eslesme.group(1)


def test_runbookun_anahtar_sayisi_iddiasi_gercek_sayiyla_esit():
    """Bu PR'in asil bulgusu ('38 anahtar' iddiasi bayatlamisti, gercek sayi
    41 -- #252/#254/#255 GROQ_*/RADAR_JUDGE_CONCURRENCY ekledi) bir daha
    SESSIZCE kaymasin: runbook'un '<N> anahtarın tamamı' cumlesindeki N,
    `.env.example`'daki GERCEK anahtar sayisiyla (duz satirlar + 1 yorum-only
    CORS_ORIGINS) HER ZAMAN esit olmali. Yeni bir anahtar eklenip runbook'un
    metnindeki N guncellenmezse bu test kirmizi olur (icerik tam olsa bile)."""
    gercek_sayi = len(_env_example_keys()) + 1  # +1: CORS_ORIGINS (yorum-only)
    runbook = _runbook_text()
    eslesme = re.search(r"\*\*(\d+) anahtarın tamamı\*\*", runbook)
    assert eslesme, (
        "runbook'ta '**<N> anahtarın tamamı**' bicimli sayi-iddiasi bulunamadi — "
        "ifade degistiyse bu testin regex'ini guncelle"
    )
    iddia_edilen = int(eslesme.group(1))
    assert iddia_edilen == gercek_sayi, (
        f"runbook '{iddia_edilen} anahtarın tamamı' diyor ama .env.example'da "
        f"gercekte {gercek_sayi} anahtar var (40 duz satir + 1 yorum-only "
        "CORS_ORIGINS) — sayi bayatlamis, runbook'u guncelle (bu PR'in asil "
        "bulgusu ayni sekilde 38 -> 41 kaymisti)"
    )


def test_env_example_anahtarlarinin_tamami_runbookta():
    keys = _env_example_keys()
    assert keys, ".env.example'da hic anahtar bulunamadi — regex/dosya yolu kontrol et"

    runbook = _runbook_text()
    eksik = [k for k in keys if k not in runbook]
    assert not eksik, (
        f"docs/deploy-runbook.md su .env.example anahtarlarini kapsamiyor: {eksik} "
        "(kabul kriteri 1 — Ek A/A1 tablosuna satir ekle)"
    )


def test_cors_origins_yorumlu_anahtar_da_kapsanir():
    # CORS_ORIGINS .env.example'da yalniz "# CORS_ORIGINS=..." yorum-ornegi
    # olarak gecer -> duz-satir regex'i onu YAKALAMAZ. Runbook yine de bu
    # anahtari kapsamak zorunda (kabul kriteri 1); burada acikca iddia edilir
    # ki sessiz bosluk kalmasin.
    env_text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert _COMMENT_ONLY_KEY not in _ENV_KEY_RE.findall(env_text), (
        f"{_COMMENT_ONLY_KEY} artik duz satir olarak geciyor gibi gorunuyor — "
        "bu testin varsayimini guncelle"
    )
    assert f"# {_COMMENT_ONLY_KEY}=" in env_text or f"#{_COMMENT_ONLY_KEY}=" in env_text

    runbook = _runbook_text()
    assert _COMMENT_ONLY_KEY in runbook, (
        f"{_COMMENT_ONLY_KEY} .env.example'da yorum-ornegi olsa da "
        "docs/deploy-runbook.md tablosunda satiri olmali"
    )


def test_deploy_kapisi_ve_pr_kapisi_kume_farki_isimle_belirtilir():
    """Drift kilidi (#190 bulgusu): deploy kapisi (workflow_run, ci.yml'in
    TAMAMI) ile PR/main required-check listesi ORTUSEN AMA OZDES OLMAYAN iki
    ayri kume - deploy kapisinda `gitleaks` var `check-single-issue` yok, PR
    kapisinda tam tersi. Runbook bu iki baglami ISIMLE ayirt etmeli: deploy
    kapisi satirinda `gitleaks` gecmeli, PR/required-check satirinda
    `check-single-issue` gecmeli - ayrica her satir kendi kumesinde
    OLMAYAN uyeyi de acikca (YOK ile) belirtmeli (asil bilgi orada, §190
    bulgusu bunun eksikligiydi). Tam cumle eslemesi YAPMAZ (bicim/kelime
    sirasi degisikligine dayanikli); yalnizca ilgili baglam-satirinda bu
    isimlerin birlikte gectigini kontrol eder.
    """
    bolum = _bolum_1_topoloji()
    satirlar = [s for s in bolum.splitlines() if s.strip()]

    deploy_satirlari = [s for s in satirlar if "deploy kapısı" in s]
    assert deploy_satirlari, (
        "'deploy kapısı' baglamini adlandiran bir satir bulunamadi — "
        "deploy kapisi (workflow_run) PR/main required-check listesinden "
        "ayri, kendi basina adlandirilmis bir kume olarak anilmali"
    )
    assert any("gitleaks" in s for s in deploy_satirlari), (
        "deploy kapısı baglamindaki satir(lar) 'gitleaks'i ISIMLE anmiyor"
    )
    assert any("check-single-issue" in s and "YOK" in s for s in deploy_satirlari), (
        "deploy kapısı baglaminda 'check-single-issue'nun bu kumede OLMADIGI "
        "acikca (YOK ile) belirtilmeli — asil bilgi orada"
    )

    pr_satirlari = [s for s in satirlar if "required-check listesi" in s]
    assert pr_satirlari, (
        "'PR/main required-check listesi' baglamini adlandiran bir satir "
        "bulunamadi — deploy kapisindan ayri, kendi basina adlandirilmis "
        "bir kume olarak anilmali"
    )
    assert any("check-single-issue" in s for s in pr_satirlari), (
        "PR/main required-check baglamindaki satir(lar) 'check-single-issue'u "
        "ISIMLE anmiyor"
    )
    assert any("gitleaks" in s and "YOK" in s for s in pr_satirlari), (
        "PR/main required-check baglaminda 'gitleaks'in bu kumede OLMADIGI "
        "acikca (YOK ile) belirtilmeli — asil bilgi orada"
    )

    # Ana bulgu (#190): iki kapinin AYNI kural oldugu POZITIF iddia
    # edilmemeli. ("aynı kural" DEGIL negasyonu serbest — bilerek kullaniliyor;
    # yasakli olan pozitif "...kuralını uygular" ifadesi, orijinal bulgu buydu.)
    #
    # NOT: eskiden burada `"kuralını uygular" not in bolum` seklinde §1'in
    # TAMAMI uzerinde genis bir substring yasagi vardi. Bu, tamamen mesru bir
    # GELECEK cumleyi de kirar (orn. "check-single-issue tek-issue kuralını
    # uygular") — o cumle "aynı kural" iddiasiyla ilgisiz ama yine de
    # yasakli deseni iceriyor. Bunun yerine yalniz "aynı" ile "kuralını
    # uygular" AYNI CUMLEDE (nokta siniri icinde) birlikte gectigi durumu
    # yasakla — orijinal bulgunun tam sekli buydu ("...aynı ... kuralını
    # uygular").
    cumleler = re.split(r"(?<=[.!?])\s+", bolum)
    ihlal_eden_cumleler = [c for c in cumleler if "aynı" in c and "kuralını uygular" in c]
    assert not ihlal_eden_cumleler, (
        "runbook'ta 'aynı' ile 'kuralını uygular' AYNI CUMLEDE gecen ifade(ler) "
        f"var — deploy kapisi ile PR/main required-check listesinin ayni kurali "
        f"uyguladigini iddia ediyor gibi gorunuyor (#190 bulgusu geri donmus "
        f"olabilir; iki kume ortusen ama ozdes DEGIL): {ihlal_eden_cumleler!r}"
    )


def test_deploy_kapisi_kumesi_ci_yml_ile_ozdes_pr_kapisi_farkli():
    """Drift kilidinin GERCEK versiyonu (review turu 2 bulgusu — ACIK 1):
    yukaridaki `test_deploy_kapisi_ve_pr_kapisi_kume_farki_isimle_belirtilir`
    yalniz ISIM VARLIGINI olcuyor (gitleaks/check-single-issue kelimeleri
    satirda geciyor mu) — kume icerigi TERS cevrilse bile (deploy kumesine
    check-single-issue, PR kumesine gitleaks yazilsa) o test yesil kalmaya
    devam ediyor (bkz. PR govdesindeki mutasyon kaniti).

    Bu test GERCEK kume karsilastirmasi yapar — `test_ci_drift_guard.py`'nin
    izledigi desenle ayni: ci.yml'i PyYAML ile parse edip `jobs` anahtarlarini
    dogruluk kaynagi olarak kullanir.

    - deploy kapisi kumesi ci.yml'in KENDI job isimlerinden turetilir
      (`set(yaml.safe_load(...)["jobs"].keys())`) — runbook'un DEDIGI degil,
      ci.yml'in GERCEKTEN NE OLDUGU.
    - runbook'un deploy-kapisi cumlesinin bu gercek kumeyi TAM OLARAK
      (fazlasiz/eksiksiz) saydigini dogrular.
    - PR/main required-check kumesi runbook metninden cikarilir (bu kume
      branch-protection ayari — repoda baska bir dosyada YAsamiyor) ve deploy
      kumesiyle AYNI OLMADIGI assert edilir.
    - Kume-cumlesi ile YOK-cumlesi AYRI parse edilir (bkz. `_kume_ve_yok_cumlesi`)
      ve her baglamin YOK iddiasi capraz dogrulanir: bir baglamda 'YOK' denen
      isim o baglamin KENDI kumesinde OLMAMALI, DIGER baglamin kumesinde
      OLMALI.
    """
    assert _CI_YML.exists(), f"CI workflow bulunamadi: {_CI_YML}"
    ci_dokuman = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    deploy_gercek = set(ci_dokuman["jobs"].keys())
    assert deploy_gercek, f"ci.yml'de hic job bulunamadi: {_CI_YML}"

    bolum = _bolum_1_topoloji()
    deploy_satir = _baglam_satiri(bolum, "deploy kapısı")
    pr_satir = _baglam_satiri(bolum, "PR/main required-check listesi")

    deploy_kume_cumlesi, deploy_yok_cumlesi = _kume_ve_yok_cumlesi(deploy_satir)
    pr_kume_cumlesi, pr_yok_cumlesi = _kume_ve_yok_cumlesi(pr_satir)

    deploy_runbook = _kume_uyeleri(deploy_kume_cumlesi)
    pr_runbook = _kume_uyeleri(pr_kume_cumlesi)

    assert deploy_runbook == deploy_gercek, (
        f"runbook'un deploy-kapisi cumlesi ({sorted(deploy_runbook)}) ci.yml'in "
        f"gercek job kumesiyle ({sorted(deploy_gercek)}) ORTUSMUYOR — runbook "
        f"ci.yml'i yanlis tasvir ediyor olabilir: {deploy_kume_cumlesi!r}"
    )

    assert pr_runbook != deploy_gercek, (
        "PR/main required-check listesi, ci.yml'in TAMAMIYLA (deploy kapisiyla) "
        f"AYNI kume olarak yazilmis gorunuyor ({sorted(pr_runbook)}) — bu iki "
        "kapi ortusen ama ozdes DEGIL olmali (kumeler ters cevrilmis olabilir): "
        f"{pr_kume_cumlesi!r}"
    )

    deploy_yok = _yok_uyesi(deploy_yok_cumlesi)
    pr_yok = _yok_uyesi(pr_yok_cumlesi)

    assert deploy_yok not in deploy_runbook, (
        f"deploy kapısı YOK-cumlesi '{deploy_yok}'in bu kumede olmadigini iddia "
        f"ediyor ama '{deploy_yok}' aslinda deploy kumesinde ({sorted(deploy_runbook)}) "
        "bulunuyor — YOK iddiasi yanlis (kumeler karismis olabilir)"
    )
    assert deploy_yok in pr_runbook, (
        f"deploy kapısı YOK-cumlesindeki '{deploy_yok}' PR/main kumesinde de "
        f"({sorted(pr_runbook)}) bulunmuyor — YOK iddiasi anlamsiz, bu isim ait "
        "oldugu 'diger' kumede gorunmeli"
    )

    assert pr_yok not in pr_runbook, (
        f"PR/main required-check YOK-cumlesi '{pr_yok}'in bu kumede olmadigini "
        f"iddia ediyor ama '{pr_yok}' aslinda PR kumesinde ({sorted(pr_runbook)}) "
        "bulunuyor — YOK iddiasi yanlis (kumeler karismis olabilir)"
    )
    assert pr_yok in deploy_runbook, (
        f"PR/main required-check YOK-cumlesindeki '{pr_yok}' deploy kumesinde de "
        f"({sorted(deploy_runbook)}) bulunmuyor — YOK iddiasi anlamsiz"
    )


def test_platform_etiketleri_ve_zorunlu_notlar_var():
    runbook = _runbook_text()
    # "Fly secret" ARTIK gercek mekanizma etiketi degil (D-46, self-host
    # donusumu) -- yerini "sunucu env dosyasi" aldi. Eski etiketi burada
    # ZORUNLU saymak yanlis bir sinyal olurdu (bkz. asagidaki
    # test_fly_operasyonel_komut_olarak_gecmiyor - Fly'in GERCEK mekanizma
    # olarak ANILMADIGINI ayrica kilitler).
    for etiket in ("sunucu env dosyası", "Vercel env", "yalnız-local", "CI secret"):
        assert etiket in runbook, f"platform sinif etiketi eksik: {etiket!r}"

    for kritik in (
        "GITHUB_APP_PRIVATE_KEY",
        "PEM",
        "VITE_API_BASE_URL",
        "alembic upgrade head",
        "Instant Rollback",
        # Self-host CD'nin yeni kapi/kavramlari (#236) — Fly'in
        # FLY_API_TOKEN'inin yerini alan seyler, eskisi degil.
        "DEPLOY_ENABLED",
        "ENSEMBLE_ENV_FILE",
    ):
        assert kritik in runbook, f"kritik dizgi eksik: {kritik!r}"


_KOD_BLOGU_RE = re.compile(r"```(?:bash)?\n(.*?)```", re.DOTALL)


def test_fly_operasyonel_komut_olarak_gecmiyor():
    """D-46 kilidi: Fly.io TAMAMEN terk edildi (#246) -- runbook Fly'i yalniz
    TARIHSEL/KARSILASTIRMALI DUZYAZIDA anabilir ("Fly'daki `fly secrets set`in
    eşdeğeri..." gibi karsilastirma cumleleri MESRU), ama hicbir Fly CLI
    komutunu OPERATOR'UN BUGUN CALISTIRACAGI bir ```bash KOD BLOGU icinde
    SUNAMAZ -- kontrol bu yuzden yalniz kod bloklarinin ICERIGINE bakar, tum
    dokumana degil (duzyazidaki mesru karsilastirma cumleleri boylece
    yanlislikla kirmizi vermez).
    """
    runbook = _runbook_text()
    kod_bloklari = "\n".join(_KOD_BLOGU_RE.findall(runbook))
    assert kod_bloklari, "runbook'ta hic ```bash kod blogu bulunamadi — regex/dosya kontrol et"

    yasakli_komutlar = (
        "fly secrets set",
        "fly secrets list",
        "fly apps create",
        "fly volumes create",
        "fly ssh console",
        "fly deploy",
        "fly tokens create",
        "fly launch",
        "fly status -a",
        "fly releases",
        "flyctl deploy",
        "flyctl version",
        "flyctl",
    )
    for komut in yasakli_komutlar:
        assert komut not in kod_bloklari, (
            f"runbook'un bir ```bash kod blogunda hâlâ '{komut}' Fly CLI cagrisi "
            "var — D-46 self-host donusumunden sonra bu artik operatorun "
            "calistiracagi gecerli bir komut DEGIL (fly.toml/flyctl main'de yok, #246)"
        )


def test_self_host_gerceginin_temel_dizgileri_var():
    """Runbook'un self-host mimarisini GERCEKTEN anlattigini (Fly'i anlatan
    eski metnin kopyalanip yer-degistirilmis isimlerle birakilmadigini)
    dogrulayan pozitif kontrol -- her dizgi ilgili gercek dosyadan (compose/
    caddy/workflow) alinmis, uydurulmamis (bkz. bu dosyanin PR govdesindeki
    dogrulama notlari)."""
    runbook = _runbook_text()
    for dizgi in (
        "docker-compose.prod.yml",
        "/etc/ensemble/ensemble.env",
        "ensemble.caddy",
        "recommend2me.com",
        "service_completed_successfully",
        "ensemble-prod",
        "DEPLOY_ENABLED",
    ):
        assert dizgi in runbook, f"self-host gerceginin dizgisi eksik: {dizgi!r}"


def test_runbookta_sir_degeri_yok():
    runbook = _runbook_text()

    # Bilinen sir imzalari — hicbiri gercek bir ornekte/placeholder'da gorunmemeli.
    yasakli_desenler = (
        "-----BEGIN",
        "ghp_",
        "gho_",
        "AIza",
        "fo1_",  # Fly API token onexi
    )
    for desen in yasakli_desenler:
        assert desen not in runbook, f"runbook'ta sir-benzeri desen bulundu: {desen!r}"

    # `_KEY=` / `_SECRET=` / `_TOKEN=` sagindaki deger 20+ karakter ham metinse
    # (placeholder/bos DEGILSE) bu gercek bir sizinti olabilir. Placeholder'lar
    # `<...>` ya da bos oldugu icin bu desenle eslesmez.
    # Tirnak-toleransli: deger `="..."` ya da `='...'` seklinde baslarsa da
    # (acilis tirnagi opsiyonel `\s*["']?`) yakalanir -- eskiden `=` sonrasi
    # ILK karakter dogrudan disarida-birakilan-sinifa (tirnak dahil) girdigi
    # icin tirnakli bir deger regex'i hic eslesmeden gecerdi (sessiz kor nokta).
    cig_deger_re = re.compile(r"[A-Z_]*(?:KEY|SECRET|TOKEN)=\s*[\"']?([^\s<`\"']{20,})")
    for eslesme in cig_deger_re.finditer(runbook):
        deger = eslesme.group(1)
        assert False, f"placeholder olmayan uzun deger bulundu: {deger!r}"


def test_imaj_budama_sayisi_runbook_ile_deploy_yml_arasinda_esit():
    """#262 drift kilidi: `deploy.yml`'in 'Eski imajlari budala' adiminin
    `IMAGE_KEEP_COUNT` degeri ile runbook'un §5 Rollback bolumunde iddia
    ettigi 'tutulan surum sayisi' AYNI olmali -- biri guncellenip digeri
    unutulursa (orn. workflow'da 5 -> 10 degisir ama runbook hala 'son 5
    SHA etiketini' der) operator yanlis bir rollback penceresine gore
    planlama yapar (N deploy once bir SHA'nin hala yerelde oldugunu sanip
    '--no-build' dener, aslinda budanmis olabilir)."""
    assert _DEPLOY_YML.exists(), f"Deploy workflow bulunamadi: {_DEPLOY_YML}"
    deploy = yaml.safe_load(_DEPLOY_YML.read_text(encoding="utf-8"))
    deploy_steps = deploy["jobs"]["deploy"].get("steps", []) or []
    prune_step = next((s for s in deploy_steps if "docker rmi" in (s.get("run") or "")), None)
    assert prune_step is not None, "deploy.yml'de 'docker rmi' kosan bir adim bulunamadi."

    keep_count_raw = prune_step.get("env", {}).get("IMAGE_KEEP_COUNT")
    assert keep_count_raw is not None, "budama adiminin env.IMAGE_KEEP_COUNT'u yok."
    keep_count = int(keep_count_raw)

    runbook = _runbook_text()
    eslesme = re.search(r"son \*\*(\d+) SHA etiketini\*\*", runbook)
    assert eslesme, (
        "runbook'ta 'son **<N> SHA etiketini**' bicimli bir tutma-sayisi iddiasi "
        "bulunamadi -- ifade degistiyse bu testin regex'ini guncelle"
    )
    iddia_edilen = int(eslesme.group(1))
    assert iddia_edilen == keep_count, (
        f"runbook 'son {iddia_edilen} SHA etiketini' diyor ama deploy.yml'in budama "
        f"adiminda IMAGE_KEEP_COUNT={keep_count} -- sayilar birbirinden kaymis "
        "(workflow guncellenip runbook unutulmus, ya da tam tersi)."
    )


# ── #331 doğrulama bulgusu: runbook prod imajında OLMAYAN ikiliyi çağırıyordu ──


def _runtime_asamasinda_olmayan_ikililer() -> set[str]:
    """Prod imajının runtime katmanında BULUNMAYAN, ama yanlışlıkla çağrılması
    kolay ikililer.

    `Dockerfile` iki aşamalı: `uv` yalnız **builder**'a kopyalanır
    (`COPY --from=uv /uv /uvx /bin/`), runtime ise yalnız
    `COPY --from=builder /app /app` alır. `Makefile` hiç kopyalanmaz.
    Yani `make` ve `uv` runtime'da YOKTUR — `python` çalışır çünkü
    `ENV PATH=/app/.venv/bin:$PATH` venv'i öne alır.
    """
    return {"make", "uv"}


def test_runbook_exec_komutlari_imajda_OLMAYAN_ikili_cagirmaz() -> None:
    """MUTASYON KİLİDİ: runbook'taki `docker compose exec api ... make rebuild`
    satırını geri koy → bu test düşer.

    Neden var: #331 düzeltmesini prod'da devreye sokan TEK elle adım
    `docker compose exec api sh -c "cd /app && make rebuild"` idi ve **çalışmıyordu**.
    Testler yeşildi, mühendislik doğruydu, ama onu canlıya indiren komut yoktu —
    bu projenin tekrar eden hatası ("motoru yaz, son santimi bağlama").
    Sınıfı burada kilitliyoruz ki bir daha sessizce dönmesin.
    """
    yasak = _runtime_asamasinda_olmayan_ikililer()
    ihlaller: list[tuple[int, str, str]] = []
    for no, satir in enumerate(_RUNBOOK.read_text(encoding="utf-8").splitlines(), 1):
        if "docker compose exec api" not in satir:
            continue
        # KOMUTU ölç, cümleyi DEĞİL. İlk denemem `exec api`den sonrasının
        # tamamına bakıyordu ve yanlış kırmızı veriyordu: satır 405'te komut
        # `alembic downgrade` iken, aynı satırın DÜZYAZISI `make rebuild`den
        # (yerel geliştirme komutu) söz ediyor. Markdown'da komut ya bir
        # backtick aralığındadır (satır içi) ya da fenced blok satırının
        # kendisidir (backtick yok).
        araliklar = re.findall(r"`([^`]+)`", satir)
        komutlar = [a for a in araliklar if "docker compose exec api" in a] or (
            [] if araliklar else [satir]
        )
        for komut in komutlar:
            govde = komut.split("docker compose exec api", 1)[1]
            for ikili in yasak:
                if re.search(rf"(?<![\w-]){re.escape(ikili)}\s", govde):
                    ihlaller.append((no, ikili, komut.strip()))

    assert not ihlaller, (
        "runbook, prod imajının runtime katmanında BULUNMAYAN bir ikiliyi "
        "`docker compose exec api` ile çağırıyor — komut sunucuda çalışmaz:\n"
        + "\n".join(f"  satır {no}: `{i}` → {s}" for no, i, s in ihlaller)
        + "\n\nDoğrusu: `docker compose exec api python -m <modul>` "
        "(PATH=/app/.venv/bin venv python'unu zaten öne alır)."
    )


def test_runbook_rebuild_adimi_dogru_modulu_cagirir() -> None:
    """`make rebuild` hedefi neyi koşuyorsa (`python -m ensemble.store.rebuild`)
    runbook da aynı modülü çağırmalı — ikisi ayrışırsa sunucuda yanlış şey koşar."""
    makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "python -m ensemble.store.rebuild" in makefile, (
        "Makefile `rebuild` hedefi değişmiş; runbook kilidi güncellenmeli"
    )
    metin = _RUNBOOK.read_text(encoding="utf-8")
    assert "docker compose exec api python -m ensemble.store.rebuild" in metin
