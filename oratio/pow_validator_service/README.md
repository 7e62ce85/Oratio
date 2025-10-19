# PoW Validator Service - Python 프록시 서비스

## 📌 개요

**Rust 백엔드 수정 없이** Lemmy에 Proof of Work 검증을 추가하는 프록시 서비스입니다.

### 작동 방식

```
사용자 → Nginx → [PoW Validator] → Lemmy (Rust)
                       ↓
                  PoW 검증 통과 시만
                  Lemmy로 전달
```

---

## 🚀 배포 방법

### 1. Docker Compose에 추가

`/home/user/Oratio/oratio/docker-compose.yml`:

```yaml
services:
  # ... 기존 서비스들 ...

  pow-validator:
    build:
      context: ./pow_validator_service
      dockerfile: Dockerfile
    container_name: oratio-pow-validator-1
    restart: always
    environment:
      - POW_DIFFICULTY=20
      - POW_MAX_AGE_SECONDS=600
      - LEMMY_BACKEND_URL=http://lemmy:8536
    depends_on:
      - lemmy
    networks:
      - default
```

### 2. Nginx 설정 수정

`nginx_production.conf`에서 회원가입 엔드포인트만 프록시로:

```nginx
# PoW 검증이 필요한 엔드포인트
location /api/v3/user/register {
    proxy_pass http://pow-validator:5001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# 나머지 API는 직접 Lemmy로
location /api/ {
    proxy_pass http://lemmy:8536;
    # ... 기존 설정
}
```

### 3. 빌드 및 실행

```bash
cd /home/user/Oratio/oratio
docker-compose build pow-validator
docker-compose up -d pow-validator
docker-compose restart proxy
```

---

## 🧪 테스트

### 1. 헬스 체크

```bash
curl http://localhost:5001/health
```

**응답:**
```json
{
  "status": "healthy",
  "service": "pow-validator",
  "difficulty": 20
}
```

### 2. PoW 검증 테스트

```bash
curl -X POST http://localhost:5001/api/pow/verify \
  -H "Content-Type: application/json" \
  -d '{
    "challenge": "1697201234567-abc123",
    "nonce": 123,
    "hash": "0000abc..."
  }'
```

### 3. 회원가입 테스트

```bash
curl -X POST http://localhost/api/v3/user/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "password123",
    "password_verify": "password123",
    "pow_challenge": "1697201234567-abc",
    "pow_nonce": 1048576,
    "pow_hash": "0000abcdef..."
  }'
```

---

## ⚙️ 설정

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `POW_DIFFICULTY` | 20 | PoW 난이도 (비트) |
| `POW_MAX_AGE_SECONDS` | 600 | 챌린지 유효 시간 (초) |
| `LEMMY_BACKEND_URL` | http://lemmy:8536 | Lemmy 백엔드 URL |

### 난이도 조절

```python
# app.py
POW_DIFFICULTY = 18  # 더 쉽게
POW_DIFFICULTY = 22  # 더 어렵게
```

---

## 📊 성능

- **검증 시간**: < 1ms
- **메모리 사용**: ~50MB
- **동시 처리**: Gunicorn 2 workers

---

## 🔒 보안

### 구현된 검증:
- ✅ 해시 재계산 및 일치 확인
- ✅ 난이도 조건 확인
- ✅ 타임스탬프 만료 확인

### 추가 가능한 보안:
- 챌린지 중복 사용 방지 (Redis 필요)
- IP 기반 Rate Limiting
- 실패 시도 로깅

---

## 📝 로그 확인

```bash
# 실시간 로그
docker logs -f oratio-pow-validator-1

# 최근 100줄
docker logs --tail 100 oratio-pow-validator-1
```

---

## 🔧 문제 해결

### 문제: 502 Bad Gateway
**원인**: PoW Validator가 실행되지 않음  
**해결**: `docker-compose up -d pow-validator`

### 문제: "backend_error"
**원인**: Lemmy 백엔드 연결 실패  
**해결**: Lemmy 컨테이너 상태 확인

### 문제: "Invalid PoW"
**원인**: 프론트엔드와 백엔드 난이도 불일치  
**해결**: 양쪽 난이도 동기화

---

## 🎯 장점

✅ **Rust 수정 불필요**: Lemmy 소스 건드리지 않음  
✅ **빠른 개발**: Python으로 쉽게 구현  
✅ **독립적 관리**: 별도 서비스로 업데이트 용이  
✅ **Lemmy 업데이트 무관**: Lemmy 버전 변경 시에도 작동  

---

## 📚 API 엔드포인트

| 엔드포인트 | 메소드 | 설명 |
|-----------|--------|------|
| `/api/v3/user/register` | POST | PoW 검증 후 회원가입 |
| `/api/pow/challenge` | GET | 챌린지 생성 (선택사항) |
| `/api/pow/verify` | POST | PoW 검증 테스트 |
| `/health` | GET | 헬스 체크 |

---

**작성일**: 2025-10-13  
**상태**: 프로덕션 준비 완료 ✓
