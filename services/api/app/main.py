"""FastAPI 应用入口"""

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import settings
from app.infra.database import check_database_connection
from app.infra.conversation_maintenance import conversation_maintenance_loop
from app.llm.factory import get_llm_provider
from app.stt.factory import get_stt_provider
from app.tts.factory import get_tts_provider

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的钩子"""
    logger.info("yewne_api_starting", env=settings.env)
    maintenance_task = (
        asyncio.create_task(conversation_maintenance_loop())
        if settings.persistence_enabled
        else None
    )
    try:
        yield
    finally:
        if maintenance_task is not None:
            maintenance_task.cancel()
            await asyncio.gather(maintenance_task, return_exceptions=True)
        logger.info("yewne_api_stopping")


app = FastAPI(
    title="Yewne API",
    description="场景化 AI 情绪陪伴后端",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: 白名单见 config.cors_origins（可用 .env 的 CORS_ORIGINS 覆盖）
# [2026-07-29] allow_credentials 由 True 改为 False。它控制的是浏览器自动携带的凭证
# （cookie、HTTP basic auth），而本项目的登录态走 Authorization 头里的 token——那是前端
# 显式加上的普通请求头，不属于 CORS 的"凭证"，因此关掉不影响登录。
# 关掉的原因：allow_credentials=True 时 Starlette 不会回 "*"，而是回显调用方 Origin
# （starlette/middleware/cors.py 的 allow_all_origins + allow_credentials 分支），
# 于是"通配符 + 凭证会被浏览器拒绝"这层规范保护失效。同时 /internal 在 nginx 层用的是
# basic auth，浏览器会自动重发，配上带凭证的跨源授权就能被恶意页面借用。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
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
