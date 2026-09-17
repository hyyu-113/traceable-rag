from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceLocation(BaseModel):
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    section_path: str | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    row_start: int | None = None
    row_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    sheet_name: str | None = None
    cell_range: str | None = None


class Document(BaseModel):
    document_id: str
    file_name: str
    file_type: str
    file_path: str
    file_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["indexing", "ready", "failed"] = "indexing"
    chunk_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentBlock(BaseModel):
    block_id: str
    document_id: str
    block_type: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_location: SourceLocation


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    source_location: SourceLocation
    section_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class SearchResult(BaseModel):
    chunk: Chunk
    score: float


class Citation(BaseModel):
    citation_id: str
    document_id: str
    chunk_id: str
    file_name: str
    text: str
    source_location: SourceLocation


class Answer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
