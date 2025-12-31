#!/bin/bash
# SSL 인증서 자동 갱신 스크립트
# Let's Encrypt 인증서는 90일 유효, 60일에 갱신 권장

set -e
cd /home/user/Oratio/oratio

LOG_FILE="/home/user/Oratio/oratio/logs/ssl_renew.log"
mkdir -p /home/user/Oratio/oratio/logs

echo "$(date): SSL 인증서 갱신 시작" >> "$LOG_FILE"

# nginx 중지 (standalone 모드 사용을 위해)
docker-compose stop proxy >> "$LOG_FILE" 2>&1

# certbot 갱신 실행
docker run --rm \
  -p 80:80 \
  -v /home/user/Oratio/oratio/data/certbot/conf:/etc/letsencrypt \
  -v /home/user/Oratio/oratio/data/certbot/www:/var/www/certbot \
  certbot/certbot renew --standalone >> "$LOG_FILE" 2>&1

RESULT=$?

# nginx 재시작
docker-compose start proxy >> "$LOG_FILE" 2>&1

if [ $RESULT -eq 0 ]; then
    echo "$(date): SSL 인증서 갱신 완료" >> "$LOG_FILE"
else
    echo "$(date): SSL 인증서 갱신 실패 (exit code: $RESULT)" >> "$LOG_FILE"
fi

echo "---" >> "$LOG_FILE"
