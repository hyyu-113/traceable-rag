@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
    if errorlevel 1 pause
    exit /b
)
where uv >nul 2>nul
if errorlevel 1 (
    echo 请先安装 Python 3.12 和 uv，再按 README 创建运行环境。
    pause
    exit /b 1
)
uv run --frozen python main.py
if errorlevel 1 pause
