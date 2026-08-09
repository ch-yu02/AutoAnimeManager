from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String(2000), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mtime_ns: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    inode: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    partial_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    full_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    video_codec: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(50), nullable=True)
    audio_languages: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    subtitle_languages: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    parse_result: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    review_reason: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    exists: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject_mapping_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    subject_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    subject_reasons: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    subject_manually_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class IgnoredMediaPath(Base):
    __tablename__ = "ignored_media_paths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String(2000), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EpisodeFile(Base):
    __tablename__ = "episode_files"
    __table_args__ = (UniqueConstraint("episode_id", "media_file_id", name="uq_episode_media_file"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    media_file_id: Mapped[int] = mapped_column(
        ForeignKey("media_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mapping_source: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasons: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    manually_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LibraryScanRun(Base):
    __tablename__ = "library_scan_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    moved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
