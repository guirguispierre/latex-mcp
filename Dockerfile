FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    libfreetype6-dev \
    libpng-dev \
    pkg-config \
    fonts-dejavu-core \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastmcp>=2.11.3" \
    "matplotlib>=3.9.0" \
    "pydantic>=2.11.0" \
    "uvicorn>=0.35.0"

COPY src/ ./src/
RUN touch src/__init__.py

# Verify matplotlib works headless
RUN python3 -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; print('matplotlib OK')"

ENV MCP_TRANSPORT=streamable-http
ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONPATH=/app
ENV MPLBACKEND=Agg

EXPOSE 8000

CMD ["python", "-m", "src.server"]
