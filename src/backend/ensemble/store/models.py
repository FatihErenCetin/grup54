"""SQLAlchemy 2.0 modelleri — projeksiyon tabloları (#41).

NormalizedEvent (#16) ve .harness/ (#13) verisinin hızlı-sorgu projeksiyonu.
Kanonik DEĞİL — .harness/ + GitHub her zaman kazanır; bu tablolar
rebuild_projection() ile yeniden kurulabilir (rebuildable cache).

users/accounts/profiles tablosu YOK (kapsam-sinirlari.md: kapsam dışı).
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ensemble.models import BoardCard, NormalizedEvent


class Base(DeclarativeBase):
    """Tüm projeksiyon tablolarının temel sınıfı."""


class EventRow(Base):
    """NormalizedEvent'in DB projeksiyonu — ingest çıktısı (#16)."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(255), index=True)
    branch: Mapped[str | None] = mapped_column(String(255))
    files: Mapped[list] = mapped_column(JSON, default=list)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    ref: Mapped[str] = mapped_column(String(255))

    def to_domain(self) -> NormalizedEvent:
        """DB satırından Pydantic modeline dönüştür."""
        return NormalizedEvent(
            id=self.id,
            type=self.type,
            actor=self.actor,
            branch=self.branch,
            files=self.files,
            ts=self.ts,
            ref=self.ref,
        )

    @classmethod
    def from_domain(cls, event: NormalizedEvent) -> "EventRow":
        """Pydantic modelinden DB satırına dönüştür."""
        return cls(
            id=event.id,
            type=event.type,
            actor=event.actor,
            branch=event.branch,
            files=event.files,
            ts=event.ts,
            ref=event.ref,
        )


class TaskProjectionRow(Base):
    """.harness/tasks/ projeksiyonu — board'ın hızlı-sorgu cache'i.

    Durum modeli (D-55, İş 2): `status` GERÇEK kanonik değerdir — `seed_status`
    (.harness dosyasındaki tohum) ile `task_status_events` tablosundaki
    geçişlerin `fold_status()` ile katlanmasının SONUCUDUR. `seed_status`
    yalnızca fold'un başlangıç noktasını ayrı tutmak için saklanır; .harness
    dosyası elle düzenlenip tohum değişse bile birikmiş geçişler yeniden
    katlanınca aynı `status`'e ulaşılır (bkz. store/rebuild.py fold_status).
    """

    __tablename__ = "task_projection"

    task_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), index=True, default="backlog")
    seed_status: Mapped[str] = mapped_column(String(20), default="backlog")
    assignee: Mapped[str | None] = mapped_column(String(255))
    ref: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_transition_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def to_board_card(self) -> BoardCard:
        """DB satırından BoardCard Pydantic modeline dönüştür."""
        return BoardCard(
            task_id=self.task_id,
            title=self.title,
            status=self.status,
            assignee=self.assignee,
            ref=self.ref,
        )

    @classmethod
    def from_harness(cls, data: dict) -> "TaskProjectionRow":
        """Harness task dict'inden DB satırına dönüştür (tohum satırı).

        data: HarnessPort.read_tasks() çıktısındaki tek bir task dict'i.
        Beklenen alanlar: task_id (veya id), title, status, assignee, ref.

        `status` burada yalnızca TOHUM değeridir (`seed_status` ile aynı
        başlar) — rebuild_projection() bunun üzerine task_status_events'i
        katlayıp gerçek `status`'ü belirler.
        """
        seed = data.get("status", "backlog")
        return cls(
            task_id=data.get("task_id") or data.get("id", ""),
            title=data.get("title", ""),
            status=seed,
            seed_status=seed,
            assignee=data.get("assignee"),
            ref=data.get("ref"),
        )


class PresenceRow(Base):
    """.harness/active/ projeksiyonu — kim ne üzerinde çalışıyor (canlı varlık)."""

    __tablename__ = "presence"

    handle: Mapped[str] = mapped_column(String(255), primary_key=True)
    task: Mapped[str | None] = mapped_column(String(50))
    module: Mapped[str | None] = mapped_column(String(255))
    intent: Mapped[str | None] = mapped_column(Text)
    branch: Mapped[str | None] = mapped_column(String(255))
    since: Mapped[datetime | None] = mapped_column(DateTime)

    @classmethod
    def from_harness(cls, data: dict) -> "PresenceRow":
        """Harness active dict'inden DB satırına dönüştür.

        data: HarnessPort.read_active() çıktısındaki tek bir active dict'i
        (active.schema.json alan adları: handle, task_id, module, intent,
        branch, updated_at — updated_at şemada string olarak zorunlu, bu
        yüzden DateTime kolonuna yazmadan önce parse ediyoruz).
        """
        updated_at = data.get("updated_at")
        return cls(
            handle=data.get("handle", ""),
            task=data.get("task_id"),
            module=data.get("module"),
            intent=data.get("intent"),
            branch=data.get("branch"),
            since=datetime.fromisoformat(updated_at) if updated_at else None,
        )


