from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


class ReleaseSearch(Base):
    __tablename__ = "release_searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    query: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReleaseCandidate(Base):
    __tablename__ = "release_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    search_id: Mapped[str] = mapped_column(
        ForeignKey("release_searches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    release_url: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    magnet_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    magnet_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    author: Mapped[str | None] = mapped_column(String(300), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    normalized_title: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    release_group: Mapped[str | None] = mapped_column(String(300), nullable=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    part: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    episode_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    subtitle_language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(30), nullable=True)
    codec: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_batch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    decision: Mapped[str] = mapped_column(String(30), nullable=False, default="REJECT")
    match_reasons: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    reject_reasons: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    debug_selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
