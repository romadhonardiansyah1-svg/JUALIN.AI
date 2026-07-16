# JUALIN.AI Backend — Dockerfile
FROM python:3.14.6-slim

WORKDIR /app

# System deps for psycopg2 + build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Pre-download embedding model (cached in volume)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" || true

# Expose port
EXPOSE 8000

# Run with a single worker by default.
# Multiple workers duplicate the in-process scheduler and embedding model memory.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}"]
