"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的钩子"""
    logger.info("momo_api_starting", env=settings.env)
    yield
    logger.info("momo_api_stopping")


app = FastAPI(
    title="MOMO API",
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
    return {"service": "momo-api", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "healthy", "env": settings.env}
