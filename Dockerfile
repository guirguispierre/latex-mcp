FROM python:3.12-slim

# Install system dependencies for matplotlib
RUN apt-get update && apt-get install -y \
    libfreetype6-dev \
    libpng-dev \
    pkg-config \
    fonts-dejavu-core \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastmcp>=2.11.3" \
    "matplotlib>=3.9.0" \
    "pydantic>=2.11.0"

# Copy source
COPY src/ ./src/

# Create __init__.py so src is a package
RUN touch src/__init__.py

ENV MCP_TRANSPORT=streamable-http
ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONPATH=/app
ENV MPLBACKEND=Agg

EXPOSE 8000

CMD ["python", "-m", "src.server"]
