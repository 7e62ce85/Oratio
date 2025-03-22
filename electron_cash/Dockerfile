FROM python:3.9-slim

WORKDIR /app

# 필요 패키지 설치
RUN apt-get update && apt-get install -y \
    wget \
    git \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
RUN pip install --no-cache-dir \
    requests \
    jsonrpclib-pelix

# Electron Cash 설치 (안정적인 버전)
RUN wget -q https://electroncash.org/downloads/4.2.7/win-linux/Electron-Cash-4.2.7.tar.gz \
    && tar -xzf Electron-Cash-4.2.7.tar.gz \
    && cd Electron-Cash-4.2.7 \
    && pip install --no-cache-dir . \
    && cd .. \
    && rm -rf Electron-Cash-4.2.7.tar.gz

# 설정 디렉토리 생성
RUN mkdir -p /root/.electron-cash/wallets \
    && chmod 700 /root/.electron-cash

# RPC 설정
RUN echo '{ \
    "rpcuser": "bchrpc", \
    "rpcpassword": "secure_password_change_me", \
    "rpchost": "0.0.0.0", \
    "rpcport": 7777 \
}' > /root/.electron-cash/config

# RPC 포트 노출
EXPOSE 7777

# # 시작 스크립트 복사
# COPY start-electron-cash.sh /app/
# RUN chmod +x /app/start-electron-cash.sh

# 환경 변수 파일 복사 부분 제거 (Docker Compose에서 환경 변수를 전달하도록 변경)
# COPY .env /.env

# RPC 포트 노출
EXPOSE 7777

# # 시작 스크립트 실행
# CMD ["/app/start-electron-cash.sh"]

# 단순화된 시작 스크립트
COPY start.sh /app/
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]

# FROM python:3.9-slim

# WORKDIR /app

# # Install dependencies
# RUN apt-get update && apt-get install -y \
#     wget \
#     git \
#     libssl-dev \
#     python3-pyqt5 \
#     && rm -rf /var/lib/apt/lists/*

# # Install Python dependencies
# RUN pip install --no-cache-dir \
#     qrcode \
#     protobuf

# # Download and install Electron Cash
# RUN wget -q https://electroncash.org/downloads/4.2.11/win-linux/Electron-Cash-4.2.11.tar.gz \
#     && tar -xzf Electron-Cash-4.2.11.tar.gz \
#     && cd Electron-Cash-4.2.11 \
#     && pip install . \
#     && cd .. \
#     && rm -rf Electron-Cash-4.2.11.tar.gz

# # Create configuration directory
# RUN mkdir -p /root/.electron-cash \
#     && chmod 700 /root/.electron-cash

# # Create JSON-RPC configuration
# RUN echo '{ \
#     "rpcuser": "bchrpc", \
#     "rpcpassword": "CHANGE_THIS_PASSWORD_IN_PRODUCTION", \
#     "rpchost": "0.0.0.0", \
#     "rpcport": 7777 \
# }' > /root/.electron-cash/config \
#     && chmod 600 /root/.electron-cash/config

# # Create a script to start Electron Cash
# COPY start-electron-cash.sh /app/
# RUN chmod +x /app/start-electron-cash.sh

# # Expose RPC port
# EXPOSE 7777

# # Run the script
# CMD ["/app/start-electron-cash.sh"]
