from uuid import UUID

from qdrant_client import QdrantClient, models

from traceable_rag.domain import Chunk
from traceable_rag.utils import VectorStoreError


class VectorStore:
    def __init__(self, client: QdrantClient, collection: str) -> None:
        self.client, self.collection = client, collection

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        try:
            dimension = len(chunks[0].embedding or [])
            if not dimension:
                raise ValueError("缺少向量")
            if not self.client.collection_exists(self.collection):
                self.client.create_collection(
                    self.collection, vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE)
                )
            else:
                config = self.client.get_collection(self.collection).config.params.vectors
                if not isinstance(config, models.VectorParams) or config.size != dimension:
                    raise ValueError("已有集合的向量维度不一致")
            for offset in range(0, len(chunks), 64):
                points = [
                    models.PointStruct(
                        id=str(UUID(chunk.chunk_id[:32])),
                        vector=chunk.embedding,
                        payload=chunk.model_dump(mode="json", exclude={"embedding"}),
                    )
                    for chunk in chunks[offset : offset + 64]
                ]
                self.client.upsert(self.collection, points=points, wait=True)
        except Exception as exc:
            raise VectorStoreError("向量写入失败，请检查 Qdrant 或集合维度。") from exc

    def search(self, vector: list[float], top_k: int, allowed_ids: set[str], min_score: float) -> list[tuple[str, float]]:
        if not allowed_ids:
            return []
        try:
            result = self.client.query_points(
                self.collection,
                query=vector,
                limit=top_k,
                score_threshold=min_score,
                with_payload=True,
                query_filter=models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchAny(any=sorted(allowed_ids)))]),
            )
            return [(point.payload["chunk_id"], point.score) for point in result.points]
        except Exception as exc:
            raise VectorStoreError("向量检索失败，请检查 Qdrant 服务。") from exc

    def delete_document(self, document_id: str) -> None:
        try:
            if self.client.collection_exists(self.collection):
                selector = models.FilterSelector(
                    filter=models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))])
                )
                self.client.delete(self.collection, points_selector=selector, wait=True)
        except Exception as exc:
            raise VectorStoreError("清理旧向量失败，请检查 Qdrant 服务。") from exc
