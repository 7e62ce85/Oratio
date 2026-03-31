# Oratio 자체 이메일 시스템 구축 가이드

**작성일**: 2025-11-06  
**상태**: 진행 중  
**목적**: 비밀번호 재설정 이메일을 개인정보 노출 최소화하여 자체 SMTP로 발송

---

## 📋 목차
1. [현재 상황](#현재-상황)
2. [문제 분석](#문제-분석)
3. [해결 방안](#해결-방안)
4. [현재까지 완료된 작업](#현재까지-완료된-작업)
5. [다음 단계](#다음-단계)
6. [상세 설정 가이드](#상세-설정-가이드)
7. [문제 해결](#문제-해결)

---

## 현재 상황

### 증상
- 사용자가 비밀번호 재설정 요청 시 "비밀번호를 재설정하기 위해 이메일을 보냈습니다" 메시지 표시
- **실제로 이메일은 발송되지 않음**

### 시스템 구성
```
Lemmy → email-service (port 1025) → Resend API → 사용자 이메일
```

### 현재 이메일 서비스 설정
- **email-service**: SMTP 프록시 (포트 1025)
- **외부 API**: Resend (https://resend.com)
- **API Key**: `.env`의 `RESEND_API_KEY` 참조
- **인증된 도메인**: defadb.com
- **미인증 도메인**: oratio.space, oratio.com

---

## 문제 분석

### 발견된 문제

#### 1. 도메인 불일치 (주요 원인)
```bash
# .env 및 lemmy.hjson
SMTP_FROM_ADDRESS=noreply@oratio.com
ADMIN_EMAIL=admin@oratio.com

# 하지만 Resend에 인증된 도메인
- defadb.com ✅ (인증됨)
- oratio.com ❌ (미인증)
- oratio.space ❌ (미인증)
```

**에러 로그**:
```
ERROR:__main__:이메일 발송 실패: 403, 
{"statusCode":403,"message":"The oratio.com domain is not verified. 
Please, add and verify your domain on https://resend.com/domains",
"name":"validation_error"}
```

#### 2. 외부 서비스 의존성
- Resend API에 전적으로 의존
- 개인정보 제공 필요 (계정 등록 시)
- API 키 관리 필요

---

## 해결 방안

### 옵션 비교

| 옵션 | 개인정보 노출 | 비용 | 난이도 | 전달률 | 독립성 |
|------|-------------|------|--------|--------|--------|
| **1. 자체 Postfix** | ⭐⭐⭐⭐⭐ ZERO | 무료 | 높음 | 중간 | ⭐⭐⭐⭐⭐ |
| 2. SMTP2GO Relay | ⭐⭐⭐⭐ 최소 | 무료* | 낮음 | 높음 | ⭐⭐⭐ |
| 3. Resend (현재) | ⭐⭐⭐ 보통 | 무료* | 매우 낮음 | 높음 | ⭐⭐ |
| 4. Gmail SMTP | ⭐⭐ 높음 | 무료 | 낮음 | 높음 | ⭐ |

**선택**: 자체 Postfix 서버 (완전한 독립성과 개인정보 보호)

---

## 현재까지 완료된 작업

### ✅ 완료된 것들

#### 1. 인프라 확인
```bash
# 서버 정보
- IP: 70.34.244.93
- 도메인: oratio.space
- 서버 유형: 자체 하드웨어 서버 (클라우드 아님)
```

#### 2. DNS 레코드 확인 (2025-11-06)
```bash
✅ MX 레코드 존재
✅ A 레코드 존재 (mail.oratio.space → 70.34.244.93)
✅ PTR 레코드 존재 (역방향 DNS)
❌ SPF 레코드 없음
❌ DKIM 레코드 없음
❌ DMARC 레코드 없음
```

#### 3. Postfix 컨테이너 상태
```bash
✅ Postfix 컨테이너 실행 중 (oratio-postfix-1)
✅ 이미지: docker.io/mwader/postfix-relay
⚠️ 설정: localhost 모드 (외부 발송 불가)
```

#### 4. 포트 확인
```bash
❌ 포트 25 (SMTP): 차단됨 - ISP가 차단 (일반적)
✅ 포트 587 (Submission): 열림
```

#### 5. 진단 스크립트 생성
- `setup_postfix_check.sh`: 현재 상태 확인 스크립트 작성 완료
- `setup_postfix_dns_guide.md`: DNS 설정 가이드 작성 완료

---

## 다음 단계

### Phase 1: 포트 25 개방 확인 (현재 단계)

#### ISP에 문의할 내용:
```
"자체 웹서버(oratio.space)를 운영 중이며, 
이메일 발송 기능이 필요합니다.
포트 25 (SMTP) 개방을 요청합니다."
```

#### 확인 방법:
```bash
# 외부에서 포트 25 접근 테스트
telnet mail.oratio.space 25

# 또는
nc -zv mail.oratio.space 25
```

---

### Phase 2A: 포트 25 개방 성공 시 (자체 SMTP)

#### Step 1: SPF 레코드 추가 (필수)
```
타입: TXT
호스트: @
값: v=spf1 ip4:70.34.244.93 a:mail.oratio.space -all
TTL: 3600
```

#### Step 2: DKIM 설정
```bash
# DKIM 키 생성
docker-compose exec postfix opendkim-genkey -t -s mail -d oratio.space

# 생성된 공개키를 DNS에 추가
타입: TXT
호스트: mail._domainkey
값: (생성된 공개키)
TTL: 3600
```

#### Step 3: DMARC 레코드 추가
```
타입: TXT
호스트: _dmarc
값: v=DMARC1; p=quarantine; rua=mailto:admin@oratio.space
TTL: 3600
```

#### Step 4: Postfix 설정 변경
```yaml
# docker-compose.yml
postfix:
  image: docker.io/mwader/postfix-relay
  environment:
    - POSTFIX_myhostname=mail.oratio.space
    - POSTFIX_mydomain=oratio.space
    - POSTFIX_myorigin=oratio.space
    - POSTFIX_inet_interfaces=all
    - POSTFIX_inet_protocols=ipv4
    - POSTFIX_message_size_limit=10240000
  ports:
    - "25:25"  # 외부 포트 개방
  restart: always
```

#### Step 5: Lemmy 설정 변경
```hjson
// lemmy.hjson
email: {
  smtp_server: "postfix:25"
  smtp_from_address: "noreply@oratio.space"
  tls_type: "none"
}
```

#### Step 6: 재시작 및 테스트
```bash
docker-compose down
docker-compose up -d
docker-compose logs -f lemmy
```

---

### Phase 2B: 포트 25 차단 시 (Relay 사용)

#### 옵션 1: SMTP2GO Relay (권장)

##### 장점
- 개인정보 최소화 (도메인 이메일만 필요)
- 무료 1,000 emails/month
- 신용카드 불필요
- 높은 전달률
- 자동 SPF/DKIM 설정

##### 설정 단계

**1. SMTP2GO 가입**
```
https://www.smtp2go.com/
- Email: admin@oratio.space
- Company: Oratio (선택)
```

**2. SMTP 인증 정보 획득**
```
SMTP Server: mail.smtp2go.com
Port: 2525 (권장) 또는 587
Username: (대시보드에서 확인)
Password: (대시보드에서 생성)
```

**3. 도메인 인증 (선택, 권장)**
```
Dashboard → Domains → Add Domain → oratio.space
- SPF: v=spf1 include:smtp2go.com ~all
- DKIM: (SMTP2GO 제공 값)
- DMARC: v=DMARC1; p=none;
```

**4. Postfix Relay 설정**
```yaml
# docker-compose.yml
postfix:
  image: docker.io/mwader/postfix-relay
  environment:
    - POSTFIX_myhostname=mail.oratio.space
    - POSTFIX_relayhost=mail.smtp2go.com:2525
    - POSTFIX_smtp_sasl_auth_enable=yes
    - POSTFIX_smtp_sasl_password=mail.smtp2go.com:YOUR_USERNAME:YOUR_PASSWORD
    - POSTFIX_smtp_sasl_security_options=noanonymous
    - POSTFIX_smtp_tls_security_level=encrypt
```

**5. Lemmy 설정 (변경 없음)**
```hjson
email: {
  smtp_server: "postfix:25"
  smtp_from_address: "noreply@oratio.space"
  tls_type: "none"
}
```

#### 옵션 2: Lemmy에서 직접 SMTP2GO 사용

**장점**: Postfix 불필요, 더 간단

```hjson
// lemmy.hjson
email: {
  smtp_server: "mail.smtp2go.com"
  smtp_login: "your_smtp2go_username"
  smtp_password: "your_smtp2go_password"
  smtp_from_address: "noreply@oratio.space"
  tls_type: "tls"
}
```

**환경변수 사용 (더 안전)**:
```bash
# .env
SMTP_SERVER=mail.smtp2go.com
SMTP_PORT=2525
SMTP_LOGIN=your_username
SMTP_PASSWORD=your_password
SMTP_FROM_ADDRESS=noreply@oratio.space
```

---

### Phase 3: 테스트 및 검증

#### 1. 비밀번호 재설정 테스트
```bash
# 웹 브라우저에서:
1. 로그아웃
2. "비밀번호 찾기" 클릭
3. 이메일 입력
4. "Reset Password" 클릭
5. 이메일 수신 확인 (inbox + spam folder)
```

#### 2. 로그 확인
```bash
# Lemmy 로그
docker-compose logs lemmy | grep -i email

# Postfix 로그
docker-compose logs postfix

# email-service 로그 (현재 사용 중이라면)
docker-compose logs email-service
```

#### 3. 이메일 전달률 테스트
```
https://www.mail-tester.com/
- 테스트 이메일 주소로 발송
- 점수 10/10 목표
- SPF, DKIM, DMARC 체크 확인
```

#### 4. 스팸 점수 확인
```
https://mxtoolbox.com/SuperTool.aspx
- 도메인 입력: oratio.space
- Blacklist 확인
- DNS 레코드 확인
```

---

## 상세 설정 가이드

### DNS 레코드 전체 목록

```dns
# MX 레코드 (메일 수신)
타입: MX
호스트: @
값: mail.oratio.space
우선순위: 10
TTL: 3600

# A 레코드 (메일 서버)
타입: A
호스트: mail
값: 70.34.244.93
TTL: 3600

# SPF 레코드 (발신자 인증)
타입: TXT
호스트: @
값: v=spf1 ip4:70.34.244.93 a:mail.oratio.space -all
# 또는 SMTP2GO 사용 시:
값: v=spf1 include:smtp2go.com ~all
TTL: 3600

# DKIM 레코드 (이메일 서명)
타입: TXT
호스트: mail._domainkey
값: (Postfix에서 생성된 공개키 또는 SMTP2GO 제공 값)
TTL: 3600

# DMARC 레코드 (정책)
타입: TXT
호스트: _dmarc
값: v=DMARC1; p=quarantine; rua=mailto:admin@oratio.space; fo=1
TTL: 3600

# PTR 레코드 (역방향 DNS) - 이미 설정됨
IP: 70.34.244.93
PTR: 현재 → 129c261364c553678d7882b6067932e2.hostedonsporestack.com
변경 필요 → mail.oratio.space (ISP에 요청)
```

### DNS 전파 확인 명령어

```bash
# MX 레코드
dig MX oratio.space +short

# A 레코드
dig A mail.oratio.space +short

# SPF 레코드
dig TXT oratio.space +short | grep spf

# DKIM 레코드
dig TXT mail._domainkey.oratio.space +short

# DMARC 레코드
dig TXT _dmarc.oratio.space +short

# PTR 레코드 (역방향)
dig -x 70.34.244.93 +short
```

---

## 문제 해결

### 이메일이 발송되지 않음

#### 1. 로그 확인
```bash
# Lemmy 로그에서 에러 찾기
docker-compose logs lemmy --tail=100 | grep -i error

# Postfix 로그 확인
docker-compose logs postfix --tail=100

# email-service 로그 (현재 시스템)
docker-compose logs email-service --tail=50
```

#### 2. SMTP 연결 테스트
```bash
# Postfix 컨테이너에서 직접 테스트
docker-compose exec postfix telnet localhost 25

# 또는
docker-compose exec lemmy nc -zv postfix 25
```

### 이메일이 스팸 폴더로 감

#### 원인과 해결
```
1. SPF 레코드 없음 → SPF 추가
2. DKIM 서명 없음 → DKIM 설정
3. PTR 레코드 불일치 → ISP에 PTR 변경 요청
4. IP 평판 낮음 → 시간이 필요 (또는 SMTP2GO 사용)
5. 이메일 내용 문제 → mail-tester.com으로 확인
```

### 포트 25 차단 해제 안됨

#### 대안
```
1. SMTP2GO로 relay (권장)
2. Gmail SMTP 사용
3. 다른 VPS로 이전 (포트 25 지원하는 곳)
4. AWS SES, SendGrid 등 사용
```

---

## 참고 파일

### 프로젝트 파일 위치
```
/home/user/Oratio/oratio/
├── docker-compose.yml          # Postfix 설정
├── lemmy.hjson                 # Lemmy 이메일 설정
├── .env                        # 환경변수 (SMTP 인증 정보)
├── email-service/              # 현재 이메일 서비스
│   ├── app.py                  # Resend API 프록시
│   ├── Dockerfile
│   └── requirements.txt
├── setup_postfix_check.sh      # 상태 확인 스크립트
└── setup_postfix_dns_guide.md  # DNS 설정 가이드
```

### 관련 문서
```
/home/user/Oratio/docs/
├── archive/resolved-issues/
│   └── EMAIL_VERIFICATION_GUIDE.md  # 회원가입 이메일 인증 (참고용)
└── features/
    └── SELF_HOSTED_EMAIL_SYSTEM.md  # 이 문서
```

---

## 타임라인

### 완료된 작업
- **2025-11-06**: 문제 진단, 현재 시스템 분석
- **2025-11-06**: DNS 레코드 확인
- **2025-11-06**: Postfix 상태 확인
- **2025-11-06**: 포트 확인 (25 차단, 587 열림)

### 대기 중
- **포트 25 개방 여부 확인**: ISP 문의 필요

### 예상 일정
```
Phase 1: ISP 포트 25 확인           → 1~3일
Phase 2A (포트 25 성공):
  - DNS 레코드 추가                 → 1시간
  - Postfix 설정                    → 30분
  - 테스트                          → 30분
  총계: 약 2시간

Phase 2B (포트 25 차단):
  - SMTP2GO 가입                    → 10분
  - 설정 변경                       → 20분
  - 테스트                          → 10분
  총계: 약 40분
```

---

## 체크리스트

### 포트 25 개방 성공 시
- [ ] SPF 레코드 추가
- [ ] DKIM 키 생성 및 DNS 추가
- [ ] DMARC 레코드 추가
- [ ] PTR 레코드 변경 (ISP 요청)
- [ ] docker-compose.yml 수정
- [ ] lemmy.hjson 수정
- [ ] 컨테이너 재시작
- [ ] 비밀번호 재설정 테스트
- [ ] mail-tester.com 점수 확인
- [ ] email-service 제거 (선택)

### 포트 25 차단 시 (SMTP2GO)
- [ ] SMTP2GO 계정 생성
- [ ] SMTP 인증 정보 획득
- [ ] oratio.space 도메인 추가
- [ ] DNS 레코드 추가 (SPF, DKIM, DMARC)
- [ ] Postfix relay 설정 또는 Lemmy 직접 연결
- [ ] .env 파일에 인증 정보 저장
- [ ] 컨테이너 재시작
- [ ] 비밀번호 재설정 테스트
- [ ] SMTP2GO Activity 확인
- [ ] email-service 제거 (선택)

---

## 보안 고려사항

### 개인정보 보호
```
✅ 자체 Postfix: 개인정보 노출 ZERO
✅ SMTP2GO: 도메인 이메일만 필요, 개인 이메일 불필요
⚠️ Resend (현재): API 키 관리 필요
⚠️ Gmail SMTP: 개인 Gmail 계정 노출
```

### 인증 정보 관리
```bash
# .env 파일에 민감 정보 저장
SMTP_LOGIN=username
SMTP_PASSWORD=password

# .gitignore에 추가
echo ".env" >> .gitignore

# 파일 권한 설정
chmod 600 .env
```

### 모니터링
```bash
# 이메일 발송 로그 주기적 확인
docker-compose logs postfix | grep "status=sent"

# SMTP2GO 사용 시 Dashboard 모니터링
# - 발송 성공률
# - 바운스율
# - 스팸 신고
```

---

## 연락처 및 리소스

### ISP 문의
- 포트 25 개방 요청
- PTR 레코드 변경 요청

### 외부 서비스
- **SMTP2GO**: https://www.smtp2go.com/
- **Resend**: https://resend.com/

### 테스트 도구
- **Mail Tester**: https://www.mail-tester.com/
- **MX Toolbox**: https://mxtoolbox.com/
- **DKIM Validator**: https://dkimvalidator.com/

### 참고 문서
- **Postfix**: http://www.postfix.org/documentation.html
- **SPF**: https://www.spfwizard.net/
- **DKIM**: https://dkim.org/
- **DMARC**: https://dmarc.org/

---

## 마지막 업데이트
- **날짜**: 2025-11-06
- **작성자**: GitHub Copilot
- **다음 작업**: ISP 포트 25 개방 확인

================================================
Scenario A: 포트 25 개방 성공 시 (자체 SMTP)
필요한 DNS 레코드 5개:
1. A 레코드 (메일 서버)
[타입: A
호스트: mail
값: 70.34.244.93
TTL: 3600]

2. MX 레코드 (메일 수신)
[타입: MX
호스트: @ (또는 비워둠)
값: mail.oratio.space
우선순위: 10
TTL: 3600]

3. SPF 레코드 (필수! - 스팸 방지)
[타입: TXT
호스트: @ (또는 비워둠)
값: v=spf1 ip4:70.34.244.93 a:mail.oratio.space -all
TTL: 3600]

4. DMARC 레코드 (권장)
[타입: TXT
호스트: _dmarc
값: v=DMARC1; p=quarantine; rua=mailto:admin@oratio.space
TTL: 3600]

5. DKIM 레코드 (나중에, 키 생성 후)
[타입: TXT
호스트: _dmarc
값: v=DMARC1; p=quarantine; rua=mailto:admin@oratio.space
TTL: 3600]

타입: TXT호스트: mail._domainkey값: (Postfix에서 생성된 공개키)TTL: 3600
ISP 요청 2개:
✅ 포트 25 개방
✅ PTR 레코드 변경 (70.34.244.93 → mail.oratio.space)
---------------
Scenario B: 포트 25 차단 시 (SMTP2GO Relay)
필요한 DNS 레코드 1~3개:
1. SPF 레코드 (필수!)
[타입: TXT
호스트: @ (또는 비워둠)
값: v=spf1 include:smtp2go.com ~all
TTL: 3600]

2. DMARC 레코드 (권장)
[타입: TXT
호스트: _dmarc
값: v=DMARC1; p=none; rua=mailto:admin@oratio.space
TTL: 3600]

3. DKIM 레코드 (SMTP2GO 제공 값)
[타입: TXT
호스트: (SMTP2GO가 알려주는 값, 예: s1._domainkey)
값: (SMTP2GO가 제공하는 공개키)
TTL: 3600]

ISP 요청:
❌ 필요 없음!
-------------------
