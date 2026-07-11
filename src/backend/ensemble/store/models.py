"""SQLAlchemy 2.0 modelleri — projeksiyon tabloları (#41).

NormalizedEvent (#16) ve .harness/ (#13) verisinin hızlı-sorgu projeksiyonu.
Kanonik DEĞİL — .harness/ + GitHub her zaman kazanır; bu tablolar
rebuild_projection() ile yeniden kurulabilir (rebuildable cache).

users/accounts/profiles tablosu YOK (kapsam-sinirlari.md: kapsam dışı).
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
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
    """.harness/tasks/ projeksiyonu — board'ın hızlı-sorgu cache'i."""

    __tablename__ = "task_projection"

    task_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), index=True, default="backlog")
    assignee: Mapped[str | None] = mapped_column(String(255))
    ref: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
        """Harness task dict'inden DB satırına dönüştür.

        data: HarnessPort.read_tasks() çıktısındaki tek bir task dict'i.
        Beklenen alanlar: task_id (veya id), title, status, assignee, ref.
        """
        return cls(
            task_id=data.get("task_id") or data.get("id", ""),
            title=data.get("title", ""),
            status=data.get("status", "backlog"),
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

        data: HarnessPort.read_active() çıktısındaki tek bir active dict'i.
        Beklenen alanlar: handle, task, module, intent, branch, since.
        """
        return cls(
            handle=data.get("handle", ""),
            task=data.get("task"),
            module=data.get("module"),
            intent=data.get("intent"),
            branch=data.get("branch"),
            since=data.get("since"),
        )


# Vektör kolonu burada YOK — #15 (Semih) ekleyecek.
# pgvector extension migration'ı ayrı bir alembic adımında (002_pgvector_extension.py).
