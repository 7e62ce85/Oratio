# ✅ defadb.com 도메인 전환 완료!

모든 설정 파일이 `khankorean.com`에서 `defadb.com`으로 성공적으로 변경되었습니다.

## 📋 변경된 도메인

| 서비스 | 새로운 URL |
|--------|------------|
| 메인 사이트 | https://defadb.com |
| WWW 리다이렉션 | https://www.defadb.com |
| 결제 서비스 | https://payments.defadb.com |

## 🔧 변경된 파일들

### 1. 설정 파일
- `lemmy.hjson`: hostname을 defadb.com으로 변경, 이메일 주소 업데이트
- `docker-compose.yml`: 환경변수를 실제 도메인으로 업데이트, SSL 인증서 마운트 활성화
- `nginx_production.conf`: 새로 생성된 프로덕션용 nginx 설정

### 2. 빌드 설정
- `webpack.config.js`: BCH 서비스 URL을 https://payments.defadb.com으로 변경

### 3. 스크립트 및 정적 파일
- `refresh_passwords.sh`: BCH API URL 업데이트
- `nginx/js/bch-payment-button.js`: 결제 버튼 URL을 실제 도메인으로 변경

### 4. 새로 생성된 파일
- `.env.production`: 프로덕션 환경변수 템플릿
- `setup_ssl.sh`: SSL 인증서 자동 발급 스크립트
- `deploy_production.sh`: 프로덕션 배포 자동화 스크립트
- `DEPLOYMENT_GUIDE.md`: 배포 가이드 문서

## 주요 변경사항

### URL 변경
| 기존 (localhost) | 변경 후 (defadb.com) |
|------------------|----------------------|
| http://localhost | https://defadb.com |
| http://localhost:8081 | https://payments.defadb.com |
| localhost:8081/api/user_credit | payments.defadb.com/api/user_credit |

### SSL/HTTPS 활성화
- HTTP에서 HTTPS로 자동 리다이렉션
- SSL 인증서 자동 발급 스크립트 제공
- 보안 헤더 추가 (HSTS, CSP 등)

### 환경변수 업데이트
- `LEMMY_UI_LEMMY_EXTERNAL_HOST`: localhost → defadb.com
- `LEMMY_UI_HTTPS`: false → true
- `LEMMY_BCH_*_URL`: localhost → payments.defadb.com

## 🚀 다음 단계

### 1. DNS 설정
```bash
# DNS 레코드 설정 (도메인 관리 패널에서)
defadb.com           A    [서버 IP]
www.defadb.com       A    [서버 IP]
payments.defadb.com  A    [서버 IP]
```

### 2. SSL 인증서 발급
```bash
cd /home/joshham/khankorean/oratio
./setup_ssl_production.sh
```

### 3. 환경변수 설정
```bash
cp .env.production .env
nano .env  # LEMMY_API_KEY 설정
```

### 4. 프로덕션 배포
```bash
./deploy_production.sh
```

### 5. 확인
```bash
# 서비스 상태 확인
docker-compose ps

# 웹사이트 접속 테스트
curl -I https://defadb.com
curl -I https://payments.defadb.com
```

## ⚠️ 주의사항

1. **DNS 전파**: DNS 변경 후 최대 48시간 소요될 수 있습니다
2. **SSL 인증서**: Let's Encrypt 인증서 발급 전에 DNS가 올바르게 설정되어야 합니다
3. **방화벽**: 포트 80, 443이 열려있는지 확인하세요
4. **API 키**: `.env` 파일의 `LEMMY_API_KEY`를 실제 값으로 설정하세요

## 📋 배포 전 체크리스트

### 서버 요구사항 ✓
- [ ] Ubuntu/Debian Linux
- [ ] Docker & Docker Compose 설치  
- [ ] 최소 2GB RAM, 20GB 저장공간
- [ ] 포트 80, 443 방화벽 오픈

### DNS 설정 ✓
- [ ] defadb.com A 레코드 설정
- [ ] www.defadb.com A 레코드 설정  
- [ ] payments.defadb.com A 레코드 설정

### 설정 파일 ✓
- [ ] .env 파일 생성 및 LEMMY_API_KEY 설정
- [ ] SSL 인증서 발급 (setup_ssl.sh 실행)
- [ ] nginx 설정 확인

### 배포 실행 ✓
- [ ] deploy_production.sh 스크립트 실행
- [ ] 서비스 상태 확인
- [ ] 웹사이트 접속 테스트

모든 준비가 완료되면 https://defadb.com 으로 접속할 수 있습니다! 🎉

## 🔄 롤백 방법

만약 문제가 발생하면 다음 명령으로 롤백할 수 있습니다:

```bash
# 기존 설정으로 복원
cp nginx_internal.conf.backup nginx_internal.conf

# localhost 환경변수로 변경
export LEMMY_UI_LEMMY_EXTERNAL_HOST=localhost
export LEMMY_UI_HTTPS=false
export LEMMY_BCH_API_URL=http://localhost:8081/api/user_credit
export LEMMY_BCH_PAYMENT_URL=http://localhost:8081/

# 컨테이너 재시작
docker-compose down
docker-compose up -d
```

## 🔧 문제 해결

### SSL 인증서 문제
```bash
# 인증서 상태 확인
sudo certbot certificates

# 인증서 갱신
sudo certbot renew
```

### 컨테이너 로그 확인
```bash
# 모든 서비스 로그
docker-compose logs

# 특정 서비스 로그  
docker-compose logs lemmy-ui
docker-compose logs proxy
```

### DNS 전파 확인
```bash
# DNS 확인
nslookup defadb.com
nslookup www.defadb.com
nslookup payments.defadb.com
```

### 방화벽 설정
```bash
# Ubuntu UFW
sudo ufw allow 80
sudo ufw allow 443

# 또는 iptables
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT
```
