"""add playback progress state

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playback_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("media_file_id", sa.Integer(), nullable=True),
        sa.Column("position_seconds", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("progress_ratio", sa.Float(), nullable=False),
        sa.Column("watched", sa.Boolean(), nullable=False),
        sa.Column("watched_source", sa.String(length=20), nullable=True),
        sa.Column("last_played_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_file_id"], ["media_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id"),
    )
    op.create_index("ix_playback_states_episode_id", "playback_states", ["episode_id"], unique=True)
    op.create_index("ix_playback_states_media_file_id", "playback_states", ["media_file_id"], unique=False)
    op.create_index("ix_playback_states_watched", "playback_states", ["watched"], unique=False)
    op.create_index("ix_playback_states_last_played_at", "playback_states", ["last_played_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_playback_states_last_played_at", table_name="playback_states")
    op.drop_index("ix_playback_states_watched", table_name="playback_states")
    op.drop_index("ix_playback_states_media_file_id", table_name="playback_states")
    op.drop_index("ix_playback_states_episode_id", table_name="playback_states")
    op.drop_table("playback_states")
