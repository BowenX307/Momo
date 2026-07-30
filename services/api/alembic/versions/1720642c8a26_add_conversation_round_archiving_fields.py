"""给 conversations 加"轮次归档"字段(ended_at / mood / letter)。

迁移版本：1720642c8a26
上一版本：b3849e6be60e
创建时间：2026-07-26 21:11:53.535089

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1720642c8a26"
down_revision: Union[str, Sequence[str], None] = "b3849e6be60e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """加 ended_at(结束时间)、mood/letter(结束时生成的拍立得内容)三个可空字段。"""
    op.add_column("conversations", sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("mood", sa.String(length=16), nullable=True))
    op.add_column("conversations", sa.Column("letter", sa.Text(), nullable=True))


def downgrade() -> None:
    """撤销当前版本，回退到上一版本。"""
    op.drop_column("conversations", "letter")
    op.drop_column("conversations", "mood")
    op.drop_column("conversations", "ended_at")
