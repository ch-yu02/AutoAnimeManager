"""track provisional ANi media replacement

Revision ID: 0013
Revises: 0012
"""

from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "download_jobs",
        sa.Column("replacement_media_ids_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "download_jobs",
        sa.Column("replaces_job_ids_json", sa.Text(), nullable=False, server_default="[]"),
    )
    constraints = {
        item["name"] for item in sa.inspect(op.get_bind()).get_unique_constraints(
            "download_job_episodes"
        )
    }
    if "uq_download_episode" in constraints:
        with op.batch_alter_table("download_job_episodes") as batch_op:
            batch_op.drop_constraint("uq_download_episode", type_="unique")


def downgrade() -> None:
    op.execute("""
        DELETE FROM download_job_episodes
        WHERE id NOT IN (
            SELECT MAX(id) FROM download_job_episodes GROUP BY episode_id
        )
    """)
    constraints = {
        item["name"] for item in sa.inspect(op.get_bind()).get_unique_constraints(
            "download_job_episodes"
        )
    }
    if "uq_download_episode" not in constraints:
        with op.batch_alter_table("download_job_episodes") as batch_op:
            batch_op.create_unique_constraint("uq_download_episode", ["episode_id"])
    op.drop_column("download_jobs", "replaces_job_ids_json")
    op.drop_column("download_jobs", "replacement_media_ids_json")
