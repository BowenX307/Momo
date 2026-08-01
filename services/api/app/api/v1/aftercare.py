"""POST /v1/aftercare/generate —— 拍立得 Aftercare 内容生成。

相机点击后调这个：读对话历史 → 判情绪档 + 按人格写金句。编排在
`app.domain.aftercare.service.generate_aftercare` 里，失败静默兜底。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import RedisDep, enforce_rate_limit
from app.core.config import settings
from app.domain.aftercare.schemas import AftercareRequest, AftercareResponse
from app.domain.aftercare.service import archive_round, generate_aftercare
from app.infra.database import get_db_session

router = APIRouter(prefix="/aftercare", tags=["aftercare"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/generate", response_model=AftercareResponse)
async def aftercare_generate(
    request: AftercareRequest,
    session: DatabaseSession,
    http_request: Request,
    redis: RedisDep,
) -> AftercareResponse:
    await enforce_rate_limit(
        http_request,
        redis,
        bucket="aftercare",
        limit=settings.rate_limit_aftercare_per_minute,
        identity=request.external_user_id,
    )
    result = await generate_aftercare(request)
    if settings.persistence_enabled and request.conversation_id and request.external_user_id:
        await archive_round(
            session,
            conversation_id=request.conversation_id,
            external_user_id=request.external_user_id,
            result=result,
        )
    return result
