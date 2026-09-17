import re

import jieba
from rank_bm25 import BM25Plus

from traceable_rag.domain import Chunk, SearchResult

STOP_WORDS = {"的", "了", "是", "多少", "什么", "请问", "吗", "有", "和", "与", "请", "一下", "哪些"}


def tokenize(text: str) -> list[str]:
    return [word for word in jieba.lcut(text.lower()) if re.search(r"[\w]", word) and word not in STOP_WORDS]


class BM25Index:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        tokens = [
            tokenize(chunk.text + " " + (chunk.section_path or "") + " " + str(chunk.metadata.get("table_header", ""))) for chunk in chunks
        ]
        # BM25Plus 的正 IDF 适合小语料，避免少量文件时常见词出现负分。
        self.index = BM25Plus([words or ["__empty__"] for words in tokens], delta=0) if chunks else None

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        if self.index is None:
            return []
        scores = self.index.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], self.chunks[i].chunk_id))
        return [SearchResult(chunk=self.chunks[i], score=float(scores[i])) for i in order[:top_k] if scores[i] > 0]


def reciprocal_rank_fusion(rankings: list[list[SearchResult]], k: int = 60) -> list[SearchResult]:
    """rank 从 1 起算；每个检索列表中同一 Chunk 只计分一次。"""
    if k < 0:
        raise ValueError("k 不能小于 0")
    scores: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    for ranking in rankings:
        seen = set()
        for rank, result in enumerate(ranking, 1):
            key = result.chunk.chunk_id
            if key in seen:
                continue
            seen.add(key)
            chunks[key] = result.chunk
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return [SearchResult(chunk=chunks[key], score=score) for key, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]
