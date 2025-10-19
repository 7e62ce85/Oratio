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

# RPC 서버 실행 (더 안정적인 방식으로 변경)
log "ElectronCash RPC 서버 시작 중..."

# 기존 데몬 프로세스 정리 (강제 종료)
log "기존 프로세스 정리 중..."
killall -9 python3 2>/dev/null || true
pkill -9 -f "electron-cash" 2>/dev/null || true
sleep 5

# 남아있는 프로세스 확인 및 추가 정리
REMAINING=$(pgrep -f "electron-cash" | wc -l)
if [ "$REMAINING" -gt 0 ]; then
  log "⚠️ $REMAINING 개의 프로세스가 남아있습니다. 추가 정리 중..."
  pgrep -f "electron-cash" | xargs kill -9 2>/dev/null || true
  sleep 3
fi

# 설정 파일 생성 - RPC 서버 직접 실행을 위한 설정
cat > /root/.electron-cash/config << EOF
{
  "rpcuser": "${RPC_USER}",
  "rpcpassword": "${RPC_PASSWORD}",
  "rpchost": "0.0.0.0",
  "rpcport": 7777,
  "server": "0.0.0.0:7777",
  "rpcallowip": "0.0.0.0/0"
}
EOF

chmod 600 /root/.electron-cash/config

# PID 파일 경로
PID_FILE="/tmp/electron-cash-daemon.pid"

# 지갑 로드를 먼저 시도
log "지갑 로드 시도 중..."
python3 /app/electron-cash -w "$WALLET_PATH" daemon start 2>/root/.electron-cash/daemon_start.log &
DAEMON_PID=$!
echo $DAEMON_PID > $PID_FILE
log "데몬 PID: $DAEMON_PID"

# 데몬이 시작될 때까지 대기 (더 긴 시간)
log "데몬 시작 대기 중 (PID: $DAEMON_PID)..."
sleep 15

# 데몬 상태 확인
for i in {1..15}; do
  if python3 /app/electron-cash daemon status >/dev/null 2>&1; then
    log "✅ 데몬이 성공적으로 시작되었습니다 (시도 ${i}/15)"
    break
  else
    log "데몬 시작 대기 중... (${i}/15)"
    if [ $i -eq 15 ]; then
      log "❌ 데몬 시작 실패. 로그를 확인합니다:"
      cat /root/.electron-cash/daemon_start.log 2>/dev/null || log "로그 파일이 없습니다."
      log "직접 RPC 서버 모드로 전환합니다..."
      
      # 대체 방법: 직접 RPC 서버 실행
      # 기존 프로세스 완전 정리
      if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat $PID_FILE)
        kill -9 $OLD_PID 2>/dev/null || true
      fi
      killall -9 python3 2>/dev/null || true
      pkill -9 -f "electron-cash" 2>/dev/null || true
      sleep 5
      
      # 직접 실행 방식
      python3 /app/electron-cash -w "$WALLET_PATH" daemon &
      DAEMON_PID=$!
      echo $DAEMON_PID > $PID_FILE
      log "새 데몬 PID: $DAEMON_PID"
      sleep 10
    fi
    sleep 3
  fi
done

if python3 /app/electron-cash daemon status >/dev/null 2>&1; then
  log "✅ ElectronCash 데몬 최종 확인 성공"
else
  log "⚠️ 데몬 상태를 확인할 수 없지만 계속 진행합니다"
fi

# JSON-RPC 서버가 정상적으로 실행 중인지 확인
log "JSON-RPC 서버 연결 테스트 중..."
for i in {1..5}; do
  if curl -s -u "${RPC_USER}:${RPC_PASSWORD}" -X POST -H "Content-Type: application/json" \
       -d '{"id":"curltest","method":"getinfo","params":[]}' http://localhost:7777 > /dev/null 2>&1; then
    log "✅ JSON-RPC 서버 연결 성공!"
    break
  else
    log "JSON-RPC 서버 연결 시도 ${i}/5..."
    sleep 3
  fi
