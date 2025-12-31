# Oratio 이메일 시스템 설정 - Resend

**작성일**: 2025-12-31  
**상태**: DNS 레코드 추가 대기 중  
**목적**: 비밀번호 재설정 이메일 발송 기능 구현

---

## 📋 진행 상황 요약

### ✅ 완료된 작업

| 단계 | 상태 | 설명 |
|------|------|------|
| 옵션 비교 분석 | ✅ 완료 | 4가지 옵션 비교 (자체 Postfix, SMTP2GO, Resend, Gmail) |
| 자체 Postfix 시도 | ❌ 중단 | ISP 포트 25 차단으로 진행 불가 |
| SMTP2GO 시도 | ❌ 실패 | 무료 이메일(@proton.me)로 가입 불가 (Error code 6) |
| Resend 도메인 등록 | ✅ 완료 | oratio.space 도메인 추가함 |
| DNS 레코드 추가 | ⏳ 대기 중 | 도메인 구매처에서 추가 필요 |

---

## 🔧 현재 해야 할 일: DNS 레코드 추가

### 도메인 정보
- **도메인**: oratio.space
- **네임서버**: managedns.org (Porkbun 또는 유사 서비스)
- **DNS 관리**: 도메인 구매처에서 관리

### 도메인 구매처 찾기
결제 내역 또는 이메일에서 "oratio.space" 검색하여 확인 필요.

가능한 후보:
- Porkbun: https://porkbun.com/account/domains
- Spaceship: https://www.spaceship.com/
- Namecheap: https://ap.www.namecheap.com/domains/list

---

## 📝 추가해야 할 DNS 레코드 (Resend 요구사항)

### 1. DKIM 레코드 (필수) - Enable Sending
```
타입: TXT
Name/Host: resend._domainkey
Value: (Resend 대시보드에서 복사)
TTL: 3600 또는 기본값
```

### 2. SPF 레코드 (필수) - Enable Sending
```
타입: TXT
Name/Host: @ (또는 빈칸)
Value: v=spf1 include:resend.com ~all
TTL: 3600 또는 기본값
```

### 3. DMARC 레코드 (선택, 권장)
```
타입: TXT
Name/Host: _dmarc
Value: v=DMARC1; p=none;
TTL: 3600 또는 기본값
```

---

## ⏭️ DNS 추가 후 다음 단계

### Step 1: Resend 도메인 인증 확인
1. Resend Dashboard 접속
2. Domains → oratio.space 선택
3. "Verify" 버튼 클릭
4. 모든 레코드 ✅ 표시 확인

### Step 2: API 키 확인/생성
```
Resend Dashboard → API Keys → 기존 키 사용 또는 새로 생성
```

### Step 3: Lemmy 설정 변경
```hjson
// lemmy.hjson
email: {
  smtp_server: "smtp.resend.com"
  smtp_port: 465
  smtp_login: "resend"
  smtp_password: "re_XXXXXXXX"  // API 키
  smtp_from_address: "noreply@oratio.space"
  tls_type: "tls"
}
```

### Step 4: 서비스 재시작 및 테스트
```bash
cd /home/user/Oratio/oratio
docker-compose down
docker-compose up -d
docker-compose logs -f lemmy | grep -i email
```

### Step 5: 비밀번호 재설정 테스트
1. 웹에서 로그아웃
2. "비밀번호 찾기" 클릭
3. 이메일 입력
4. 이메일 수신 확인 (inbox + spam)

---

## 📊 옵션 비교 (참고용)

| 옵션 | 개인정보 노출 | 가입 조건 | 결과 |
|------|-------------|----------|------|
| 자체 Postfix | 없음 | 포트 25 필요 | ❌ ISP 차단 |
| SMTP2GO | 최소 | 자체 도메인 이메일 필요 | ❌ 가입 불가 |
| **Resend** | 보통 | 무료 이메일 OK | ✅ 진행 중 |
| Gmail SMTP | 높음 | Google 계정 + 2FA | 미시도 |

---

## 🔗 관련 문서
- [기존 이메일 시스템 문서](./SELF_HOSTED_EMAIL_SYSTEM.md)
- [SSL 설정](../SSL_LETSENCRYPT_SETUP.md)

---

## 📌 메모

### 왜 다른 옵션 안 되나?
- **자체 Postfix**: ISP(hostedonsporestack)가 포트 25 차단 - 스팸 방지 정책
- **SMTP2GO**: 비즈니스 서비스라 @proton.me 같은 무료 이메일로 가입 차단

### Resend 장점
- 무료 이메일로 가입 가능
- 무료 티어: 3,000 emails/month
- 신용카드 불필요
- 간단한 API/SMTP 설정
