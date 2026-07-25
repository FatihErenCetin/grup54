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

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS_DIR / name).read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    """`on:` anahtarini dondurur (PyYAML 1.1: `on` -> `True` anahtar tuzagi)."""
    return wf.get("on", wf.get(True, {}))


def _all_workflows() -> list[tuple[str, dict]]:
    return [(p.name, yaml.safe_load(p.read_text(encoding="utf-8"))) for p in sorted(WORKFLOWS_DIR.glob("*.yml"))]


def _all_steps(job: dict) -> list[dict]:
    return job.get("steps", []) or []


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
    """Elle kacis kapisi: workflow_run yalniz varsayilan daldan tetiklenir,
    bu yuzden workflow_dispatch olmadan deploy.yml ilk PR'da hic denenemez."""
    deploy_on = _triggers(DEPLOY)
    assert "workflow_dispatch" in deploy_on, "workflow_dispatch kacis kapisi kayboldu."


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
    """Generik: `flyctl` kosan HER job, bir `has_token` output'u ureten job'a
    `needs` ile baglanmali VE `if`'i o output'u referans almali -- yarin
    ikinci bir flyctl job'i eklenirse bu test onu da yakalar."""
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


def test_token_degeri_asla_loglanmaz():
    """Hijyen: hicbir `run:` adimi FLY_API_TOKEN'in DEGERINI echo/printf ile
    yazdirmiyor ve GITHUB_OUTPUT/GITHUB_ENV'e degeri yazmiyor; `${{ secrets.
    FLY_API_TOKEN }}` yalniz `env:`/`with:` haritalarinda gecmeli, `run:`
    metninde degil. (Var-mi-yok-mu kontrolu -- `[ -n "$FLY_API_TOKEN" ]` --
    degeri LOGLAMADIGI icin bilincli olarak SERBEST birakilir.)"""
    # echo/printf + ayni satirda $FLY_API_TOKEN -> degeri stdout'a yazdirir.
    echo_leak_re = re.compile(r"\b(echo|printf)\b[^\n]*\$\{?FLY_API_TOKEN\}?")
    # $FLY_API_TOKEN degeri ayni satirda GITHUB_OUTPUT/GITHUB_ENV'e akiyor.
    output_leak_re = re.compile(r"\$\{?FLY_API_TOKEN\}?[^\n]*>>\s*\"?\$\{?(GITHUB_OUTPUT|GITHUB_ENV)\}?\"?")

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
    checkout = next((s for s in deploy_steps if s.get("uses", "").startswith("actions/checkout")), None)
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
    assert perms.get("contents") == "read", f"deploy.yml permissions.contents={perms.get('contents')!r} -- 'read' degil."
    assert perms.get("actions") == "read", f"deploy.yml permissions.actions={perms.get('actions')!r} -- 'read' degil."
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
    checkout = next((s for s in smoke_steps if s.get("uses", "").startswith("actions/checkout")), None)
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
    deploy edilebiliyordu. workflow_dispatch artik `github.ref ==
    'refs/heads/main'` ile VE'lenmis olmali."""
    assert "workflow_dispatch' && github.ref == 'refs/heads/main'" in PREFLIGHT_IF, (
        f"preflight.if={PREFLIGHT_IF!r} -- workflow_dispatch, github.ref=='refs/heads/main' "
        "ile VE'lenmemis (bare '||' hala kapinin TAMAMINI short-circuit edebilir)."
    )


def test_elle_tetikte_ci_dogrulama_adimi_var_ve_basarisizlikta_durur():
    """Elle tetikte, ayni SHA icin basarili (conclusion=success) bir ci.yml
    kosumu YOKSA adim ::error:: verip exit 1 ile durmali -- preflight
    basarisiz olur, `needs: preflight` uzerinden deploy job'i hic
    denenmez."""
    preflight_steps = _all_steps(DEPLOY["jobs"]["preflight"])
    ci_check_step = next(
        (
            s
            for s in preflight_steps
            if "workflow_dispatch" in str(s.get("if") or "") and "gh api" in (s.get("run") or "")
        ),
        None,
    )
    assert ci_check_step is not None, (
        "preflight'ta workflow_dispatch'e ozel, 'gh api' kosan bir CI-dogrulama adimi bulunamadi."
    )
    run_body = ci_check_step["run"]
    assert "actions/workflows/ci.yml/runs" in run_body, (
        f"CI-dogrulama adimi ci.yml'in workflow-run listesini sorgulamiyor: {run_body!r}"
    )
    assert "exit 1" in run_body, "CI-dogrulama adimi basarisizlikta exit 1 ile durmuyor."
    # Injection onlemi: SHA dogrudan ${{ }} ile run govdesine enterpole EDILMEMELI,
    # env uzerinden gecmeli (dosyadaki mevcut FLY_API_TOKEN deseniyle ayni).
    assert "${{ github.sha }}" not in run_body, (
        "github.sha run govdesine dogrudan enterpole edilmis -- env uzerinden verilmeli (injection onlemi)."
    )
    step_env = ci_check_step.get("env", {})
    assert any("github.sha" in str(v) for v in step_env.values()), (
        "CI-dogrulama adiminin env'inde github.sha referansi yok -- SHA hicbir yerden gecmiyor olabilir."
    )


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

    setup_step = next((s for s in all_steps if "flyctl-actions/setup-flyctl" in s.get("uses", "")), None)
    assert setup_step is not None, "superfly/flyctl-actions/setup-flyctl adimi bulunamadi."
    ref = setup_step["uses"].split("@")[-1]
    assert ref not in forbidden_refs, f"setup-flyctl {ref!r}'e pinli -- hareketli pin repo konvansiyonunu ihlal eder."

    deploy_run_step = next((s for s in all_steps if "flyctl deploy" in (s.get("run") or "")), None)
    assert deploy_run_step is not None, "'flyctl deploy' kosan bir adim bulunamadi."
    assert "--remote-only" in deploy_run_step["run"], "flyctl deploy '--remote-only' bayragi olmadan kosuyor."


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
