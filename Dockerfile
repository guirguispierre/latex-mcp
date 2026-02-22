FROM python:3.12-slim

# Install system dependencies for matplotlib
RUN apt-get update && apt-get install -y \
    libfreetype6-dev \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies
RUN uv pip install --system --no-cache \
    "fastmcp>=2.11.3" \
    "matplotlib>=3.9.0" \
    "pydantic>=2.11.0"

# Copy source
COPY src/ ./src/
COPY pyproject.toml ./

# Pre-download matplotlib math fonts (speeds up first request)
RUN python3 -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; print('matplotlib OK')"

EXPOSE 8000

ENV MCP_TRANSPORT=streamable-http
ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONPATH=/app

CMD ["python3", "-m", "src.server"]
