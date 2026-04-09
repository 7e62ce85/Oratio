# Oratio 이메일 시스템 - Resend

**최종 업데이트**: 2026-04-09  
**상태**: SMTP 프록시 동작 ✅ / Resend 도메인 인증 대기 ⏳  

---

## 현재 아키텍처

```
Lemmy (lettre SMTP) → email-service:1025 (aiosmtpd) → Resend API → 사용자 이메일
```

| 구성 요소 | 역할 | 상태 |
|-----------|------|------|
| `lemmy.hjson` `email.smtp_server` | `email-service:1025`, `tls_type: "none"` | ✅ |
| `email-service` 컨테이너 | aiosmtpd SMTP → Resend API 프록시 | ✅ 동작 |
| Resend API | 실제 이메일 발송 | ❌ 도메인 미인증 (403) |

---

## TODO: Resend 도메인 인증

### 1. 도메인 DNS 관리 페이지 접속
- **도메인**: `oratio.space`
- **네임서버**: managedns.org (Porkbun 등)
- 구매처 후보: Porkbun / Spaceship / Namecheap

### 2. DNS 레코드 3개 추가

| # | 타입 | Host | Value | 비고 |
|---|------|------|-------|------|
| 1 | TXT | `resend._domainkey` | *(Resend 대시보드에서 복사)* | DKIM (필수) |
| 2 | TXT | `@` | `v=spf1 include:resend.com ~all` | SPF (필수) |
| 3 | TXT | `_dmarc` | `v=DMARC1; p=none;` | DMARC (권장) |

> Resend 대시보드: https://resend.com/domains → oratio.space → 정확한 값 확인

### 3. 인증 확인
```
Resend Dashboard → Domains → oratio.space → Verify → 모든 레코드 ✅
```

### 4. 테스트
```bash
# settings에서 이메일 변경 → 인증 메일 수신 확인
# 비밀번호 재설정 → 이메일 수신 확인
# 로그 확인
docker-compose logs --tail=20 email-service
```

---

## 관련 파일

```
oratio/
├── lemmy.hjson              # email.smtp_server = "email-service:1025"
├── docker-compose.yml       # email-service 정의
├── .env                     # RESEND_API_KEY, SMTP_FROM_ADDRESS
└── email-service/
    ├── app.py               # aiosmtpd + Flask (Resend API 프록시)
    ├── Dockerfile
    └── requirements.txt
```

---

## 참고

- Resend 무료: 3,000 emails/month, 신용카드 불필요
- ISP 포트 25 차단 → 자체 Postfix 불가 → Resend 선택
- SMTP2GO도 무료 이메일 가입 불가로 탈락
