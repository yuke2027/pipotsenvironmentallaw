"""Independent v2 schema; legacy tables are never dropped."""
from alembic import op
from pathlib import Path

revision = "v2_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Frozen DDL prevents future ORM edits from silently changing the initial revision.
    sql = (Path(__file__).parents[1] / "v2_initial.sql").read_text("utf-8")
    for statement in sql.split(";"):
        if statement.strip(): op.get_bind().exec_driver_sql(statement)


def downgrade() -> None:
    raise RuntimeError("v2 downgrade is disabled: restore the verified backup instead")
