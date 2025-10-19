# 2025-10-06 변경사항

## 주요 변경 내역

### 1. BCH 결제 서비스 서브경로 배포
- **변경**: `payments.oratio.space` → `oratio.space/payments/`
- **이유**: DNS 레코드 없이 서비스 가능
- **영향**: 모든 BCH 관련 URL 변경

### 2. 백그라운드 결제 모니터링 개선
- **변경**: 5분 주기 → 30초 주기
- **이유**: 실시간 결제 확인 필요
- **파일**: `bitcoincash_service/services/background_tasks.py`

### 3. gunicorn 환경에서 백그라운드 태스크 자동 시작
- **문제**: gunicorn 사용 시 백그라운드 태스크 미시작
- **해결**: app.py 모듈 로드 시점에 `start_background_tasks()` 호출
- **파일**: `bitcoincash_service/app.py`

### 4. 템플릿 경로 수정
- **문제**: 서브경로 환경에서 상대/절대 경로 오류
- **해결**: JavaScript에서 동적 경로 계산
- **파일**: 
  - `templates/index.html`
  - `templates/invoice.html`
  - `templates/invoice_new.html`

### 5. nginx 프록시 설정
- `proxy_redirect` 추가로 Flask 리다이렉트 경로 수정
- `/payments/` location 블록 추가

## 수정된 파일 목록

### Backend (BCH Service)
```
oratio/bitcoincash_service/
├── app.py                          # 백그라운드 태스크 시작 로직 추가
├── services/
│   └── background_tasks.py         # 모니터링 주기 30초로 변경
└── templates/
    ├── index.html                  # form action 상대 경로로 변경
    ├── invoice.html                # JavaScript 경로 계산 로직 추가
    └── invoice_new.html            # JavaScript 경로 계산 로직 추가
```

### Frontend (Lemmy UI)
```
lemmy-ui-custom/src/
├── server/utils/
│   └── create-ssr-html.tsx         # BCH URL 기본값 변경
└── shared/components/
    ├── app/navbar.tsx              # BCH URL 기본값 변경
    └── common/ad-banner.tsx        # BCH URL 기본값 변경
```

### Infrastructure
```
oratio/
├── nginx_production.conf           # /payments/ location 블록 추가
├── refresh_passwords.sh            # BCH URL 기본값 변경
├── .env                            # refresh_passwords.sh로 재생성됨
└── docs/
    └── deployment/
        └── SUBPATH_DEPLOYMENT.md   # 새 문서 추가
```

## 테스트 결과

### ✅ 작동 확인
- [x] 로컬에서 `oratio.space` 접속 (/etc/hosts 설정)
- [x] 외부에서 `oratio.space` 접속
- [x] BCH 결제 페이지 접근 (`/payments/`)
- [x] 인보이스 생성 및 QR 코드 표시
- [x] 결제 상태 API 호출 (`/payments/api/user_credit/username`)
- [x] 백그라운드 모니터링 작동 (30초 주기)
- [x] nginx 프록시 리다이렉트 처리

### 🔧 개선 필요
- [ ] 실제 BCH 송금 후 자동 확인 테스트 (Electron Cash 연동)
- [ ] payment_success 페이지로 자동 리다이렉트 테스트
- [ ] 크레딧 추가 로직 검증

## 배포 명령어

```bash
cd /home/user/Oratio/oratio

# 1. 환경변수 재생성
bash refresh_passwords.sh

# 2. 서비스 재시작
docker-compose restart proxy
docker-compose restart bitcoincash-service

# 3. lemmy-ui 재빌드
docker-compose stop lemmy-ui
docker-compose rm -f lemmy-ui
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui
```

## 다음 단계

1. **Electron Cash 안정성 개선**
   - 지갑 로드 실패 시 자동 재시도 로직
   - 데몬 연결 모니터링 강화

2. **결제 확인 프로세스 최적화**
   - WebSocket을 통한 실시간 알림 고려
   - 백그라운드 체크 주기 동적 조정

3. **에러 처리 개선**
   - 사용자 친화적인 에러 메시지
   - 결제 실패 시 복구 옵션 제공

4. **모니터링 및 로깅**
   - 결제 성공/실패율 추적
   - 평균 결제 확인 시간 측정

## 관련 이슈

- DNS 레코드 없이 서브경로로 서비스 가능해짐
- gunicorn 환경에서 백그라운드 태스크 정상 작동
- 실시간 결제 확인 가능 (30초 주기)

---

**작성자**: GitHub Copilot  
**날짜**: 2025-10-06  
**문서**: [SUBPATH_DEPLOYMENT.md](./SUBPATH_DEPLOYMENT.md)
