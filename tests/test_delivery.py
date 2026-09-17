from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from scripts.package_release import build_archive
from traceable_rag.api import create_app
from traceable_rag.config import Settings
from traceable_rag.domain import Document


def test_chinese_validation_and_configured_upload_limit(tmp_path: Path) -> None:
    vector = QdrantClient(":memory:")
    settings = Settings(data_dir=tmp_path, max_upload_mb=3, _env_file=None)
    with TestClient(create_app(settings, vector_client=vector)) as client:
        assert client.get("/health").json()["max_upload_mb"] == 3
        for body, expected in [
            ({}, "请提供问题。"),
            ({"question": "  "}, "问题不能为空。"),
            ({"question": "隐私" * 1100}, "问题过长，最多支持2000个字符。"),
            ({"question": 123}, "问题需要填写文字。"),
            ([], "请求格式不正确，请检查输入。"),
        ]:
            response = client.post("/chat", json=body)
            assert response.status_code == 422
            assert response.json() == {"detail": expected}
        response = client.post("/search", json={"query": "秘密问题", "top_k": 51})
        assert response.json() == {"detail": "返回数量不能大于50。"}
        response = client.post("/chat", content="{", headers={"content-type": "application/json"})
        assert response.status_code == 422
        assert response.json() == {"detail": "请求内容不是有效的 JSON 格式。"}
    vector.close()


def test_original_download_after_directory_move(tmp_path: Path) -> None:
    vector = QdrantClient(":memory:")
    uploads = tmp_path / "new-uploads"
    uploads.mkdir()
    original = uploads / "abc.pdf"
    original.write_bytes(b"new original")
    stale = tmp_path / "old.pdf"
    stale.write_bytes(b"stale file must not be downloaded")
    app = create_app(Settings(data_dir=tmp_path, upload_dir=uploads, _env_file=None), vector_client=vector)
    with TestClient(app) as client:
        app.state.store.save_document(
            Document(document_id="doc", file_name="合同.pdf", file_type="pdf", file_path=str(stale), file_hash="abc", status="ready")
        )
        response = client.get("/documents/doc/file")
        assert response.status_code == 200
        assert response.content == b"new original"
        original.unlink()
        assert client.get("/documents/doc/file").status_code == 404
        app.state.store.save_document(
            Document(document_id="bad", file_name="合同.pdf", file_type="pdf", file_path=str(stale), file_hash="../old", status="ready")
        )
        assert client.get("/documents/bad/file").status_code == 404
    vector.close()


def test_release_excludes_private_and_generated_files(tmp_path: Path) -> None:
    root = tmp_path / "source"
    files = {
        "README.md": "项目说明",
        "main.py": "pass",
        ".env.example": "LLM_API_KEY=",
        "traceable_rag/api.py": "pass",
        "tests/test_api.py": "pass",
        ".vscode/launch.json": "{}",
        ".env": "private-key",
        "data/uploads/customer.pdf": "private-document",
        "docs/.hidden/private.md": "private",
        "traceable_rag/__pycache__/generated.py": "private",
        ".venv/secret.py": "private",
        "client-contract.md": "private",
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    output = tmp_path / "release.zip"
    assert build_archive(root, output) == 6
    with ZipFile(output) as archive:
        assert set(archive.namelist()) == {
            "traceable-rag/" + name
            for name in ("README.md", "main.py", ".env.example", "traceable_rag/api.py", "tests/test_api.py", ".vscode/launch.json")
        }
        assert all(b"private" not in archive.read(name) for name in archive.namelist())
    with pytest.raises(FileExistsError):
        build_archive(root, output)
