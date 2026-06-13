from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中读取环境变量，避免配置散落在业务代码中。"""

    app_name: str = "职析 API"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./data/job_assistant.db"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_recycle_seconds: int = 1800
    database_connect_timeout_seconds: int = 10
    frontend_origin: str = "http://localhost:3000"
    deepseek_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_timeout_seconds: float = 60.0
    max_pdf_size_mb: int = 8
    jwt_secret_key: str = "change-this-local-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    user_daily_analysis_limit: int = 3
    user_daily_interview_limit: int = 10
    global_daily_analysis_limit: int = 30
    global_daily_interview_limit: int = 100
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024
    knowledge_max_documents: int = 10
    knowledge_max_characters: int = 50000
    knowledge_top_k: int = 4
    knowledge_min_similarity: float = 0.35
    user_daily_knowledge_limit: int = 5
    global_daily_knowledge_limit: int = 50
    portfolio_user_email: str = ""
    portfolio_user_password: str = ""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_data_directory(self) -> None:
        """SQLite 使用相对路径时，提前创建数据目录。"""
        if self.database_url.startswith("sqlite:///./"):
            relative_path = self.database_url.removeprefix("sqlite:///./")
            Path(relative_path).parent.mkdir(parents=True, exist_ok=True)

    def sqlalchemy_database_url(self) -> str:
        """统一使用 psycopg 3，兼容云平台常见的 PostgreSQL 地址格式。"""
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace(
                "postgres://",
                "postgresql+psycopg://",
                1,
            )
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1,
            )
        return self.database_url

    def allowed_frontend_origins(self) -> list[str]:
        """线上可传入逗号分隔域名，同时保留两个本地开发地址。"""
        configured = {
            origin.strip()
            for origin in self.frontend_origin.split(",")
            if origin.strip()
        }
        return sorted(
            configured
            | {"http://localhost:3000", "http://127.0.0.1:3000"}
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
