#!/bin/bash
set -e

echo "Starting Electron Cash Daemon..."

# 환경 변수에서 사용자 및 비밀번호 가져오기
# (Docker Compose에서 설정)
RPC_USER=${RPC_USER:-bchrpc}
RPC_PASSWORD=${RPC_PASSWORD:-secure_password_change_me}

# 설정 디렉토리 생성
mkdir -p /root/.electron-cash/wallets

# 환경 변수 설정
export PYTHONIOENCODING=utf8

# 설정 파일 생성
cat > /root/.electron-cash/config << CONFEOF
{
    "rpcuser": "${RPC_USER}",
    "rpcpassword": "${RPC_PASSWORD}",
    "rpchost": "0.0.0.0",
    "rpcport": 7777,
    "gap_limit": 100,
    "auto_connect": true
}
CONFEOF

# 지갑 파일 존재 여부 확인
if [ ! -f "/root/.electron-cash/wallets/default_wallet" ]; then
    echo "=== 신규 지갑 생성 ==="
    
    # 간단한 방법으로 지갑 생성 (constants 모듈 사용 안함)
    electron-cash create_wallet -w /root/.electron-cash/wallets/default_wallet
    
    # 지갑 비밀번호 설정 (선택사항)
    # echo "secure_wallet_password" | electron-cash -w /root/.electron-cash/wallets/default_wallet password
    
    # 중요: 실제 구현시 안전한 시드 백업 절차 필요
    echo "=== 중요: 지갑 백업을 안전하게 저장하세요 ==="
else
    echo "기존 지갑 사용 중..."
fi

# JSON-RPC 서버 시작
echo "Electron Cash 데몬 시작..."
electron-cash daemon

# 대기
sleep 5

# RPC 서버 실행
echo "RPC 서버 실행..."
electron-cash daemon load_wallet
electron-cash daemon start

echo "Electron Cash가 RPC 모드로 실행 중입니다."
echo "RPC 서버가 7777 포트에서 실행 중입니다."

# 컨테이너 실행 유지
tail -f /dev/null

# #!/bin/bash
# set -e

# echo "Starting Electron Cash Daemon..."

# # 비밀번호 설정
# WALLET_PASSWORD="securepassword123"
# WALLET_PATH="/root/.electron-cash/wallets/default_wallet"

# # 설정 디렉토리 생성
# mkdir -p /root/.electron-cash/wallets

# # 환경 변수 설정 - 대화형 프롬프트 방지
# export PYTHONIOENCODING=utf8

# # 지갑 파일이 존재하는지 확인
# if [ ! -f "$WALLET_PATH" ]; then
#     echo "Creating new wallet..."
    
#     # 저장된 시드로 지갑 생성 (테스트용)
#     TEST_SEED="witch collapse practice feed shame open despair creek road again ice least"
    
#     # 비대화형 방식으로 지갑 생성
#     mkdir -p /tmp/electrum_data
#     echo "$TEST_SEED" > /tmp/seed.txt
#     echo "$WALLET_PASSWORD" > /tmp/password.txt
    
#     # 수동으로 지갑 파일 생성
#     cat > "$WALLET_PATH" << EOF
# {
#     "wallet_type": "standard",
#     "use_encryption": true,
#     "seed": "$TEST_SEED",
#     "seed_version": 11
# }
# EOF
    
#     echo "Created wallet with test seed. DO NOT USE FOR REAL FUNDS!"
# else
#     echo "Using existing wallet..."
# fi

# # 데몬 실행
# echo "Starting Electron Cash daemon..."
# electron-cash daemon

# # 잠시 대기
# sleep 5

# # 간단한 JSON-RPC 서버 수동 시작
# echo "Starting JSON-RPC server..."
# cat > /tmp/rpc_server.py << EOF
# import os
# import time
# from electroncash import commands, daemon

# config = daemon.get_config()
# config.set_key('rpcuser', 'bchrpc')
# config.set_key('rpcpassword', 'CHANGE_THIS_PASSWORD_IN_PRODUCTION')
# config.set_key('rpchost', '0.0.0.0')
# config.set_key('rpcport', 7777)

# d = daemon.Daemon(config, daemon.get_fd_or_server)
# cmd = commands.Commands(config, None, d)
# d.start()

# print("RPC server running on port 7777")
# while True:
#     time.sleep(1)
# EOF

# python3 /tmp/rpc_server.py &

# echo "Electron Cash is running with JSON-RPC enabled."
# echo "RPC server listening on port 7777"

# # 컨테이너 실행 유지
# tail -f /dev/null
