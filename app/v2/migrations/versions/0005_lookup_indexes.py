"""Add lookup indexes for idempotent jobs, recovery, model state and collection evidence."""
from alembic import op
import sqlalchemy as sa

revision = "v2_0005"
down_revision = "v2_0004"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_v2_jobs_target_key", "v2_jobs", ("target_key",)),
    ("ix_v2_jobs_status_heartbeat", "v2_jobs", ("status", "heartbeat_at")),
    ("ix_v2_models_task_status", "v2_models", ("task", "status")),
    ("ix_v2_source_attempts_date_kind_status", "v2_source_attempts", ("local_date", "kind", "status")),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_indexes("v2_jobs")}
    existing |= {item["name"] for item in inspector.get_indexes("v2_models")}
    existing |= {item["name"] for item in inspector.get_indexes("v2_source_attempts")}
    for name, table, columns in _INDEXES:
        if name not in existing:
            op.create_index(name, table, list(columns))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for name, table, _columns in reversed(_INDEXES):
        if name in {item["name"] for item in inspector.get_indexes(table)}:
            op.drop_index(name, table_name=table)
