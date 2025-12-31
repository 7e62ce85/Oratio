# Oratio Postfix 자체 SMTP 서버 DNS 설정 가이드

## 서버 정보
- **서버 IP**: 70.34.244.93
- **도메인**: oratio.space
- **호스트명**: mail.oratio.space

## 필수 DNS 레코드

### 1. MX 레코드 (Mail Exchanger)
```
타입: MX
호스트: @
값: mail.oratio.space
우선순위: 10
TTL: 3600
```

### 2. A 레코드 (메일 서버)
```
타입: A
호스트: mail
값: 70.34.244.93
TTL: 3600
```

### 3. SPF 레코드 (발신자 인증)
```
타입: TXT
호스트: @
값: v=spf1 ip4:70.34.244.93 a:mail.oratio.space -all
TTL: 3600
```

**설명:**
- `v=spf1`: SPF 버전
- `ip4:70.34.244.93`: 이 IP에서 보낸 이메일 허용
- `a:mail.oratio.space`: 이 호스트에서 보낸 이메일 허용
- `-all`: 나머지는 모두 거부 (엄격)

### 4. DKIM 레코드 (이메일 서명)

**먼저 DKIM 키 생성 (나중에 설정 단계에서):**
```bash
docker exec -it postfix opendkim-genkey -t -s mail -d oratio.space
```

생성 후 다음 레코드 추가:
```
타입: TXT
호스트: mail._domainkey
값: (생성된 공개키 - 나중에 추가)
TTL: 3600
```

### 5. DMARC 레코드 (정책 설정)
```
타입: TXT
호스트: _dmarc
값: v=DMARC1; p=quarantine; rua=mailto:admin@oratio.space; ruf=mailto:admin@oratio.space; fo=1
TTL: 3600
```

**설명:**
- `p=quarantine`: 실패한 이메일을 스팸 폴더로 (처음엔 이게 안전)
- `rua`: 집계 보고서 받을 이메일
- `ruf`: 포렌식 보고서 받을 이메일
- `fo=1`: 실패 시 보고서 생성

### 6. PTR 레코드 (역방향 DNS) - 매우 중요!

**ISP에 요청해야 합니다:**
```
IP: 70.34.244.93
PTR: mail.oratio.space
```

**PTR 없으면 Gmail/Outlook이 스팸으로 분류합니다!**

---

## DNS 설정 순서

### 1단계: 기본 레코드부터
```
1. A 레코드 (mail.oratio.space)
2. MX 레코드
3. SPF 레코드
```

### 2단계: 보안 레코드
```
4. DKIM 레코드 (키 생성 후)
5. DMARC 레코드
```

### 3단계: ISP 요청
```
6. PTR 레코드 (ISP 고객센터에 요청)
```

---

## DNS 전파 확인

### 명령어로 확인:
```bash
# MX 레코드
dig MX oratio.space

# A 레코드
dig A mail.oratio.space

# SPF 레코드
dig TXT oratio.space | grep spf

# DMARC 레코드
dig TXT _dmarc.oratio.space

# PTR 레코드 (역방향)
dig -x 70.34.244.93
```

### 온라인 도구:
- https://mxtoolbox.com/SuperTool.aspx
- https://www.dmarcanalyzer.com/spf/checker/
- https://dkimvalidator.com/

---

## 예상 시간

- DNS 레코드 추가: **10분**
- DNS 전파 대기: **10분 ~ 2시간**
- PTR 레코드 (ISP 요청): **1~3일**

---

## 주의사항

⚠️ **PTR 레코드가 없으면:**
- Gmail → 90% 스팸 폴더
- Outlook → 거의 100% 차단
- 반드시 ISP에 요청해야 함!

⚠️ **DKIM 없으면:**
- 이메일 위조 가능성으로 분류
- 전달률 50% 이하

✅ **모두 설정하면:**
- 전달률 95% 이상
- 스팸 분류 거의 없음
