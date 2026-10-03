"""Keep source rolling maxima distinct from calendar-day assessment values."""
from alembic import op

revision = 'v2_0003'
down_revision = 'v2_0002'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("UPDATE v2_observations SET basis='rolling_max_24h' WHERE pollutant='O3' AND basis='daily_max_1h'")
    op.execute("UPDATE v2_observations SET basis='rolling_max_8h_24h' WHERE pollutant='O3' AND basis='daily_max_8h'")

def downgrade() -> None:
    raise RuntimeError('Restore the verified backup; derived assessment snapshots are retained')
