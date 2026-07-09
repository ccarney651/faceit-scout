FROM python:3.12-slim

# Faster, cleaner Python in containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FACEIT_DB=/data/faceit.sqlite3

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY faceit_sync ./faceit_sync
RUN pip install --no-cache-dir .

# SQLite lives on a mounted volume so data survives container recreation.
VOLUME ["/data"]

ENTRYPOINT ["faceit-sync"]
CMD ["--help"]
