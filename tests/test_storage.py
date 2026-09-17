from pathlib import Path

from traceable_rag.domain import Chunk, Document, SourceLocation
from traceable_rag.storage import MetadataStore


def test_commit_restart_and_interrupted_import(tmp_path: Path) -> None:
    path = tmp_path / "metadata.db"
    store = MetadataStore(path)
    doc = Document(document_id="d", file_hash="h", file_name="a.pdf", file_type="pdf", file_path="a.pdf")
    store.save_document(doc)
    assert store.chunks() == []
    assert MetadataStore(path).get_by_hash("h").status == "failed"
    chunk = Chunk(chunk_id="c", document_id="d", text="证据", source_location=SourceLocation(page_number=1))
    store.commit_chunks(doc, [chunk])
    restored = MetadataStore(path)
    assert restored.get_by_hash("h").status == "ready"
    assert restored.chunks()[0].text == "证据"
