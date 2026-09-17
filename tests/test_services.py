from pathlib import Path

import pytest
from docx import Document as WordDocument
from qdrant_client import QdrantClient

from traceable_rag.config import Settings
from traceable_rag.embeddings import EmbeddingProvider
from traceable_rag.rerank import NoopReranker
from traceable_rag.services import IngestionService, RetrievalService
from traceable_rag.storage import MetadataStore
from traceable_rag.utils import EmbeddingError
from traceable_rag.vectors import VectorStore


class TestEmbeddings(EmbeddingProvider):
    __test__ = False
    fail = False

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise EmbeddingError("测试故障")
        return [[1.0, 0.0] for text in texts]


def test_ingestion_duplicate_failure_and_restart(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    store = MetadataStore(tmp_path / "db.sqlite")
    embeddings = TestEmbeddings()
    client = QdrantClient(":memory:")
    vectors = VectorStore(client, "test")
    retrieval = RetrievalService(settings, store, embeddings, vectors, NoopReranker())
    ingest = IngestionService(settings, store, embeddings, vectors, retrieval)
    path = tmp_path / "sample.docx"
    word = WordDocument()
    word.add_paragraph("北京普通员工住宿标准600元。")
    word.save(path)
    embeddings.fail = True
    with pytest.raises(EmbeddingError):
        ingest.ingest(path.name, path.read_bytes())
    assert store.documents()[0].status == "failed"
    assert store.chunks() == []
    embeddings.fail = False
    document, duplicate = ingest.ingest(path.name, path.read_bytes())
    assert not duplicate and document.status == "ready"
    repeated, duplicate = ingest.ingest("renamed.docx", path.read_bytes())
    assert duplicate and repeated.document_id == document.document_id
    assert len(store.documents()) == 1
    restored = RetrievalService(settings, MetadataStore(tmp_path / "db.sqlite"), embeddings, vectors, NoopReranker())
    assert "600" in restored.search("北京住宿标准")[0].chunk.text
    client.close()
