"""Centralized application settings loaded from environment / .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """All runtime configuration. Override via environment or .env."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM providers ---
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")

    # --- Observability ---
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="supply-chain-risk-ai", alias="LANGSMITH_PROJECT")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")

    # --- Models ---
    primary_llm_model: str = Field(default="gpt-4o-mini", alias="PRIMARY_LLM_MODEL")
    fallback_llm_model: str = Field(default="llama-3.3-70b-versatile", alias="FALLBACK_LLM_MODEL")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    fallback_embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="FALLBACK_EMBEDDING_MODEL",
    )

    # --- Paths ---
    data_csv_path: Path = Field(
        default=PROJECT_ROOT / "data" / "supply_chain_data.csv",
        alias="DATA_CSV_PATH",
    )
    chroma_persist_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "chroma_db",
        alias="CHROMA_PERSIST_DIR",
    )

    # --- App ---
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache
def get_settings() -> Settings:
    """Singleton settings accessor."""
    return Settings()
