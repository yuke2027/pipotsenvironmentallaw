"""Persist the stage and human-readable message of a running job."""

from alembic import op
import sqlalchemy as sa

revision = "v2_0004"
down_revision = "v2_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("v2_jobs")}
    if "progress_stage" not in columns:
        op.add_column("v2_jobs", sa.Column("progress_stage", sa.String(80), nullable=True))
    if "progress_message" not in columns:
        op.add_column("v2_jobs", sa.Column("progress_message", sa.String(240), nullable=True))


def downgrade() -> None:
    # Existing job history must remain readable on rollback. Restore the
    # verified database backup instead of dropping audit-facing state.
    raise RuntimeError("Restore the verified pre-upgrade backup; job progress history is retained")
