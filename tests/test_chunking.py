from traceable_rag.chunking import chunk_blocks
from traceable_rag.domain import DocumentBlock, SourceLocation


def test_overlap_and_provenance() -> None:
    block = DocumentBlock(
        block_id="b",
        document_id="d",
        block_type="paragraph",
        text="0123456789abcdef",
        source_location=SourceLocation(page_number=2),
        metadata={"file_name": "test.pdf"},
    )
    chunks = chunk_blocks([block], 10, 3)
    assert [chunk.text for chunk in chunks] == ["0123456789", "789abcdef"]
    assert all(chunk.source_location.page_number == 2 for chunk in chunks)
    assert chunks[1].metadata["char_start"] == 7
    assert chunks[0].chunk_id == chunk_blocks([block], 10, 3)[0].chunk_id


def test_table_not_split() -> None:
    block = DocumentBlock(
        block_id="t",
        document_id="d",
        block_type="table",
        text="城市 | 标准\n北京 | 600" * 40,
        source_location=SourceLocation(table_index=1),
    )
    assert len(chunk_blocks([block], 100, 10)) == 1
