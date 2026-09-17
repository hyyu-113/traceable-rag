from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_host: str = "127.0.0.1"
    app_port: int = Field(8000, ge=1, le=65535)
    data_dir: Path = Path("data")
    upload_dir: Path | None = None
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "traceable_chunks"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: SecretStr = SecretStr("")
    embedding_model: str = ""
    reranker_enabled: bool = False
    reranker_base_url: str = ""
    reranker_api_key: SecretStr = SecretStr("")
    reranker_model: str = ""
    top_k_bm25: int = Field(20, ge=1, le=100)
    top_k_vector: int = Field(20, ge=1, le=100)
    top_k_rrf: int = Field(12, ge=1, le=100)
    top_k_rerank: int = Field(5, ge=1, le=50)
    chunk_size: int = Field(800, ge=100, le=4000)
    chunk_overlap: int = Field(100, ge=0)
    max_upload_mb: int = Field(20, ge=1, le=100)
    request_timeout: float = Field(60, gt=0)
    vector_min_score: float = Field(0.25, ge=-1, le=1)

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        if self.reranker_enabled and (not self.reranker_base_url.strip() or not self.reranker_model.strip()):
            raise ValueError("启用重排序时必须填写 RERANKER_BASE_URL 和 RERANKER_MODEL")
        self.upload_dir = self.upload_dir or self.data_dir / "uploads"
        return self
