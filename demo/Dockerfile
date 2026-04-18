FROM python:3.13-slim AS base

# System deps for cryptography wheel
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy build metadata (hatchling needs README.md)
COPY pyproject.toml uv.lock README.md ./

# Install all dependencies including demo deps (layer cache)
COPY src/ src/
RUN uv sync --frozen

# Copy demo app
COPY demo/ demo/

# Demo entrypoint
COPY demo/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000

# Runtime config — secrets passed at run time, not baked in
ENV AGENTWRIT_BROKER_URL=http://broker:8080
ENV LLM_BASE_URL=https://api.openai.com/v1
ENV LLM_MODEL=gpt-4o-mini

ENTRYPOINT ["/entrypoint.sh"]
