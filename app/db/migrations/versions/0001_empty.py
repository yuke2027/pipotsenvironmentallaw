"""Empty predecessor revision so an existing database can be upgraded."""

from __future__ import annotations

revision = "0001_empty"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
