"""add Bangumi metadata and sync tables

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bangumi_subject_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("name_cn", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("image_url", sa.String(length=1000), nullable=False),
        sa.Column("subject_type", sa.Integer(), nullable=True),
        sa.Column("air_date", sa.Date(), nullable=True),
        sa.Column("air_status", sa.String(length=100), nullable=False),
        sa.Column("platform", sa.String(length=100), nullable=False),
        sa.Column("total_main_episodes", sa.Integer(), nullable=True),
        sa.Column("collection_type", sa.String(length=30), nullable=True),
        sa.Column("collection_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("keep_forever", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bangumi_subject_id"),
    )
    op.create_index("ix_subjects_bangumi_subject_id", "subjects", ["bangumi_subject_id"], unique=True)
    op.create_index("ix_subjects_collection_type", "subjects", ["collection_type"], unique=False)

    op.create_table(
        "subject_relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("related_subject_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["related_subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_id", "related_subject_id", "relation_type", name="uq_subject_relation"),
    )
    op.create_index("ix_subject_relations_subject_id", "subject_relations", ["subject_id"], unique=False)
    op.create_index("ix_subject_relations_related_subject_id", "subject_relations", ["related_subject_id"], unique=False)

    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bangumi_episode_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("episode_type", sa.String(length=20), nullable=False),
        sa.Column("sort_number", sa.Float(), nullable=True),
        sa.Column("display_number", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("name_cn", sa.String(length=500), nullable=False),
        sa.Column("air_date", sa.Date(), nullable=True),
        sa.Column("bangumi_watch_status", sa.String(length=50), nullable=True),
        sa.Column("watched", sa.Boolean(), nullable=False),
        sa.Column("ignored", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bangumi_episode_id", name="uq_episode_bangumi_id"),
    )
    op.create_index("ix_episodes_bangumi_episode_id", "episodes", ["bangumi_episode_id"], unique=True)
    op.create_index("ix_episodes_subject_id", "episodes", ["subject_id"], unique=False)
    op.create_index("ix_episodes_episode_type", "episodes", ["episode_type"], unique=False)

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_runs_status", "sync_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sync_runs_status", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_episodes_episode_type", table_name="episodes")
    op.drop_index("ix_episodes_subject_id", table_name="episodes")
    op.drop_index("ix_episodes_bangumi_episode_id", table_name="episodes")
    op.drop_table("episodes")
    op.drop_index("ix_subject_relations_related_subject_id", table_name="subject_relations")
    op.drop_index("ix_subject_relations_subject_id", table_name="subject_relations")
    op.drop_table("subject_relations")
    op.drop_index("ix_subjects_collection_type", table_name="subjects")
    op.drop_index("ix_subjects_bangumi_subject_id", table_name="subjects")
    op.drop_table("subjects")
