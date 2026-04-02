FROM python:3.11-slim

WORKDIR /app

# System deps: poppler-utils cho pypdf (PDF text extract), curl cho healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency install
RUN pip install uv

# Copy dependency spec first (layer cache)
COPY pyproject.toml .
RUN uv pip install --system -e ".[test]"

# Copy source
COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
