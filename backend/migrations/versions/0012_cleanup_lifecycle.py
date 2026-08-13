"""add cleanup lifecycle audit records

Revision ID: 0012
Revises: 0011
"""

from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "episodes",
        sa.Column("successfully_imported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("""
        UPDATE episodes
        SET successfully_imported_at = CURRENT_TIMESTAMP
        WHERE EXISTS (
            SELECT 1 FROM download_job_episodes dje
            JOIN download_jobs dj ON dj.id = dje.job_id
            WHERE dje.episode_id = episodes.id AND dj.state = 'IMPORTED'
        ) OR EXISTS (
            SELECT 1 FROM episode_files ef
            WHERE ef.episode_id = episodes.id AND ef.mapping_source = 'DOWNLOAD_JOB'
        )
    """)
    op.create_table(
        "cleanup_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=False),
        sa.Column("episode_snapshot_json", sa.Text(), nullable=False),
        sa.Column("files_json", sa.Text(), nullable=False),
        sa.Column("bytes_total", sa.BigInteger(), nullable=False),
        sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cleanup_records_subject_id", "cleanup_records", ["subject_id"], unique=False)
    op.create_index("ix_cleanup_records_status", "cleanup_records", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cleanup_records_status", table_name="cleanup_records")
    op.drop_index("ix_cleanup_records_subject_id", table_name="cleanup_records")
    op.drop_table("cleanup_records")
    op.drop_column("episodes", "successfully_imported_at")
