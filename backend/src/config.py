"""
config.py — Application settings loaded from environment variables.

Dùng pydantic-settings để validate và type-check tất cả env vars.
Mọi module import `from src.config import settings` để lấy config.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # llama.cpp servers (hoặc bất kỳ OpenAI-compatible provider nào)
    llamacpp_chat_url: str = "http://llamacpp-chat:8080/v1"
    llamacpp_embed_url: str = "http://llamacpp-embed:8081/v1"
    llm_api_key: str = "llama-cpp"  # "llama-cpp" cho local, real key cho OpenAI/Groq/etc.

    # Model identifiers (as sent in API calls)
    gguf_chat_model: str = "Qwen3.5-9B.Q6_K.gguf"
    gguf_embed_model: str = "nomic-embed-text-v1.5.Q4_K_M.gguf"

    # Qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "nexus_docs"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # RAG
    chunk_size: int = 512
    chunk_overlap: int = 50
    retriever_top_k: int = 5

    # Langfuse tracing (optional — để trống để disable)
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Accept comma-separated string or list."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


settings = Settings()
