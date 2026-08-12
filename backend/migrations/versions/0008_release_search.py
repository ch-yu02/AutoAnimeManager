"""add release searches and candidates

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_searches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_release_searches_episode_id", "release_searches", ["episode_id"], unique=False)
    op.create_table(
        "release_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("search_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("release_url", sa.String(length=2000), nullable=False),
        sa.Column("magnet_uri", sa.Text(), nullable=True),
        sa.Column("magnet_hash", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author", sa.String(length=300), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("normalized_title", sa.String(length=1000), nullable=False),
        sa.Column("release_group", sa.String(length=300), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("part", sa.Integer(), nullable=True),
        sa.Column("episode_start", sa.Float(), nullable=True),
        sa.Column("episode_end", sa.Float(), nullable=True),
        sa.Column("subtitle_language", sa.String(length=100), nullable=True),
        sa.Column("resolution", sa.String(length=30), nullable=True),
        sa.Column("codec", sa.String(length=30), nullable=True),
        sa.Column("is_batch", sa.Boolean(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("match_reasons", sa.Text(), nullable=False),
        sa.Column("reject_reasons", sa.Text(), nullable=False),
        sa.Column("duplicate", sa.Boolean(), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_job_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["search_id"], ["release_searches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_release_candidates_search_id", "release_candidates", ["search_id"], unique=False)
    op.create_index("ix_release_candidates_episode_id", "release_candidates", ["episode_id"], unique=False)
    op.create_index("ix_release_candidates_magnet_hash", "release_candidates", ["magnet_hash"], unique=False)
    op.create_index("ix_release_candidates_download_job_id", "release_candidates", ["download_job_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_release_candidates_download_job_id", table_name="release_candidates")
    op.drop_index("ix_release_candidates_magnet_hash", table_name="release_candidates")
    op.drop_index("ix_release_candidates_episode_id", table_name="release_candidates")
    op.drop_index("ix_release_candidates_search_id", table_name="release_candidates")
    op.drop_table("release_candidates")
    op.drop_index("ix_release_searches_episode_id", table_name="release_searches")
    op.drop_table("release_searches")
