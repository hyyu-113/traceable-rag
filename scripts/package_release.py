"""按白名单导出作品源码，排除运行数据、密钥和本机缓存。"""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT_FILES = {
    "README.md",
    "pyproject.toml",
    "uv.lock",
    "main.py",
    "start.cmd",
    "Dockerfile",
    "docker-compose.yml",
    ".env.example",
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    ".python-version",
    "traceable-rag.code-workspace",
}
DIRECTORIES = {
    "traceable_rag": {".py", ".html", ".css", ".js"},
    "tests": {".py"},
    "scripts": {".py"},
    "docs": {".md", ".png"},
    ".vscode": {".json"},
}


def build_archive(root: Path, output: Path) -> int:
    """仅收集明确允许的文件；同名压缩包存在时拒绝覆盖。"""
    root = root.resolve()
    candidates = [root / name for name in sorted(ROOT_FILES)]
    for directory, suffixes in DIRECTORIES.items():
        folder = root / directory
        if folder.is_dir() and not folder.is_symlink():
            candidates.extend(path for path in sorted(folder.rglob("*")) if path.suffix in suffixes)
    selected = []
    for path in candidates:
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts[1:]):
            continue
        if not path.resolve().is_relative_to(root):
            continue
        if any(parent.is_symlink() for parent in path.parents if parent != root and parent.is_relative_to(root)):
            continue
        selected.append((path, relative))
    if not selected:
        raise ValueError("没有可导出的作品文件。")
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for path, relative in selected:
            archive.write(path, str(Path("traceable-rag") / relative))
    return len(selected)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="导出不含密钥与运行数据的作品源码包")
    parser.add_argument("--output", type=Path, default=root.parent / "traceable-rag-作品源码.zip")
    args = parser.parse_args()
    try:
        count = build_archive(root, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"导出失败：{exc}\n")
    print(f"已导出 {count} 个文件：{args.output}")
