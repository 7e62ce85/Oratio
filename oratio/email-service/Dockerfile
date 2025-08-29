FROM python:3.9-slim

WORKDIR /app

# 필요한 패키지만 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 1025 8025

CMD ["python", "app.py"]
