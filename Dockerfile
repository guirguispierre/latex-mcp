FROM python:3.12-slim

# System deps for matplotlib
RUN apt-get update && apt-get install -y \
    libfreetype6-dev \
    pkg-config \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

RUN uv pip install --system --no-cache \
    "fastmcp>=2.11.3" \
    "matplotlib>=3.9.0" \
    "pydantic>=2.11.0"

COPY src/server.py ./server.py

# Pre-warm matplotlib font cache so first request is fast
RUN python3 -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; print('OK')"

EXPOSE 8000

ENV MCP_TRANSPORT=streamable-http
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000
ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["python3", "server.py"]
