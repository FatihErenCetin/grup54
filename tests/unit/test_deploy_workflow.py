"""Deploy CD workflow (#192) sozlesme testleri.

Kabul kriteri odagi: `.github/workflows/deploy.yml`'in main->Fly CD kapisi
GERCEKTEN fail-safe mi (token yoksa/CI kirmiziysa main asla kirilmiyor mu),
ve `ci.yml` ile capraz-dosya baglantisi kirilgan noktalarda dogru mu.

PyYAML 1.1 tuzagi: `on:` anahtari `safe_load` ile boolean `True`'ya cevrilir
(repodaki 6 mevcut workflow'da da deneysel olarak dogrulandi) -- `_triggers()`
bunu telafi eder.

Tautoloji-karsiti not: testlerin cogu (1, 2, 6, 7, 8, 9, 13) tek dosyanin
metnini tekrar etmez -- ya iki dosyanin (ci.yml <-> deploy.yml) birbiriyle
tutarliligini, ya da TUM workflow'lara uygulanan bir GitHub-semantigi kuralini
olcer; bu yuzden bu PR'dan bagimsiz gelecek regresyonlari da yakalar.
"""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS_DIR / name).read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    """`on:` anahtarini dondurur (PyYAML 1.1: `on` -> `True` anahtar tuzagi)."""
    return wf.get("on", wf.get(True, {}))


def _all_workflows() -> list[tuple[str, dict]]:
    return [
        (p.name, yaml.safe_load(p.read_text(encoding="utf-8")))
        for p in sorted(WORKFLOWS_DIR.glob("*.yml"))
    ]


def _all_steps(job: dict) -> list[dict]:
    return job.get("steps", []) or []


def _norm_expr(expr: str) -> str:
    """`${{ x }}` bicimli GitHub ifadelerini bosluk-duyarsiz karsilastirmak
    icin normalize eder (anahtar-bazli TAM ESITLIK testlerinde kullanilir --
    alt-dizgi degil, deger tam olarak beklenen ifadeye esit olmali)."""
    return re.sub(r"\s+", "", expr or "")


CI = _load("ci.yml")
DEPLOY = _load("deploy.yml")
PREFLIGHT_IF = DEPLOY["jobs"]["preflight"]["if"]


def test_ci_ismi_deploy_kapisiyla_ayni():
    """Kirilma: `ci.yml`'in `name:`i degisirse deploy `workflow_run` SESSIZCE
    hic kosmaz -- bu capraz-dosya baglanti bu testle korunur."""
    ci_name = CI["name"]
    deploy_watches = _triggers(DEPLOY)["workflow_run"]["workflows"]
    assert ci_name in deploy_watches, (
        f"deploy.yml, ci.yml'in adini ('{ci_name}') degil {deploy_watches} degerini "
        "izliyor -- ci.yml yeniden adlandirildi da deploy.yml guncellenmedi mi?"
    )


def test_ci_main_pushta_kosuyor():
    """Kapinin on-kosulu: CI gercekten main push'ta kosmali, aksi halde
    'push main -> CI -> deploy' zinciri hic tetiklenmez."""
    ci_on = _triggers(CI)
    assert "push" in ci_on, "ci.yml artik 'push' tetikleyicisi tasimiyor."
    assert "main" in (ci_on["push"].get("branches") or []), (
        "ci.yml 'push' artik main dalini izlemiyor -- deploy zincirinin girdisi kayboldu."
    )


def test_workflow_dispatch_ile_elle_tetiklenebilir():
    """workflow_run yalniz varsayilan daldaki dosyadan tetiklenir, bu yuzden
    workflow_dispatch olmadan deploy.yml ilk PR'da hic denenemez. Bu artik bir
    kacis kapisi DEGIL -- main'e (github.ref) VE CI-yesilligine (ci_ok
    output'u) ayni anda tabi, ikinci bir tetikleyici yoldur (bkz. deploy.yml
    basligi, tuzak 4/5)."""
    deploy_on = _triggers(DEPLOY)
    assert "workflow_dispatch" in deploy_on, "workflow_dispatch tetikleyicisi kayboldu."


def test_ci_kirmiziysa_kapi_kapali():
    """`preflight.if` CI conclusion'i acikca kontrol etmeli -- yoksa kirmizi
    CI'dan sonra da deploy denenir."""
    assert "workflow_run.conclusion == 'success'" in PREFLIGHT_IF, (
        "preflight.if icinde CI conclusion=='success' kontrolu yok -- "
        "CI kirmiziyken de deploy tetiklenebilir."
    )


def test_fork_ve_pr_kosulari_elenir():
    """Uc AYRI guard -- her biri gercek bir saldiri/kaza senaryosuna karsi:
    (a) PR kosusu, (b) main disi dal, (c) fork reposu."""
    assert "workflow_run.event == 'push'" in PREFLIGHT_IF, (
        "event=='push' kontrolu yok -- ci.yml'in pull_request kosusu da "
        "workflow_run uretir ve deploy'u tetikleyebilir."
    )
    assert "head_branch == 'main'" in PREFLIGHT_IF, (
        "head_branch=='main' kontrolu yok -- fork'ta 'main' adli bir daldan "
        "acilan PR, yalniz 'branches: [main]' filtresini gecebilir."
    )
    assert "head_repository.full_name == github.repository" in PREFLIGHT_IF, (
        "head_repository.full_name==github.repository kontrolu yok -- bir "
        "fork'taki ayni-isimli workflow_run bu repoyu tetikleyebilir."
    )


