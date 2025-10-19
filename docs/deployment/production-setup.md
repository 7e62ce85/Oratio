# oratio.space 프로덕션 배포 가이드

## 📋 개요
이 문서는 Rust-Lemmy + BCH Payment 시스템을 `oratio.space` 도메인으로 프로덕션 배포하는 완전한 가이드입니다.

## 🎯 배포 완료 현황 (2025-07-13)

### ✅ 성공적으로 완료된 항목
- **도메인 전환**: `khankorean.com` → `oratio.space`
- **SSL 인증서**: Let's Encrypt 정식 인증서 적용
- **서비스 안정화**: 7개 컨테이너 모두 정상 동작
- **BCH 결제 시스템**: 실제 거래 처리 중

### 🌐 서비스 URL
| 서비스 | URL | 상태 |
|--------|-----|------|
| 메인 사이트 | https://oratio.space | ✅ 운영 중 |
| WWW 리다이렉션 | https://www.oratio.space | ✅ 정상 |
| 결제 서비스 | https://payments.oratio.space | ✅ 정상 |

## 🏗️ 시스템 아키텍처

### 컨테이너 구조
```
┌─────────────────────┐    ┌─────────────────────┐
│   nginx (proxy)     │    │   lemmy-ui          │
│   Port: 80,443      │────│   (Custom BCH UI)   │
│   SSL Termination   │    │                     │
└─────────────────────┘    └─────────────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────┐    ┌─────────────────────┐
│   lemmy (core)      │    │   bitcoincash-      │
│   Rust Backend      │    │   service           │
│   Port: 8536        │    │   Flask API         │
└─────────────────────┘    │   Port: 8081        │
           │                └─────────────────────┘
           ▼                           │
┌─────────────────────┐                ▼
│   postgres          │    ┌─────────────────────┐
│   User Data         │    │   electron-cash     │
│   Forums, Users     │    │   BCH Wallet        │
└─────────────────────┘    │   Port: 7777        │
           │                └─────────────────────┘
           ▼
┌─────────────────────┐
│   pictrs + postfix │
│   Images + Email    │
└─────────────────────┘
```

## 🔧 주요 변경사항

### 1. 도메인 및 URL 변경
| 기존 (localhost) | 변경 후 (oratio.space) |
|------------------|----------------------|
| http://localhost | https://oratio.space |
| http://localhost:8081 | https://payments.oratio.space |
| localhost:8081/api/user_credit | payments.oratio.space/api/user_credit |

### 2. SSL/HTTPS 활성화
- HTTP에서 HTTPS로 자동 리다이렉션
- Let's Encrypt 정식 인증서 (유효기간: 2025-10-11)
- 보안 헤더 추가 (HSTS, CSP 등)

### 3. 환경변수 업데이트
```bash
# 주요 환경변수 변경
LEMMY_UI_LEMMY_EXTERNAL_HOST=oratio.space
LEMMY_UI_HTTPS=true
LEMMY_BCH_API_URL=https://payments.oratio.space/api/user_credit
LEMMY_BCH_PAYMENT_URL=https://payments.oratio.space/
```

## 📁 변경된 파일들

### 1. 핵심 설정 파일
- `lemmy.hjson`: hostname을 oratio.space으로 변경, 이메일 주소 업데이트
- `docker-compose.yml`: 환경변수를 실제 도메인으로 업데이트, SSL 인증서 마운트 활성화
- `nginx_production.conf`: 프로덕션용 nginx 설정 (SSL 지원)

### 2. 빌드 및 스크립트
- `webpack.config.js`: BCH 서비스 URL을 https://payments.oratio.space으로 변경
- `refresh_passwords.sh`: BCH API URL 업데이트
- `nginx/js/bch-payment-button.js`: 결제 버튼 URL을 실제 도메인으로 변경

### 3. 배포 자동화 스크립트
- `setup_ssl_production.sh`: SSL 인증서 자동 발급
- `deploy_production.sh`: 프로덕션 배포 자동화
- `.env.production`: 프로덕션 환경변수 템플릿

## 🚀 새로운 서버 배포 가이드

### 1. 사전 준비사항

#### 서버 요구사항
- **OS**: Ubuntu/Debian Linux
- **리소스**: 최소 2GB RAM, 20GB 저장공간
- **네트워크**: 포트 80, 443 방화벽 오픈
- **도구**: Docker & Docker Compose 설치

#### 도메인 DNS 설정
```bash
# DNS 레코드 설정 (도메인 관리 패널에서)
oratio.space           A    [서버 IP]
www.oratio.space       A    [서버 IP]
payments.oratio.space  A    [서버 IP]
```

### 2. 배포 실행

#### Step 1: 코드 배포
```bash
# 프로젝트 클론 (또는 파일 업로드)
cd /opt
git clone https://github.com/your-repo/khankorean
cd khankorean/oratio
```

#### Step 2: 환경변수 설정
```bash
# 프로덕션 환경변수 복사
cp .env.production .env

# API 키 설정 (중요!)
nano .env
# LEMMY_API_KEY=실제_API_키_입력
```

#### Step 3: SSL 인증서 발급
```bash
# Let's Encrypt 인증서 자동 발급
./setup_ssl_production.sh
```

#### Step 4: 서비스 시작
```bash
# 프로덕션 배포 실행
./deploy_production.sh
```

### 3. 배포 후 확인

