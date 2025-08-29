#!/bin/bash

# ElectronCash 헬스 체크 및 자동 재시작 스크립트
# 작성일: 2025년 8월 3일
# 목적: "Connection to electron-cash timed out" 오류 자동 해결

LOG_FILE="/opt/khankorean/oratio/logs/health_check.log"
RESTART_LOG="/opt/khankorean/oratio/logs/restart_history.log"

# 로그 디렉토리 생성
mkdir -p /opt/khankorean/oratio/logs

# 로그 함수
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

restart_log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$RESTART_LOG"
}

# ElectronCash 연결 테스트 함수
test_electron_cash_connection() {
    log_message "ElectronCash 연결 테스트 시작..."
    
    # Docker 컨테이너 내에서 연결 테스트
    timeout 5 docker exec bitcoincash-service curl -s -f \
        -u "bchrpc:Uv6ZnoQKs8nPgzJ" \
        -X POST \
        -H "Content-Type: application/json" \
        -d '{"method": "getbalance", "params": [], "jsonrpc": "2.0", "id": 1}' \
        http://electron-cash:7777/ > /dev/null 2>&1
    
    return $?
}

# BCH 서비스 워커 타임아웃 체크
check_worker_timeout() {
    # 최근 5분간 워커 타임아웃 오류 확인
    timeout_count=$(docker compose logs --since="5m" bitcoincash-service 2>/dev/null | grep -c "WORKER TIMEOUT" 2>/dev/null || echo "0")
    
    # 숫자 검증
    if ! [[ "$timeout_count" =~ ^[0-9]+$ ]]; then
        timeout_count=0
    fi
    
    if [ "$timeout_count" -gt 0 ]; then
        log_message "워커 타임아웃 감지: $timeout_count 건"
        return 1
    fi
    
    return 0
}

# 컨테이너 재시작 함수
restart_containers() {
    log_message "===== 컨테이너 재시작 시작 ====="
    restart_log "자동 재시작 실행 - ElectronCash 연결 실패"
    
    # ElectronCash 재시작
    log_message "ElectronCash 컨테이너 재시작 중..."
    cd /opt/khankorean/oratio
    docker compose restart electron-cash
    
    if [ $? -eq 0 ]; then
        log_message "ElectronCash 재시작 성공"
        sleep 15  # ElectronCash 초기화 대기
        
        # BCH 서비스 재시작
        log_message "BCH 서비스 컨테이너 재시작 중..."
        docker compose restart bitcoincash-service
        
        if [ $? -eq 0 ]; then
            log_message "BCH 서비스 재시작 성공"
            sleep 10  # 서비스 초기화 대기
            
            # 재시작 후 연결 테스트
            if test_electron_cash_connection; then
                log_message "✅ 재시작 후 연결 테스트 성공"
                restart_log "재시작 성공 - 연결 복구됨"
                return 0
            else
                log_message "❌ 재시작 후에도 연결 실패"
                restart_log "재시작 실패 - 연결 여전히 불가"
                return 1
            fi
        else
            log_message "❌ BCH 서비스 재시작 실패"
            restart_log "BCH 서비스 재시작 실패"
            return 1
        fi
    else
        log_message "❌ ElectronCash 재시작 실패"
        restart_log "ElectronCash 재시작 실패"
        return 1
    fi
}

# 메인 헬스 체크 로직
main() {
    log_message "===== 헬스 체크 시작 ====="
    
    # 1. ElectronCash 연결 테스트
    if test_electron_cash_connection; then
        log_message "✅ ElectronCash 연결 정상"
        
        # 2. 워커 타임아웃 체크
        if check_worker_timeout; then
            log_message "✅ BCH 서비스 정상"
            log_message "===== 모든 서비스 정상 ====="
            exit 0
        else
            log_message "⚠️  워커 타임아웃 감지 - 재시작 필요"
        fi
    else
        log_message "❌ ElectronCash 연결 실패 - 재시작 필요"
    fi
    
    # 3. 재시작 실행
    if restart_containers; then
        log_message "===== 자동 복구 완료 ====="
        exit 0
    else
        log_message "===== 자동 복구 실패 - 수동 개입 필요 ====="
        exit 1
    fi
}

# 스크립트 실행
main "$@"
