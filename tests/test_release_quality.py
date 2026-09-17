from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from traceable_rag.api import create_app
from traceable_rag.config import Settings
from traceable_rag.embeddings import OpenAICompatibleEmbeddingProvider
from traceable_rag.utils import EmbeddingError


@pytest.mark.parametrize("top_k", [True, False, 1.0, "5"])
def test_search_requires_json_integer(tmp_path: Path, top_k: object) -> None:
    vector = QdrantClient(":memory:")
    try:
        with TestClient(create_app(Settings(data_dir=tmp_path, _env_file=None), vector_client=vector)) as client:
            response = client.post("/search", json={"query": "住宿", "top_k": top_k})
            assert response.status_code == 422
            assert response.json() == {"detail": "返回数量需要填写整数。"}
    finally:
        vector.close()


@pytest.mark.parametrize("index, embedding", [(False, [1, 0]), (0.0, [1, 0]), (0, [True, False]), (0, ["1", "0"])])
def test_embedding_rejects_coerced_protocol_values(index: object, embedding: list) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": index, "embedding": embedding}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = OpenAICompatibleEmbeddingProvider(Settings(embedding_model="fixture", _env_file=None), client)
        with pytest.raises(EmbeddingError):
            provider.embed_query("测试")


@pytest.mark.parametrize(
    "settings",
    [
        {"app_port": 0},
        {"app_port": 65536},
        {"reranker_enabled": True},
        {"reranker_enabled": True, "reranker_base_url": "https://example.test/rerank"},
    ],
)
def test_invalid_startup_configuration(settings: dict) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, **settings)
