"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import settings
from app.infra.database import check_database_connection
from app.llm.factory import get_llm_provider
from app.stt.factory import get_stt_provider
from app.tts.factory import get_tts_provider

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的钩子"""
    logger.info("yewne_api_starting", env=settings.env)
    yield
    logger.info("yewne_api_stopping")


app = FastAPI(
    title="Yewne API",
    description="场景化 AI 情绪陪伴后端",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: 开发阶段允许所有，上线前必须收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(v1_router)


@app.get("/")
async def root():
    return {"service": "yewne-api", "status": "ok"}


@app.get("/health")
async def health():
    _, llm_is_mock = get_llm_provider()
    _, stt_is_mock = get_stt_provider()
    _, tts_is_mock = get_tts_provider()
    database_connected = (
        await check_database_connection() if settings.persistence_enabled else None
    )
    return {
        "status": "degraded" if database_connected is False else "healthy",
        "env": settings.env,
        "persistence_enabled": settings.persistence_enabled,
        "database_connected": database_connected,
        "llm_provider": settings.llm_provider,
        "llm_is_mock": llm_is_mock,
        "stt_provider": settings.stt_provider,
        "stt_is_mock": stt_is_mock,
        "tts_provider": settings.tts_provider,
        "tts_is_mock": tts_is_mock,
    }
