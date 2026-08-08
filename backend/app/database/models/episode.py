from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (UniqueConstraint("bangumi_episode_id", name="uq_episode_bangumi_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bangumi_episode_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_type: Mapped[str] = mapped_column(String(20), nullable=False, default="OTHER", index=True)
    sort_number: Mapped[float | None] = mapped_column(nullable=True)
    display_number: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    name_cn: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    air_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bangumi_watch_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    watched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