def test_hicbir_workflow_if_icinde_secrets_kullanmiyor():
    """GitHub semantigi: `secrets` context'i `if:` icinde KULLANILAMAZ --
    kullanilirsa ifade sessizce bos/yanlis degerlendirilir ve kapi TERS
    calisir (deploy her zaman skip ya da her zaman calisir)."""
    violations = []
    for wf_name, wf in _all_workflows():
        for job_id, job in (wf.get("jobs") or {}).items():
            job_if = job.get("if")
            if job_if and "secrets." in str(job_if):
                violations.append(f"{wf_name}:{job_id} (job-level if)")
            for step in _all_steps(job):
                step_if = step.get("if")
                if step_if and "secrets." in str(step_if):
                    step_name = step.get("name", step.get("id", "?"))
                    violations.append(f"{wf_name}:{job_id}:{step_name} (step-level if)")
    assert not violations, (
        "`if:` icinde `secrets.` referansi bulundu (GitHub'da bu context if'te "
        f"gecersizdir -- kapi ters calisir): {violations}"
    )


def test_flyctl_kosan_her_job_token_kapisina_bagli():
    """Generik: `flyctl` kosan HER job, bir `has_token` VE bir `ci_ok`
    output'u ureten job'a `needs` ile baglanmali VE `if`'i HER IKI output'u
    da referans almali -- yarin ikinci bir flyctl job'i (orn. `deploy2`)
    eklenirse, `ci_ok` kontrolu olmadan da (yalniz has_token'a bagliyken) bu
    test onu yakalar (DELIK 1, S192 sertlestirme: token varsa ama CI kirmiziyken
    de flyctl kosabilecek bir job sessizce eklenebilirdi)."""
    for wf_name, wf in _all_workflows():
        for job_id, job in (wf.get("jobs") or {}).items():
            runs_flyctl = any("flyctl" in (step.get("run") or "") for step in _all_steps(job))
            if not runs_flyctl:
                continue
            needs = job.get("needs")
            needs_list = [needs] if isinstance(needs, str) else list(needs or [])
            assert needs_list, (
                f"{wf_name}:{job_id} 'flyctl' kosuyor ama 'needs' tanimlamiyor -- "
                "token varlik kapisina bagli olmadan calisabilir."
            )
            job_if = str(job.get("if") or "")
            assert any(f"needs.{n}.outputs.has_token" in job_if for n in needs_list), (
                f"{wf_name}:{job_id} 'flyctl' kosuyor ama if kosulunda "
                "'needs.<job>.outputs.has_token' referansi yok -- token "
                "yokken de calisabilir (fail-safe kapi delinmis)."
            )
            assert any(f"needs.{n}.outputs.ci_ok" in job_if for n in needs_list), (
                f"{wf_name}:{job_id} 'flyctl' kosuyor ama if kosulunda "
                "'needs.<job>.outputs.ci_ok' referansi yok -- CI kirmiziyken de "
                "calisabilir (fail-safe kapi delinmis, DELIK 1)."
            )


def test_deploy_if_ciplak_or_alternatifi_yok():
    """DELIK 1 (S192 sertlestirme): deploy.if bugun ciplak bir '||' icermiyor,
    ama biri `|| github.event_name == 'workflow_dispatch'` gibi bir alternatif
    eklerse iki kapiyi (has_token + ci_ok) birden short-circuit eder -- bu,
    dosyanin kendi "tuzak 4" paragrafinda preflight.if icin belgelenen ve
    kapatilan anti-kalibin AYNISIDIR, burada deploy.if icin tekrarlanir:
    tepe-seviye '||' ile bol, HER alternatifin hem has_token hem ci_ok
    kontrolu icerdigini dogrula (ciplak/kosulsuz bir alternatif kalmamali)."""
    deploy_if = str(DEPLOY["jobs"]["deploy"].get("if") or "")
    alternatifler = [alt.strip() for alt in deploy_if.split("||")]
    for alt in alternatifler:
        assert "has_token" in alt and "ci_ok" in alt, (
            f"deploy.if alternatiflerinden biri ('{alt}') hem has_token hem ci_ok "
            f"kontrolu icermiyor -- ciplak bir '||' ile kapi(lar) short-circuit "
            f"edilebilir (tam if={deploy_if!r})."
        )


def test_token_degeri_asla_loglanmaz():
    """Hijyen: hicbir `run:` adimi FLY_API_TOKEN'in DEGERINI echo/printf ile
    yazdirmiyor ve GITHUB_OUTPUT/GITHUB_ENV'e degeri yazmiyor; `${{ secrets.
    FLY_API_TOKEN }}` yalniz `env:`/`with:` haritalarinda gecmeli, `run:`
    metninde degil. (Var-mi-yok-mu kontrolu -- `[ -n "$FLY_API_TOKEN" ]` --
    degeri LOGLAMADIGI icin bilincli olarak SERBEST birakilir.)"""
    # echo/printf + ayni satirda $FLY_API_TOKEN -> degeri stdout'a yazdirir.
    echo_leak_re = re.compile(r"\b(echo|printf)\b[^\n]*\$\{?FLY_API_TOKEN\}?")
    # $FLY_API_TOKEN degeri ayni satirda GITHUB_OUTPUT/GITHUB_ENV'e akiyor.
    output_leak_re = re.compile(
        r"\$\{?FLY_API_TOKEN\}?[^\n]*>>\s*\"?\$\{?(GITHUB_OUTPUT|GITHUB_ENV)\}?\"?"
    )

    for wf_name, wf in _all_workflows():
        for job_id, job in (wf.get("jobs") or {}).items():
            for step in _all_steps(job):
                run_body = step.get("run")
                if not run_body:
                    continue
                assert "secrets.FLY_API_TOKEN" not in run_body, (
                    f"{wf_name}:{job_id} bir 'run:' adiminda '${{{{ secrets.FLY_API_TOKEN }}}}' "
                    "dogrudan geciyor -- token yalniz env:/with: uzerinden akitilmali."
                )
                leak = echo_leak_re.search(run_body)
                assert not leak, (
                    f"{wf_name}:{job_id} bir echo/printf FLY_API_TOKEN degerini yazdiriyor: "
                    f"{leak.group(0)!r}"
                )
                output_leak = output_leak_re.search(run_body)
                assert not output_leak, (
                    f"{wf_name}:{job_id} FLY_API_TOKEN degeri GITHUB_OUTPUT/GITHUB_ENV'e "
                    f"yaziliyor: {output_leak.group(0)!r}"
                )


