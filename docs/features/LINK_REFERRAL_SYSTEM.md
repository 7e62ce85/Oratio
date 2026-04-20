# 🔗 Link Referral System

> **Version**: v1.0 | **Status**: ✅ Phase C+ Complete (3-Strike · Replace · UI) | **Priority**: Phase D (Dashboard)

---

## 🎯 한줄 요약

외부 사이트에 Oratio 백링크를 게시한 사용자에게 단계적 보상(뱃지 → 1년 무료 멤버십)을 제공하는 시스템.

---

## 📜 운영 정책 (Core Rules)

### 1. 보상 기준

| 규칙 | 값 | 비고 |
|------|----|------|
| 사용자당 보상 횟수 | **1회** | 멤버십 만료 후 재제출 가능 |
| 도메인당 보상 횟수 | **1회** | 멤버십 만료 후 재제출 가능 |
| 최소 도메인 나이 | **6개월** | WHOIS 기반, 신규 도메인 차단 |
| 인정되는 링크 유형 | **dofollow만** | nofollow/ugc/sponsored 링크는 SEO 효과 없으므로 제외 |
| 링크 유지 의무 기간 | **12개월** (보상 기간 전체) | 중간에 삭제 시 보상 취소 |
| 활성 멤버십 보유자 | **제출 불가** | 이미 유료/기존 멤버십이 활성인 사용자는 제출 차단, 만료 후 가능 |

### 2. 보상 단계

> **뱃지는 🔗 하나만 사용.** Phase가 올라가면 뱃지가 바뀌는 게 아니라, 동일 뱃지에 **추가 보상**이 붙는 구조.

| Phase | 동작 | 보상 | 자동/수동 | 상태 |
|-------|------|------|-----------|------|
| A (MVP) | 제출 → admin approve/reject | 🔗 **Referral 뱃지** | 수동 (admin) | ✅ 구현 완료 |
| B | 자동 크롤러가 1차 검증 (admin 부담 경감) | 🔗 뱃지 (동일) | 반자동 | ✅ 구현 완료 |
| C | approve 시 1년 무료 멤버십 자동 부여 | 🔗 뱃지 + 🥇 **Gold 멤버십** | 자동 | ✅ 구현 완료 |

### 3. 차단/거부 조건 (블랙리스트)

아래에 해당하면 **즉시 거부**:

- 악성/피싱/불법 콘텐츠 사이트
- NSFW 사이트 (정책상 제외)
- 무료 블로그 플랫폼의 빈 페이지 (예: `blogspot`, `wordpress.com` 서브도메인에 내용 없는 글)
- URL 단축 서비스 (bit.ly, t.co 등)
- 리다이렉트/iframe으로만 링크를 삽입한 경우
- Oratio 자체 도메인 (`oratio.space`)

### 4. 재검증 & 취소

| 시점 | 행동 |
|------|------|
| 제출 시 | 1차 자동 크롤 검증 (즉시) |
| 승인 후 초반 (0~64일) | **지수 백오프 재검증** — 12h→1d→2d→4d→8d→16d→32d→64d 간격 |
| 매 3개월 (64일 이후~) | 정기 재검증 (링크 존재 여부) |
| 재검증 실패 시 | 14일 유예 → 유예 후에도 미복구 시 멤버십 비활성화 + 뱃지 제거 |
| 사용자 신고 시 | 관리자 즉시 리뷰 |

> **지수 백오프 재검증**: 승인 직후가 악용 위험이 가장 높으므로, 초반에 촘촘하게 검증하고 점점 간격을 넓혀서 90일 정기 재검증에 합류시킨다. 백그라운드 작업(12시간 루프)에서 자동 실행.

### 5. 3-Strike 자동취소 ⭐ (v1.0 — 영구차단 제거됨)

| 규칙 | 값 | 설명 |
|------|----|------|
| **누적 실패 한도** | **3회** (`TOTAL_FAIL_LIMIT`) | 승인 후 누적 재검증 실패 3회 → 유예 없이 **즉시 자동취소** |

**흐름**:
```
검증 실패 1회 → 경고 (fail 1/3)
검증 실패 2회 → 경고 + 14일 유예 시작 (fail 2/3)
검증 실패 3회 → 즉시 자동취소 (3-strike), 유예 무시
         └→ 취소 후 새 링크 재제출 가능 (영구차단 없음)
```

> **누적**이란 연속이 아닌 **총 횟수** 기준. 중간에 검증 성공해도 카운터 리셋되지 않음.
> **v1.0 변경**: 영구차단(`AUTO_REVOKE_BAN_THRESHOLD`) 제거 — 자동취소 후에도 새 링크 제출 허용.

