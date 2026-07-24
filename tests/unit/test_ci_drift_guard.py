"""#56 — openapi.json <-> TS client drift-check'in CI'daki bağlantı dokusunu
statik olarak doğrular. Bkz. docs/kontrat-drift-guardrail.md.

Bu testler ".github/workflows/ci.yml"i PyYAML ile parse eder. PyYAML burada
YENİ bir bağımlılık DEĞİL: "ensemble-shared" (src/shared/pyproject.toml)
PyYAML>=6.0'ı doğrudan bağımlılık olarak taşıyor ve kök `ensemble` paketi
workspace üzerinden ona bağımlı — `uv sync --all-packages` zaten kurar.

Anti-tautoloji notu (PR gövdesinde de raporlanır): her iki test de kasıtlı
mutasyonla kırmızıya döndürülüp geri alınarak doğrulandı — testler gerçekten
bir şey ölçüyor, hep yeşil kalan boş iskeletler değil.
"""

from pathlib import Path

import yaml

CI_YML = Path(__file__).parent.parent.parent / ".github" / "workflows" / "ci.yml"


def _load_ci_yaml() -> dict:
    assert CI_YML.exists(), f"CI workflow bulunamadı: {CI_YML}"
    # NOT: YAML'da "on:" anahtarı PyYAML tarafından bool True'ya çözülebilir
    # (YAML 1.1 sözlüğü); bu testler yalnız "jobs" ağacını okuduğu için
    # etkilenmiyor ama bilinçli not düşülüyor.
    return yaml.safe_load(CI_YML.read_text(encoding="utf-8"))


def _find_step(steps: list[dict], name: str) -> dict:
    for step in steps:
        if step.get("name") == name:
            return step
    raise AssertionError(f"'{name}' adımı bulunamadı. Adımlar: {[s.get('name') for s in steps]}")


def test_client_drift_pathspec_cwd_goreli():
    """
    `frontend` job'ının working-directory'si "src/frontend" olduğu için
    "Client tip drift-check" adımındaki git pathspec CWD'YE GÖRELİ yazılmak
    ZORUNDA ("src/api/schema.d.ts"), repo-kökü stilinde DEĞİL
    ("src/frontend/src/api/schema.d.ts").

    Neden önemli: bu tam olarak geçmişte gerçekleşmiş bir regresyon sınıfı
    (commit 3bd3bff, "adversarial dogrulama bulgulari - CI pathspec no-op'u").
    Yanlış pathspec FAIL-OPEN'dır: git diff --exit-code sessizce 0 döner,
    check yeşil kalır, kimse fark etmez (birinci-elden ölçüldü — bkz.
    docs/kontrat-drift-guardrail.md §4).

    Mutasyon kanıtı: pathspec'i kasten "src/frontend/src/api/schema.d.ts"
    yapıp bu testi tekrar çalıştırdım -> kırmızı oldu; geri alınca yeşile
    döndü (PR gövdesinde rapor edildi).
    """
    doc = _load_ci_yaml()
    frontend_job = doc["jobs"]["frontend"]

    working_dir = frontend_job.get("defaults", {}).get("run", {}).get("working-directory")
    assert working_dir == "src/frontend", (
        f"frontend job'ının working-directory'si beklenenden farklı: {working_dir!r}. "
        "Bu test yalnız working-directory=src/frontend varsayımı altında pathspec'i "
        "doğrular; job defaults'u değiştiyse bu testi de güncelle."
    )

    step = _find_step(frontend_job["steps"], "Client tip drift-check")
    run_script = step["run"]

    assert "src/api/schema.d.ts" in run_script, (
        "'Client tip drift-check' adımı schema.d.ts'e artık dokunmuyor gibi görünüyor "
        f"— run script:\n{run_script}"
    )
    assert "src/frontend/src/api/schema.d.ts" not in run_script, (
        "Pathspec repo-kökü stilinde yazılmış ('src/frontend/src/api/schema.d.ts'). "
        "working-directory=src/frontend olduğu için bu, git'in aramayı "
        "'src/frontend/src/frontend/src/api/schema.d.ts' altında yapmasına yol açar "
        "-> hiçbir dosyayla eşleşmez -> `git diff --exit-code` SESSİZCE exit 0 döner "
        "(fail-open no-op). Doğru pathspec CWD'ye göreli olmalı: 'src/api/schema.d.ts'. "
        "Detay: docs/kontrat-drift-guardrail.md §4."
    )


def test_drift_adimlari_zorunlu_joblarda():
    """
    Coupling belgesi (güvenlik kapısı DEĞİL — job yeniden adlandırma GitHub'da
    fail-closed'dır, required-context eksik kalınca PR pending'de bekler,
    sessizce geçmez). Asıl koruduğu şey: birinin "OpenAPI drift-check"i
    `lint-test`'ten ya da "Client tip drift-check"i `frontend`'den alıp ayrı,
    zorunlu-OLMAYAN bir job'a taşıması/silmesi — bu FAIL-OPEN'dır ve bugünkü
    zorlayıcı kapıları (main required check listesi
    = ["lint-test", "check-single-issue", "frontend"]) yok eder.

    Mutasyon kanıtı 1: "OpenAPI drift-check" adımını `lint-test`'ten silip yeni
    bir job'a taşıdım -> bu test kırmızı oldu; geri alınca yeşile döndü (PR
    gövdesinde rapor edildi).

    Mutasyon kanıtı 2: `ci.yml`'deki "Client tip drift-check" adımının
    `git diff --exit-code -- src/api/schema.d.ts` satırını sildim (yalnız
    `npm run gen:api` kaldı) -> bu test kırmızı oldu (yeni assert olmadan önce
    bu mutasyonla yeşil kalıyordu — asimetrinin kanıtı); satırı geri koyunca
    yeşile döndü.
    """
    doc = _load_ci_yaml()
    jobs = doc["jobs"]

    assert "lint-test" in jobs, "main branch protection'ın zorunlu context'i 'lint-test' — job kayboldu."
    assert "frontend" in jobs, "'Client tip drift-check' adımının yaşadığı 'frontend' job'ı kayboldu."

    openapi_step = _find_step(jobs["lint-test"]["steps"], "OpenAPI drift-check")
    run_script = openapi_step["run"]
    assert "make openapi" in run_script, (
        "'OpenAPI drift-check' adımı artık 'make openapi' çalıştırmıyor — "
        f"run script:\n{run_script}"
    )
    assert "git diff --exit-code src/shared/openapi.json" in run_script, (
        "'OpenAPI drift-check' adımı artık openapi.json'ı `git diff --exit-code` ile "
        f"doğrulamıyor — run script:\n{run_script}"
    )

    client_step = _find_step(jobs["frontend"]["steps"], "Client tip drift-check")
    run_script = client_step["run"]
    assert "npm run gen:api" in run_script, (
        "'Client tip drift-check' adımı artık 'npm run gen:api' çalıştırmıyor — "
        f"run script:\n{run_script}"
    )
    assert "git diff --exit-code -- src/api/schema.d.ts" in run_script, (
        "'Client tip drift-check' adımı artık schema.d.ts'i `git diff --exit-code` ile "
        "doğrulamıyor — bu asimetri, tüm client diff bloğu silinse bile bu testin yeşil "
        f"kalmasına yol açardı (fail-open). run script:\n{run_script}"
    )
