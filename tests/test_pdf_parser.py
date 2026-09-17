from pathlib import Path

import pytest
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas
from test_loaders import document

from traceable_rag.chunking import chunk_blocks
from traceable_rag.loaders import LoaderFactory
from traceable_rag.utils import DocumentParseError


def test_chinese_pages_and_top_left_coordinates(tmp_path: Path) -> None:
    path = tmp_path / "中文制度.pdf"
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    canvas = Canvas(str(path), pagesize=(600, 800))
    canvas.setFont("STSong-Light", 12)
    canvas.drawString(72, 728, "北京住宿标准为600元。")
    canvas.drawString(72, 550, "上海住宿标准为500元。")
    canvas.showPage()
    canvas.setFont("STSong-Light", 12)
    canvas.drawString(72, 700, "软件交付期限为20个工作日。")
    canvas.save()
    blocks = LoaderFactory.load(document(path))
    assert [b.source_location.page_number for b in blocks] == [1, 1, 2]
    assert "北京住宿标准为600元" in blocks[0].text
    assert "上海住宿标准为500元" in blocks[1].text
    assert "20个工作日" in blocks[2].text
    left, top, right, bottom = blocks[0].source_location.bbox
    assert left == pytest.approx(72)
    assert 50 < top < bottom < 90
    assert left < right <= 600
    assert blocks[0].metadata["page_height"] == 800
    chunks = chunk_blocks(blocks)
    assert chunks[0].source_location == blocks[0].source_location
    assert chunks[0].metadata["pdf_parser"] == "pdfminer.six"


def test_form_xobject_text_is_not_lost_or_duplicated(tmp_path: Path) -> None:
    path = tmp_path / "form.pdf"
    canvas = Canvas(str(path), pagesize=(600, 800))
    canvas.beginForm("form")
    canvas.drawString(72, 700, "Text inside a form")
    canvas.endForm()
    canvas.doForm("form")
    canvas.save()
    blocks = LoaderFactory.load(document(path))
    assert len(blocks) == 1
    assert blocks[0].text == "Text inside a form"


@pytest.mark.parametrize("password", ["secret", ""])
def test_encrypted_pdf_has_clear_error(tmp_path: Path, password: str) -> None:
    path = tmp_path / "encrypted.pdf"
    canvas = Canvas(str(path), encrypt=StandardEncryption(password, ownerPassword="owner"))
    canvas.drawString(72, 700, "Private text")
    canvas.save()
    with pytest.raises(DocumentParseError, match="加密 PDF"):
        LoaderFactory.load(document(path))


def test_damaged_pdf_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nnot a valid document")
    with pytest.raises(DocumentParseError, match="解析失败"):
        LoaderFactory.load(document(path))


def test_rotated_page_keeps_valid_coordinates(tmp_path: Path) -> None:
    path = tmp_path / "rotated.pdf"
    canvas = Canvas(str(path), pagesize=(600, 800))
    canvas.setPageRotation(90)
    canvas.drawString(72, 400, "Rotated text")
    canvas.save()
    blocks = LoaderFactory.load(document(path))
    assert blocks
    for block in blocks:
        x0, y0, x1, y1 = block.source_location.bbox
        assert 0 <= x0 < x1 <= block.metadata["page_width"]
        assert 0 <= y0 < y1 <= block.metadata["page_height"]
        assert block.source_location.page_number == 1


def test_image_only_pdf_requests_ocr(tmp_path: Path) -> None:
    from PIL import Image

    path = tmp_path / "scan.pdf"
    canvas = Canvas(str(path))
    canvas.drawInlineImage(Image.new("RGB", (100, 100), "white"), 72, 500)
    canvas.save()
    with pytest.raises(DocumentParseError, match="OCR"):
        LoaderFactory.load(document(path))


def test_pdf_upload_search_citation_and_download(tmp_path: Path) -> None:
    import httpx
    from fastapi.testclient import TestClient
    from qdrant_client import QdrantClient
    from test_integration import protocol_response

    from traceable_rag.api import create_app
    from traceable_rag.config import Settings

    path = tmp_path / "差旅.pdf"
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    canvas = Canvas(str(path), pagesize=(600, 800))
    canvas.setFont("STSong-Light", 12)
    canvas.drawString(72, 728, "北京普通员工住宿标准为600元。")
    canvas.save()
    settings = Settings(data_dir=tmp_path / "app", embedding_model="fixture", llm_model="fixture", _env_file=None)
    vector = QdrantClient(":memory:")
    try:
        with (
            httpx.Client(transport=httpx.MockTransport(protocol_response)) as http,
            TestClient(create_app(settings, vector_client=vector, http_client=http)) as client,
        ):
            response = client.post("/documents/upload", files={"file": (path.name, path.read_bytes())})
            assert response.status_code == 200, response.text
            answer = client.post("/chat", json={"question": "北京住宿标准是多少？"}).json()
            assert "600" in answer["answer"]
            citation = answer["citations"][0]
            assert citation["source_location"]["page_number"] == 1
            assert citation["source_location"]["bbox"][1] < 90
            assert client.get("/documents/" + citation["document_id"] + "/file").content == path.read_bytes()
    finally:
        vector.close()