### 6. 링크 교체 (Replace) ⭐ NEW

| 조건 | 설명 |
|------|------|
| 대상 | `approved` + `verified=false` (유예 기간 중) 링크만 |
| 권한 | 원래 제출자 본인만 |
| 동작 | 새 URL로 교체 → 즉시 자동 검증 → 성공 시 `verified=true` |
| 차단 | ~~영구차단 사용자는 교체도 불가~~ (v1.0: 영구차단 제거됨) |

---

## 🗄️ DB 스키마

```sql
-- 제출된 링크 목록
CREATE TABLE IF NOT EXISTS referral_links (
    id TEXT PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    normalized_url TEXT UNIQUE,
    domain TEXT NOT NULL,
    submitted_by TEXT NOT NULL,          -- username
    status TEXT DEFAULT 'pending',       -- pending | approved | rejected
    reject_reason TEXT,
    verified BOOLEAN DEFAULT FALSE,
    last_verified_at INTEGER,
    submitted_at INTEGER NOT NULL
);

-- 보상 기록
CREATE TABLE IF NOT EXISTS referral_awards (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    link_id TEXT NOT NULL,
    award_type TEXT NOT NULL,            -- badge | membership
    awarded_at INTEGER NOT NULL,
    expires_at INTEGER,
    revoked BOOLEAN DEFAULT FALSE,
    revoke_reason TEXT,
    FOREIGN KEY(link_id) REFERENCES referral_links(id)
);

-- 재검증 로그
CREATE TABLE IF NOT EXISTS referral_verification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id TEXT NOT NULL,
    checked_at INTEGER NOT NULL,
    http_status INTEGER,
    link_found BOOLEAN,                  -- 0=실패, 1=성공 (3-strike 카운트 대상)
    notes TEXT,
    FOREIGN KEY(link_id) REFERENCES referral_links(id)
);

-- 백그라운드 작업 스케줄러 상태 (v0.9)
CREATE TABLE IF NOT EXISTS background_task_state (
    task_name TEXT PRIMARY KEY,
    last_run_at INTEGER,
    updated_at INTEGER
);
```

---

## 📡 API 엔드포인트

| Method | Path | Auth | 설명 |
|--------|------|------|------|
| POST | `/api/referral/submit` | ✅ user | URL 제출 |
| GET | `/api/referral/status/<username>` | ✅ user | 내 제출 상태 조회 (`fail_count`, `next_check_in_hours`, `recent_checks` 포함) |
| GET | `/api/referral/check/<username>` | ✅ user | 뱃지/멤버십 보유 여부 조회 |
| GET | `/api/referral/list` | ✅ admin | 전체 목록 (필터: status) |
| POST | `/api/referral/approve/<link_id>` | ✅ admin | 승인 + 자동 멤버십 부여 |
| POST | `/api/referral/reject/<link_id>` | ✅ admin | 거부 (reason 포함) |
| POST | `/api/referral/verify/<link_id>` | ✅ admin | 수동 재검증 트리거 |
| POST | `/api/referral/replace/<link_id>` | ✅ user | 유예 기간 중 URL 교체 ⭐ NEW |

---

## 🛡️ URL 정규화 규칙

제출된 URL은 저장 전 다음 처리를 거침:

1. 소문자 변환 (scheme + host)
2. trailing slash 제거
3. 쿼리 파라미터 정렬 (`?a=1&b=2` → 일관된 순서)
4. fragment (`#...`) 제거
5. `www.` prefix 통일 (있으면 제거)
6. 도메인 추출 (`urllib.parse` 사용)

→ 정규화된 URL과 도메인 모두 UNIQUE 제약으로 중복 차단.

---

## 📊 Phase별 구현 로드맵

