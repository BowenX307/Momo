"""内部工作看板的读写逻辑：todo 列表 + 需求/bug 反馈。"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.workboard.schemas import (
    FeedbackCreateRequest,
    FeedbackUpdateRequest,
    TodoCreateRequest,
    TodoUpdateRequest,
)
from app.infra.models import FeedbackItem, TodoItem


async def list_todos(session: AsyncSession) -> list[TodoItem]:
    """未完成的排前面，同状态内按 position 再按创建时间排序。"""
    statement = select(TodoItem).order_by(
        (TodoItem.status == "done"),
        TodoItem.position,
        TodoItem.created_at,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def create_todo(session: AsyncSession, payload: TodoCreateRequest) -> TodoItem:
    todo = TodoItem(title=payload.title, detail=payload.detail)
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    return todo


async def update_todo(
    session: AsyncSession,
    todo_id: UUID,
    payload: TodoUpdateRequest,
) -> TodoItem:
    todo = await session.get(TodoItem, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="todo not found")

    if payload.title is not None:
        todo.title = payload.title
    if payload.detail is not None:
        todo.detail = payload.detail
    if payload.status is not None:
        todo.status = payload.status

    await session.commit()
    await session.refresh(todo)
    return todo


async def delete_todo(session: AsyncSession, todo_id: UUID) -> None:
    todo = await session.get(TodoItem, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="todo not found")
    await session.delete(todo)
    await session.commit()


async def list_feedback(session: AsyncSession) -> list[FeedbackItem]:
    """最新的排最前面，方便 IT 一打开就看到刚提交的需求。"""
    statement = select(FeedbackItem).order_by(FeedbackItem.created_at.desc())
    result = await session.execute(statement)
    return list(result.scalars().all())


async def create_feedback(
    session: AsyncSession,
    payload: FeedbackCreateRequest,
) -> FeedbackItem:
    feedback = FeedbackItem(
        content=payload.content,
        author_name=payload.author_name,
        kind=payload.kind,
    )
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return feedback


async def update_feedback(
    session: AsyncSession,
    feedback_id: UUID,
    payload: FeedbackUpdateRequest,
) -> FeedbackItem:
    feedback = await session.get(FeedbackItem, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="feedback not found")
    feedback.status = payload.status
    await session.commit()
    await session.refresh(feedback)
    return feedback
