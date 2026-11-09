# syntax=docker/dockerfile:1.7
# Build context: repository root (docker build -f api/Dockerfile .)
# Supply chain: for reproducible production builds, pin the base image by digest, e.g.
#   FROM python:3.13-slim-bookworm@sha256:<digest>   (update via Dependabot/Renovate)
FROM python:3.13-slim-bookworm AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN pip install --no-cache-dir uv==0.11.32
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY engine/pyproject.toml engine/pyproject.toml
COPY api/pyproject.toml api/pyproject.toml
# install third-party dependencies first for better layer caching
RUN --mount=type=cache,target=/root/.cache/uv \
    mkdir -p engine/src/atsurvey api/src/atsurvey_api && \
    touch engine/src/atsurvey/__init__.py api/src/atsurvey_api/__init__.py && \
    uv sync --frozen --no-dev --package atsurvey-api --no-install-workspace
COPY engine engine
COPY api api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package atsurvey-api --no-editable

FROM python:3.13-slim-bookworm
RUN useradd --system --uid 10001 --home /app app
WORKDIR /app
COPY --from=build --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "atsurvey_api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
