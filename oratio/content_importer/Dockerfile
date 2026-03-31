FROM python:3.11-slim

LABEL maintainer="admin@oratio.space"
LABEL description="Oratio Content Importer — auto-imports trending posts from across the web"

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Data volume (SQLite dedup DB)
VOLUME /data

EXPOSE 8085

CMD ["python", "app.py"]