def test_deploy_concurrency_iptal_edilemez():
    """`group=='deploy'` + `cancel-in-progress: false` -- generik varyant:
    flyctl kosan HER workflow iptal-edilemez olmali (yarim deploy/yarim
    release-migrate riskine karsi)."""
    for wf_name, wf in _all_workflows():
        jobs = wf.get("jobs") or {}
        runs_flyctl = any(
            "flyctl" in (step.get("run") or "") for job in jobs.values() for step in _all_steps(job)
        )
        if not runs_flyctl:
            continue
        concurrency = wf.get("concurrency")
        assert concurrency, f"{wf_name} flyctl kosuyor ama workflow-level concurrency tanimlamiyor."
        assert concurrency.get("group") == "deploy", (
            f"{wf_name} concurrency.group == {concurrency.get('group')!r} -- 'deploy' degil."
        )
        assert concurrency.get("cancel-in-progress") is False, (
            f"{wf_name} cancel-in-progress False degil -- kosan bir deploy yarida kesilebilir."
        )


def test_deploy_ci_dogruladigi_shayi_checkout_eder():
    """Checkout adimi `needs.preflight.outputs.sha`'ya referans vermeli --
    aksi halde CI'in DOGRULAMADIGI, ilerlemis bir main tepesi deploy edilir."""
    deploy_steps = _all_steps(DEPLOY["jobs"]["deploy"])
    checkout = next(
        (s for s in deploy_steps if s.get("uses", "").startswith("actions/checkout")), None
    )
    assert checkout is not None, "deploy job'inda actions/checkout adimi yok."
    ref = checkout.get("with", {}).get("ref", "")
    assert "needs.preflight.outputs.sha" in ref, (
        f"checkout ref={ref!r} -- needs.preflight.outputs.sha referansi yok, "
        "CI'in dogruladigi commit yerine ilerlemis bir main tepesi deploy edilebilir."
    )


def test_deploy_izinleri_salt_okunur():
    """workflow_run'da varsayilan GITHUB_TOKEN yazma alabilir -- acikca
    salt-okunura indirilmeli. `actions: read` elle-tetik CI-dogrulama adimi
    (`gh api actions/workflows/ci.yml/runs`) icin gerekli -- yazma izni yok."""
    perms = DEPLOY.get("permissions") or {}
    assert perms.get("contents") == "read", (
        f"deploy.yml permissions.contents={perms.get('contents')!r} -- 'read' degil."
    )
    assert perms.get("actions") == "read", (
        f"deploy.yml permissions.actions={perms.get('actions')!r} -- 'read' degil."
    )
    assert set(perms.values()) == {"read"}, (
        f"deploy.yml permissions={perms!r} -- 'read' disinda bir deger var (yazma izni sizmis olabilir)."
    )


def test_smoke_job_var_ve_needs_preflight_ve_deploy():
    """Regresyon: eskiden `smoke` job'i TAMAMEN silinse bile mevcut testler
    13/13 yesil kaliyordu -- hicbiri job'in VARLIGINI hic olcmuyordu. Bu test
    hem varligini hem `needs` baglantisini (tam olarak [preflight, deploy])
    dogrudan YAML'dan olcer, duz metin grep'i degil."""
    jobs = DEPLOY["jobs"]
    assert "smoke" in jobs, "deploy.yml'de 'smoke' job'i yok."
    needs = jobs["smoke"].get("needs")
    needs_list = [needs] if isinstance(needs, str) else list(needs or [])
    assert needs_list == ["preflight", "deploy"], (
        f"smoke.needs={needs_list!r} -- tam olarak ['preflight', 'deploy'] degil."
    )


def test_smoke_checkout_dogrulanmis_shayi_kullanir():
    """smoke job'inin checkout adimi da (deploy gibi) preflight'in
    dogruladigi sha'yi kullanmali -- aksi halde deploy edilenden FARKLI bir
    commit smoke-test edilebilir (yanlis pozitif/negatif kanit riski)."""
    smoke_steps = _all_steps(DEPLOY["jobs"]["smoke"])
    checkout = next(
        (s for s in smoke_steps if s.get("uses", "").startswith("actions/checkout")), None
    )
    assert checkout is not None, "smoke job'inda actions/checkout adimi yok."
    ref = checkout.get("with", {}).get("ref", "")
    assert "needs.preflight.outputs.sha" in ref, (
        f"smoke checkout ref={ref!r} -- needs.preflight.outputs.sha referansi yok."
    )


