import tomllib
from pathlib import Path


def test_project_entrypoints() -> None:
    root = Path(__file__).parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["requires-python"] == ">=3.12,<3.13"
    assert (root / "uv.lock").is_file()
    assert '"main.py"' in (root / "Dockerfile").read_text()
    assert "qdrant/storage" in (root / "docker-compose.yml").read_text()
