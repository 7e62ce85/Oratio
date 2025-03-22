FROM python:3.9-slim

WORKDIR /app

# 기본 도구 및 진단 도구 설치
RUN apt-get update && apt-get install -y \
    curl \
    iputils-ping \
    net-tools \
    telnet \
    dnsutils \
    sqlite3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
    

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir werkzeug==2.0.3
RUN pip install --no-cache-dir -r requirements.txt flask==2.0.3

# Copy application code
COPY . .

# Create templates directory if it doesn't exist
RUN mkdir -p templates

# Expose port
EXPOSE 8081

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV MOCK_MODE=true

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8081", "app:app"]
