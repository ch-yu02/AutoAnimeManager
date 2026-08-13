from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


class CleanupRecord(Base):
    __tablename__ = "cleanup_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    reasons_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    episode_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    files_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    bytes_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    eligible_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
