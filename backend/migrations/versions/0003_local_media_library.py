"""add local media library and episode mappings

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subjects",
        sa.Column("aliases", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "episodes",
        sa.Column("local_status", sa.String(length=30), nullable=False, server_default="MISSING"),
    )
    op.create_index("ix_episodes_local_status", "episodes", ["local_status"], unique=False)
    op.create_table(
        "media_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=2000), nullable=False),
        sa.Column("filename", sa.String(length=1000), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mtime_ns", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("inode", sa.Integer(), nullable=True),
        sa.Column("partial_hash", sa.String(length=64), nullable=True),
        sa.Column("full_hash", sa.String(length=64), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("video_codec", sa.String(length=100), nullable=True),
        sa.Column("resolution", sa.String(length=50), nullable=True),
        sa.Column("audio_languages", sa.Text(), nullable=False),
        sa.Column("subtitle_languages", sa.Text(), nullable=False),
        sa.Column("parse_result", sa.Text(), nullable=False),
        sa.Column("review_reason", sa.String(length=100), nullable=True),
        sa.Column("exists", sa.Boolean(), nullable=False),
        sa.Column("ignored", sa.Boolean(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("subject_mapping_source", sa.String(length=30), nullable=True),
        sa.Column("subject_confidence", sa.Float(), nullable=True),
        sa.Column("subject_reasons", sa.Text(), nullable=False),
        sa.Column("subject_manually_locked", sa.Boolean(), nullable=False),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path"),
    )
    for name, columns in [
        ("ix_media_files_device_id", ["device_id"]), ("ix_media_files_inode", ["inode"]),
        ("ix_media_files_partial_hash", ["partial_hash"]), ("ix_media_files_full_hash", ["full_hash"]),
        ("ix_media_files_review_reason", ["review_reason"]),
        ("ix_media_files_exists", ["exists"]), ("ix_media_files_ignored", ["ignored"]),
        ("ix_media_files_subject_id", ["subject_id"]),
    ]:
        op.create_index(name, "media_files", columns, unique=False)
    op.create_table(
        "episode_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("media_file_id", sa.Integer(), nullable=False),
        sa.Column("mapping_source", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reasons", sa.Text(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("manually_locked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_file_id"], ["media_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", "media_file_id", name="uq_episode_media_file"),
    )
    op.create_index("ix_episode_files_episode_id", "episode_files", ["episode_id"], unique=False)
    op.create_index("ix_episode_files_media_file_id", "episode_files", ["media_file_id"], unique=False)
    op.create_table(
        "library_scan_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("added_count", sa.Integer(), nullable=False),
        sa.Column("changed_count", sa.Integer(), nullable=False),
        sa.Column("moved_count", sa.Integer(), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_library_scan_runs_status", "library_scan_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_library_scan_runs_status", table_name="library_scan_runs")
    op.drop_table("library_scan_runs")
    op.drop_index("ix_episode_files_media_file_id", table_name="episode_files")
    op.drop_index("ix_episode_files_episode_id", table_name="episode_files")
    op.drop_table("episode_files")
    for name in [
        "ix_media_files_subject_id", "ix_media_files_ignored", "ix_media_files_exists",
        "ix_media_files_review_reason", "ix_media_files_full_hash", "ix_media_files_partial_hash", "ix_media_files_inode",
        "ix_media_files_device_id",
    ]:
        op.drop_index(name, table_name="media_files")
    op.drop_table("media_files")
    op.drop_index("ix_episodes_local_status", table_name="episodes")
    op.drop_column("episodes", "local_status")
    op.drop_column("subjects", "aliases")
