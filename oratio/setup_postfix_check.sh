#!/bin/bash
# Oratio Postfix SMTP 서버 설정 스크립트

echo "======================================"
echo "Oratio Postfix 자체 SMTP 서버 설정"
echo "======================================"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 서버 정보
SERVER_IP="70.34.244.93"
DOMAIN="oratio.space"
MAIL_HOSTNAME="mail.oratio.space"

echo ""
echo "📋 설정 정보:"
echo "  - 서버 IP: $SERVER_IP"
echo "  - 도메인: $DOMAIN"
echo "  - 메일 호스트: $MAIL_HOSTNAME"
echo ""

# Step 1: DNS 레코드 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1단계: DNS 레코드 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "🔍 MX 레코드 확인..."
dig MX $DOMAIN +short
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} MX 레코드 조회 성공"
else
    echo -e "${RED}✗${NC} MX 레코드 없음 - DNS 설정 필요!"
fi

echo ""
echo "🔍 A 레코드 확인 (mail.$DOMAIN)..."
dig A $MAIL_HOSTNAME +short
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} A 레코드 조회 성공"
else
    echo -e "${RED}✗${NC} A 레코드 없음 - DNS 설정 필요!"
fi

echo ""
echo "🔍 SPF 레코드 확인..."
dig TXT $DOMAIN +short | grep spf
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} SPF 레코드 존재"
else
    echo -e "${YELLOW}⚠${NC} SPF 레코드 없음 - 추가 권장"
fi

echo ""
echo "🔍 PTR 레코드 확인 (역방향 DNS)..."
dig -x $SERVER_IP +short
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} PTR 레코드 존재"
else
    echo -e "${YELLOW}⚠${NC} PTR 레코드 없음 - ISP에 요청 필요!"
fi

# Step 2: Postfix 컨테이너 확인
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2단계: Postfix 컨테이너 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if docker-compose ps | grep -q postfix; then
    echo -e "${GREEN}✓${NC} Postfix 컨테이너 실행 중"
    docker-compose ps | grep postfix
else
    echo -e "${RED}✗${NC} Postfix 컨테이너 실행 안됨"
fi

# Step 3: DKIM 키 생성 (아직 없다면)
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3단계: DKIM 키 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
read -p "DKIM 키를 생성하시겠습니까? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "DKIM 키 생성 중..."
    
    # Postfix 컨테이너에서 DKIM 키 생성
    docker-compose exec postfix opendkim-genkey -t -s mail -d $DOMAIN || {
        echo -e "${YELLOW}⚠${NC} OpenDKIM이 설치되지 않은 이미지일 수 있습니다."
        echo "대신 로컬에서 생성하거나 다른 도구 사용 필요"
    }
    
    echo ""
    echo "생성된 공개키를 DNS TXT 레코드로 추가하세요:"
    echo "호스트: mail._domainkey.$DOMAIN"
    echo ""
else
    echo "DKIM 키 생성 건너뜀"
fi

# Step 4: 포트 확인
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4단계: SMTP 포트 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "🔍 포트 25 (SMTP) 확인..."
timeout 3 nc -zv smtp.gmail.com 25 2>&1 | grep -q succeeded
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} 포트 25 열림 - 직접 발송 가능"
else
    echo -e "${YELLOW}⚠${NC} 포트 25 차단됨 - ISP에 개방 요청 필요"
    echo "   또는 포트 587로 relay 설정 필요"
fi

echo ""
echo "🔍 포트 587 (Submission) 확인..."
timeout 3 nc -zv smtp.gmail.com 587 2>&1 | grep -q succeeded
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} 포트 587 열림"
else
    echo -e "${RED}✗${NC} 포트 587 차단됨"
fi

# Step 5: 요약 및 다음 단계
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 설정 요약 및 다음 단계"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "✅ 완료해야 할 작업:"
echo ""
echo "1. DNS 레코드 추가 (setup_postfix_dns_guide.md 참고)"
echo "   - MX 레코드"
echo "   - A 레코드 (mail.$DOMAIN)"
echo "   - SPF 레코드"
echo "   - DKIM 레코드"
echo "   - DMARC 레코드"
echo ""
echo "2. ISP에 요청:"
echo "   - 포트 25 개방 (차단되어 있다면)"
echo "   - PTR 레코드 설정 ($SERVER_IP -> $MAIL_HOSTNAME)"
echo ""
echo "3. Postfix 설정 업데이트:"
echo "   - docker-compose.yml 수정"
echo "   - 컨테이너 재시작"
echo ""
echo "4. 테스트:"
echo "   - 이메일 발송 테스트"
echo "   - 스팸 점수 확인 (mail-tester.com)"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "자세한 가이드: setup_postfix_dns_guide.md"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
