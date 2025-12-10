"""Add transfer to transaction type enum

Revision ID: 82791701dfe6
Revises: 6139a02d9ff2
Create Date: 2025-12-10 18:34:33.824789

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82791701dfe6'
down_revision: Union[str, None] = '6139a02d9ff2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'transfer' to the transactiontype enum
    op.execute("ALTER TYPE transactiontype ADD VALUE 'transfer'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum and updating all references
    pass
