#!/bin/bash

# 프로덕션 배포 스크립트 - defadb.com
# 로컬호스트에서 실제 도메인으로 전환하는 스크립트

echo "=== defadb.com 프로덕션 배포 시작 ==="

# 현재 디렉토리 확인
if [ ! -f "docker-compose.yml" ]; then
    echo "오류: docker-compose.yml 파일이 없습니다. oratio 디렉토리에서 실행하세요."
    exit 1
fi

# 환경변수 파일 설정
if [ ! -f ".env" ]; then
    echo "환경변수 파일을 생성합니다..."
    cp .env.production .env
    echo "주의: .env 파일의 LEMMY_API_KEY를 실제 값으로 설정하세요!"
fi

# 기존 컨테이너 중지
echo "기존 컨테이너를 중지합니다..."
docker-compose down

# nginx 설정을 프로덕션용으로 변경
echo "nginx 설정을 프로덕션용으로 변경합니다..."
if [ -f "nginx_production.conf" ]; then
    cp nginx_internal.conf nginx_internal.conf.backup
    cp nginx_production.conf nginx_internal.conf
    echo "nginx 설정이 프로덕션용으로 변경되었습니다."
else
    echo "경고: nginx_production.conf 파일이 없습니다."
fi

# SSL 인증서 확인
if [ ! -d "/etc/letsencrypt/live/defadb.com" ]; then
    echo "경고: SSL 인증서가 없습니다."
    echo "먼저 './setup_ssl.sh' 스크립트를 실행하여 SSL 인증서를 발급받으세요."
    echo "또는 HTTP만으로 테스트하려면 nginx 설정에서 SSL 부분을 주석 처리하세요."
fi

# Lemmy UI 이미지 재빌드
echo "Lemmy UI 이미지를 재빌드합니다..."
docker-compose build lemmy-ui

# 컨테이너 시작
echo "프로덕션 컨테이너를 시작합니다..."
docker-compose up -d

# 상태 확인
echo "컨테이너 상태 확인:"
docker-compose ps

echo ""
echo "=== 배포 완료 ==="
echo "웹사이트: https://defadb.com"
echo "결제 서비스: https://payments.defadb.com"
echo ""
echo "주의사항:"
echo "1. DNS 설정이 올바른지 확인하세요."
echo "2. 포트 80, 443이 열려있는지 확인하세요."
echo "3. .env 파일의 LEMMY_API_KEY를 실제 값으로 설정하세요."
echo "4. SSL 인증서가 없다면 setup_ssl.sh를 먼저 실행하세요."
