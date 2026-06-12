from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.services.llm import LLMService

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """数据库结构由 Alembic 管理，应用启动时只初始化外部服务。"""
    app.state.llm_service = LLMService(settings)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_frontend_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)
