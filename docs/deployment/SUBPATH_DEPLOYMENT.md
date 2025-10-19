# Subpath Deployment Guide

## 📋 개요
이 문서는 BCH 결제 서비스를 서브도메인 대신 **서브 경로**로 배포하는 방법을 설명합니다.

**변경 이유**: `payments.oratio.space` DNS 레코드 없이도 서비스 가능하도록 `oratio.space/payments/`로 변경

## 🔄 변경 사항 요약

### **URL 구조 변경**
```
이전: https://payments.oratio.space/
현재: https://oratio.space/payments/
```

### **주요 엔드포인트**
- 메인 페이지: `https://oratio.space/payments/`
- 인보이스 생성: `https://oratio.space/payments/generate_invoice?amount=0.0001&user_id=36`
- 인보이스 확인: `https://oratio.space/payments/invoice/{invoice_id}`
- 결제 상태 확인: `https://oratio.space/payments/check_payment/{invoice_id}`
- 결제 성공 페이지: `https://oratio.space/payments/payment_success/{invoice_id}`
- 사용자 크레딧 API: `https://oratio.space/payments/api/user_credit/{username}`

## 🔧 수정된 파일들

### 1. **nginx 설정** (`nginx_production.conf`)

```nginx
# BCH Payment Service - 서브경로로 서비스
location /payments/ {
    proxy_pass http://bitcoincash-service:8081/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Flask 리다이렉트 경로 수정 (/ -> /payments/)
    proxy_redirect / /payments/;
    proxy_redirect http://$host/ http://$host/payments/;
    proxy_redirect https://$host/ https://$host/payments/;
    
    # 레이트 리미팅
    limit_req zone=payments burst=10 nodelay;
    limit_req_status 429;
}
```

**핵심 포인트**:
- `proxy_pass`의 마지막 `/`가 중요 - 경로를 제거하고 전달
- `proxy_redirect`로 Flask의 리다이렉트 응답 수정

### 2. **환경변수** (`.env`, `refresh_passwords.sh`)

```bash
# BCH 결제 서비스 URL - 서브경로로 서비스
LEMMY_BCH_API_URL=https://oratio.space/payments/api/user_credit
LEMMY_BCH_PAYMENT_URL=https://oratio.space/payments/
```

### 3. **Frontend 기본값** 

**파일들**:
- `lemmy-ui-custom/src/server/utils/create-ssr-html.tsx`
- `lemmy-ui-custom/src/shared/components/app/navbar.tsx`
- `lemmy-ui-custom/src/shared/components/common/ad-banner.tsx`

```typescript
// 기본값은 실제 운영 도메인의 서브경로로 설정
const BCH_PAYMENT_URL = "https://oratio.space/payments/";
const BCH_API_URL = "https://oratio.space/payments/api/user_credit";
```

### 4. **HTML 템플릿 경로 수정**

**수정된 템플릿들**:
- `index.html`: form action을 상대 경로로 변경
- `invoice.html`: JavaScript에서 올바른 API 경로 계산
- `invoice_new.html`: JavaScript에서 올바른 API 경로 계산

**주요 변경**:
```html
<!-- 이전 -->
<form action="/generate_invoice" method="get">

<!-- 현재 -->
<form action="generate_invoice" method="get">
```

```javascript
// 이전
const response = await fetch(`/check_payment/${invoiceId}`);

// 현재 - 동적 경로 계산
const currentPath = window.location.pathname; // /payments/invoice/xxx
const basePath = currentPath.substring(0, currentPath.lastIndexOf('/'));
const checkUrl = basePath.replace('/invoice', '/check_payment') + '/' + invoiceId;
const response = await fetch(checkUrl);
```

### 5. **백그라운드 모니터링 개선**

**파일**: `bitcoincash_service/services/background_tasks.py`

```python
# 30초마다 실행 (실시간 결제 확인을 위해)
time.sleep(30)
```

**변경 이유**: 5분 → 30초로 단축하여 실시간 결제 확인 가능

### 6. **gunicorn 환경에서 백그라운드 태스크 시작**

**파일**: `bitcoincash_service/app.py`

```python
# 백그라운드 태스크 시작 (gunicorn 워커에서도 실행되도록)
import os
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' or os.environ.get('FLASK_ENV') != 'development':
    start_background_tasks()
```

**변경 이유**: gunicorn을 사용할 때 `if __name__ == "__main__"` 블록이 실행되지 않아 백그라운드 태스크가 시작되지 않던 문제 해결