def test_smoke_make_smoke_adimi_ready_ciktisina_bagli():
    """`make smoke` kosan bir adim VAR olmali VE `smoke_check.outputs.ready`
    kapisina bagli olmali -- aksi halde #189 merge olmadan Makefile'da hedef
    yokken adim 'No rule to make target' ile PATLAR (fail-safe delinir)."""
    smoke_steps = _all_steps(DEPLOY["jobs"]["smoke"])
    make_smoke_step = next((s for s in smoke_steps if "make smoke" in (s.get("run") or "")), None)
    assert make_smoke_step is not None, "'make smoke' kosan bir adim bulunamadi."
    step_if = str(make_smoke_step.get("if") or "")
    assert "steps.smoke_check.outputs.ready" in step_if, (
        f"'make smoke' adiminin if={step_if!r} -- steps.smoke_check.outputs.ready kapisina bagli degil."
    )


def test_workflow_dispatch_main_disina_sinirli():
    """Dogrulanmis blocker (S192, Semih): eskiden `preflight.if`
    `github.event_name == 'workflow_dispatch' || (...)` seklinde bare bir
    `||` ile basliyordu -- main DISINDAKI bir dal, CI hic dogrulanmadan elle
    deploy edilebiliyordu. workflow_dispatch artik main-kisitlamasiyla
    VE'lenmis olmali.

    Duz alt-dizgi eslemesi YERINE (anlamca ayni yeniden yazimlar -- sira
    degisimi, `github.ref_name` kullanimi, araya ek guard girmesi -- bunu
    kirardi): (a) 'workflow_dispatch' VE main-kisitlamasinin AYRI AYRI var
    oldugunu, (b) ifadeyi TEPE SEVIYE '||' uzerinden alternatiflere bolup
    workflow_dispatch'i iceren alternatifin TEK BASINA (main kisitlamasi
    olmadan) durmadigini -- yani ciplak bir '||' ile CI-yesil kapisini
    short-circuit ETMEDIGINI -- kontrol eder."""
    assert "workflow_dispatch" in PREFLIGHT_IF, "preflight.if'te workflow_dispatch referansi yok."

    main_kisitlamasi_re = re.compile(r"github\.ref(_name)?\s*==\s*'(refs/heads/)?main'")
    assert main_kisitlamasi_re.search(PREFLIGHT_IF), (
        f"preflight.if={PREFLIGHT_IF!r} -- github.ref(_name)=='(refs/heads/)main' bicimli bir "
        "main-kisitlamasi bulunamadi."
    )

    # Tepe seviye '||' ile boler (bu ifadede parantez ic ice degil -- '&&'
    # gruplari '||' ile ayriliyor, bu yuzden duz split yeterli).
    alternatifler = [alt.strip() for alt in PREFLIGHT_IF.split("||")]
    dispatch_alts = [alt for alt in alternatifler if "workflow_dispatch" in alt]
    assert dispatch_alts, (
        f"preflight.if={PREFLIGHT_IF!r} -- workflow_dispatch iceren alternatif yok."
    )
    # DELIK 4 (S192 sertlestirme): `next(...)` ile YALNIZ ILK workflow_dispatch
    # alternatifine bakmak yeterli DEGIL -- preflight.if'in SONUNA ikinci,
    # ciplak bir workflow_dispatch alternatifi eklenirse ilk (dogru korunmus)
    # alternatif testi gecirir ama yeni ciplak alternatif hic kontrol
    # EDILMEZ. `all(...)` ile TUM workflow_dispatch iceren alternatifler
    # kontrol edilir -- docstring'in "TUM workflow_dispatch iceren
    # alternatifler" iddiasini gercekten karsilar.
    assert all("&&" in alt for alt in dispatch_alts), (
        f"workflow_dispatch iceren alternatiflerden biri '&&' icermiyor "
        f"({dispatch_alts!r}) -- ciplak bir '||' ile CI-yesil kapisinin TAMAMI "
        "short-circuit edilebilir (S192, tuzak 4 regresyonu)."
    )
    assert all(main_kisitlamasi_re.search(alt) for alt in dispatch_alts), (
        f"workflow_dispatch iceren alternatiflerden biri main-kisitlamasi ICERMIYOR "
        f"({dispatch_alts!r}) -- main disindaki bir daldan elle tetik, CI hic "
        "dogrulanmadan gecebilir."
    )


