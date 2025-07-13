#!/bin/bash

# SSL 인증서 설정 스크립트 (실제 배포용)
set -e

echo "=== SSL 인증서 자동 설정 시작 ==="

# 도메인 설정
MAIN_DOMAIN="defadb.com"
PAYMENT_DOMAIN="payments.defadb.com"
EMAIL="admin@defadb.com"  # Let's Encrypt 알림용 이메일

# Certbot 설치 확인
if ! command -v certbot &> /dev/null; then
    echo "Certbot 설치 중..."
    sudo apt update
    sudo apt install -y certbot python3-certbot-nginx
fi

# nginx 서비스 중지 (인증서 생성을 위해)
echo "nginx 서비스 임시 중지..."
docker-compose stop proxy

# Let's Encrypt 인증서 생성
echo "Let's Encrypt 인증서 생성 중..."

# 메인 도메인 인증서
if [ ! -f "/etc/letsencrypt/live/$MAIN_DOMAIN/fullchain.pem" ]; then
    echo "메인 도메인 ($MAIN_DOMAIN) 인증서 생성..."
    sudo certbot certonly --standalone \
        --agree-tos \
        --email $EMAIL \
        --no-eff-email \
        -d $MAIN_DOMAIN \
        -d www.$MAIN_DOMAIN
else
    echo "메인 도메인 인증서가 이미 존재함"
fi

# 결제 도메인 인증서
if [ ! -f "/etc/letsencrypt/live/$PAYMENT_DOMAIN/fullchain.pem" ]; then
    echo "결제 도메인 ($PAYMENT_DOMAIN) 인증서 생성..."
    sudo certbot certonly --standalone \
        --agree-tos \
        --email $EMAIL \
        --no-eff-email \
        -d $PAYMENT_DOMAIN
else
    echo "결제 도메인 인증서가 이미 존재함"
fi

# 인증서 자동 갱신 설정
echo "인증서 자동 갱신 설정..."
sudo crontab -l | grep -q "certbot renew" || (sudo crontab -l; echo "0 12 * * * /usr/bin/certbot renew --quiet") | sudo crontab -

# nginx 설정을 프로덕션용으로 변경
echo "nginx 설정을 SSL 활성화 버전으로 변경..."
cp nginx_internal.conf nginx_internal.conf.backup.$(date +%Y%m%d_%H%M%S)

# pictrs 권한 수정
echo "pictrs 볼륨 권한 수정..."
sudo chown -R 991:991 volumes/pictrs/

echo "=== SSL 설정 완료 ==="
echo "이제 docker-compose를 다시 시작하세요:"
echo "docker-compose up -d"
echo ""
echo "인증서 위치:"
echo "- 메인 도메인: /etc/letsencrypt/live/$MAIN_DOMAIN/"
echo "- 결제 도메인: /etc/letsencrypt/live/$PAYMENT_DOMAIN/"
