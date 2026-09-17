import httpx
import pytest
from test_retrieval import result

from traceable_rag.config import Settings
from traceable_rag.rerank import HttpReranker, NoopReranker
from traceable_rag.utils import RetrievalError


def test_noop_and_http() -> None:
    items = [result("a"), result("b")]
    assert NoopReranker().rerank("q", items, 1) == items[:1]
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"results": [{"index": 1, "relevance_score": 0.9}]}))
    ) as client:
        reranker = HttpReranker(Settings(reranker_base_url="https://test/rerank", _env_file=None), client)
        assert reranker.rerank("q", items, 1)[0].chunk.chunk_id == "b"
        with pytest.raises(RetrievalError):
            reranker.rerank("q", items, 2)
