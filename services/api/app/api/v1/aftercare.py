"""POST /v1/aftercare/generate —— 拍立得 Aftercare 内容生成。

相机点击后调这个：读对话历史 → 判情绪档 + 按人格写金句。编排在
`app.domain.aftercare.service.generate_aftercare` 里，失败静默兜底。
"""

from fastapi import APIRouter

from app.domain.aftercare.schemas import AftercareRequest, AftercareResponse
from app.domain.aftercare.service import generate_aftercare

router = APIRouter(prefix="/aftercare", tags=["aftercare"])


@router.post("/generate", response_model=AftercareResponse)
async def aftercare_generate(request: AftercareRequest) -> AftercareResponse:
    return await generate_aftercare(request)
