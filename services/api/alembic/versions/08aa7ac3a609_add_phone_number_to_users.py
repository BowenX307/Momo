"""给 users 加 phone_number(登录系统:手机号+验证码用)。

迁移版本：08aa7ac3a609
上一版本：1720642c8a26
创建时间：2026-07-28 22:09:18.504853

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "08aa7ac3a609"
down_revision: Union[str, Sequence[str], None] = "1720642c8a26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """加可空、唯一的 phone_number 字段 + 索引。"""
    op.add_column("users", sa.Column("phone_number", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_users_phone_number"), "users", ["phone_number"], unique=True)


def downgrade() -> None:
    """撤销当前版本，回退到上一版本。"""
    op.drop_index(op.f("ix_users_phone_number"), table_name="users")
    op.drop_column("users", "phone_number")
