#!/bin/bash

# Directory for shared files
SHARED_DIR="/shared"
mkdir -p "$SHARED_DIR"

# Set executable permissions for our authentication script
chmod +x /electron-cash/setup_auth.sh

# Run the authentication setup script
/electron-cash/setup_auth.sh

# Start the Electron Cash daemon
echo "[$(date +"%Y-%m-%d %H:%M:%S")] RPC 설정 업데이트 중..."
source /shared/electron_cash_auth.env

# Create wallet if it doesn't exist
if [ ! -f "/root/.electron-cash/wallets/default_wallet" ]; then
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] 새 지갑을 생성합니다..."
    electron-cash create
else
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] 기존 지갑을 사용합니다: /root/.electron-cash/wallets/default_wallet"
fi

# Start the daemon with the correct RPC settings
echo "[$(date +"%Y-%m-%d %H:%M:%S")] ElectronCash RPC 서버 시작 중..."
electron-cash daemon start
sleep 2

# Test if wallet is loaded
echo "[$(date +"%Y-%m-%d %H:%M:%S")] 지갑 로드 중..."
electron-cash daemon load_wallet
sleep 2
electron-cash listaddresses

# Test wallet info
echo "[$(date +"%Y-%m-%d %H:%M:%S")] 지갑 정보 확인 중..."
electron-cash getinfo || true

# Test new address creation
echo "[$(date +"%Y-%m-%d %H:%M:%S")] 주소 생성 테스트 중..."
NEW_ADDRESS=$(python3 /app/electron-cash daemon getunusedaddress 2>&1) || echo "[$(date +"%Y-%m-%d %H:%M:%S")] 새 주소를 생성할 수 없습니다."
if [[ "$NEW_ADDRESS" == bitcoincash:* ]]; then
  echo "[$(date +"%Y-%m-%d %H:%M:%S")] 새 주소 생성 성공: $NEW_ADDRESS"
else
  echo "[$(date +"%Y-%m-%d %H:%M:%S")] 새 주소 생성 실패 또는 예상치 못한 응답: $NEW_ADDRESS"
fi

# Test JSON-RPC connection from another container's perspective
echo "[$(date +"%Y-%m-%d %H:%M:%S")] JSON-RPC 서버 연결 테스트 중..."
curl -s --user "$ELECTRON_CASH_USER:$ELECTRON_CASH_PASSWORD" -X POST -H "Content-Type: application/json" -d '{"method":"getinfo","params":[],"id":1}' http://localhost:7777/
if [ $? -eq 0 ]; then
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] JSON-RPC 서버 연결 성공!"
else
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] JSON-RPC 서버 연결 실패. 오류를 확인하세요."
fi

echo "[$(date +"%Y-%m-%d %H:%M:%S")] ElectronCash 서버가 실행 중입니다. 로그를 확인하세요."

# Keep the container running
tail -f /dev/null