def test_elle_tetikte_ci_dogrulama_adimi_var_ve_basarisizlikta_ci_ok_false_yazar():
    """Elle tetikte, ayni SHA icin basarili (conclusion=success) bir ci.yml
    kosumu YOKSA adim ::error:: basip GITHUB_OUTPUT'a ci_ok=false yazmali --
    artik `exit 1` ile preflight job'ini KIRMAZ (S192 review, acik 2): kapi
    ACIK bir `ci_ok` outputuna needs. ile baglanir (bkz.
    test_deploy_if_hem_has_token_hem_ci_ok_sart_kosar), ortuk needs-
    basarisizlik semantigine guvenilmez."""
    preflight_steps = _all_steps(DEPLOY["jobs"]["preflight"])
    ci_check_step = next((s for s in preflight_steps if s.get("id") == "ci_check"), None)
    assert ci_check_step is not None, "preflight'ta id: ci_check olan bir adim bulunamadi."

    run_body = ci_check_step["run"]
    assert "actions/workflows/ci.yml/runs" in run_body, (
        f"CI-dogrulama adimi ci.yml'in workflow-run listesini sorgulamiyor: {run_body!r}"
    )
    assert "ci_ok=false" in run_body, "Basarisizlik yolunda 'ci_ok=false' yazan bir satir yok."
    assert "ci_ok=true" in run_body, "Basari yolunda 'ci_ok=true' yazan bir satir yok."
    assert "::error::" in run_body, "Basarisizlikta ::error:: ile gorunur bir aciklama basilmiyor."
    assert re.search(r"\bexit 1\b", run_body) is None, (
        "Adim hala 'exit 1' iceriyor -- artik job'i KIRMAMALI, yalniz ci_ok=false yazmali "
        "(S192 review, acik 2: ortuk needs-basarisizlik semantigine degil, acik output'a baglan)."
    )

    # Injection onlemi: SHA/REPO dogrudan ${{ }} ile run govdesine enterpole
    # EDILMEMELI, env uzerinden gecmeli (dosyadaki mevcut FLY_API_TOKEN deseniyle ayni).
    assert "${{ github.sha }}" not in run_body, (
        "github.sha run govdesine dogrudan enterpole edilmis -- env uzerinden verilmeli (injection onlemi)."
    )
    assert "${{ github.repository }}" not in run_body, (
        "github.repository run govdesine dogrudan enterpole edilmis -- env uzerinden verilmeli "
        "(dosyadaki 'github.sha icin uygulanan ama repository icin uygulanmayan' tuzagi kapatildi)."
    )
    # DELIK 2 (S192 sertlestirme): alt-dizgi "herhangi bir degerde var mi"
    # YERINE anahtar-bazli TAM ESITLIK -- aksi halde SHA/REPO degerleri
    # birbiriyle TAKAS edilse de (kopyala-yapistir hatasi) ya da EVENT_NAME
    # "github.event_name == 'push'" gibi bir KARSILASTIRMA ifadesine
    # cevrilse de (runtime'da 'false' -> govde otomatik-yol dalini secer ->
    # gh HIC CAGRILMADAN ci_ok=true olur, fail-open) alt-dizgi kontrolu
    # farki gormezdi.
    step_env = ci_check_step.get("env", {})
    assert _norm_expr(step_env.get("EVENT_NAME", "")) == "${{github.event_name}}", (
        f"CI-dogrulama adiminin env.EVENT_NAME degeri {step_env.get('EVENT_NAME')!r} -- "
        "tam olarak '${{ github.event_name }}' degil (fail-open riski: bir karsilastirma "
        "ifadesine cevrilirse elle tetik CI hic sorgulanmadan gecebilir)."
    )
    assert _norm_expr(step_env.get("SHA", "")) == "${{github.sha}}", (
        f"CI-dogrulama adiminin env.SHA degeri {step_env.get('SHA')!r} -- tam olarak "
        "'${{ github.sha }}' degil (SHA/REPO takasi gibi kopyala-yapistir hatalarina karsi)."
    )
    assert _norm_expr(step_env.get("REPO", "")) == "${{github.repository}}", (
        f"CI-dogrulama adiminin env.REPO degeri {step_env.get('REPO')!r} -- tam olarak "
        "'${{ github.repository }}' degil (SHA/REPO takasi gibi kopyala-yapistir hatalarina karsi)."
    )


def test_ci_dogrulama_sorgusu_event_ve_branch_filtreli():
    """`gh api` sorgusu yalniz head_sha degil, event=push VE branch=main de
    filtrelemeli -- aksi halde ayni SHA icin PR kosusu da (ci.yml
    pull_request'te de kosuyor, tuzak 1) sonuc kumesine girebilir ve
    `.workflow_runs[0]` ortuk siralamaya guvenmis olur."""
    ci_check_step = next(
        (s for s in _all_steps(DEPLOY["jobs"]["preflight"]) if s.get("id") == "ci_check"), None
    )
    assert ci_check_step is not None, "preflight'ta id: ci_check olan bir adim bulunamadi."
    run_body = ci_check_step["run"]
    assert "head_sha=$SHA" in run_body, (
        "gh api sorgusunda 'head_sha=$SHA' filtresi yok -- baska bir commit'in CI kosumu "
        "yanlislikla dogrulanmis sayilabilir."
    )
    assert "event=push" in run_body, "gh api sorgusunda 'event=push' filtresi yok."
    assert "branch=main" in run_body, "gh api sorgusunda 'branch=main' filtresi yok."
    # DELIK 3 (S192 sertlestirme): status=completed filtresi olmadan henuz
    # bitmemis (in_progress/queued) bir ci.yml kosumu da sonuc kumesine
    # girebilir -- conclusion alani boyle bir kosumda anlamli/kararli degildir.
    assert "status=completed" in run_body, "gh api sorgusunda 'status=completed' filtresi yok."
    # GH_TOKEN olmadan `gh api` cagrisi kimliksiz kalir (adim GITHUB_TOKEN'i
    # env uzerinden GH_TOKEN'e aktarmali -- has_token/FLY_API_TOKEN deseniyle
    # ayni yontem).
    step_env = ci_check_step.get("env", {})
    assert _norm_expr(step_env.get("GH_TOKEN", "")) == "${{secrets.GITHUB_TOKEN}}", (
        f"CI-dogrulama adiminin env.GH_TOKEN degeri {step_env.get('GH_TOKEN')!r} -- tam olarak "
        "'${{ secrets.GITHUB_TOKEN }}' degil, 'gh api' cagrisi kimliksiz kalabilir."
    )


