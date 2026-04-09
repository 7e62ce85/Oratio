# 504 Gateway Timeout — Gunicorn Worker Crash Loop 해결

## 📋 문제 개요
- **발생일**: 2026-03-31
- **영향 범위**: oratio.space 전체 (모든 `/payments/api/*` 엔드포인트)
- **심각도**: Critical (사이트 접속 불가)

## 🔍 증상

### 주요 증상
- oratio.space 접속 시 **504 Gateway Time-out**
- nginx 프록시 로그에 `upstream timed out (110: Connection timed out)` 반복
- lemmy-ui에서 `UND_ERR_HEADERS_TIMEOUT` (300초 타임아웃 후 실패)

### 로그 패턴
```
# nginx (proxy)
upstream timed out (110: Connection timed out) while reading response header from upstream,
upstream: "http://172.18.0.4:8081/api/user_credit/..."

# bitcoincash-service (gunicorn)
[CRITICAL] WORKER TIMEOUT (pid:XX)
Worker exiting → Booting worker → ElectronCash 연결 실패 → WORKER TIMEOUT → 반복

# electron-cash
⚠️ ElectronCash 데몬 문제 감지 (연속 실패: 2/3)
```

## 🔬 근본 원인 (Root Cause Analysis)

### Cascading Failure Chain

```
electron-cash 데몬 hang (09:22~)
    → bitcoincash-service: ElectronCash RPC timeout (10s × 2 retries = 20s)
        → gunicorn worker: init_electron_cash()가 모듈 로드 시점에 블로킹 실행
            → 30s 초과 → gunicorn master가 SIGKILL로 worker 종료
                → 새 worker spawn → 다시 init_electron_cash() → 다시 timeout → 무한루프
                    → 살아있는 worker 0개 → 모든 HTTP 요청 응답 불가
                        → nginx: upstream timeout → 504
```

핵심: **gunicorn worker의 부팅 경로(module import time)에 blocking I/O가 있었음.**

Python에서 `import services.electron_cash` 시 모듈 최하단의 `init_electron_cash()`와 `debug_electron_cash_connection()`이 **모듈 로드 시점에 동기 실행**됨. ElectronCash 데몬이 응답하지 않으면 이 초기화가 20~30초 블로킹 → gunicorn의 `--timeout 30` 초과 → worker kill.

### 부수 에러 3건

| 에러 | 원인 |
|------|------|
| `database is locked` | SQLite WAL 모드/busy_timeout이 일부 연결에만 적용됨 |
| `name 'FORWARD_PAYMENTS' is not defined` | `electron_cash.py`에서 `config` 임포트 누락 |
| `Migration file not found: upload_quota_system.sql` | 도커 볼륨 미마운트 + SQL에 PostgreSQL 전용 구문 |

## 🛠️ 수정 사항

### 1. Worker Crash Loop 방지 — 초기화 비동기화

**파일**: `services/electron_cash.py`

모듈 최하단의 `init_electron_cash()` + `debug_electron_cash_connection()`을 **daemon thread**로 이동.
Worker 부팅 경로에서 blocking I/O를 제거하여, ElectronCash가 죽어도 gunicorn worker는 정상 기동.

```python
# Before: 모듈 import 시 동기 실행 (blocking)
if EC_AVAILABLE:
    init_electron_cash()       # ← 20~30s blocking 가능
debug_electron_cash_connection(electron_cash)

# After: daemon thread로 비동기 실행
_init_thread = threading.Thread(target=_background_init, daemon=True)
_init_thread.start()  # worker 부팅을 막지 않음
```

### 2. SQLite `database is locked` 해결 — WAL + busy_timeout 통일

**파일**: `models.py`, `services/cp_moderation.py`, `services/upload_quota_service.py`, `middleware/cp_post_blocker.py`

SQLite의 concurrent write는 단일 writer lock을 사용한다. 여러 스레드(백그라운드 태스크 + HTTP 핸들러)가 동시에 쓰기할 때:
- **WAL (Write-Ahead Logging)** 모드: reader가 writer를 블로킹하지 않음
- **busy_timeout**: lock 획득 실패 시 즉시 에러 대신 지정 시간만큼 재시도

```python
# Before: get_db_connection()에 PRAGMA 없음
conn = sqlite3.connect(DB_PATH, timeout=30)

# After: 모든 연결에 WAL + busy_timeout 적용
conn = sqlite3.connect(DB_PATH, timeout=30)
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA busy_timeout = 30000")
```

cp_moderation.py의 `busy_timeout=5000` (5초) → `30000` (30초)로 통일.

### 3. `FORWARD_PAYMENTS` / `MIN_PAYOUT_AMOUNT` 미정의 해결

**파일**: `config.py`, `services/electron_cash.py`

```python
# config.py — MIN_PAYOUT_AMOUNT 추가
MIN_PAYOUT_AMOUNT = float(os.environ.get('MIN_PAYOUT_AMOUNT', '0.001'))

# electron_cash.py — 임포트에 추가
from config import (..., FORWARD_PAYMENTS, MIN_PAYOUT_AMOUNT)
```

### 4. Migration 파일 경로 해결

**파일**: `docker-compose.yml`, `services/upload_quota_service.py`, `migrations/upload_quota_system.sql`

- `docker-compose.yml`에 `./migrations:/migrations:ro` 볼륨 마운트 추가
- `upload_quota_service.py`에서 `/migrations/` 우선 탐색 + 로컬 fallback
- `upload_quota_system.sql`에서 SQLite 비호환 `COMMENT ON TABLE` 구문 제거

## 📊 수정 전/후 비교

```
Before:
  - electron-cash hang → bitcoincash-service worker 무한 crash → 504
  - 15초마다 "database is locked" 에러
  - 15초마다 "FORWARD_PAYMENTS is not defined" 에러
  - 매 worker 부팅마다 "Migration file not found" 경고

After:
  - electron-cash hang → worker 정상 기동, 백그라운드에서 재연결 시도
  - SQLite lock contention 해소 (WAL + 30s busy_timeout)
  - 모든 config 변수 정상 임포트
  - Migration SQL 정상 실행
  - API 응답: 0.001s, 사이트 응답: 0.02s
```

## 🔑 교훈

1. **모듈 로드 시점에 네트워크 I/O 금지** — Python의 `import` 경로에 blocking call을 넣으면, 해당 모듈을 임포트하는 모든 프로세스(gunicorn worker 등)가 영향받는다. 초기화는 lazy 또는 background thread로.
2. **SQLite multi-thread 접근 시 WAL 필수** — 기본 journal mode(DELETE)는 reader와 writer가 상호 배제. WAL 모드는 reader-writer 동시성을 허용.
3. **gunicorn worker timeout < 외부 서비스 timeout일 때 crash loop** — 외부 서비스 호출 timeout(20s)이 gunicorn worker timeout(30s)에 근접하면 위험. 부팅 경로에서는 아예 제거하거나 timeout을 짧게.

## 🔧 복구 명령어 (참고용)

```bash
# 1. electron-cash 먼저 재시작
docker restart electron-cash && sleep 30

# 2. bitcoincash-service 재시작
docker restart bitcoincash-service && sleep 15

# 3. 확인
docker logs --tail 20 bitcoincash-service 2>&1 | grep -E "ERROR|CRITICAL|✅"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8081/api/cp/reported-content-ids
curl -sk -o /dev/null -w "HTTP %{http_code}\n" https://localhost/
```
