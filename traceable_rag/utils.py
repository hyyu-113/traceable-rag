import hashlib
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_document_id(data: bytes) -> str:
    return sha256(data)


class AppError(Exception):
    status_code = 502


class UnsupportedFileTypeError(AppError):
    status_code = 415


class DocumentParseError(AppError):
    status_code = 422


class EmbeddingError(AppError):
    """向量编码服务失败。"""


class VectorStoreError(AppError):
    """向量存储失败。"""


class RetrievalError(AppError):
    """检索或重排序失败。"""


class LLMError(AppError):
    """生成服务失败。"""


def configure_logging(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(data_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", handlers=[handler, logging.StreamHandler()], force=True
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
