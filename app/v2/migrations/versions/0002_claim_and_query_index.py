"""Lead ownership and date-filter query index."""
from alembic import op
import sqlalchemy as sa

revision = "v2_0002"
down_revision = "v2_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial revision is also used for empty installs; add only on upgrades.
    inspector = sa.inspect(op.get_bind())
    if "claimed_by" not in {c["name"] for c in inspector.get_columns("v2_leads")}:
        op.add_column("v2_leads", sa.Column("claimed_by", sa.String(36), nullable=True))
        op.create_foreign_key("fk_v2_lead_claimed_by", "v2_leads", "v2_users", ["claimed_by"], ["id"])
    if "ix_v2_obs_date_basis_pollutant" not in {i["name"] for i in inspector.get_indexes("v2_observations")}:
        op.create_index("ix_v2_obs_date_basis_pollutant", "v2_observations", ["local_date", "basis", "pollutant", "station_id"])


def downgrade() -> None:
    raise RuntimeError("Use the verified pre-upgrade backup for rollback")
