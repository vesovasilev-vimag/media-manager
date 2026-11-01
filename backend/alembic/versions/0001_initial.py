"""Initial PostgreSQL schema. Minimum and maximum application schema: 0001."""

from alembic import op
from app.persistence import metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())
    op.execute(
        "CREATE INDEX ix_job_tasks_ready ON job_tasks (priority, run_after) WHERE state IN ('QUEUED','RETRYABLE','RECONCILING')"
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_present_torrent ON torrent_instances(client_id,info_hash) WHERE present"
    )


def downgrade() -> None:
    # Data-destructive downgrade is permitted only in an explicitly disposable test database.
    from alembic import context

    if context.get_x_argument(as_dictionary=True).get("disposable") != "true":
        raise RuntimeError(
            "Downgrade requires -x disposable=true; use compatible image rollback in production"
        )
    metadata.drop_all(op.get_bind())
