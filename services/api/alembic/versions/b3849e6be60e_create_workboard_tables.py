"""创建内部工作看板数据表(todo_items / feedback_items)。

迁移版本：b3849e6be60e
上一版本：2da7822385f4
创建时间：2026-07-25 23:32:21.880402

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3849e6be60e"
down_revision: Union[str, Sequence[str], None] = "2da7822385f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 todo_items、feedback_items 及状态约束。"""
    op.create_table(
        "todo_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'done')",
            name="ck_todo_items_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "feedback_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("author_name", sa.String(length=64), server_default="", nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="other", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="new", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('bug', 'feature', 'other')",
            name="ck_feedback_items_kind",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'triaged', 'done')",
            name="ck_feedback_items_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """按依赖顺序删除两张表。"""
    op.drop_table("feedback_items")
    op.drop_table("todo_items")
