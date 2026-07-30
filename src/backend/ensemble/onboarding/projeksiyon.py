"""Sihirbaz yazdıktan SONRA board'u dolduran DAR ve EKLEYİCİ yol (#340).

Neden ayrı bir modül ve neden `rebuild_projection` DEĞİL
--------------------------------------------------------
Board bir **DB projeksiyonudur**, `.harness/`'i canlı okumaz. Sihirbaz
dosyaları yazdıktan sonra bir şey projeksiyonu tazelemezse kullanıcı
*"yazdı ama hiçbir şey olmadı"* görür. Bu yüzden başarı ekranı önce
`make rebuild` çalıştırmayı söylüyordu — ama o komut **hedef kurulumda
çalışmıyor**: gerçek bir GitHub App yapılandırılmamış yeni bir projede
rebuild fail-closed kapıya çarpıp reddediliyor (D-51: sahte veri gerçek
DB'nin üstüne yazılmaz). Yani sihirbazın son adımı, yeni kullanıcı için
kapalı bir kapıya işaret ediyordu.

Akla gelen çözüm — `rebuild_projection(session, harness, github=None)` —
**VERİ KAYBETTİRİR** (ölçüldü, 30 Tem): o fonksiyon `EventRow`'ları
KOŞULSUZ siler, ama yalnız `github` verilmişse geri doldurur. `github=None`
ile çağırmak tüm olay geçmişini (Activity akışı, dokunma grafı, board
geçişleri) YOK EDER. Yani "GitHub gerektirmeyen güvenli yol" gibi görünen
çağrı, sessizce yıkıcıdır.

Bu modül onun yerine yalnız **eksik kartları ekler**:
  * hiçbir şey SİLMEZ,
  * var olan bir satırı EZMEZ (`.harness` kazanır ama mevcut satır korunur —
    `Projector.upsert_issue_cards` ile aynı ilke),
  * art arda çağrılabilir (idempotent).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ensemble.store.models import TaskProjectionRow
from ensemble_shared.harness import HarnessPort

logger = logging.getLogger("ensemble.onboarding.projeksiyon")


def eksik_kartlari_ekle(
    session: Session, harness: HarnessPort, *, repo_full_name: str
) -> int:
    """`.harness/tasks/` içindeki, projeksiyonda KARŞILIĞI OLMAYAN görevler
    için kart açar. Dönen sayı EKLENEN kart adedidir.

    Silme yok, üzerine yazma yok — bu yüzden mevcut bir kurulumda çağrılması
    güvenlidir ve sihirbazın yeni yazdığı görevler board'da anında görünür.
    """
    mevcut = {
        satir.task_id
        for satir in session.query(TaskProjectionRow)
        .filter_by(repo_full_name=repo_full_name)
        .all()
    }
    eklenen = 0
    for gorev in harness.read_tasks():
        task_id = str(gorev.get("task_id") or "").strip()
        if not task_id or task_id in mevcut:
            continue
        session.add(TaskProjectionRow.from_harness(gorev, repo_full_name=repo_full_name))
        mevcut.add(task_id)
        eklenen += 1
    if eklenen:
        session.commit()
        logger.info("onboarding: projeksiyona %d yeni kart eklendi", eklenen)
    return eklenen
