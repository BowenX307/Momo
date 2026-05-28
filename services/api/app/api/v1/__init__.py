from fastapi import APIRouter

from app.api.v1.chat import router as chat_router
from app.api.v1.speech import router as speech_router

router = APIRouter(prefix="/v1")
router.include_router(chat_router)
router.include_router(speech_router)

__all__ = ["router"]
