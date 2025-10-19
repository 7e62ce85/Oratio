# Docker 컨테이너 재시작 문제 해결 가이드

## 📋 문제 개요
- **발생일**: 2025-07-13
- **영향 범위**: oratio-pictrs-1, oratio-proxy-1 컨테이너
- **심각도**: 중간 (서비스 불안정)

## 🔍 증상

### 1. pictrs 서비스 재시작 문제
```
Permission denied (os error 13): /mnt/sled-repo
```
- pictrs 컨테이너가 지속적으로 재시작
- 이미지 업로드 기능 마비

### 2. nginx proxy 서비스 재시작 문제
```
nginx: [emerg] cannot load certificate "/etc/letsencrypt/live/oratio.space/fullchain.pem"
```
- SSL 인증서 파일을 찾을 수 없음
- HTTPS 접속 불가

## 🛠️ 해결 과정

### 1단계: pictrs 권한 문제 분석
- **원인**: pictrs가 user `991:991`로 실행되지만 볼륨 디렉토리가 root 소유
- **영향**: 컨테이너가 데이터 디렉토리에 쓰기 권한이 없어 재시작 반복

### 2단계: pictrs 권한 문제 해결
```bash
# pictrs 볼륨 디렉토리 소유권 변경
sudo chown -R 991:991 /opt/khankorean/oratio/volumes/pictrs

# 권한 확인
ls -la volumes/pictrs/
# drwxr-xr-x 991 991 pictrs
```

### 3단계: SSL 인증서 문제 분석
- **원인**: Let's Encrypt SSL 인증서 파일이 존재하지 않음
- **임시 해결**: 자체 서명 인증서 생성
- **최종 해결**: Let's Encrypt 정식 인증서 발급

### 4단계: 자체 서명 SSL 인증서 생성 (임시)
```bash
# SSL 인증서 디렉토리 생성
mkdir -p ssl-certs

# oratio.space용 자체 서명 인증서
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl-certs/privkey.pem \
  -out ssl-certs/fullchain.pem \
  -subj "/C=KR/ST=Seoul/L=Seoul/O=oratio/CN=oratio.space"

# payments.oratio.space용 자체 서명 인증서
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl-certs/payments-privkey.pem \
  -out ssl-certs/payments-fullchain.pem \
  -subj "/C=KR/ST=Seoul/L=Seoul/O=oratio/CN=payments.oratio.space"
```

### 5단계: nginx 설정 수정
#### docker-compose.yml 볼륨 마운트 변경:
```yaml
volumes:
  - ./nginx_production.conf:/etc/nginx/nginx.conf:ro,Z
  - ./proxy_params:/etc/nginx/proxy_params:ro,Z
  - ./nginx/js:/etc/nginx/js:ro,Z
  - ./ssl-certs:/etc/ssl/certs:ro,Z  # 자체 서명 인증서
```

#### nginx_production.conf SSL 경로 수정:
```nginx
# 메인 도메인
ssl_certificate /etc/ssl/certs/fullchain.pem;
ssl_certificate_key /etc/ssl/certs/privkey.pem;

# 결제 도메인  
ssl_certificate /etc/ssl/certs/payments-fullchain.pem;
ssl_certificate_key /etc/ssl/certs/payments-privkey.pem;
```

### 6단계: Let's Encrypt 정식 인증서로 전환 (최종 해결)
```bash
# Let's Encrypt 인증서 발급
sudo certbot certonly --standalone --agree-tos \
  --email admin@oratio.space --no-eff-email \
  -d oratio.space -d www.oratio.space

sudo certbot certonly --standalone --agree-tos \
  --email admin@oratio.space --no-eff-email \
  -d payments.oratio.space

# nginx 설정을 Let's Encrypt 경로로 변경
# docker-compose.yml 볼륨 마운트:
volumes:
  - /etc/letsencrypt:/etc/letsencrypt:ro,Z

# nginx_production.conf 경로:
ssl_certificate /etc/letsencrypt/live/oratio.space/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/oratio.space/privkey.pem;
```

### 7단계: 불필요한 파일 정리
삭제된 파일들:
- `nginx_dev.conf` - 개발용 설정
- `nginx_ssl_setup.conf` - SSL 설정용 임시 파일
- `certbot-webroot/` - Let's Encrypt용 임시 디렉토리
- `setup_ssl.sh` - 기본 SSL 스크립트 (프로덕션 버전과 중복)

## ✅ 최종 결과

### 서비스 상태 (정상):
```bash
docker-compose ps

NAME                  STATUS
bitcoincash-service   Up 5 minutes
electron-cash         Up 5 minutes  
oratio-lemmy-1        Up 5 minutes
oratio-lemmy-ui-1     Up 5 minutes (healthy)
oratio-pictrs-1       Up 5 minutes           # ✅ 해결됨
oratio-postfix-1      Up 5 minutes
oratio-postgres-1     Up 5 minutes (healthy)
oratio-proxy-1        Up 5 minutes           # ✅ 해결됨
```

### SSL 설정 완료:
- HTTPS 443 포트 활성화
- HTTP → HTTPS 자동 리다이렉션
- Let's Encrypt 정식 인증서 (유효기간: 2025-10-11)
- 브라우저에서 안전한 HTTPS 연결 확인

## 🔍 근본 원인 분석

