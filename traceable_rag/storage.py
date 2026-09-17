import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from traceable_rag.domain import Chunk, Document


class MetadataStore:
    """SQLite 是元数据事实来源；BM25 从已提交的 Chunk 重建。"""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, hash TEXT UNIQUE NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), body TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            # 单进程启动时将中断任务标记失败，允许用户再次上传同一文件恢复。
            rows = db.execute("SELECT body FROM documents WHERE status='indexing'").fetchall()
            for row in rows:
                document = Document.model_validate_json(row[0])
                document.status = "failed"
                db.execute("UPDATE documents SET status=?, body=? WHERE id=?", ("failed", document.model_dump_json(), document.document_id))

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_document(self, document: Document) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, body=excluded.body",
                (document.document_id, document.file_hash, document.status, document.model_dump_json()),
            )

    def get_by_hash(self, digest: str) -> Document | None:
        with self.connect() as db:
            row = db.execute("SELECT body FROM documents WHERE hash=?", (digest,)).fetchone()
        return Document.model_validate_json(row[0]) if row else None

    def documents(self) -> list[Document]:
        with self.connect() as db:
            rows = db.execute("SELECT body FROM documents ORDER BY rowid DESC").fetchall()
        return [Document.model_validate_json(row[0]) for row in rows]

    def commit_chunks(self, document: Document, chunks: list[Chunk]) -> None:
        document.status, document.chunk_count = "ready", len(chunks)
        with self.connect() as db:
            db.execute("DELETE FROM chunks WHERE document_id=?", (document.document_id,))
            db.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?)",
                [(chunk.chunk_id, chunk.document_id, chunk.model_dump_json(exclude={"embedding"})) for chunk in chunks],
            )
            db.execute("UPDATE documents SET status='ready', body=? WHERE id=?", (document.model_dump_json(), document.document_id))

    def chunks(self) -> list[Chunk]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT c.body FROM chunks c JOIN documents d ON c.document_id=d.id WHERE d.status='ready' ORDER BY c.rowid"
            ).fetchall()
        return [Chunk.model_validate_json(row[0]) for row in rows]

    def verify_embedding_profile(self, profile: str) -> None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='embedding_profile'").fetchone()
            if row and row[0] != profile:
                raise ValueError("Embedding 配置已变化。请使用新的 DATA_DIR 和 QDRANT_COLLECTION 重新导入。")
            db.execute("INSERT OR IGNORE INTO settings VALUES ('embedding_profile', ?)", (profile,))
