from traceable_rag.domain import Chunk, DocumentBlock
from traceable_rag.utils import sha256


def chunk_blocks(blocks: list[DocumentBlock], size: int = 800, overlap: int = 100) -> list[Chunk]:
    """结构块不跨来源合并；表格保持整行批次，长段落才做滑窗。"""
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("切块大小和重叠不合法")
    chunks = []
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        spans = [(0, len(text))] if block.block_type == "table" else []
        if not spans:
            start = 0
            while start < len(text):
                end = min(start + size, len(text))
                spans.append((start, end))
                if end == len(text):
                    break
                start = end - overlap
        for start, end in spans:
            chunks.append(
                Chunk(
                    chunk_id=sha256(f"v1:{block.block_id}:{start}:{end}".encode()),
                    document_id=block.document_id,
                    text=text[start:end],
                    source_location=block.source_location.model_copy(deep=True),
                    section_path=block.source_location.section_path,
                    metadata={
                        **block.metadata,
                        "block_id": block.block_id,
                        "block_type": block.block_type,
                        "char_start": start,
                        "char_end": end,
                    },
                )
            )
    return chunks
