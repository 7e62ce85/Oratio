# Oratio Forum 이메일 인증 시스템 설정 가이드

## 개요
이 가이드는 Oratio Forum에서 자동 이메일 인증 시스템을 구현하는 방법을 설명합니다.

## 구현된 기능

### 1. 이메일 인증 시스템
- 사용자 가입 시 이메일 인증 필수
- 관리자 승인 프로세스
- 자동 이메일 발송
- 커스텀 이메일 템플릿

### 2. 보안 설정
- CAPTCHA 활성화
- Rate Limiting 설정
- 스팸 방지 설정

## 설정 파일

### 1. 환경 변수 (.env)
```bash
# Email Configuration
SMTP_SERVER=postfix:25
SMTP_FROM_ADDRESS=noreply@oratio.space
ADMIN_EMAIL=admin@oratio.space
SITE_NAME=Oratio Forum
SITE_DESCRIPTION=A forum for meaningful discussions
DOMAIN=oratio.space
```

### 2. Lemmy 설정 (lemmy.hjson)
주요 이메일 관련 설정:
- `require_email_verification: true` - 이메일 인증 필수
- `registration_mode: "RequireApplication"` - 관리자 승인 필요
- `application_email_admins: true` - 신규 가입 시 관리자에게 알림

## 배포 방법

### 1. 스크립트를 사용한 자동 배포
```bash
cd /opt/khankorean/oratio
./deploy_email_verification.sh
```

### 2. 수동 배포
```bash
# 1. 설정 파일 업데이트
./setup_email_verification.sh

# 2. 서비스 재시작
docker-compose down
docker-compose up -d

# 3. 상태 확인
docker-compose ps
docker-compose logs lemmy
docker-compose logs postfix
```

## 이메일 전송 테스트

### 기본 테스트
```bash
./test_email.sh your-email@example.com
```

### 로그 확인
```bash
# Postfix 로그
docker-compose logs postfix

# Lemmy 로그
docker-compose logs lemmy
```

## DNS 설정 (중요!)

이메일이 스팸으로 분류되지 않도록 하기 위해 다음 DNS 레코드를 설정해야 합니다:

### 1. SPF 레코드
```
TXT 레코드: v=spf1 ip4:YOUR_SERVER_IP include:_spf.google.com ~all
```

### 2. DKIM 설정 (권장)
```bash
# DKIM 키 생성
docker-compose exec postfix opendkim-genkey -t -s mail -d oratio.space

# 생성된 키를 DNS에 추가
```

### 3. DMARC 설정 (권장)
```
TXT 레코드 (_dmarc.oratio.space): v=DMARC1; p=none; rua=mailto:admin@oratio.space
```

### 4. PTR 레코드 (역방향 DNS)
서버 IP에 대한 PTR 레코드를 oratio.space으로 설정

## 사용자 가입 프로세스

1. **사용자가 가입 신청**
   - 이메일 주소 입력 필수
   - CAPTCHA 인증

2. **이메일 인증**
   - 자동으로 인증 메일 발송
   - 사용자가 링크 클릭하여 인증

3. **관리자 승인**
   - 관리자에게 알림 메일 발송
   - 관리자가 수동으로 승인

4. **계정 활성화**
   - 승인 후 계정 사용 가능

## 문제 해결

### 이메일이 전송되지 않는 경우
1. Postfix 컨테이너 상태 확인: `docker-compose ps postfix`
2. 로그 확인: `docker-compose logs postfix`
3. DNS 설정 확인
4. 방화벽 설정 확인 (포트 25, 587)

### 이메일이 스팸으로 분류되는 경우
1. SPF 레코드 설정 확인
2. DKIM 설정 추가
3. DMARC 설정 추가
4. PTR 레코드 설정 확인

### Lemmy 설정 문제
1. lemmy.hjson 문법 확인
2. 환경 변수 확인
3. 데이터베이스 연결 확인

## 모니터링

### 이메일 전송 상태 모니터링
```bash
# 실시간 로그 모니터링
docker-compose logs -f postfix

# 이메일 큐 확인
docker-compose exec postfix mailq
```

### 사용자 가입 모니터링
```bash
# Lemmy 로그 확인
docker-compose logs -f lemmy | grep -i email
```

## 보안 고려사항

1. **Rate Limiting**: 설정된 제한을 통해 스팸 가입 방지
2. **CAPTCHA**: 자동화된 가입 시도 차단
3. **이메일 인증**: 유효한 이메일 주소 확인
4. **관리자 승인**: 수동 검토를 통한 품질 관리

## 유지보수

### 정기 점검 항목
1. 이메일 전송 로그 검토
2. 스팸 신고 모니터링
3. DNS 설정 상태 확인
4. SSL 인증서 갱신 상태 확인

### 백업
- `/opt/khankorean/oratio/volumes/postgres/`: 사용자 데이터
- `/opt/khankorean/oratio/.env`: 환경 설정
- `/opt/khankorean/oratio/lemmy.hjson`: Lemmy 설정
