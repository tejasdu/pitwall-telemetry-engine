FROM python:3.12-slim

WORKDIR /app

# Install Astral uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project specification files and lockfile
COPY pyproject.toml uv.lock .python-version README.md ./

# Copy application source code
COPY src/ src/

# Install dependencies into container environment using uv
RUN uv sync --frozen --no-dev

# Expose internal metrics port for Prometheus
EXPOSE 8000

# Set default execution command
CMD ["uv", "run", "pitwall-telemetry-engine"]
