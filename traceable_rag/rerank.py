import math
from abc import ABC, abstractmethod

import httpx

from traceable_rag.config import Settings
from traceable_rag.domain import SearchResult
from traceable_rag.utils import RetrievalError


class RerankerProvider(ABC):
    @abstractmethod
    def rerank(self, query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        """对候选重新排序。"""


BaseReranker = RerankerProvider


class NoopReranker(BaseReranker):
    def rerank(self, query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        return results[:top_k]


class HttpReranker(BaseReranker):
    def __init__(self, settings: Settings, client: httpx.Client) -> None:
        self.settings, self.client = settings, client

    def rerank(self, query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        if not results:
            return []
        try:
            response = self.client.post(
                self.settings.reranker_base_url,
                headers={"Authorization": f"Bearer {self.settings.reranker_api_key.get_secret_value()}"},
                json={
                    "model": self.settings.reranker_model,
                    "query": query,
                    "documents": [item.chunk.text for item in results],
                    "top_n": min(top_k, len(results)),
                },
            )
            response.raise_for_status()
            rows = response.json()["results"]
            ranked, seen = [], set()
            for row in rows:
                index, score = row["index"], float(row["relevance_score"])
                if (
                    not isinstance(index, int)
                    or isinstance(index, bool)
                    or index < 0
                    or index >= len(results)
                    or index in seen
                    or not math.isfinite(score)
                ):
                    raise ValueError("非法重排序结果")
                seen.add(index)
                ranked.append(SearchResult(chunk=results[index].chunk, score=score))
            if len(ranked) < min(top_k, len(results)):
                raise ValueError("重排序结果不完整")
            return sorted(ranked, key=lambda item: -item.score)[:top_k]
        except Exception as exc:
            raise RetrievalError("重排序调用失败，请检查 HTTP 协议配置，或关闭 RERANKER_ENABLED。") from exc
