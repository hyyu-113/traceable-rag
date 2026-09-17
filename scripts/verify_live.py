import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx


def verify(base_url: str, output: Path) -> bool:
    """通过真实 HTTP 服务验收；不替换 Embedding、LLM 或 Qdrant。"""
    report = {"time": datetime.now(UTC).isoformat(), "base_url": base_url, "checks": []}
    checks = report["checks"]
    try:
        local_service = urlparse(base_url).hostname in {"localhost", "127.0.0.1", "::1"}
        with httpx.Client(base_url=base_url, timeout=180, trust_env=not local_service) as client:
            health = client.get("/health")
            health.raise_for_status()
            if health.json()["status"] != "ok":
                raise RuntimeError("服务未就绪：请安装并启动 Qdrant，配置真实 LLM 与 Embedding 后重试。")
            checks.append({"check": "health", "ok": True})
            root = Path(__file__).resolve().parents[1]
            files = [root / "data" / "demo" / name for name in ["员工差旅管理制度.docx", "软件采购合同.docx", "产品价格表.xlsx"]]
            for path in files:
                response = client.post("/documents/upload", files={"file": (path.name, path.read_bytes())})
                response.raise_for_status()
                checks.append({"check": f"upload:{path.name}", "ok": response.json()["status"] == "ready"})
            questions = [("北京普通员工住宿标准是多少？", "600", "docx"), ("A100型号产品多少钱？", "1299", "xlsx")]
            for question, expected, kind in questions:
                response = client.post("/chat", json={"question": question})
                response.raise_for_status()
                answer = response.json()
                citations = answer.get("citations", [])
                matching = [item for item in citations if item["file_name"].endswith(kind) and expected in item["text"]]
                correct = expected in answer["answer"].replace(",", "") and bool(matching)
                if matching:
                    location = matching[0]["source_location"]
                    correct = correct and (
                        location["sheet_name"] == "产品价格" and location["cell_range"] == "A1:E5"
                        if kind == "xlsx"
                        else bool(location["paragraph_index"] or location["table_index"])
                    )
                checks.append({"check": question, "ok": correct, "result": answer})
            repeat = client.post("/documents/upload", files={"file": (files[0].name, files[0].read_bytes())})
            repeat.raise_for_status()
            checks.append({"check": "duplicate", "ok": repeat.json()["duplicate"]})
            unknown = client.post("/chat", json={"question": "火星基地的预算是多少？"})
            unknown.raise_for_status()
            checks.append({"check": "no_evidence", "ok": unknown.json() == {"answer": "根据当前知识库没有找到足够证据。", "citations": []}})
            checks.append({"check": "reranker_disabled", "ok": not health.json()["reranker_enabled"]})
    except (httpx.HTTPError, OSError, ValueError, KeyError, RuntimeError) as exc:
        checks.append({"check": "execution", "ok": False, "error_type": type(exc).__name__})
        print("真实验收未通过：检查服务状态、data/demo 文件以及 .env 配置。")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    success = bool(checks) and all(check["ok"] for check in checks)
    print(f"验收{'通过' if success else '未通过'}，报告：{output}")
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="真实服务端到端验收，不使用测试夹具")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("data/live-verification.json"))
    args = parser.parse_args()
    raise SystemExit(0 if verify(args.base_url, args.output) else 1)
