import pytest

from traceable_rag.domain import Chunk, SearchResult, SourceLocation
from traceable_rag.retrieval import BM25Index, reciprocal_rank_fusion


def result(key: str, text: str = "证据") -> SearchResult:
    return SearchResult(chunk=Chunk(chunk_id=key, document_id="d", text=text, source_location=SourceLocation()), score=1)


def test_rrf_formula_and_duplicates() -> None:
    a, b, c = result("a"), result("b"), result("c")
    merged = reciprocal_rank_fusion([[a, b], [b, c]])
    assert [item.chunk.chunk_id for item in merged] == ["b", "a", "c"]
    assert merged[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert reciprocal_rank_fusion([[a, a]])[0].score == pytest.approx(1 / 61)
    assert reciprocal_rank_fusion([]) == []


def test_chinese_and_product_search() -> None:
    index = BM25Index([result("a", "北京普通员工住宿标准600元").chunk, result("b", "A100 产品价格1200元").chunk])
    assert index.search("北京住宿标准", 2)[0].chunk.chunk_id == "a"
    assert index.search("A100多少钱", 2)[0].chunk.chunk_id == "b"
    assert index.search("火星天气", 2) == []
