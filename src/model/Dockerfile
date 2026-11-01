FROM python:3.10-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY create_model.py .
COPY src/data ./data

CMD ["python", "create_model.py"]