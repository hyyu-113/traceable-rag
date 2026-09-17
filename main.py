import os
from pathlib import Path

import uvicorn

from traceable_rag.api import create_app
from traceable_rag.config import Settings


def main() -> None:
    """统一工作目录，使 VSCode 和命令行读取同一份配置。"""
    os.chdir(Path(__file__).resolve().parent)
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.app_host, port=settings.app_port, workers=1)


if __name__ == "__main__":
    main()
