from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database.base import Base


class DownloadJob(Base):
    __tablename__ = "download_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    magnet_uri: Mapped[str] = mapped_column(Text, nullable=False)
    magnet_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    torrent_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    qbittorrent_task: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="CREATED", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    save_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replacement_media_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    replaces_job_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DownloadJobEpisode(Base):
    __tablename__ = "download_job_episodes"
    __table_args__ = (
        UniqueConstraint("job_id", "episode_id", name="uq_download_job_episode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("download_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
