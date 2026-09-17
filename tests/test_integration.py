import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from scripts.create_demo_data import create_demo_data
from traceable_rag.api import create_app
from traceable_rag.config import Settings
from traceable_rag.generation import NO_EVIDENCE


def protocol_response(request: httpx.Request) -> httpx.Response:
    """离线协议夹具只验证链路，不代表真实模型的语义能力。"""
    body = json.loads(request.content)
    if request.url.path.endswith("/embeddings"):
        return httpx.Response(200, json={"data": [{"index": index, "embedding": [1.0, 0.0]} for index, _ in enumerate(body["input"])]})
    content = body["messages"][-1]["content"]
    context_text, question = content.split("\n\n问题：", 1)
    records = json.loads(context_text.split("\n", 1)[1])
    answer = NO_EVIDENCE
    for record in records:
        if "住宿" in question and "600元" in record["text"]:
            answer = "北京普通员工住宿标准为600元每晚。" + record["id"]
            break
        if "A100" in question and "A100" in record["text"]:
            answer = "A100含税单价为1299元。" + record["id"]
            break
    return httpx.Response(200, json={"choices": [{"message": {"content": answer}, "finish_reason": "stop"}]})


def test_full_pipeline_with_protocol_fixture(tmp_path: Path) -> None:
    files = create_demo_data(tmp_path / "demo")
    settings = Settings(data_dir=tmp_path / "app", embedding_model="fixture", llm_model="fixture", _env_file=None)
    vector = QdrantClient(path=str(tmp_path / "qdrant"))
    with httpx.Client(transport=httpx.MockTransport(protocol_response)) as http:
        for cycle in range(2):
            with TestClient(create_app(settings, vector_client=vector, http_client=http)) as client:
                assert client.get("/health").json()["status"] == "ok"
                for path in files:
                    response = client.post("/documents/upload", files={"file": (path.name, path.read_bytes())})
                    assert response.status_code == 200, response.text
                    assert response.json()["duplicate"] is bool(cycle)
                assert len(client.get("/documents").json()) == 3
                for question, expected in [("北京普通员工住宿标准是多少？", "600"), ("A100型号产品多少钱？", "1299")]:
                    response = client.post("/chat", json={"question": question})
                    answer = response.json()
                    assert expected in answer["answer"], answer
                    assert answer["citations"]
                    citation = answer["citations"][0]
                    location = citation["source_location"]
                    if "A100" in question:
                        assert location["sheet_name"] == "产品价格"
                        assert location["cell_range"] == "A1:E5"
                    else:
                        assert "住宿标准" in location["section_path"]
                        assert location["paragraph_index"] is not None
                    assert client.get(f"/documents/{citation['document_id']}/file").status_code == 200
                assert client.post("/chat", json={"question": "火星基地的预算是多少？"}).json() == {"answer": NO_EVIDENCE, "citations": []}
    vector.close()