def test_ci_check_adiminda_devre_disi_birakan_if_yok():
    """`ci_check` adiminin step-level bir `if:` kosulu OLMAMALI -- adim
    kendi karari icin EVENT_NAME'e (env) bakar (bkz. ISTENEN 1), bu yuzden
    HER iki tetikleyicide de kosmali. Bir `if:` (orn. eski
    `github.event_name == 'workflow_dispatch'` ya da onu sessizce
    'and false' ile notrlestiren bir varyant) adimi tamamen SKIP ederse,
    preflight.outputs.ci_ok hicbir zaman set edilmez ve `deploy.if`teki
    `needs.preflight.outputs.ci_ok == 'true'` DAIMA yanlis kalir -- bu,
    davranis testinin (run govdesini dogrudan calistiran testler) KACIRDIGI
    bir mutasyon sinifidir (adim govdesi degismez, sadece hic CALISMAZ);
    o yuzden ayri, YAML-seviyeli bir kontrol gerekir."""
    ci_check_step = next(
        (s for s in _all_steps(DEPLOY["jobs"]["preflight"]) if s.get("id") == "ci_check"), None
    )
    assert ci_check_step is not None, "preflight'ta id: ci_check olan bir adim bulunamadi."
    assert ci_check_step.get("if") is None, (
        f"ci_check.if={ci_check_step.get('if')!r} -- adim step-level bir 'if' ile devre disi "
        "birakilabilir/kosullandirilabilir; adim HER zaman kosmali, karari EVENT_NAME env'i "
        "uzerinden kendisi vermeli."
    )


def test_preflight_outputs_ci_ok_step_ciktisina_baglanir():
    """`preflight.outputs.ci_ok` dogrudan `steps.ci_check.outputs.ci_ok`'a
    baglanmali -- `has_token`/`token` deseniyle BIREBIR ayni tel."""
    outputs = DEPLOY["jobs"]["preflight"].get("outputs", {})
    assert outputs.get("ci_ok") == "${{ steps.ci_check.outputs.ci_ok }}", (
        f"preflight.outputs.ci_ok={outputs.get('ci_ok')!r} -- steps.ci_check.outputs.ci_ok'a baglanmamis."
    )


def test_preflight_outputs_has_token_step_ciktisina_baglanir():
    """DELIK 5 (S192 sertlestirme): `ci_ok` icin yazilan tam-esitlik
    baglanma testinin esi -- `preflight.outputs.has_token` dogrudan
    `steps.token.outputs.has_token`'a baglanmali. Aksi halde has_token sabit
    'true' gibi bir degere sabitlenebilir ve token-varlik kapisi tamamen
    etkisizlesir (uretim davranis testleri bunu YAKALAMAZ -- output baglantisi
    YAML-seviyeli, run govdesi degismeden delinebilir)."""
    outputs = DEPLOY["jobs"]["preflight"].get("outputs", {})
    assert outputs.get("has_token") == "${{ steps.token.outputs.has_token }}", (
        f"preflight.outputs.has_token={outputs.get('has_token')!r} -- "
        "steps.token.outputs.has_token'a baglanmamis (kapi sabit bir degere sabitlenmis olabilir)."
    )


def test_preflight_outputs_sha_workflow_run_ve_github_sha_fallback_icerir():
    """DELIK 5 (S192 sertlestirme): `ci_ok` icin yazilan tam-esitlik baglanma
    testinin esi -- `preflight.outputs.sha` TAM olarak
    `github.event.workflow_run.head_sha || github.sha` ifadesine esit olmali.
    Bu fallback silinip yalniz `github.sha` birakilirsa, otomatik yolda
    CI'in dogruladigi commit YERINE deploy anindaki dal-tepesi checkout
    edilir -- dosya basliginin "deploy TAM O commit'i checkout eder" vaadi
    sessizce cignenir (run govdesi degismedigi icin davranis testleri
    bunu YAKALAMAZ)."""
    outputs = DEPLOY["jobs"]["preflight"].get("outputs", {})
    assert _norm_expr(outputs.get("sha", "")) == "${{github.event.workflow_run.head_sha||github.sha}}", (
        f"preflight.outputs.sha={outputs.get('sha')!r} -- tam olarak "
        "'${{ github.event.workflow_run.head_sha || github.sha }}' degil "
        "(fallback eksikse otomatik yolda yanlis commit deploy edilir)."
    )


def test_deploy_if_hem_has_token_hem_ci_ok_sart_kosar():
    """S192 review acik 2: deploy job'i yalniz `has_token`'a degil, artik
    `ci_ok` outputuna da ACIKCA baglanmali -- ortuk needs-basarisizlik
    semantigine guvenilmemeli (bkz. deploy.yml basligi, tuzak 5)."""
    deploy_if = str(DEPLOY["jobs"]["deploy"].get("if") or "")
    assert "needs.preflight.outputs.has_token == 'true'" in deploy_if, (
        f"deploy.if={deploy_if!r} -- has_token kontrolu yok."
    )
    assert "needs.preflight.outputs.ci_ok == 'true'" in deploy_if, (
        f"deploy.if={deploy_if!r} -- ci_ok kontrolu yok (S192 review acik 2)."
    )
    assert "&&" in deploy_if, (
        "deploy.if iki kosulu '&&' ile birlestirmiyor (biri digerini muaf tutabilir)."
    )


