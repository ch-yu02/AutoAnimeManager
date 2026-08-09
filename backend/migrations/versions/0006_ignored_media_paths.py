"""retain ignored paths while deleting media records

Revision ID: 0006
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ignored_media_paths",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path"),
    )


def downgrade() -> None:
    op.drop_table("ignored_media_paths")