done

# 간단한 테스트
log "기본 테스트 수행 중..."
python3 /app/electron-cash daemon getinfo 2>/dev/null && log "✅ getinfo 명령 성공" || log "⚠️ getinfo 명령 실패"

# 중요: 지갑 로드
log "지갑 로드 중..."
python3 /app/electron-cash daemon load_wallet -w "$WALLET_PATH" 2>/dev/null && log "✅ 지갑 로드 성공" || log "⚠️ 지갑 로드 실패"

# 지갑 로드 확인
log "지갑 상태 확인 중..."
python3 /app/electron-cash daemon getbalance 2>/dev/null && log "✅ 지갑 접근 성공" || log "⚠️ 지갑 접근 실패"

# 프로세스를 계속 실행하여 컨테이너 유지
log "🚀 ElectronCash 서버가 실행 중입니다. 모니터링을 시작합니다."

# 재시작 횟수 및 백오프 관리
RESTART_COUNT=0
MAX_RESTART_BEFORE_LONG_WAIT=3
FAILED_CHECKS=0

# 간소화된 주기적 상태 확인
while true; do
  sleep 120  # 2분마다 확인
  
  # 간단한 ping 테스트
  if python3 /app/electron-cash daemon status >/dev/null 2>&1; then
    log "✅ ElectronCash 데몬 정상 ($(date '+%H:%M:%S'))"
    FAILED_CHECKS=0
    RESTART_COUNT=0
  else
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    log "⚠️ ElectronCash 데몬 문제 감지 (연속 실패: ${FAILED_CHECKS}/3)"
    
    # 3번 연속 실패 시에만 재시작 (false positive 방지)
    if [ $FAILED_CHECKS -ge 3 ]; then
      RESTART_COUNT=$((RESTART_COUNT + 1))
      log "🔄 ElectronCash 데몬 재시작 시도 중... (재시작 횟수: ${RESTART_COUNT})"
      
      # 기존 프로세스 완전 정리
      if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat $PID_FILE)
        log "기존 PID $OLD_PID 종료 중..."
        kill -15 $OLD_PID 2>/dev/null || true
        sleep 3
        kill -9 $OLD_PID 2>/dev/null || true
      fi
      
      # 모든 electron-cash 프로세스 강제 종료
      killall -9 python3 2>/dev/null || true
      pkill -9 -f "electron-cash" 2>/dev/null || true
      sleep 5
      
      # 남은 프로세스 확인
      REMAINING=$(pgrep -f "electron-cash" | wc -l)
      if [ "$REMAINING" -gt 0 ]; then
        log "⚠️ 여전히 $REMAINING 개의 프로세스가 실행 중입니다."
        pgrep -f "electron-cash" | xargs kill -9 2>/dev/null || true
        sleep 3
      fi
      
      # 백오프 전략: 잦은 재시작 방지
      if [ $RESTART_COUNT -ge $MAX_RESTART_BEFORE_LONG_WAIT ]; then
        WAIT_TIME=$((RESTART_COUNT * 60))
        log "⏰ 잦은 재시작 감지. ${WAIT_TIME}초 대기 후 재시작..."
        sleep $WAIT_TIME
      fi
      
      # 새 프로세스 시작
      python3 /app/electron-cash -w "$WALLET_PATH" daemon &
      DAEMON_PID=$!
      echo $DAEMON_PID > $PID_FILE
      log "새 데몬 시작됨 (PID: $DAEMON_PID)"
      sleep 15
      
      # 재시작 검증
      if python3 /app/electron-cash daemon status >/dev/null 2>&1; then
        log "✅ 재시작 성공"
        FAILED_CHECKS=0
      else
        log "❌ 재시작 실패 - 다음 주기에 재시도"
      fi
    fi
  fi
done