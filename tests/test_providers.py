import httpx
import pytest
from qdrant_client import QdrantClient

from traceable_rag.config import Settings
from traceable_rag.domain import Chunk, SourceLocation
from traceable_rag.embeddings import OpenAICompatibleEmbeddingProvider
from traceable_rag.utils import EmbeddingError, sha256
from traceable_rag.vectors import VectorStore


def test_embedding_order_and_validation() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = OpenAICompatibleEmbeddingProvider(Settings(embedding_model="test", _env_file=None), client)
        assert provider.embed_documents(["a", "b"]) == [[1, 0], [0, 1]]
        with pytest.raises(EmbeddingError):
            provider.embed_query("a")


def test_real_qdrant_local() -> None:
    client = QdrantClient(":memory:")
    store = VectorStore(client, "tests")
    chunk = Chunk(chunk_id=sha256(b"c"), document_id="d", text="标准600元", embedding=[1, 0], source_location=SourceLocation(page_number=2))
    store.upsert([chunk])
    assert store.search([1, 0], 5, {"d"}, 0.2)[0][0] == chunk.chunk_id
    assert store.search([1, 0], 5, {"other"}, 0.2) == []
    store.delete_document("d")
    assert store.search([1, 0], 5, {"d"}, 0.2) == []
    client.close()
