
"""add cancelled job status

Revision ID: d9fb8de1df25
Revises: e69bfc66bd40
"""

from typing import Sequence, Union

from alembic import op


# Revision identifiers, used by Alembic.
revision: str = "d9fb8de1df25"
down_revision: Union[str, Sequence[str], None] = "e69bfc66bd40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cancelled to the existing PostgreSQL job-status enum."""
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE dubbing_job_status "
            "ADD VALUE IF NOT EXISTS 'cancelled'"
        )


def downgrade() -> None:
    """Keep the enum value during downgrade.

    PostgreSQL does not directly support removing an enum value.
    Removing it requires rebuilding the enum and checking existing data.
    """
    pass