## 🧪 테스트 방법

### 1. **로컬 컴퓨터에서 테스트**

```bash
# /etc/hosts에 추가 (이미 완료)
127.0.0.1 oratio.space

# 브라우저에서 접속
https://oratio.space/payments/
```

### 2. **외부 (휴대폰)에서 테스트**

```bash
# 휴대폰 브라우저에서 접속
https://oratio.space/payments/

# 결제 테스트
1. Generate Invoice 클릭
2. BCH 주소로 송금
3. Check Payment 버튼 클릭 또는 자동 확인 대기 (30초마다)
4. 완료 시 payment_success 페이지로 자동 이동
```

### 3. **API 테스트**

```bash
# 사용자 크레딧 조회
curl -s "https://oratio.space/payments/api/user_credit/gookjob" \
  -H "X-API-Key: YOUR_API_KEY"

# 결과
{"credit_balance": 0.0003, "username": "gookjob"}
```

## ⚠️ 주의사항

### **proxy_pass 마지막 슬래시의 중요성**

```nginx
# ✅ 올바름 - 경로를 제거하고 전달
location /payments/ {
    proxy_pass http://backend:8081/;
}
# 요청: /payments/invoice/123 → 백엔드: /invoice/123

# ❌ 잘못됨 - 경로를 유지
location /payments/ {
    proxy_pass http://backend:8081;
}
# 요청: /payments/invoice/123 → 백엔드: /payments/invoice/123
```

### **상대 경로 vs 절대 경로**

HTML/JavaScript에서:
- ✅ 상대 경로: `generate_invoice` (현재 위치 기준)
- ✅ 동적 경로: JavaScript로 현재 경로 파싱
- ❌ 절대 경로: `/generate_invoice` (서브패스 무시됨)

### **리다이렉트 처리**

Flask가 `redirect(url_for(...))`를 사용할 때 절대 경로를 반환하므로 nginx의 `proxy_redirect`로 수정 필요

## 🔄 배포 절차

### **전체 재배포**

```bash
cd /home/user/Oratio/oratio

# 1. 환경변수 재생성 (이미 완료)
bash refresh_passwords.sh

# 2. 서비스 재시작
docker-compose restart proxy
docker-compose restart bitcoincash-service
docker-compose restart lemmy-ui
```

### **부분 업데이트**

```bash
# nginx만 재시작 (설정 변경 시)
docker-compose restart proxy

# BCH 서비스만 재시작 (Python 코드 변경 시)
docker-compose restart bitcoincash-service

# lemmy-ui 재빌드 (TypeScript 코드 변경 시)
docker-compose stop lemmy-ui
docker-compose rm -f lemmy-ui
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui
```

## 📊 성능 개선

### **백그라운드 모니터링**
- 이전: 5분마다 체크
- 현재: 30초마다 체크
- 결과: 실시간 결제 확인 가능

### **자동 리다이렉트**
- 결제 완료 시 2초 후 자동으로 payment_success 페이지 이동
- 사용자 경험 개선

## 🐛 트러블슈팅

### **문제: Check Payment 버튼 클릭 시 "Check Failed"**

**원인**: JavaScript에서 잘못된 경로로 API 호출

**해결**: 
```javascript
// 동적 경로 계산으로 수정 완료
const currentPath = window.location.pathname;
const basePath = currentPath.substring(0, currentPath.lastIndexOf('/'));
const checkUrl = basePath.replace('/invoice', '/check_payment') + '/' + invoiceId;
```

### **문제: 결제 완료 후 페이지 이동 안 됨**

**원인**: 상대 경로 `payment_success/${invoiceId}` 사용

**해결**:
```javascript
// ../payment_success/${invoiceId}로 변경
window.location.href = `../payment_success/${invoiceId}`;
```

### **문제: 백그라운드 모니터링 작동 안 함**

**원인**: gunicorn 환경에서 백그라운드 태스크 미시작

**해결**: app.py에서 모듈 로드 시점에 `start_background_tasks()` 호출

## 📝 관련 문서

- [Environment Variables Flow](./environment-variables-flow.md)
- [BCH Payment System](../features/bch-payment-system.md)
- [SSL Setup Guide](../SSL_LETSENCRYPT_SETUP.md)

---

**작성일**: 2025-10-06  
**버전**: 1.0  
**마지막 업데이트**: 2025-10-06
