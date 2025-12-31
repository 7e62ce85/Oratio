#!/bin/bash
# ==============================================
# BCH 출금 스크립트 - 관리자 전용
# ElectronCash 지갑에서 지정 주소로 BCH 전송
# ==============================================

# 색상
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}          BCH 출금 - 관리자 전용${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""

# 사용자 확인
if [ "$USER" != "user" ] && [ "$USER" != "root" ]; then
    echo -e "${RED}❌ 권한 없는 사용자: $USER${NC}"
    exit 1
fi

# 컨테이너 확인
if ! docker ps | grep -q bitcoincash-service; then
    echo -e "${RED}❌ BCH 서비스가 실행중이지 않습니다!${NC}"
    exit 1
fi

# 현재 잔액 조회
echo -e "${GREEN}💰 현재 지갑 잔액:${NC}"
docker exec bitcoincash-service python3 -c "
import logging
logging.disable(logging.CRITICAL)
from services.electron_cash import ElectronCashClient
client = ElectronCashClient()
info = client.call_method('getbalance')
if info:
    confirmed = float(info.get('confirmed', '0'))
    unconfirmed = float(info.get('unconfirmed', '0'))
    print(f'   확정:     {confirmed:.8f} BCH')
    print(f'   미확정:   {unconfirmed:.8f} BCH')
    print(f'   출금가능: {confirmed:.8f} BCH (확정된 금액만 전송 가능)')
" 2>/dev/null
echo ""

# 기본 출금 지갑
DEFAULT_PAYOUT=$(grep PAYOUT_WALLET /home/user/Oratio/oratio/.env | cut -d'=' -f2)

# 목적지 주소 입력
echo -e "${YELLOW}📤 받는 주소 입력${NC}"
echo -e "   (Enter키를 누르면 기본 PAYOUT_WALLET 사용)"
echo -e "   기본값: ${DEFAULT_PAYOUT}"
read -p "   주소: " DEST_ADDRESS

if [ -z "$DEST_ADDRESS" ]; then
    DEST_ADDRESS="$DEFAULT_PAYOUT"
fi

# 주소 형식 검증
if [[ ! "$DEST_ADDRESS" =~ ^bitcoincash: ]] && [[ ! "$DEST_ADDRESS" =~ ^q ]]; then
    echo -e "${RED}❌ 올바르지 않은 BCH 주소 형식${NC}"
    exit 1
fi

echo ""

# 금액 입력
echo -e "${YELLOW}💵 전송할 금액 입력 (BCH 단위)${NC}"
echo -e "   예시: 0.01"
read -p "   금액: " AMOUNT

# 금액 검증
if ! [[ "$AMOUNT" =~ ^[0-9]+\.?[0-9]*$ ]]; then
    echo -e "${RED}❌ 올바르지 않은 금액 형식${NC}"
    exit 1
fi

if (( $(echo "$AMOUNT <= 0" | bc -l) )); then
    echo -e "${RED}❌ 금액은 0보다 커야 합니다${NC}"
    exit 1
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}⚠️  거래 요약${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "   받는 주소: ${DEST_ADDRESS}"
echo -e "   금액:      ${AMOUNT} BCH"
echo -e "   수수료:    ~0.00001 BCH (자동)"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""

# 이중 확인
echo -e "${RED}⚠️  경고: 이 작업은 되돌릴 수 없습니다!${NC}"
read -p "   확인하려면 '전송'을 입력하세요: " CONFIRM

if [ "$CONFIRM" != "전송" ]; then
    echo -e "${YELLOW}❌ 거래가 취소되었습니다${NC}"
    exit 0
fi

echo ""
echo -e "${CYAN}🔄 거래 처리중...${NC}"

# 거래 실행
RESULT=$(docker exec bitcoincash-service python3 -c "
import logging
logging.disable(logging.CRITICAL)
from services.electron_cash import ElectronCashClient
import json

client = ElectronCashClient()
dest = '$DEST_ADDRESS'
amount = float('$AMOUNT')

# bitcoincash: 접두사 추가
if not dest.startswith('bitcoincash:'):
    dest = 'bitcoincash:' + dest

try:
    # 트랜잭션 생성 및 브로드캐스트
    result = client.call_method('payto', [dest, amount])
    if result:
        signed = client.call_method('signtransaction', [result])
        if signed:
            txid = client.call_method('broadcast', [signed])
            if txid:
                print(json.dumps({'success': True, 'txid': txid}))
            else:
                print(json.dumps({'success': False, 'error': '브로드캐스트 실패'}))
        else:
            print(json.dumps({'success': False, 'error': '서명 실패'}))
    else:
        print(json.dumps({'success': False, 'error': '트랜잭션 생성 실패'}))
except Exception as e:
    print(json.dumps({'success': False, 'error': str(e)}))
" 2>/dev/null)

# 결과 파싱
if echo "$RESULT" | grep -q '"success": true'; then
    TXID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['txid'])")
    echo ""
    echo -e "${GREEN}✅ 전송 성공!${NC}"
    echo -e "   TXID: ${TXID}"
    echo ""
    echo -e "   탐색기에서 보기:"
    echo -e "   https://blockchair.com/bitcoin-cash/transaction/${TXID}"
    
    # 트랜잭션 로그 기록
    LOG_FILE="/home/user/Oratio/oratio/logs/withdrawals.log"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$(date '+%Y-%m-%d %H:%M:%S') | TXID: ${TXID} | Amount: ${AMOUNT} BCH | To: ${DEST_ADDRESS}" >> "$LOG_FILE"
    echo ""
    echo -e "${CYAN}📝 거래 기록됨: ${LOG_FILE}${NC}"
else
    ERROR=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', '알 수 없는 오류'))" 2>/dev/null || echo "$RESULT")
    echo ""
    echo -e "${RED}❌ 전송 실패!${NC}"
    echo -e "   오류: ${ERROR}"
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