#### 서비스 상태 확인
```bash
# 컨테이너 상태 확인
docker-compose ps

# 예상 출력:
# NAME                  STATUS
# oratio-proxy-1        Up (healthy)
# oratio-lemmy-ui-1     Up (healthy)
# oratio-lemmy-1        Up
# oratio-postgres-1     Up (healthy)
# oratio-pictrs-1       Up
# oratio-postfix-1      Up
# bitcoincash-service   Up
# electron-cash         Up
```

#### 웹사이트 접속 테스트
```bash
# SSL 인증서 확인
curl -I https://oratio.space

# 결제 서비스 확인
curl -I https://payments.oratio.space

# BCH API 테스트
curl https://payments.oratio.space/health
```

## 🔧 문제 해결

### Docker 컨테이너 재시작 문제

#### 증상
- `oratio-pictrs-1` 지속적 재시작
- `oratio-proxy-1` SSL 인증서 오류

#### 해결방법
```bash
# 1. pictrs 권한 문제 해결
sudo chown -R 991:991 volumes/pictrs

# 2. SSL 인증서 확인
ls -la /etc/letsencrypt/live/oratio.space/

# 3. nginx 설정 검증
docker-compose exec proxy nginx -t

# 4. 서비스 재시작
docker-compose restart
```

### SSL 인증서 문제

#### 증상
- "자체 서명 인증서" 브라우저 경고
- SSL 연결 실패

#### 해결방법
```bash
# 1. 인증서 상태 확인
sudo certbot certificates

# 2. 인증서 갱신
sudo certbot renew

# 3. nginx 재시작
docker-compose restart proxy
```

### BCH 결제 서비스 연결 문제

#### 증상
- "Connection to electron-cash timed out"
- 결제 기능 오류

#### 해결방법
```bash
# 1. electron-cash 컨테이너 재시작
docker-compose restart electron-cash

# 2. 연결 테스트
curl -u "bchrpc:password" \
  -X POST http://localhost:7777 \
  -H "Content-Type: application/json" \
  -d '{"method":"getbalance","params":[],"id":1}'

# 3. BCH 서비스 재시작
docker-compose restart bitcoincash-service
```

## 📊 모니터링 및 유지보수

### 일일 확인사항
```bash
# 1. 서비스 상태
docker-compose ps

# 2. 시스템 리소스
df -h  # 디스크 사용량
free -h  # 메모리 사용량

# 3. 로그 확인
docker-compose logs --tail=50 proxy
docker-compose logs --tail=50 bitcoincash-service
```

### 주간 확인사항
```bash
# 1. SSL 인증서 만료일 확인
sudo certbot certificates

# 2. 백업 확인
ls -la volumes/postgres/
ls -la volumes/pictrs/

# 3. 보안 업데이트
sudo apt update && sudo apt list --upgradable
```

### 월별 확인사항
- Docker 이미지 업데이트
- 로그 파일 정리
- 성능 모니터링 리포트
- 백업 전략 검토

## 🔄 롤백 방법

### 긴급 롤백 (localhost로 복원)
```bash
# 1. 기존 설정으로 복원
cp nginx_internal.conf.backup nginx_internal.conf

# 2. localhost 환경변수로 변경
export LEMMY_UI_LEMMY_EXTERNAL_HOST=localhost
export LEMMY_UI_HTTPS=false
export LEMMY_BCH_API_URL=http://localhost:8081/api/user_credit
export LEMMY_BCH_PAYMENT_URL=http://localhost:8081/

# 3. 컨테이너 재시작
docker-compose down
docker-compose up -d
```

### 부분 롤백 (특정 서비스)
```bash
# nginx만 롤백
docker-compose stop proxy
# 설정 파일 복원 후
docker-compose start proxy

# BCH 서비스만 롤백
docker-compose stop bitcoincash-service
# 설정 복원 후
docker-compose start bitcoincash-service
```

## 📋 배포 체크리스트

### 사전 준비 ✅
- [ ] 서버 리소스 확인 (2GB+ RAM, 20GB+ 저장공간)
- [ ] Docker & Docker Compose 설치
- [ ] 방화벽 설정 (포트 80, 443 오픈)
- [ ] DNS 레코드 설정 완료

### 배포 실행 ✅
- [ ] 프로젝트 코드 배포
- [ ] `.env` 파일 설정 (LEMMY_API_KEY 포함)
- [ ] SSL 인증서 발급
- [ ] 컨테이너 시작
- [ ] 서비스 상태 확인

### 배포 후 검증 ✅
- [ ] https://oratio.space 접속 확인
- [ ] https://payments.oratio.space 접속 확인
- [ ] BCH 결제 기능 테스트
- [ ] 이메일 발송 기능 테스트
- [ ] SSL 인증서 브라우저 확인

### 운영 준비 ✅
- [ ] 모니터링 스크립트 설정
- [ ] 백업 정책 수립
- [ ] 로그 로테이션 설정
- [ ] 보안 정책 검토

---

## 📞 지원 및 문의

### 기술 지원
- **GitHub Issues**: 버그 리포트 및 기능 요청
- **Discord**: 실시간 기술 지원
- **Email**: admin@oratio.space

### 긴급 상황 대응
1. **서비스 장애**: 즉시 롤백 프로세스 실행
2. **보안 문제**: 관련 서비스 즉시 중단
3. **데이터 손실**: 백업에서 복원

---

**마지막 업데이트**: 2025-09-07  
**문서 버전**: v2.0  
**배포 환경**: Production (oratio.space)  
**SSL 만료일**: 2025-10-11
