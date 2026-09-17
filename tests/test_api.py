from pathlib import Path

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from traceable_rag.api import create_app
from traceable_rag.config import Settings
from traceable_rag.generation import NO_EVIDENCE


def test_api_validation_and_empty_knowledge_base(tmp_path: Path) -> None:
    vector = QdrantClient(":memory:")
    with TestClient(create_app(Settings(data_dir=tmp_path, _env_file=None), vector_client=vector)) as client:
        assert "每一个回答" in client.get("/").text
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/health").json()["status"] == "degraded"
        assert client.get("/documents").json() == []
        assert client.post("/chat", json={"question": "住宿标准"}).json()["answer"] == NO_EVIDENCE
        assert client.post("/search", json={"query": " "}).status_code == 422
        assert client.post("/documents/upload", files={"file": ("a.exe", b"x")}).status_code == 415
        assert client.post("/documents/upload", files={"file": ("broken.pdf", b"wrong")}).status_code == 422
        assert "Traceback" not in client.post("/chat", json={"question": "?"}).text
    vector.close()


def test_chunked_upload_limit(tmp_path: Path) -> None:
    vector = QdrantClient(":memory:")
    with TestClient(create_app(Settings(data_dir=tmp_path, max_upload_mb=1, _env_file=None), vector_client=vector)) as client:
        response = client.post(
            "/documents/upload", content=iter([b"x" * 3_000_000]), headers={"Content-Type": "multipart/form-data; boundary=test"}
        )
        assert response.status_code == 413
    vector.close()