### 1. Docker 권한 관리 문제
- **문제**: 컨테이너 내 사용자 ID와 호스트 볼륨 소유권 불일치
- **교훈**: Docker 볼륨 마운트 시 사용자 권한 사전 확인 필요

### 2. SSL 인증서 경로 문제
- **문제**: nginx 설정의 인증서 경로와 실제 파일 위치 불일치
- **교훈**: 프로덕션 배포 전 SSL 인증서 발급 프로세스 확립 필요

### 3. 파일 정리 미흡
- **문제**: 개발/테스트용 파일들이 프로덕션 환경에 잔존
- **교훈**: 배포 시 불필요한 파일 정리 자동화 필요

## 🔧 예방 조치

### 1. 권한 확인 스크립트
```bash
#!/bin/bash
# check_permissions.sh - 컨테이너 권한 사전 확인

echo "=== Docker 볼륨 권한 확인 ==="
echo "pictrs 볼륨 권한:"
ls -la volumes/pictrs/ | head -5

echo "postgres 볼륨 권한:"
ls -la volumes/postgres/ | head -5

echo "=== 권한 문제 해결 ==="
sudo chown -R 991:991 volumes/pictrs
sudo chown -R 999:999 volumes/postgres
echo "권한 수정 완료"
```

### 2. SSL 인증서 확인 스크립트
```bash
#!/bin/bash
# check_ssl.sh - SSL 인증서 상태 확인

echo "=== SSL 인증서 확인 ==="
if [ -f "/etc/letsencrypt/live/oratio.space/fullchain.pem" ]; then
    echo "✅ oratio.space 인증서 존재"
    openssl x509 -in /etc/letsencrypt/live/oratio.space/fullchain.pem -noout -dates
else
    echo "❌ oratio.space 인증서 없음"
    echo "sudo certbot certonly --standalone -d oratio.space 실행 필요"
fi

if [ -f "/etc/letsencrypt/live/payments.oratio.space/fullchain.pem" ]; then
    echo "✅ payments.oratio.space 인증서 존재"
    openssl x509 -in /etc/letsencrypt/live/payments.oratio.space/fullchain.pem -noout -dates
else
    echo "❌ payments.oratio.space 인증서 없음"
    echo "sudo certbot certonly --standalone -d payments.oratio.space 실행 필요"
fi
```

### 3. 배포 전 검증 체크리스트
```bash
#!/bin/bash
# pre_deploy_check.sh - 배포 전 검증

echo "=== 배포 전 검증 체크리스트 ==="

# 1. 권한 확인
echo "1. Docker 볼륨 권한 확인..."
./check_permissions.sh

# 2. SSL 인증서 확인
echo "2. SSL 인증서 확인..."
./check_ssl.sh

# 3. 환경변수 확인
echo "3. 환경변수 확인..."
if [ -f ".env" ]; then
    echo "✅ .env 파일 존재"
    if grep -q "LEMMY_API_KEY=" .env; then
        echo "✅ LEMMY_API_KEY 설정됨"
    else
        echo "❌ LEMMY_API_KEY 미설정"
    fi
else
    echo "❌ .env 파일 없음"
fi

# 4. nginx 설정 검증
echo "4. nginx 설정 검증..."
docker run --rm -v "$(pwd)/nginx_production.conf:/etc/nginx/nginx.conf:ro" nginx nginx -t

echo "=== 검증 완료 ==="
```

## 🚨 문제 재발 시 대응 매뉴얼

### pictrs 재시작 문제
```bash
# 1. 로그 확인
docker-compose logs pictrs

# 2. 권한 재확인
ls -la volumes/pictrs/
sudo chown -R 991:991 volumes/pictrs

# 3. 컨테이너 재시작
docker-compose restart pictrs
```

### nginx SSL 문제
```bash
# 1. 인증서 확인
sudo certbot certificates

# 2. nginx 설정 테스트
docker-compose exec proxy nginx -t

# 3. 인증서 갱신 (필요시)
sudo certbot renew

# 4. nginx 재시작
docker-compose restart proxy
```

## 📊 성능 모니터링

### 컨테이너 리소스 사용량
```bash
# CPU, 메모리 사용량 확인
docker stats --no-stream

# 디스크 사용량 확인
du -sh volumes/*
df -h
```

### 서비스 응답 시간 측정
```bash
# 메인 사이트 응답 시간
curl -w "@curl-format.txt" -o /dev/null -s https://oratio.space

# 결제 서비스 응답 시간
curl -w "@curl-format.txt" -o /dev/null -s https://payments.oratio.space/health
```

## 📝 핵심 학습 포인트

1. **Docker 권한 관리**: 컨테이너 내 사용자와 호스트 볼륨 권한 일치 중요
2. **SSL 인증서 경로**: nginx 설정의 인증서 경로와 실제 파일 위치 일치 필요
3. **자체 서명 인증서**: 개발/테스트 환경에서 SSL 활성화 방법
4. **파일 정리**: 배포 환경에서 불필요한 개발용 파일 제거의 중요성
5. **사전 검증**: 배포 전 권한, SSL, 환경변수 확인 자동화 필요

---

**문제 해결일**: 2025-07-13  
**소요 시간**: 약 30분  
**주요 도구**: Docker Compose, OpenSSL, nginx, Let's Encrypt  
**최종 상태**: ✅ 완전 해결됨
