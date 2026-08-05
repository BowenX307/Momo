"""合并密码登录与会话生命周期两条并行迁移链。

迁移版本：e2f4a6b8c0d1
上一版本：c4f1a2d7b8e3、d7c8f2a91b64
创建时间：2026-08-02
"""

from collections.abc import Sequence


revision: str = "e2f4a6b8c0d1"
down_revision: str | Sequence[str] | None = (
    "c4f1a2d7b8e3",
    "d7c8f2a91b64",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """两条父迁移已经完成结构修改，这里只合并版本图。"""


def downgrade() -> None:
    """回退到两个并行迁移头，不修改数据库结构。"""