# --- Davranis testi: ci_check adiminin run govdesini YAML'dan cikarip
# GERCEKTEN bash altinda calistirir (metnin kopyasi/yeniden-yazimi DEGIL) --
# PATH'e sahte bir `gh` konur, ag erisimi YOK.
#
# Sahte `gh`, `--jq` argumanini (run govdesindeki GERCEK filtre metnini)
# alip sistem `jq` binary'sine (ag erisimi gerektirmez, salt yerel islem)
# uydurma bir JSON govdesi uzerinden GERCEKTEN uygular -- boylece filtrenin
# KENDISINE yapilan bir mutasyon (orn. `// "none"` -> `// "success"`, fail-
# open) da testi kirar; yalniz "gh sunu dondursun" diye sabitlenmis bir
# ciktiyi taklit etmek bu mutasyonu KACIRIRDI.
_JQ_ON_PATH = shutil.which("jq") is not None

_FAKE_GH_SCRIPT = """#!/usr/bin/env bash
set -u
if [ "${GH_FAKE_EXIT:-0}" != "0" ]; then
  echo "gh: simulated API failure" >&2
  exit "${GH_FAKE_EXIT}"
fi
# gercek cagri sekli: gh api "<url>" --jq '<filter>' -- filtre HER ZAMAN son
# argumandir; run govdesindeki filtre metni AYNEN buraya ulasir (mutasyona
# acik kalir).
filter="${@: -1}"
case "${GH_FAKE_RUNS:-empty}" in
  success) payload='{"workflow_runs": [{"conclusion": "success"}]}' ;;
  failure) payload='{"workflow_runs": [{"conclusion": "failure"}]}' ;;
  *)       payload='{"workflow_runs": []}' ;;
esac
echo "$payload" | jq -r "$filter"
"""


def _ci_check_run_body() -> str:
    step = next(s for s in _all_steps(DEPLOY["jobs"]["preflight"]) if s.get("id") == "ci_check")
    return step["run"]


