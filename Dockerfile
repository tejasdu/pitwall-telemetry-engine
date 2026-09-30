FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./
# Sync dependencies (frozen ensures lockfile consistency)
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim-bookworm
WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

# Copy source code
COPY src /app/src

EXPOSE 8000
# Run as a non-root user for security
USER 10001

CMD ["uvicorn", "pitwall_telemetry_engine.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
