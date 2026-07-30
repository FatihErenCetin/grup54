"""#342 — `rebuild` toplu işinin İKİ bütçesi de kod'dan gelir (env'e bağlı değil).

Ölçüldü (30 Tem, canlı sunucu): `#337` deploy'undan sonra zorunlu tek-seferlik
rebuild **ilk 429'da düştü** (`GeminiTransientError: 429 RESOURCE_EXHAUSTED ...
Please retry in 49.1s`). Kök neden yarısı düşünülmüş bir ayardı: `rebuild.py`
kendisinin toplu iş olduğunu bilip **bekleme tavanını** 120 sn'ye yükseltiyor
ama **deneme sayısını** yükseltmiyordu. Sunucuda D-54 ile
`GEMINI_MAX_RETRIES=1` sabit — süreç "120 saniye beklemeye razı ama hiç
beklemeye fırsat bulamıyor" durumundaydı. Elle `-e GEMINI_MAX_RETRIES=12`
verilince aynı komut ilerledi.

Bu dosya GERÇEK giriş noktasını (`python -m ensemble.store.rebuild`, yani
`make rebuild`'in ve runbook'un koştuğu komut) alt süreç olarak çalıştırır —
sabiti okuyup kendisiyle karşılaştıran totolojik bir kontrol DEĞİL. Süreç,
`__main__` bloğunun ilk satırlarında etkin bütçeyi basar; biz ENV'de
**kasten 1** verip çıktının 12 dediğini doğrularız.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from ensemble.store.rebuild import _TOPLU_IS_BEKLEME_SINIRI_S, _TOPLU_IS_DENEME_SAYISI

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "src" / "backend"


def _rebuild_ciktisi(env_uzerine: dict[str, str]) -> str:
    """`python -m ensemble.store.rebuild`'i koşup stdout+stderr döndürür.

    Süreç, gerçek bir GitHub App olmadığı için D-51 fail-closed kapısına
    çarpıp SystemExit ile biter — DB'ye DOKUNMAZ. Bütçe satırı o kapıdan
    ÖNCE basılır (bilerek: "hangi bütçeyle koşuyorum" sorusu işin en başında
    yanıtlanmalı).
    """
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": "sqlite:///:memory:",
            "ENSEMBLE_ALLOW_FAKE_SEED": "0",
            "PYTHONPATH": os.pathsep.join(
                [str(_BACKEND), env["PYTHONPATH"]] if "PYTHONPATH" in env else [str(_BACKEND)]
            ),
        }
    )
    env.pop("GITHUB_APP_ID", None)
    env.pop("GITHUB_APP_PRIVATE_KEY", None)
    env.pop("GITHUB_APP_PRIVATE_KEY_PATH", None)
    env.update(env_uzerine)

    sonuc = subprocess.run(
        [sys.executable, "-m", "ensemble.store.rebuild"],
        env=env,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return sonuc.stdout + sonuc.stderr


def test_toplu_is_deneme_butcesini_ENV_1_OLSA_BILE_yukseltir():
    """MUTASYON KİLİDİ: `__main__` içindeki `model_copy(...)` sözlüğünden
    `"GEMINI_MAX_RETRIES"` satırını sil → çıktı `GEMINI_MAX_RETRIES=1` olur
    ve bu test kırmızı olur.

    D-54'ün `=1` kararı İNTERAKTİF yol için doğru; toplu yol için yanlış
    (embed kotası DAKİKALIK, beklemek gerçekten işe yarıyor). Bu test tam da
    o ayrımı kilitler: env 1 der, toplu iş 12 ile koşar.
    """
    cikti = _rebuild_ciktisi({"GEMINI_MAX_RETRIES": "1"})

    eslesme = re.search(r"GEMINI_MAX_RETRIES=(\d+)", cikti)
    assert eslesme, f"toplu iş bütçe satırı basılmadı:\n{cikti}"
    assert int(eslesme.group(1)) == _TOPLU_IS_DENEME_SAYISI, (
        "rebuild toplu iş olduğunu bildiği hâlde ENV'in interaktif deneme "
        f"bütçesiyle koşuyor (çıktı: {eslesme.group(0)}) — ilk 429 işi bitirir"
    )
    assert _TOPLU_IS_DENEME_SAYISI > 1, "tek denemelik toplu iş hiç bekleyemez"


def test_toplu_is_bekleme_tavanini_da_yukseltir():
    """İkiz bütçe hâlâ yerinde: iki bütçe ancak BİRLİKTE anlamlı (deneme hakkı
    olmadan tavan, tavan olmadan deneme hakkı işe yaramaz)."""
    cikti = _rebuild_ciktisi({"GEMINI_RETRY_AFTER_CAP_S": "10"})

    eslesme = re.search(r"GEMINI_RETRY_AFTER_CAP_S=([\d.]+)", cikti)
    assert eslesme, f"toplu iş bütçe satırı basılmadı:\n{cikti}"
    assert float(eslesme.group(1)) == _TOPLU_IS_BEKLEME_SINIRI_S


def test_env_daha_comert_verirse_kirpilmaz():
    """Bütçeler TABAN'dır, tavan değil: operatör bilerek daha büyük bir değer
    verirse toplu iş onu KÜÇÜLTMEZ (`max(...)`, düz atama değil)."""
    cikti = _rebuild_ciktisi(
        {"GEMINI_MAX_RETRIES": "30", "GEMINI_RETRY_AFTER_CAP_S": "300"}
    )

    assert "GEMINI_MAX_RETRIES=30" in cikti
    assert "GEMINI_RETRY_AFTER_CAP_S=300" in cikti


def test_runbook_rebuild_KOMUTU_env_override_tasimaz():
    """#342 kabul kriteri: runbook'taki rebuild KOMUTU artık elle
    `-e GEMINI_MAX_RETRIES=...` geçmemeli — bütçe kodda.

    MUTASYON: runbook'a `docker compose exec -e GEMINI_MAX_RETRIES=12 api
    python -m ensemble.store.rebuild` satırını geri koy → bu test kırmızı olur.

    KOMUTU ölçer, CÜMLEYİ değil (aynı disiplin `test_deploy_runbook.py`'de de
    var). İlk yazdığım hâli satır bazlıydı ve KENDİ runbook düzenlememi
    yanlış kırmızıya düşürdü: anahtar tablosundaki 25. satır hem
    `python -m ensemble.store.rebuild`'den hem `GEMINI_MAX_RETRIES`'ten söz
    eder ama bir komut DEĞİLDİR — tam da "artık override gerekmiyor" diyen
    düzyazıdır. Markdown'da komut ya bir backtick aralığındadır ya da fenced
    blok satırının kendisidir; ihlal ancak İKİSİ AYNI aralıkta geçerse vardır.
    """
    metin = (_REPO_ROOT / "docs" / "deploy-runbook.md").read_text(encoding="utf-8")
    ihlaller: list[tuple[int, str]] = []
    for no, satir in enumerate(metin.splitlines(), 1):
        araliklar = re.findall(r"`([^`]+)`", satir) or ([] if "`" in satir else [satir])
        for aralik in araliklar:
            if "ensemble.store.rebuild" in aralik and "GEMINI_MAX_RETRIES=" in aralik:
                ihlaller.append((no, aralik.strip()))

    assert not ihlaller, (
        "runbook rebuild komutu hâlâ elle retry override'ı taşıyor "
        f"(bütçe koddan gelmeli): {ihlaller}"
    )
