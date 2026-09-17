import logging
import math
from abc import ABC, abstractmethod

import httpx

from traceable_rag.config import Settings
from traceable_rag.utils import EmbeddingError

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    def embed_text(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_query(self, query: str) -> list[float]:
        return self.embed_text(query)

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量编码，返回顺序必须与输入一致。"""


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings, client: httpx.Client) -> None:
        self.settings, self.client = settings, client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.settings.embedding_model:
            raise EmbeddingError("请配置 EMBEDDING_MODEL 和对应 API 服务。")
        vectors = []
        try:
            for offset in range(0, len(texts), 32):
                batch = texts[offset : offset + 32]
                response = self.client.post(
                    self.settings.embedding_base_url.rstrip("/") + "/embeddings",
                    headers={"Authorization": f"Bearer {self.settings.embedding_api_key.get_secret_value()}"},
                    json={"model": self.settings.embedding_model, "input": batch, "encoding_format": "float"},
                )
                response.raise_for_status()
                items = response.json()["data"]
                # JSON 的布尔值在 Python 中也是 int 子类，需要显式排除，避免错误向量入库。
                if not isinstance(items, list) or any(type(item["index"]) is not int for item in items):
                    raise ValueError("向量编码返回的索引必须为整数")
                items = sorted(items, key=lambda item: item["index"])
                for item in items:
                    values = item["embedding"]
                    if not isinstance(values, list) or any(type(value) not in (int, float) for value in values):
                        raise ValueError("向量编码返回的分量必须为数值")
                if [item["index"] for item in items] != list(range(len(batch))):
                    raise ValueError("Embedding 返回的索引不完整")
                vectors.extend([[float(value) for value in item["embedding"]] for item in items])
            if vectors and (
                not vectors[0]
                or any(
                    len(vector) != len(vectors[0]) or not all(math.isfinite(value) for value in vector) or not any(vector)
                    for vector in vectors
                )
            ):
                raise ValueError("Embedding 向量维度或数值无效")
            logger.info("Embedding 完成 count=%d", len(vectors))
            return vectors
        except Exception as exc:
            raise EmbeddingError("Embedding 调用失败，请检查模型、地址和凭据。") from exc
