FROM python:3.10-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never PATH="/app/.venv/bin:$PATH"

# Uncomment to get identical results between P2 and Baseline
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Lambda Web Adapter: forwards Lambda events to uvicorn; inert outside Lambda
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.0.0 /lambda-adapter /opt/extensions/lambda-adapter
ENV AWS_LWA_PORT=8000 AWS_LWA_READINESS_CHECK_PATH=/health

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY src .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]