```
Sprint 0 ─ 정책 확정 ✅ (이 문서)
    │
Sprint 1 ─ Phase A: MVP ✅ (구현 완료)
    │   ├── DB 테이블 생성 (models.py) ✅
    │   ├── /api/referral/submit, /status, /check API ✅
    │   ├── 프론트: 제출 폼 (wallet 페이지) ✅
    │   ├── 프론트: 🔗 Referral 뱃지 표시 (SWR 캐시) ✅
    │   ├── 프론트: rejected 시 재제출 허용 ✅
    │   ├── 관리자: Admin Panel > Referrals 탭 (approve/reject UI) ✅
    │   ├── 백엔드: rejected 링크 제외하고 재제출 허용 ✅
    │   └── 이벤트 루프 최적화 (값 변경 시에만 dispatch) ✅
    │
    │   테스트 기록: 사용자 `gookjob2` — DB 초기화 완료 (2026-04-07), Phase A~C 전체 재테스트 준비됨
    │
Sprint 2 ─ Phase B: 자동 검증 ✅ (구현 완료)
    │   ├── referral_verifier.py (services/referral_verifier.py) ✅
    │   ├── 제출 시 자동 1차 검증 → 통과하면 auto-approve (admin 부담 경감) ✅
    │   ├── 검증 실패 시 status=pending 유지 → admin 수동 리뷰 ✅
    │   ├── 주기적 재검증 (background_tasks.py에서 12시간 간격 실행) ✅
    │   ├── 관리자: 수동 재검증 API (POST /api/referral/verify/<link_id>) ✅
    │   └── referral_verification_log 테이블 활용 ✅
    │
Sprint 3 ─ Phase C: 멤버십 부여 ✅ (구현 완료)
    │   ├── approve 시 _grant_referral_membership() → 1년 Gold 자동 부여 ✅
    │   ├── auto-approve (Phase B verifier) 시에도 멤버십 자동 부여 ✅
    │   ├── admin 수동 승인 시에도 멤버십 자동 부여 ✅
    │   ├── reject / 재검증 실패(유예 초과) 시 deactivate_membership() ✅
    │   ├── referral_awards에 'membership' award 기록 + expires_at ✅
    │   └── amount_paid=0, tx_hash='referral:<link_id>' 로 기록 ✅
    │
    │   추가 (v0.6):
    │   ├── 멤버십 만료 후 재제출 허용 (user/domain/url 제한 해제) ✅
    │   └── Navbar admin 아이콘에 pending referrals 개수 합산 표시 ✅
    │
    │   추가 (v1.0 — 영구차단 제거 + 버그 수정 + 상세 UI):
    │   ├── 누적 3회 검증 실패 → 유예 없이 즉시 자동취소 (3-strike) ✅
    │   ├── ~~영구차단~~ 제거 — 자동취소 후 재제출 허용 ✅
    │   ├── manual_verify (admin 수동 재검증) 3-strike 로직 누락 버그 수정 ✅
    │   ├── 유예 기간 중 링크 URL 교체 API + UI (POST /replace/<link_id>) ✅
    │   ├── Navbar 경고 아이콘 (유예 기간 링크 보유 시 ⚠ 표시, mobile+desktop) ✅
    │   ├── Wallet 상세 검증 현황 UI (실패 횟수 X/3, 다음 검증 시간, 유예 기간) ✅
    │   ├── Wallet revoke 알림에 검증 로그 테이블 (시간, HTTP, 결과, 상세) 추가 ✅
    │   ├── background_task_state DB 테이블 기반 정확한 다음 검증 시간 계산 ✅
    │   └── is_user_referral_banned() 전면 제거 (submit/status/replace 4곳) ✅
    │
Sprint 4 ─ Phase D: 운영 강화 ⬜
        ├── 대시보드 (제출 수, 승인율, 악용률)
        ├── 도메인 Authority 점수 연동 (선택)
        └── 정책 튜닝
```

---

## ⚙️ 설정값 (Config)

```python
# referral_verifier.py 상수
REFERRAL_ENABLED = True
REFERRAL_DOMAIN_LIMIT = 1          # 도메인당 최대 보상 횟수
REFERRAL_USER_LIMIT = 1            # 사용자당 최대 보상 횟수
REFERRAL_MIN_DOMAIN_AGE_DAYS = 180 # 최소 도메인 나이 (일)
REFERRAL_REVERIFY_INTERVAL_DAYS = 90
REFERRAL_GRACE_PERIOD_DAYS = 14    # 재검증 실패 후 유예 기간
REFERRAL_EARLY_BACKOFF_SCHEDULE = [0.5, 1, 2, 4, 8, 16, 32, 64]  # 승인 후 재검증 간격 (일)
TOTAL_FAIL_LIMIT = 3               # 누적 검증 실패 N회 → 즉시 자동취소 ⭐
# AUTO_REVOKE_BAN_THRESHOLD 제거됨 (v1.0) — 영구차단 폐지
REFERRAL_TARGET_DOMAIN = "oratio.space"
REFERRAL_BLACKLISTED_DOMAINS = [
    "bit.ly", "t.co", "tinyurl.com", "goo.gl",
]
REFERRAL_BLACKLISTED_PLATFORMS = [
    "*.blogspot.com",
    "*.wordpress.com",
    "*.tumblr.com",
]
```

---

_Document Version: 1.0 | Updated: 2026-04-20 | Permanent ban removed, manual_verify 3-strike bug fixed, detailed revoke UI_
