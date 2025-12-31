# PostgreSQL Password Sync Issue - 기술 분석

**작성일**: 2025-12-02  
**상태**: ✅ 해결됨

---

## 📋 문제 요약

**증상**: `bitcoincash-service`에서 PostgreSQL 연결 시 인증 실패
```
FATAL: password authentication failed for user "lemmy"
```

**원인**: `.env`의 `POSTGRES_PASSWORD`와 실제 PostgreSQL이 사용하는 `lemmy.hjson`의 password가 다름

---

## 🔍 근본 원인 분석

### 1. 비밀번호 저장 위치가 2곳

| 위치 | 용도 | 값 (예시) |
|------|------|-----------|
| `.env` → `POSTGRES_PASSWORD` | Docker 환경변수 전달 | `eR3mukLzmRBdrp1E8qUHSXWZvq6PEh8L` |
| `lemmy.hjson` → `database.password` | Lemmy 실제 DB 연결 | `FRfwa2qk6LHSbmR+O1XBb475IDVcpMZ3` |

### 2. PostgreSQL 초기화 특성

```
PostgreSQL 컨테이너 최초 시작
       ↓
POSTGRES_PASSWORD 환경변수로 초기 비밀번호 설정
       ↓
데이터 볼륨에 저장 (./volumes/postgres)
       ↓
이후 POSTGRES_PASSWORD 변경해도 → 기존 DB 비밀번호 유지
```

**핵심**: PostgreSQL은 **최초 초기화 시점**에만 `POSTGRES_PASSWORD` 환경변수를 사용. 이후 변경은 무시됨.

### 3. refresh_passwords.sh의 한계

```bash
# refresh_passwords.sh가 하는 일:
NEW_POSTGRES_PASSWORD=$(generate_password 32)
# → .env 파일에 새 비밀번호 저장

# refresh_passwords.sh가 안 하는 일:
# - lemmy.hjson 업데이트 ❌
# - PostgreSQL ALTER USER 실행 ❌
```

---

## 🛠️ 해결 방법

### 방법 1: 설정 파일에서 직접 비밀번호 읽기 (적용됨) ✅

```python
# cp_post_blocker.py
def get_lemmy_db_password():
    """lemmy.hjson에서 직접 비밀번호 읽기"""
    hjson_paths = [
        '/config/config.hjson',  # Docker mount
    ]
    
    for path in hjson_paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read()
                # regex로 password 추출
                match = re.search(r'password:\s*"([^"]+)"', content)
                if match:
                    return match.group(1)
    
    # fallback
    return os.environ.get('POSTGRES_PASSWORD', '')
```

**docker-compose.yml 수정**:
```yaml
bitcoincash-service:
  volumes:
    - ./lemmy.hjson:/config/config.hjson:ro  # 추가
```

### 방법 2: 단일 소스로 통합 (권장, 미적용)

```bash
# refresh_passwords.sh 수정안
NEW_POSTGRES_PASSWORD=$(generate_password 32)

# 1. .env 업데이트
sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$NEW_POSTGRES_PASSWORD/" .env

# 2. lemmy.hjson 업데이트
sed -i "s/password: \".*\"/password: \"$NEW_POSTGRES_PASSWORD\"/" lemmy.hjson

# 3. PostgreSQL 비밀번호 변경
docker-compose exec -T postgres psql -U lemmy -d lemmy -c \
    "ALTER USER lemmy WITH PASSWORD '$NEW_POSTGRES_PASSWORD';"
```

---

## 📐 프로그래밍 관점 분석

### Single Source of Truth 원칙 위반

```
        ┌─────────────────┐
        │   .env 파일      │ ← refresh_passwords.sh가 생성
        │ POSTGRES_PASSWORD│
        └────────┬────────┘
                 │ (동기화 안 됨)
                 ▼
        ┌─────────────────┐
        │  lemmy.hjson    │ ← Lemmy가 실제 사용
        │ database.password│
        └────────┬────────┘
                 │
                 ▼
        ┌─────────────────┐
        │   PostgreSQL    │ ← 최초 초기화 시 고정
        │  실제 비밀번호   │
        └─────────────────┘
```

**문제**: 3곳에 비밀번호가 저장되고, 동기화 메커니즘 없음

### Configuration Management Anti-Pattern

| Anti-Pattern | 설명 | 이 케이스 |
|--------------|------|-----------|
| **Scattered Config** | 설정이 여러 파일에 분산 | `.env`, `lemmy.hjson`, PostgreSQL 내부 |
| **Init-time vs Runtime** | 초기화 시점 설정이 런타임에 변경 불가 | PostgreSQL POSTGRES_PASSWORD |
| **Implicit Dependencies** | 명시적이지 않은 의존성 | bitcoincash-service → lemmy.hjson |

### 해결 패턴

#### 1. Configuration Injection Pattern
```python
# Bad: 환경변수에 의존
password = os.environ.get('POSTGRES_PASSWORD')

# Good: 설정 파일을 직접 읽음 (Single Source)
password = read_config_file('/config/config.hjson')['database']['password']
```

#### 2. Secret Management Pattern
```yaml
# docker-compose.yml - Docker Secrets 사용 (Best Practice)
secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt

services:
  postgres:
    secrets:
      - postgres_password
    environment:
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
```

---

## ✅ 적용된 수정사항

### 1. cp_post_blocker.py
- `get_lemmy_db_password()` 함수 추가
- `lemmy.hjson`에서 직접 비밀번호 읽기
- 환경변수는 fallback으로만 사용

### 2. docker-compose.yml
```yaml
bitcoincash-service:
  volumes:
    - ./lemmy.hjson:/config/config.hjson:ro  # 읽기 전용 마운트
```

### 3. 결과
- Lemmy가 사용하는 것과 동일한 비밀번호 사용 보장
- `refresh_passwords.sh` 실행과 무관하게 동작
- Single Source of Truth: `lemmy.hjson`

---

## 📝 향후 개선 권장사항

1. **refresh_passwords.sh 개선**: `lemmy.hjson`도 자동 업데이트
2. **Docker Secrets 도입**: 비밀번호를 파일로 관리
3. **환경변수 통합**: `lemmy.hjson`을 환경변수 템플릿으로 생성

---

## 🔗 관련 파일

- `/home/user/Oratio/oratio/bitcoincash_service/middleware/cp_post_blocker.py`
- `/home/user/Oratio/oratio/docker-compose.yml`
- `/home/user/Oratio/oratio/lemmy.hjson`
- `/home/user/Oratio/oratio/refresh_passwords.sh`
- `/home/user/Oratio/oratio/.env`
