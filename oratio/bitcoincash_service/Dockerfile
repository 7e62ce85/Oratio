FROM python:3.9-slim

# 컨테이너 메타데이터 추가
LABEL maintainer="admin@oratio.space"
LABEL version="1.0"
LABEL description="Bitcoin Cash 결제 서비스"

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

# ContainerConfig 문제 해결을 위해 볼륨 디렉토리 명시적 생성
VOLUME /app/data

# 의존성 설치
COPY requirements.txt .
# 특정 버전 먼저 설치
RUN pip install --no-cache-dir werkzeug==2.0.3 flask==2.0.3
# 나머지 요구 사항 설치
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# templates 디렉토리가 없으면 생성
RUN mkdir -p templates

# 스크립트를 실행 가능하게 설정
RUN chmod +x /app/start.sh

# 포트 노출
EXPOSE 8081

# 환경 변수 설정
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV MOCK_MODE=true

# 애플리케이션 실행
CMD ["/app/start.sh"]
