"""给 users 加 password_hash(密码登录:argon2 哈希串)。

迁移版本：c4f1a2d7b8e3
上一版本：08aa7ac3a609
创建时间：2026-07-30

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f1a2d7b8e3"
down_revision: Union[str, Sequence[str], None] = "08aa7ac3a609"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """加可空的 password_hash 字段。

    可空是有意的：密码是可选的第二种登录方式，老用户和只用验证码的用户这一列一直为空。
    不加索引——只按 phone_number 查用户后再比对，从不按哈希值查。
    """
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """撤销当前版本，回退到上一版本。"""
    op.drop_column("users", "password_hash")
