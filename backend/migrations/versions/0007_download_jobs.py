"""add manual download jobs

Revision ID: 0007
Revises: 0006
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("magnet_uri", sa.Text(), nullable=False),
        sa.Column("magnet_hash", sa.String(length=64), nullable=False),
        sa.Column("torrent_hash", sa.String(length=64), nullable=True),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("qbittorrent_task", sa.String(length=100), nullable=True),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("save_path", sa.String(length=2000), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("magnet_hash"),
        sa.UniqueConstraint("torrent_hash"),
    )
    op.create_index("ix_download_jobs_magnet_hash", "download_jobs", ["magnet_hash"], unique=True)
    op.create_index("ix_download_jobs_torrent_hash", "download_jobs", ["torrent_hash"], unique=True)
    op.create_index("ix_download_jobs_subject_id", "download_jobs", ["subject_id"], unique=False)
    op.create_index("ix_download_jobs_qbittorrent_task", "download_jobs", ["qbittorrent_task"], unique=False)
    op.create_index("ix_download_jobs_state", "download_jobs", ["state"], unique=False)
    op.create_table(
        "download_job_episodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["download_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", name="uq_download_episode"),
        sa.UniqueConstraint("job_id", "episode_id", name="uq_download_job_episode"),
    )
    op.create_index("ix_download_job_episodes_episode_id", "download_job_episodes", ["episode_id"], unique=False)
    op.create_index("ix_download_job_episodes_job_id", "download_job_episodes", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_download_job_episodes_job_id", table_name="download_job_episodes")
    op.drop_index("ix_download_job_episodes_episode_id", table_name="download_job_episodes")
    op.drop_table("download_job_episodes")
    op.drop_index("ix_download_jobs_state", table_name="download_jobs")
    op.drop_index("ix_download_jobs_qbittorrent_task", table_name="download_jobs")
    op.drop_index("ix_download_jobs_subject_id", table_name="download_jobs")
    op.drop_index("ix_download_jobs_torrent_hash", table_name="download_jobs")
    op.drop_index("ix_download_jobs_magnet_hash", table_name="download_jobs")
    op.drop_table("download_jobs")