class TaskStatusEventRow(Base):
    """Kalıcı durum günlüğü — GERÇEK GitHub PR/issue olayından türetilen durum
    geçişleri (D-55, İş 2). Append-only: aynı (source_event_id, task_id) ikinci
    kez yazılmaya çalışıldığında satır ÇOĞALMAZ (bkz. store/rebuild.py
    append_status_events) — GitHub'ın aynı webhook'u yeniden teslim etmesi
    (retry) durumu bozmaz.

    Bileşik PK BİLEREK (source_event_id, task_id): tek bir PR event'i hem
    branch'ten (T-<id>) hem gövdedeki her `Closes #N`'den birden fazla farklı
    task için geçiş üretebilir — PK yalnız source_event_id olsaydı bu ikinci
    task'ın satırı ilkini ezerdi (bkz. tests/unit/test_rebuild.py
    test_ayni_olay_iki_kez_yazilinca_cogalmaz).

    `status` burada ÇÖZÜLMÜŞ hedef durumdur (ham GitHub event tipi değil) —
    üretimi engine/status_rules.py'nin sorumluluğudur (İş 1); bu tablo yalnız
    sonucu kalıcılaştırır. `resets` monotonluğu BİLEREK kıran geçişleri işaretler
    (örn. issue reopened → todo); `fold_status()` bunu bilgi amaçlı taşır.
    """

    __tablename__ = "task_status_events"

    source_event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String(20))
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    reason: Mapped[str | None] = mapped_column(String(255))
    resets: Mapped[bool] = mapped_column(Boolean, default=False)


class JudgeVerdictRow(Base):
    """Kalıcı judge yargı önbelleği (#259) — `CachedConflictJudge` (bellek,
    TTL'li) MISS verince bir sonraki katmanın (`PersistentJudge`) baktığı
    kalıcı depo. Konteyner yeniden yaratıldığında (CD, #236) bellek katmanı
    her seferinde sıfırlanır ama bu tablo KALICI kalır — aynı çift için
    Gemini/Groq'a ikinci kez ödenmez.

    `cache_key`, `engine/cache.py::_digest`'in ÜRETTİĞİ AYNI içerik-adresli
    anahtardır (a+b+overlap+sim üzerinden sha256) — kaç KATTIR ki `model`de
    bu anahtara KATILMIŞ olmalıdır (çağıranın sorumluluğu, bkz.
    `verdict_store.py`): aynı çift farklı bir model tarafından yargılanınca
    farklı bir `cache_key` üretilir, eski satırın üzerine YAZILMAZ — farklı
    model farklı yargı verir, model değişince eski yargılar sessizce
    "doğru" gibi kullanılmaz. `model` kolonu AYRICA (anahtarın parçası olsa
    bile) düz metin olarak saklanır — yalnızca bayatlık teşhisi/gözlem
    içindir (örn. "şu modelin ürettiği kaç yargı var" sorgusu), PK'nin
    KENDİSİ değildir.

    `detection`, `Detection.model_dump(mode="json")` çıktısıdır; okurken
    `Detection.model_validate(...)` ile geri kurulur (bkz. verdict_store.py
    `get_verdict`). Bozuk/eski şemalı bir satır okunursa `verdict_store.py`
    sessizce `None` döner (log'lu) — bu MEŞRU bir geçiş yoludur, yargı
    yeniden hesaplanır.

    `JudgeUnavailableError` BURAYA HİÇ YAZILMAZ (#252 sözleşmesi): hata bir
    sonuç değildir, kalıcılaştırılmaz — bu tablo yalnızca GERÇEK yargıları
    tutar (bkz. `ports.py::JudgeUnavailableError` docstring'i).
    """

    __tablename__ = "judge_verdicts"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(100), index=True)
    detection: Mapped[dict] = mapped_column(JSON)
    # #264 (Semih blocker B): bu sütun ÖNCE yalnızca gözlem içindi, hiçbir
    # okuma yolu KULLANMIYORDU. Artık `verdict_store.py::get_verdict`'in
    # (opsiyonel) `ttl_days` karşılaştırmasında OKUNUR — `put_verdict` bu
    # sütunu HEM ilk INSERT'te HEM de mevcut satırın üzerine her yazışta
    # `datetime.utcnow()`'a tazeler (kolon varsayılanı yalnızca INSERT'te
    # devreye girer, UPDATE'te tazelenmez — bkz. o fonksiyonun docstring'i).
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
# Vektör kolonu burada YOK — #15 (Semih) ekleyecek.
# pgvector extension migration'ı ayrı bir alembic adımında (002_pgvector_extension.py).
