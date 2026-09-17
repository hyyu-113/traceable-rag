import logging
import threading
import time
from pathlib import Path

from traceable_rag.chunking import chunk_blocks
from traceable_rag.config import Settings
from traceable_rag.domain import Answer, Document, SearchResult
from traceable_rag.embeddings import EmbeddingProvider
from traceable_rag.generation import NO_EVIDENCE, OpenAICompatibleLLM, map_citations
from traceable_rag.loaders import LoaderFactory
from traceable_rag.rerank import RerankerProvider
from traceable_rag.retrieval import BM25Index, reciprocal_rank_fusion
from traceable_rag.storage import MetadataStore
from traceable_rag.utils import DocumentParseError, EmbeddingError, sha256, stable_document_id
from traceable_rag.vectors import VectorStore

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(
        self, settings: Settings, store: MetadataStore, embeddings: EmbeddingProvider, vectors: VectorStore, reranker: RerankerProvider
    ) -> None:
        self.settings, self.store, self.embeddings = settings, store, embeddings
        self.vectors, self.reranker = vectors, reranker
        self.lock = threading.RLock()
        self.refresh()

    def refresh(self) -> None:
        with self.lock:
            self.chunks = {chunk.chunk_id: chunk for chunk in self.store.chunks()}
            self.bm25 = BM25Index(list(self.chunks.values()))

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        started = time.perf_counter()
        with self.lock:
            if not self.chunks:
                return []
            lexical = self.bm25.search(query, self.settings.top_k_bm25)
            vector = self.embeddings.embed_query(query)
            allowed = {chunk.document_id for chunk in self.chunks.values()}
            hits = self.vectors.search(vector, self.settings.top_k_vector, allowed, self.settings.vector_min_score)
            semantic = [SearchResult(chunk=self.chunks[key], score=score) for key, score in hits if key in self.chunks]
            merged = reciprocal_rank_fusion([lexical, semantic])[: self.settings.top_k_rrf]
            results = self.reranker.rerank(query, merged, min(top_k, self.settings.top_k_rerank))
        logger.info("检索完成 results=%d elapsed_ms=%.1f", len(results), (time.perf_counter() - started) * 1000)
        return results


class IngestionService:
    def __init__(
        self, settings: Settings, store: MetadataStore, embeddings: EmbeddingProvider, vectors: VectorStore, retrieval: RetrievalService
    ) -> None:
        self.settings, self.store, self.embeddings = settings, store, embeddings
        self.vectors, self.retrieval = vectors, retrieval

    def ingest(self, file_name: str, data: bytes) -> tuple[Document, bool]:
        name = Path(file_name.replace("\\", "/")).name
        suffix = Path(name).suffix.lower()
        LoaderFactory.create(suffix)
        if not data or len(data) > self.settings.max_upload_mb * 1024 * 1024:
            raise DocumentParseError("文件为空或超过上传大小限制。")
        digest = sha256(data)
        # 单进程串行导入，查询不读取中间状态；同内容不同文件名也去重。
        with self.retrieval.lock:
            existing = self.store.get_by_hash(digest)
            if existing and existing.status == "ready":
                return existing, True
            directory = self.settings.upload_dir
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{digest}{suffix}"
            document = Document(
                document_id=stable_document_id(data), file_name=name, file_type=suffix[1:], file_path=str(path.resolve()), file_hash=digest
            )
            self.store.save_document(document)
            logger.info("文件导入 document=%s bytes=%d", digest, len(data))
            try:
                path.write_bytes(data)
                blocks = LoaderFactory.load(document)
                chunks = chunk_blocks(blocks, self.settings.chunk_size, self.settings.chunk_overlap)
                if len(chunks) > 5000:
                    raise DocumentParseError("文档切块超过5000个，请拆分后上传。")
                logger.info("切块完成 document=%s chunks=%d", digest, len(chunks))
                vectors = self.embeddings.embed_documents([chunk.text for chunk in chunks])
                if len(vectors) != len(chunks):
                    raise EmbeddingError("Embedding 数量与 Chunk 不匹配。")
                for chunk, vector in zip(chunks, vectors, strict=True):
                    chunk.embedding = vector
                self.vectors.delete_document(document.document_id)
                self.vectors.upsert(chunks)
                self.store.commit_chunks(document, chunks)
                self.retrieval.refresh()
                logger.info("索引完成 document=%s chunks=%d", digest, len(chunks))
                return document, False
            except Exception:
                document.status = "failed"
                self.store.save_document(document)
                self.retrieval.refresh()
                raise


class QaService:
    def __init__(self, retrieval: RetrievalService, llm: OpenAICompatibleLLM) -> None:
        self.retrieval, self.llm = retrieval, llm

    def answer(self, question: str) -> Answer:
        results = self.retrieval.search(question, self.retrieval.settings.top_k_rerank)
        # 不截断单个证据块，避免引用原文与模型实际读取内容不一致。
        selected, total = [], 0
        for result in results:
            size = len(result.chunk.text)
            if total + size <= 18000:
                selected.append(result)
                total += size
        if not selected:
            return Answer(answer=NO_EVIDENCE)
        raw_answer = self.llm.generate(question, selected)
        return map_citations(raw_answer, selected)
