# oratio.space 접속 불가 문제 해결 가이드

## 📋 문제 개요
- **발생일**: 2025-09-29
- **증상**: https://oratio.space/ 외부 접속 불가
- **원인**: NAT/Router 포트 포워딩 미설정
- **심각도**: 높음 (서비스 접근 불가)

## 🔍 진단 결과

### ✅ 정상 작동하는 부분
```bash
# 로컬 접속 가능
curl -I http://localhost/
# HTTP/1.1 301 Moved Permanently (정상)

# 서비스 상태
docker-compose ps
# proxy, lemmy, lemmy-ui 모두 Up 상태

# DNS 해상도
nslookup oratio.space
# 70.34.244.93 (올바른 IP)
```

### ❌ 문제가 있는 부분
```bash
# 외부 IP로 접속 불가
telnet 70.34.244.93 80
# Connection refused

```bash
# 네트워크 구성
ip route show default
# default via [게이트웨이] (NAT 환경)
# 서버 IP: [내부 IP]
```
```

## 🛠️ 해결 방법

### 방법 1: 라우터 포트 포워딩 설정 (권장)

#### 1단계: 라우터 관리 페이지 접속
```bash
# 브라우저에서 접속
# 라우터 관리 페이지
```

#### 2단계: 포트 포워딩 설정
라우터 설정에서 다음과 같이 포트 포워딩 규칙 추가:

| 서비스명 | 외부 포트 | 내부 IP | 내부 포트 | 프로토콜 |
|---------|----------|---------|----------|----------|
| HTTP | 80 | [서버 내부 IP] | 80 | TCP |
| HTTPS | 443 | [서버 내부 IP] | 443 | TCP |
| BCH Payment | 8081 | [서버 내부 IP] | 8081 | TCP |

#### 3단계: 설정 적용 후 테스트
```bash
# 외부에서 테스트 (다른 네트워크에서)
curl -I http://oratio.space/
```

### 방법 2: UPnP 자동 포트 포워딩 (임시)

#### UPnP가 활성화된 경우 자동 설정 시도:
```bash
# UPnP 도구 설치
sudo apt update
sudo apt install miniupnpc

# 포트 포워딩 자동 설정
upnpc -a [서버_내부_IP] 80 80 TCP
upnpc -a [서버_내부_IP] 443 443 TCP
upnpc -a [서버_내부_IP] 8081 8081 TCP

# 설정 확인
upnpc -l
```

### 방법 3: DMZ 설정 (비권장 - 보안 위험)

라우터에서 DMZ Host를 서버의 내부 IP로 설정
- 모든 포트가 열리므로 보안상 위험
- 테스트 목적으로만 사용

## 🧪 설정 검증

### 1. 로컬 테스트
```bash
# 내부 IP로 접속 테스트
curl -I http://localhost/
```

### 2. 외부 테스트 (포트 포워딩 설정 후)
```bash
# 외부 IP로 접속 테스트
curl -I http://70.34.244.93/

# 도메인으로 접속 테스트
curl -I http://oratio.space/
```

### 3. 포트 상태 확인
```bash
# 포트가 열렸는지 확인 (외부에서 실행)
nmap -p 80,443,8081 oratio.space
```

## 🔧 대안 해결책

### 클라우드플레어 터널 (Cloudflare Tunnel)
포트 포워딩이 불가능한 경우:

```bash
# Cloudflared 설치
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# 터널 생성
cloudflared tunnel login
cloudflared tunnel create oratio

# 설정 파일 생성
cat > ~/.cloudflared/config.yml << EOF
tunnel: oratio
credentials-file: ~/.cloudflared/[터널-ID].json

ingress:
  - hostname: oratio.space
    service: http://localhost:80
  - hostname: payments.oratio.space
    service: http://localhost:8081
  - service: http_status:404
EOF

# 터널 실행
cloudflared tunnel run oratio
```

## 📊 네트워크 구성도

```
인터넷 ←→ [공인 IP] ←→ 라우터(게이트웨이) ←→ 서버(내부 IP:80,443)
              ↑                      ↑
      oratio.space 도메인      포트포워딩 필요
```

## ✅ 최종 검증 체크리스트

- [ ] 라우터 포트 포워딩 설정 완료
- [ ] HTTP (80번 포트) 외부 접속 가능
- [ ] HTTPS (443번 포트) 외부 접속 가능
- [ ] https://oratio.space/ 브라우저 접속 가능
- [ ] SSL 인증서 경고 확인 (자체 서명 인증서)
- [ ] 결제 서비스 접속 가능 (8081번 포트)

## 🔮 향후 개선 사항

1. **Let's Encrypt 인증서 발급**
   ```bash
   sudo certbot certonly --standalone -d oratio.space -d payments.oratio.space
   ```

2. **nginx 설정 업데이트**
   - 자체 서명 → Let's Encrypt 인증서로 변경

3. **모니터링 설정**
   - 외부 접속 모니터링 스크립트 작성
   - 포트 포워딩 상태 자동 확인

## 🚨 보안 고려사항

1. **포트 최소화**: 필요한 포트만 열기 (80, 443, 8081)
2. **방화벽 설정**: 추가 보안 레이어 구축
3. **SSL/TLS 강화**: 정식 인증서 사용
4. **접속 로그 모니터링**: 비정상 접근 탐지

---

**문제 해결일**: 2025-09-29  
**해결 시간**: 진행 중  
**최종 상태**: 포트 포워딩 설정 필요

## 📞 추가 도움

포트 포워딩 설정이 어려운 경우:
1. 라우터 모델명과 제조사 확인
2. 제조사 공식 가이드 참조
3. Cloudflare Tunnel 대안 고려
