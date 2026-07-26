"""内部工作看板（/internal 页面）的 Pydantic schema。

只给团队内部人使用：一边展示 IT 现阶段的 todolist，一边接产品/设计/商业提的
需求和 bug 反馈（可以打字也可以录音转文字）。整个页面在 nginx 层用共享账号
密码挡住，接口本身不做用户鉴权。
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

TodoStatus = Literal["open", "in_progress", "done"]
FeedbackKind = Literal["bug", "feature", "other"]
FeedbackStatus = Literal["new", "triaged", "done"]


class TodoItemOut(BaseModel):
    id: UUID
    title: str
    detail: str
    status: TodoStatus
    position: int
    created_at: datetime
    updated_at: datetime


class TodoCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(default="", max_length=4000)


class TodoUpdateRequest(BaseModel):
    """所有字段可选，只更新传了的字段。"""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=4000)
    status: TodoStatus | None = None


class FeedbackItemOut(BaseModel):
    id: UUID
    author_name: str
    kind: FeedbackKind
    content: str
    status: FeedbackStatus
    created_at: datetime
    updated_at: datetime


class FeedbackCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    author_name: str = Field(default="", max_length=64)
    kind: FeedbackKind = "other"


class FeedbackUpdateRequest(BaseModel):
    status: FeedbackStatus
