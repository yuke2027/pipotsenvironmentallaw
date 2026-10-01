"""Baseline schema generated from the ORM metadata."""

from __future__ import annotations

from alembic import op

revision = "0002_baseline"
down_revision = "0001_empty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.models import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from app.db.models import Base

    Base.metadata.drop_all(bind=op.get_bind())