def _run_ci_check(
    tmp_path: Path, *, event_name: str, gh_runs: str = "empty", gh_exit: str = "0"
) -> dict:
    """`ci_check` adiminin run govdesini GERCEKTEN calistirir ve
    GITHUB_OUTPUT dosyasini + exit kodunu dondurur. GitHub Actions Linux
    runner'larinin varsayilan bash bayraklariyla ayni kabukla kosar:
    `bash --noprofile --norc -eo pipefail {0}`. `gh_runs`: 'empty' (hic
    kosum yok) | 'success' | 'failure' -- sahte gh'nin uretecegi
    `workflow_runs` listesini secer, GERCEK jq filtresi buna uygulanir."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake_gh = bin_dir / "gh"
    fake_gh.write_text(_FAKE_GH_SCRIPT)
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    run_script = tmp_path / "run.sh"
    run_script.write_text(_ci_check_run_body())
    run_script.chmod(run_script.stat().st_mode | stat.S_IEXEC)

    output_file = tmp_path / "github_output.txt"
    output_file.write_text("")

    env = {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "EVENT_NAME": event_name,
        "SHA": "deadbeefcafe",
        "REPO": "FatihErenCetin/grup54",
        "GITHUB_OUTPUT": str(output_file),
        "GH_FAKE_RUNS": gh_runs,
        "GH_FAKE_EXIT": gh_exit,
        "GH_TOKEN": "fake-token-not-used-by-fake-gh",
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(run_script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    outputs: dict[str, str] = {}
    for line in output_file.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            outputs[key] = value
    return {
        "outputs": outputs,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@pytest.mark.skipif(not _JQ_ON_PATH, reason="jq PATH'te yok -- sahte gh gercek jq'ya delege eder.")
def test_ci_check_govdesi_basarida_ci_ok_true_yazar(tmp_path):
    res = _run_ci_check(tmp_path, event_name="workflow_dispatch", gh_runs="success")
    assert res["returncode"] == 0, res
    assert res["outputs"].get("ci_ok") == "true", res


@pytest.mark.skipif(not _JQ_ON_PATH, reason="jq PATH'te yok -- sahte gh gercek jq'ya delege eder.")
def test_ci_check_govdesi_basarisizlikta_ci_ok_false_yazar(tmp_path):
    res = _run_ci_check(tmp_path, event_name="workflow_dispatch", gh_runs="failure")
    assert res["returncode"] == 0, res
    assert res["outputs"].get("ci_ok") == "false", res
    assert "::error::" in res["stdout"], f"Basarisizlikta ::error:: basilmadi: {res}"


@pytest.mark.skipif(not _JQ_ON_PATH, reason="jq PATH'te yok -- sahte gh gercek jq'ya delege eder.")
def test_ci_check_govdesi_bos_listede_fail_closed(tmp_path):
    """En kritik vaka: hic ci.yml kosumu YOKSA (`workflow_runs` BOS liste)
    fail-CLOSED olmali (ci_ok=false), fail-OPEN DEGIL -- bu repo'da cc9ebca
    ile ayiklanmis anti-kalibin (`// "none"` -> `// "success"`) AYNISI
    burada da bir regresyon olarak geri gelmemeli. Sahte gh, run govdesindeki
    GERCEK jq filtresini bos bir `workflow_runs` uzerinde calistirir --
    filtrenin varsayilan-deger kismina yapilan bir mutasyon da bu testi kirar."""
    res = _run_ci_check(tmp_path, event_name="workflow_dispatch", gh_runs="empty")
    assert res["returncode"] == 0, res
    assert res["outputs"].get("ci_ok") == "false", res


def test_ci_check_govdesi_gh_api_hatasinda_ci_ok_false_yazar(tmp_path):
    """gh sifir-disi exit ile donerse (API hatasi) de fail-CLOSED: ci_ok=false,
    VE adim `set -e` altinda job'i cokertmeden gorunur bir sekilde durmali
    (returncode==0 -- artik `exit 1` YOK, S192 review acik 2)."""
    res = _run_ci_check(tmp_path, event_name="workflow_dispatch", gh_exit="1")
    assert res["returncode"] == 0, (
        f"Adim gh basarisizliginda beklenmedik sekilde sifir-disi exit ile bitti: {res}"
    )
    assert res["outputs"].get("ci_ok") == "false", res
    assert "::error::" in res["stdout"], f"gh basarisizliginda ::error:: basilmadi: {res}"


def test_ci_check_govdesi_otomatik_yolda_daima_ci_ok_true_yazar(tmp_path):
    """workflow_run (otomatik) yolunda adim gh'a hic BAKMADAN ci_ok=true
    yazmali -- o yolda kapi zaten workflow_run.conclusion ile saglaniyor
    (preflight.if). gh burada BILEREK basarisiz/failure donecek sekilde
    kuruludur -- adim gh'i hic CAGIRMADIGINI dolayli olarak kanitlar: gh
    cagrilsaydi ci_ok=false/kirilma olurdu, ama sonuc yine de true."""
    res = _run_ci_check(tmp_path, event_name="workflow_run", gh_exit="1", gh_runs="failure")
    assert res["returncode"] == 0, res
    assert res["outputs"].get("ci_ok") == "true", res


def test_deploy_permissions_actions_read_icerir():
    """`gh api actions/workflows/ci.yml/runs` cagrisi icin `actions: read`
    sart -- olmadan elle-tetik CI-dogrulama adimi 403 ile patlar (deploy
    hicbir zaman kosamaz, sessiz degil ama beklenmedik bir kirmizi)."""
    assert DEPLOY.get("permissions", {}).get("actions") == "read", (
        f"deploy.yml permissions={DEPLOY.get('permissions')!r} -- 'actions: read' yok."
    )


def test_setup_flyctl_pinli_ve_remote_only():
    """setup-flyctl `master`/`main`/`latest`'e PINLENMEMIS olmamali (repo
    konvansiyonu hareketli pin'i reddeder) ve flyctl deploy `--remote-only`
    ile kosmali."""
    forbidden_refs = {"master", "main", "latest"}
    all_steps = _all_steps(DEPLOY["jobs"]["preflight"]) + _all_steps(DEPLOY["jobs"]["deploy"])

    setup_step = next(
        (s for s in all_steps if "flyctl-actions/setup-flyctl" in s.get("uses", "")), None
    )
    assert setup_step is not None, "superfly/flyctl-actions/setup-flyctl adimi bulunamadi."
    ref = setup_step["uses"].split("@")[-1]
    assert ref not in forbidden_refs, (
        f"setup-flyctl {ref!r}'e pinli -- hareketli pin repo konvansiyonunu ihlal eder."
    )

    deploy_run_step = next((s for s in all_steps if "flyctl deploy" in (s.get("run") or "")), None)
    assert deploy_run_step is not None, "'flyctl deploy' kosan bir adim bulunamadi."
    assert "--remote-only" in deploy_run_step["run"], (
        "flyctl deploy '--remote-only' bayragi olmadan kosuyor."
    )


def test_deploy_shell_bash_defaults_acik_belirtilir():
    """DELIK 6 (S192 sertlestirme): bu dosyanin test harness'i ('_run_ci_check')
    GitHub'in Linux runner varsayilaniymis GIBI davranarak `bash --noprofile
    --norc -eo pipefail {0}` ile kosar -- ama GitHub'in GERCEK varsayilani
    (hicbir `shell:` belirtilmemisse) `pipefail` OLMAYAN `bash -e`dir. Bugun
    govdede pipe yok, fark uretmiyor, ama latent bir fail-open: govdeye
    ileride bir pipe girerse (`cmd1 | cmd2`), uretimde ilk komutun hatasi
    sessizce yutulur -- test bunu pipefail altinda kostugu icin YAKALAYAMAZ,
    yani test uretimden DAHA SIKI olurdu. `defaults.run.shell: bash` acikca
    beyan edilerek uretim GERCEKTEN pipefail'li hale getirilir (GitHub Actions
    bash icin bu beyani gordugunde `-eo pipefail` bayraklarini ekler) -- test
    harness'inin iddiasi boylece dogru olur."""
    defaults = DEPLOY.get("defaults") or {}
    run_defaults = defaults.get("run") or {}
    assert run_defaults.get("shell") == "bash", (
        f"deploy.yml defaults.run.shell={run_defaults.get('shell')!r} -- 'bash' degil; "
        "GitHub'in gercek varsayilani pipefail'siz 'bash -e'dir, workflow'un kendi "
        "pipefail iddiasi acikca beyan edilmeden dogru olmaz."
    )


def test_tum_workflowlar_gecerli_yaml_ve_her_job_runs_on_iceriyor():
    """Repo genelinde sanity: bugune kadar workflow YAML'ini parse eden
    hicbir test yoktu -- bu, gercek bir bosluktu."""
    workflows = list(WORKFLOWS_DIR.glob("*.yml"))
    assert workflows, f"{WORKFLOWS_DIR} altinda hic workflow bulunamadi."
    for wf_path in workflows:
        wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
        assert isinstance(wf, dict), f"{wf_path.name} gecerli bir YAML mapping'i degil."
        jobs = wf.get("jobs")
        assert jobs, f"{wf_path.name} 'jobs' tanimlamiyor."
        for job_id, job in jobs.items():
            assert "runs-on" in job, f"{wf_path.name}:{job_id} 'runs-on' tanimlamiyor."
