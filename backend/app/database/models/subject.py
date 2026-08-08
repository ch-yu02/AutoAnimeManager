from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bangumi_subject_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    name_cn: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    aliases: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    image_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    subject_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    air_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    air_status: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    platform: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    total_main_episodes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collection_type: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    collection_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    keep_forever: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SubjectRelation(Base):
    __tablename__ = "subject_relations"
    __table_args__ = (
        UniqueConstraint("subject_id", "related_subject_id", "relation_type", name="uq_subject_relation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    related_subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False, default="OTHER")
