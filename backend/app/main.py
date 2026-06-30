from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.api.routes import router
from app.api.adaptive_routes import router as adaptive_router
from app.config import get_settings
from app.database import engine
from app.services.adaptive_interview import build_adaptive_interview_graph
from app.services.knowledge import EmbeddingService, validate_embedding_dimensions
from app.services.llm import LLMService

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """数据库结构由 Alembic 管理，应用启动时只初始化外部服务。"""
    validate_embedding_dimensions(settings, engine)
    app.state.llm_service = LLMService(settings)
    app.state.embedding_service = EmbeddingService(settings)
    async with AsyncExitStack() as stack:
        if settings.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
            checkpointer = await stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(settings.langgraph_postgres_url())
            )
        else:
            if settings.langgraph_sqlite_path != ":memory:":
                Path(settings.langgraph_sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            checkpointer = await stack.enter_async_context(
                AsyncSqliteSaver.from_conn_string(settings.langgraph_sqlite_path)
            )
        await checkpointer.setup()
        app.state.adaptive_interview_checkpointer = checkpointer
        app.state.adaptive_interview_graph = build_adaptive_interview_graph(checkpointer)
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
app.include_router(adaptive_router, prefix=settings.api_prefix)
