import logging
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from qdrant_client import QdrantClient
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from traceable_rag.config import Settings
from traceable_rag.domain import Answer, SearchResult
from traceable_rag.embeddings import OpenAICompatibleEmbeddingProvider
from traceable_rag.generation import OpenAICompatibleLLM
from traceable_rag.rerank import HttpReranker, NoopReranker
from traceable_rag.services import IngestionService, QaService, RetrievalService
from traceable_rag.storage import MetadataStore
from traceable_rag.utils import AppError, configure_logging
from traceable_rag.vectors import VectorStore

logger = logging.getLogger(__name__)


class RequestSizeLimit:
    """在 multipart 解析前计数，避免无 Content-Length 的上传绕过大小限制。"""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length", b"0")
        if not length.isdigit() or int(length) > self.max_bytes:
            await JSONResponse(status_code=413, content={"detail": "请求超过上传大小限制。"})(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                raise HTTPException(413, "请求超过上传大小限制。")
            return message

        await self.app(scope, limited_receive, send)


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=50, strict=True)


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=2000)


def log_exception(exc: Exception) -> None:
    # 保留每层异常类型和完整调用栈，不记录上游异常字符串，避免泄露响应正文、URL 凭据。
    chain: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        chain.append(type(current).__name__ + "\n" + "".join(traceback.format_tb(current.__traceback__)))
        current = current.__cause__
    logger.error("请求失败\n%s", "\n异常原因：\n".join(chain))


def create_app(
    settings: Settings | None = None, vector_client: QdrantClient | None = None, http_client: httpx.Client | None = None
) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(config.data_dir)
        client = http_client or httpx.Client(timeout=config.request_timeout)
        # 本地数据库直连，避免系统代理拦截 localhost 请求。
        local_qdrant = urlparse(config.qdrant_url).hostname in {"localhost", "127.0.0.1", "::1"}
        qdrant = vector_client or QdrantClient(
            url=config.qdrant_url,
            timeout=10,
            check_compatibility=False,
            trust_env=not local_qdrant,
        )
        try:
            store = MetadataStore(config.data_dir / "indexes" / "metadata.sqlite3")
            if config.embedding_model:
                store.verify_embedding_profile(f"{config.embedding_base_url}|{config.embedding_model}")
            embeddings = OpenAICompatibleEmbeddingProvider(config, client)
            vectors = VectorStore(qdrant, config.qdrant_collection)
            reranker = HttpReranker(config, client) if config.reranker_enabled else NoopReranker()
            retrieval = RetrievalService(config, store, embeddings, vectors, reranker)
            app.state.store = store
            app.state.retrieval = retrieval
            app.state.ingestion = IngestionService(config, store, embeddings, vectors, retrieval)
            app.state.qa = QaService(retrieval, OpenAICompatibleLLM(config, client))
            app.state.qdrant = qdrant
            logger.info("服务启动 documents=%d reranker=%s", len(store.documents()), config.reranker_enabled)
            yield
        finally:
            if http_client is None:
                client.close()
            if vector_client is None:
                qdrant.close()
            logger.info("服务关闭")

    app = FastAPI(title="企业文档智能知识库", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestSizeLimit, max_bytes=(config.max_upload_mb + 1) * 1024 * 1024)
    static_dir = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        log_exception(exc)
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        log_exception(exc)
        return JSONResponse(status_code=500, content={"detail": "暂时无法处理请求，请稍后重试或联系管理员。"})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 不返回原始输入，避免将问题正文或文件信息带入错误响应。
        error = exc.errors()[0]
        field = {"question": "问题", "query": "检索内容", "top_k": "返回数量", "file": "上传文件"}.get(
            str(error["loc"][-1]) if error["loc"] else "", "请求内容"
        )
        messages = {
            "missing": f"请提供{field}。",
            "string_too_short": f"{field}不能为空。",
            "string_too_long": f"{field}过长，最多支持2000个字符。",
            "string_type": f"{field}需要填写文字。",
            "int_parsing": f"{field}需要填写整数。",
            "int_type": f"{field}需要填写整数。",
            "int_from_float": f"{field}需要填写整数。",
            "greater_than_equal": f"{field}不能小于1。",
            "less_than_equal": f"{field}不能大于50。",
            "json_invalid": "请求内容不是有效的 JSON 格式。",
        }
        return JSONResponse(status_code=422, content={"detail": messages.get(error["type"], "请求格式不正确，请检查输入。")})

    @app.get("/health", summary="检查服务状态", tags=["服务状态"])
    def health() -> dict[str, Any]:
        try:
            app.state.qdrant.get_collections()
            vector_ready = True
        except Exception as exc:  # noqa: BLE001 -- 健康检查必须在外部服务异常时仍返回状态
            log_exception(exc)
            vector_ready = False
        configured = bool(config.llm_model and config.embedding_model)
        return {
            "status": "ok" if vector_ready and configured else "degraded",
            "qdrant": vector_ready,
            "models_configured": configured,
            "reranker_enabled": config.reranker_enabled,
            "max_upload_mb": config.max_upload_mb,
        }

    @app.get("/documents", summary="查看文档列表", tags=["文档管理"])
    def documents() -> list[dict[str, Any]]:
        return [document.model_dump(mode="json", exclude={"file_path"}) for document in app.state.store.documents()]

    @app.post("/documents/upload", summary="上传并建立索引", tags=["文档管理"])
    async def upload(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        try:
            data = await file.read(config.max_upload_mb * 1024 * 1024 + 1)
            if len(data) > config.max_upload_mb * 1024 * 1024:
                raise HTTPException(413, "文件超过上传大小限制。")
            document, duplicate = await run_in_threadpool(app.state.ingestion.ingest, file.filename or "", data)
            return {
                "document_id": document.document_id,
                "file_name": document.file_name,
                "chunk_count": document.chunk_count,
                "status": document.status,
                "duplicate": duplicate,
            }
        finally:
            await file.close()

    @app.get("/documents/{document_id}/file", summary="下载原始文档", tags=["文档管理"])
    def original(document_id: str) -> FileResponse:
        document = next((item for item in app.state.store.documents() if item.document_id == document_id), None)
        if document is None or document.status != "ready":
            raise HTTPException(404, "原文件不存在或尚未完成索引。")
        # 上传文件按内容哈希命名；从当前配置定位，兼容目录迁移和容器挂载。
        upload_root = config.upload_dir.resolve()
        original_path = (upload_root / f"{document.file_hash}.{document.file_type}").resolve()
        if not original_path.is_relative_to(upload_root) or not original_path.is_file():
            raise HTTPException(404, "原文件不存在，请联系管理员检查文档存储。")
        return FileResponse(original_path, filename=document.file_name)

    @app.post("/search", response_model=list[SearchResult], summary="检索原文片段", tags=["检索问答"])
    def search(body: SearchRequest) -> list[SearchResult]:
        return app.state.retrieval.search(body.query, body.top_k)

    @app.post("/chat", response_model=Answer, summary="根据文档回答问题", tags=["检索问答"])
    def chat(body: ChatRequest) -> Answer:
        return app.state.qa.answer(body.question)

    return app
