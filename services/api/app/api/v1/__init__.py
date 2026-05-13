from fastapi import APIRouter

from app.api.v1.chat import router as chat_router

router = APIRouter(prefix="/v1")
router.include_router(chat_router)

__all__ = ["router"]
