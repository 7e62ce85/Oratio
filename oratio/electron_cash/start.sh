#!/bin/bash
set -e

# 환경 변수 확인
RPC_USER=${RPC_USER:-bchrpc}
RPC_PASSWORD=${RPC_PASSWORD:-secure_password_change_me}

# 로그 함수
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# 디렉토리 생성
mkdir -p /root/.electron-cash/wallets

# RPC 설정 업데이트
log "RPC 설정 업데이트 중..."
cat > /root/.electron-cash/config << EOF
{
  "rpcuser": "${RPC_USER}",
  "rpcpassword": "${RPC_PASSWORD}",
  "rpchost": "0.0.0.0",
  "rpcport": 7777,
  "netuser": "${RPC_USER}",
  "netpassword": "${RPC_PASSWORD}"
}
EOF

chmod 600 /root/.electron-cash/config

# ElectronCash가 HD 지갑을 사용하도록 설정
cat > /root/.electron-cash/electron-cash.conf << EOF
[client]
gap_limit = 200
use_change = True
multiple_change = True
EOF

# 지갑 파일 존재 여부 확인
WALLET_PATH="/root/.electron-cash/wallets/default_wallet"
if [ ! -f "$WALLET_PATH" ]; then
  log "지갑 파일이 없습니다. 새 지갑을 생성합니다..."
  
  # 새 방식: 지갑 생성 방식 변경
  log "지갑 생성 시도 중..."
  
  # 새 방식 - 표준 명령을 사용하여 지갑 생성 (입력 파이프 처리 추가)
  echo -e "\n\n" | python3 /app/electron-cash create -w "$WALLET_PATH" 2>/root/.electron-cash/wallet_create.log
  
  # 생성 성공 여부 확인 및 디버깅
  if [ -f "$WALLET_PATH" ]; then
    log "지갑 파일이 성공적으로 생성되었습니다: $WALLET_PATH"
    # 시드 구문 찾아서 저장
    grep -A 2 "Your wallet generation seed is:" /root/.electron-cash/wallet_create.log > /root/.electron-cash/seed_phrase.txt 2>/dev/null || true
    chmod 600 /root/.electron-cash/seed_phrase.txt
  else
    log "지갑 생성 실패. 대체 방법으로 시도..."
    cat /root/.electron-cash/wallet_create.log
    
    # 추가 대체 방법: 간단한 지갑 파일 직접 생성
    cat > "$WALLET_PATH" << EOF
{
    "addr_history": {},
    "addresses": {},
    "keystore": {
        "type": "standard"
    },
    "pruned_txo": {},
    "stored_height": 0,
    "transactions": {},
    "tx_fees": {},
    "txi": {},
    "txo": {},
    "verified_tx3": {},
    "wallet_type": "standard"
}
EOF
    chmod 600 "$WALLET_PATH"
    log "기본 지갑 파일을 직접 생성했습니다."
  fi
else
  log "기존 지갑을 사용합니다: $WALLET_PATH"
fi

# RPC 서버 실행 (데몬 모드로 변경)
log "ElectronCash RPC 서버 시작 중..."
python3 /app/electron-cash daemon start

# 지갑 로드
sleep 5
log "지갑 로드 중..."
python3 /app/electron-cash daemon load_wallet -w "$WALLET_PATH" 2>/root/.electron-cash/wallet_load.log

if [ $? -ne 0 ]; then
  log "지갑 로드 중 오류 발생. 오류 내용:"
  cat /root/.electron-cash/wallet_load.log
  log "기본 작업으로 계속 진행합니다."
fi

# 지갑 정보 출력
log "지갑 정보 확인 중..."
python3 /app/electron-cash daemon getinfo 2>&1 || log "지갑 정보를 가져올 수 없습니다."

# 주소 생성 테스트 - 올바른 명령어 사용 (createnewaddress -> getunusedaddress)
log "주소 생성 테스트 중..."
NEW_ADDRESS=$(python3 /app/electron-cash daemon getunusedaddress 2>&1) || log "새 주소를 생성할 수 없습니다."
if [[ "$NEW_ADDRESS" == bitcoincash:* ]]; then
  log "새 주소 생성 성공: $NEW_ADDRESS"
else
  log "새 주소 생성 실패 또는 예상치 못한 응답: $NEW_ADDRESS"
  
  # 대체 방법 시도
  log "대체 방법 시도: 다른 형식의 명령어"
  NEW_ADDRESS=$(python3 /app/electron-cash daemon -w "$WALLET_PATH" getunusedaddress 2>&1) || log "두 번째 주소 생성 시도도 실패했습니다."
  if [[ "$NEW_ADDRESS" == bitcoincash:* ]]; then
    log "두 번째 시도로 주소 생성 성공: $NEW_ADDRESS"
  else
    log "모든 주소 생성 방법 실패: $NEW_ADDRESS"
  fi
fi

# JSON-RPC 서버가 정상적으로 실행 중인지 확인
log "JSON-RPC 서버 연결 테스트 중..."
for i in {1..5}; do
  if curl -s -u "${RPC_USER}:${RPC_PASSWORD}" -X POST -H "Content-Type: application/json" \
       -d '{"id":"curltest","method":"getinfo","params":[]}' http://localhost:7777 > /dev/null; then
    log "JSON-RPC 서버 연결 성공!"
    break
  else
    log "JSON-RPC 서버 연결 실패, 재시도 ${i}/5..."
    sleep 2
  fi
done

# 프로세스를 계속 실행하여 컨테이너 유지
log "ElectronCash 서버가 실행 중입니다. 로그를 확인하세요."
exec tail -f /dev/null

# 주기적으로 상태 확인 (5분마다)
while true; do
  sleep 300
  log "ElectronCash 상태 확인 중..."
  python3 /app/electron-cash daemon getinfo 2>&1 || log "전자 현금 데몬이 응답하지 않습니다. 재시작이 필요할 수 있습니다."
done