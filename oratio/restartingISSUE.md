# 기술적 문제 해결 요약 (Docker Compose 재시작 이슈)

## 📋 문제 상황
- Docker Compose에서 `oratio-pictrs-1`과 `oratio-proxy-1` 서비스가 지속적으로 재시작됨
- 실제 배포 환경에서 SSL 보안이 필요한 상황

## 🔍 원인 분석

### 1. pictrs 서비스 재시작 원인
```
Permission denied (os error 13): /mnt/sled-repo
```
- **문제**: pictrs가 user `991:991`로 실행되지만 볼륨 디렉토리가 root 소유
- **해결**: `sudo chown -R 991:991 volumes/pictrs` 권한 수정

### 2. nginx proxy 서비스 재시작 원인
```
nginx: [emerg] cannot load certificate "/etc/letsencrypt/live/defadb.com/fullchain.pem"
```
- **문제**: Let's Encrypt SSL 인증서 파일이 존재하지 않음
- **해결**: 자체 서명 SSL 인증서 생성 및 설정

## 🛠️ 해결 과정

### 1단계: pictrs 권한 문제 해결
```bash
# pictrs 볼륨 디렉토리 소유권 변경
sudo chown -R 991:991 /home/joshham/khankorean/oratio/volumes/pictrs
```

### 2단계: SSL 인증서 생성
```bash
# defadb.com용 자체 서명 인증서
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl-certs/privkey.pem \
  -out ssl-certs/fullchain.pem \
  -subj "/C=KR/ST=Seoul/L=Seoul/O=DefaDB/CN=defadb.com"

# payments.defadb.com용 자체 서명 인증서
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl-certs/payments-privkey.pem \
  -out ssl-certs/payments-fullchain.pem \
  -subj "/C=KR/ST=Seoul/L=Seoul/O=DefaDB/CN=payments.defadb.com"
```

### 3단계: nginx 설정 수정
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

### 4단계: 불필요한 파일 정리
삭제된 파일들:
- `nginx_dev.conf` - 개발용 설정
- `nginx_ssl_setup.conf` - SSL 설정용 임시 파일
- `certbot-webroot/` - Let's Encrypt용 디렉토리
- `setup_ssl.sh` - 기본 SSL 스크립트 (프로덕션 버전과 중복)

## ✅ 최종 결과

### 서비스 상태 (정상):
```
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
- 자체 서명 인증서로 보안 연결 지원

## 📝 핵심 학습 포인트

1. **Docker 권한 관리**: 컨테이너 내 사용자와 호스트 볼륨 권한 일치 중요
2. **SSL 인증서 경로**: nginx 설정의 인증서 경로와 실제 파일 위치 일치 필요
3. **자체 서명 인증서**: 개발/테스트 환경에서 SSL 활성화 방법
4. **파일 정리**: 배포 환경에서 불필요한 개발용 파일 제거의 중요성

## 🔧 추후 개선 사항

1. **✅ Let's Encrypt 전환 완료**: 실제 Let's Encrypt 인증서로 전환 완료 (2025년 7월 13일)
2. **자동화**: 권한 설정 및 SSL 인증서 갱신 자동화
3. **모니터링**: 서비스 상태 및 SSL 인증서 만료 모니터링

## 📋 SSL 인증서 업데이트 (2025년 7월 13일)

### 문제 상황
- Firefox에서 "자기 스스로 서명하였으므로 인증서를 신뢰할 수 없습니다" 보안 경고 발생
- 오류 코드: MOZILLA_PKIX_ERROR_SELF_SIGNED_CERT

### 해결 과정
1. **Let's Encrypt 인증서 발급**:
   ```bash
   sudo certbot certonly --standalone --agree-tos --email admin@defadb.com --no-eff-email -d defadb.com -d www.defadb.com
   sudo certbot certonly --standalone --agree-tos --email admin@defadb.com --no-eff-email -d payments.defadb.com
   ```

2. **nginx 설정 업데이트**:
   - 자체 서명 인증서에서 Let's Encrypt 인증서로 경로 변경
   - `/etc/letsencrypt/live/` 경로 사용

3. **Docker 볼륨 마운트 변경**:
   ```yaml
   volumes:
     - /etc/letsencrypt:/etc/letsencrypt:ro,Z
   ```

### 결과
- ✅ SSL 보안 경고 해결됨
- ✅ Let's Encrypt 정식 인증서 적용 (유효기간: 2025-10-11까지)
- ✅ 브라우저에서 안전한 HTTPS 연결 확인

---
생성일: 2025년 7월 13일  
해결 시간: 약 30분  
주요 도구: Docker Compose, OpenSSL, nginx
