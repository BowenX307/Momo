"""增加会话生命周期、软删除字段和长期记忆摘要表。

迁移版本：d7c8f2a91b64
上一版本：08aa7ac3a609
创建时间：2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7c8f2a91b64"
down_revision: str | Sequence[str] | None = "08aa7ac3a609"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为登录用户的七轮历史、回收站和主动记忆选择补齐结构。"""
    op.add_column(
        "conversations",
        sa.Column(
            "status", sa.String(length=20), server_default="active", nullable=False
        ),
    )
    op.add_column(
        "conversations",
        sa.Column("close_reason", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("client_session_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "include_in_memory",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    op.execute(
        sa.text(
            "UPDATE conversations "
            "SET status = CASE WHEN ended_at IS NULL THEN 'active' ELSE 'closed' END, "
            "last_activity_at = updated_at"
        )
    )
    op.create_check_constraint(
        "ck_conversations_status",
        "conversations",
        "status IN ('active', 'closed', 'pending_delete')",
    )
    op.create_check_constraint(
        "ck_conversations_close_reason",
        "conversations",
        "close_reason IS NULL OR "
        "close_reason IN ('user_end', 'browser_close', 'idle_timeout')",
    )
    op.create_index(
        "ix_conversations_user_status_created_at",
        "conversations",
        ["user_id", "status", "created_at"],
    )
    op.create_index(
        "ix_conversations_purge_after",
        "conversations",
        ["purge_after"],
    )
    op.create_index(
        "ux_conversations_user_client_session",
        "conversations",
        ["user_id", "client_session_id"],
        unique=True,
    )

    op.create_table(
        "conversation_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column(
            "prompt_version", sa.String(length=32), server_default="v1", nullable=False
        ),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'failed', 'stale')",
            name="ck_conversation_memories_status",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversation_memories_conversation_id"),
        "conversation_memories",
        ["conversation_id"],
        unique=True,
    )


def downgrade() -> None:
    """移除本阶段新增结构，不影响旧会话和消息。"""
    op.drop_index(
        op.f("ix_conversation_memories_conversation_id"),
        table_name="conversation_memories",
    )
    op.drop_table("conversation_memories")

    op.drop_index("ux_conversations_user_client_session", table_name="conversations")
    op.drop_index(
        "ix_conversations_purge_after",
        table_name="conversations",
    )
    op.drop_index(
        "ix_conversations_user_status_created_at",
        table_name="conversations",
    )
    op.drop_constraint(
        "ck_conversations_close_reason",
        "conversations",
        type_="check",
    )
    op.drop_constraint("ck_conversations_status", "conversations", type_="check")
    op.drop_column("conversations", "include_in_memory")
    op.drop_column("conversations", "purge_after")
    op.drop_column("conversations", "deleted_at")
    op.drop_column("conversations", "last_activity_at")
    op.drop_column("conversations", "client_session_id")
    op.drop_column("conversations", "close_reason")
    op.drop_column("conversations", "status")
