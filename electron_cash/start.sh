#!/bin/bash
set -e

echo "Starting Electron Cash..."

# 기존 지갑 파일 확인
if [ ! -f "/root/.electron-cash/wallets/default_wallet" ]; then
    echo "새 지갑 생성 중..."
    # 비대화형 모드로 빈 비밀번호를 사용하여 지갑 생성
    echo "" | electron-cash -w /root/.electron-cash/wallets/default_wallet create --no-password
    
    # 첫 번째 주소 생성
    electron-cash -w /root/.electron-cash/wallets/default_wallet getaddress > /app/wallet_address.txt
    echo "지갑 주소: $(cat /app/wallet_address.txt)"
else
    echo "기존 지갑 사용 중..."
    electron-cash -w /root/.electron-cash/wallets/default_wallet getaddress > /app/wallet_address.txt
    echo "지갑 주소: $(cat /app/wallet_address.txt)"
fi

# RPC 서버 시작
echo "RPC 서버 시작 중..."
electron-cash daemon start

# 지갑 로드
electron-cash -w /root/.electron-cash/wallets/default_wallet daemon load_wallet

echo "Electron Cash RPC 서버 실행 중 (포트 7777)"
echo "============================================"

# 컨테이너 실행 유지
tail -f /dev/null
