FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.11
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY traceable_rag ./traceable_rag
COPY main.py ./
ENV APP_HOST=0.0.0.0
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "python", "main.py"]
