"""内部工作看板接口：GET/POST/PATCH todo 与 feedback。

只给 /internal 页面用。整个路径在 nginx 层挡了共享账号密码，这里不做鉴权。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.workboard import service
from app.domain.workboard.schemas import (
    FeedbackCreateRequest,
    FeedbackItemOut,
    FeedbackUpdateRequest,
    TodoCreateRequest,
    TodoItemOut,
    TodoUpdateRequest,
)
from app.infra.database import get_db_session

router = APIRouter(prefix="/workboard", tags=["workboard"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/todos", response_model=list[TodoItemOut])
async def get_todos(session: DatabaseSession) -> list[TodoItemOut]:
    todos = await service.list_todos(session)
    return [TodoItemOut.model_validate(t, from_attributes=True) for t in todos]


@router.post("/todos", response_model=TodoItemOut)
async def post_todo(payload: TodoCreateRequest, session: DatabaseSession) -> TodoItemOut:
    todo = await service.create_todo(session, payload)
    return TodoItemOut.model_validate(todo, from_attributes=True)


@router.patch("/todos/{todo_id}", response_model=TodoItemOut)
async def patch_todo(
    todo_id: UUID,
    payload: TodoUpdateRequest,
    session: DatabaseSession,
) -> TodoItemOut:
    todo = await service.update_todo(session, todo_id, payload)
    return TodoItemOut.model_validate(todo, from_attributes=True)


@router.delete("/todos/{todo_id}", status_code=204)
async def remove_todo(todo_id: UUID, session: DatabaseSession) -> None:
    await service.delete_todo(session, todo_id)


@router.get("/feedback", response_model=list[FeedbackItemOut])
async def get_feedback(session: DatabaseSession) -> list[FeedbackItemOut]:
    items = await service.list_feedback(session)
    return [FeedbackItemOut.model_validate(f, from_attributes=True) for f in items]


@router.post("/feedback", response_model=FeedbackItemOut)
async def post_feedback(
    payload: FeedbackCreateRequest,
    session: DatabaseSession,
) -> FeedbackItemOut:
    feedback = await service.create_feedback(session, payload)
    return FeedbackItemOut.model_validate(feedback, from_attributes=True)


@router.patch("/feedback/{feedback_id}", response_model=FeedbackItemOut)
async def patch_feedback(
    feedback_id: UUID,
    payload: FeedbackUpdateRequest,
    session: DatabaseSession,
) -> FeedbackItemOut:
    feedback = await service.update_feedback(session, feedback_id, payload)
    return FeedbackItemOut.model_validate(feedback, from_attributes=True)
