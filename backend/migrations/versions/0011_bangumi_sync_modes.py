"""add optimized Bangumi sync metadata

Revision ID: 0011
Revises: 0010
"""

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subjects", sa.Column("metadata_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subjects", sa.Column("relations_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sync_runs", sa.Column("mode", sa.String(length=20), nullable=False, server_default="FULL"))
    op.add_column("sync_runs", sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sync_runs", sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("sync_runs", "request_count")
    op.drop_column("sync_runs", "skipped_count")
    op.drop_column("sync_runs", "mode")
    op.drop_column("subjects", "relations_synced_at")
    op.drop_column("subjects", "metadata_synced_at")
