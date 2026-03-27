# CP (아동 포르노그래피) 콘텐츠 관리 시스템

> **버전**: v2.6 | **생성일**: 2025-11-07 | **최종 업데이트**: 2026-03-24 | **상태**: ✅ **운영 중**

---

## 📝 최근 업데이트 (2025-12-05)

### 🛠️ 버그 수정

#### 1. 멤버십 사용자 피드 페이지 Re-report 불가 수정 ✅
**문제**: Moderator가 "Not CP"로 판정한 게시물을 멤버십 사용자가 피드 페이지에서 Re-report 시도하면 거부됨. 그러나 개별 게시물 페이지(`/post/140`)에서는 Report 가능.
**원인**: 클라이언트(프론트엔드)가 멤버십 상태를 로컬 캐시에서 가져오는데, 피드 페이지에서는 캐시가 동기화되지 않아 `reporter_is_member=false`로 전송됨.
**해결**: 백엔드 API(`routes/cp.py`)에서 클라이언트가 보낸 `reporter_is_member` 값을 무시하고, 내부 membership service API를 직접 호출하여 서버 측에서 멤버십 상태 결정.
```python
# routes/cp.py - api_create_report() 수정
membership_url = f"{bch_base}/api/membership/status/{reporter_username}"
resp = requests.get(membership_url, headers=headers, timeout=5)
if resp.ok:
    reporter_is_member = bool(resp.json().get('membership', {}).get('is_active', False))
```
**결과**: ✅ 멤버십 사용자(gookjob 등)가 피드 페이지에서도 Re-report 가능. Admin에게 에스컬레이션 정상 작동.

#### 2. Admin "Confirm CP" 이후 영구 삭제 미작동 수정 ✅
**문제**: Admin이 Re-reported post에 "Confirm CP"를 선택해도 실제로 콘텐츠가 삭제되지 않고, 단지 Admin pending reports 패널에서만 사라짐.
**원인**: 
1. `cp_moderation.py`가 Lemmy `remove_post` API 사용 → **Remove ≠ Purge** (Remove는 숨김 처리만, Admin은 여전히 볼 수 있음)
2. Lemmy Admin 로그인 시 PostgreSQL `duplicate key value violates unique constraint` 에러 발생

**해결**:
1. **Purge API 사용**: `remove_post()` → `purge_post()` 변경 (Lemmy `/api/v3/admin/purge/post` 엔드포인트)
2. **로그인 재시도 로직**: `login_as_admin()`에 exponential backoff 재시도 추가 (최대 3회)
```python
# lemmy_integration.py - purge_post() 추가
def purge_post(self, post_id, reason=""):
    response = self.session.post(f"{self.base_url}/api/v3/admin/purge/post", json={...})

# lemmy_integration.py - login_as_admin() 재시도 로직
for attempt in range(max_retries):
    try:
        return original_login()
    except Exception as e:
        if "duplicate key" in str(e) and attempt < max_retries - 1:
            time.sleep(delay * (2 ** attempt))  # 1s, 2s, 4s
```
**결과**: ✅ Admin "Confirm CP" 시 콘텐츠가 **완전 영구 삭제** (Admin도 접근 불가).

#### 3. 멤버십 조회 5초 Timeout 수정 ✅
**문제**: `routes/cp.py`에서 멤버십 상태 확인 시 HTTP self-call로 인해 5초 타임아웃 발생.
**원인**: 같은 Flask 서비스 내에서 자기 자신에게 HTTP 요청 → 블로킹.
**해결**: HTTP 호출 대신 직접 `get_membership_status()` 함수 호출.
```python
# routes/cp.py
from services.membership import get_membership_status
membership_info = get_membership_status(reporter_username)
```

#### 4. 멤버십 Gold Badge 깜빡임 수정 ✅
**문제**: 로그인 후 Gold badge가 50% 확률로만 표시됨 (SSR/클라이언트 hydration 타이밍 불일치).
**해결**: `navbar.tsx`에서 credit cache 업데이트 이벤트 후 다중 `forceUpdate()` 호출.
```typescript
// navbar.tsx
window.addEventListener('bch-credit-cache-updated', () => {
  setTimeout(() => this.forceUpdate(), 100);
  setTimeout(() => this.forceUpdate(), 500);
  setTimeout(() => this.forceUpdate(), 1500);
});
```
**결과**: ✅ 로그인/캐시 업데이트 후 Gold badge 안정적 표시.

**배포 방법**:
```bash
cd /home/user/Oratio/oratio
docker-compose restart bitcoincash-service
```

---

## 📝 이전 업데이트 (2025-11-30)

### ⚡ 성능 최적화 완료 - "깜빡임" 현상 완전 해결

**문제**: oratio.space 첫 접속 시 CP reported post들이 잠깐 보였다가 사라지는 현상 (~385ms 깜빡임)

**원인**: 
1. 프론트엔드 비동기 필터링 (클라이언트가 마운트 후 API 호출)
2. 네트워크 왕복 지연 (RTT ~354ms)
3. 느린 백엔드 쿼리 (50-200ms)

**해결 (2단계)**:

**Phase 1 - 백엔드 최적화**:
- SQL DISTINCT + 복합 인덱스 추가 → 쿼리 시간 **98% 감소** (50ms → 1ms)
- Middleware 5초 TTL 캐싱 → 응답 시간 **95% 감소** (200ms → 5ms)
- Admin 체크 로직 개선 → Lemmy API 호출 최소화
- HTTP 캐싱 헤더 추가 → 브라우저/CDN 레벨 캐싱
- **결과**: API 응답 **90% 단축** (50-200ms → 5-15ms), 하지만 네트워크 지연으로 여전히 깜빡임 발생

**Phase 2 - SSR Pre-fetch 구현** ✅:
- `home.tsx` fetchInitialData에서 CP 데이터 서버에서 미리 로드
- `post-listings.tsx` SSR 데이터 활용 (클라이언트 API 호출 생략)
- `cp-moderation.ts` SSR 환경에서 내부 Docker 서비스 직접 호출
- **결과**: 초기 로드 시 클라이언트 API 대기 **0ms** (네트워크 지연 완전 제거), 깜빡임 **100% 해결**

**최종 결과**: ✅ 초기 페이지 로드 시 CP post가 **처음부터 필터링된 상태로 렌더링** (깜빡임 완전 제거)

**상세 내용**: 문서 하단 "⚡ 성능 최적화" 섹션 참조

---

## 📝 이전 업데이트 (2025-11-27)

### ✅ Ban 사용자 로그인 UX 개선 완료

#### 3. Ban 로그인 시 남은 일수 표시 ✅ (2025-11-27 완료)
**문제**: Ban된 유저 로그인 시 "당신은 사이트에서 추방되었습니다" 토스트만 표시, 해제일과 남은 일수 미표시
**핵심 발견**: Lemmy API는 보안상 이유로 banned 사용자에게도 `"incorrect_login"` 에러만 반환
**해결**: 모든 로그인 실패 시 CP permissions API 조회하여 ban 상태 확인
```typescript
// login.tsx - 모든 로그인 실패 시 체크
try {
  const perms = await checkUserCPPermissions(username_or_email);
  if (perms && perms.is_banned && perms.ban_end) {
    const daysLeft = Math.ceil((perms.ban_end - now) / (24 * 60 * 60));
    const banMessage = `당신은 ${banEndDate}까지 사이트에서 추방되었습니다 (${daysLeft}일 남음). ...`;
    toast(banMessage, "danger");
  }
}
```
**결과**: ✅ 한글/영어 이중 언어 ban 메시지 + 남은 일수 + Appeal 링크 표시

**배포 완료**: 2025-11-27  
**테스트 완료**: cpcp 유저로 확인 완료

---

## 📝 이전 업데이트 (2025-11-25~26)

### ✅ 사용자 경험 개선 및 접근 제어 수정

#### 1. Report Ability Revoked Toast 표시 ✅
**문제**: `cpcp2` 유저 (`can_report_cp: false`)가 "Report CP" 버튼 클릭 시 토스트 메시지가 표시되지 않음
**원인**: 프론트엔드가 `error.detail`에서 에러 메시지를 추출했으나, 백엔드는 `error.error`로 반환
**해결**: `cp-moderation.ts`에서 에러 추출 로직 수정
```typescript
message: error.error || error.detail || 'Failed to submit report'
```
**결과**: ✅ "Revoked until YYYY-MM-DD (X days remaining). Appeal at /cp/appeal" 토스트 정상 표시

#### 2. CP Hidden Post Nginx Level Blocking 수정 ✅
**문제**: CP로 숨겨진 게시물에 admin과 moderator도 접근 불가 (403 Forbidden)
**원인**: Nginx `auth_request`에서 JWT 쿠키 전달 및 post_id 변수 추출 문제
**해결**: 
1. `auth_request` 방식 개선: `/_cp_check` 내부 location 사용
2. `$request_uri`에서 regex로 post_id 추출: `if ($request_uri ~* "^/post/(\d+)")`
3. JWT 쿠키 전달: `proxy_set_header Cookie $http_cookie`
4. Backend 로깅 추가: 모든 check 요청을 상세 로깅

```nginx
location ~ ^/post/(\d+)$ {
    set $post_id $1;
    auth_request /_cp_check;
    error_page 403 = @cp_blocked;
    proxy_pass http://oratio-lemmy-ui-1:1234;
    # ... 기타 설정
}

location = /_cp_check {
    internal;
    if ($request_uri ~* "^/post/(\d+)") {
        set $extracted_post_id $1;
    }
    proxy_pass http://bitcoincash-service:8081/api/cp/check-post-access/$extracted_post_id;
    proxy_set_header Cookie $http_cookie;  # JWT 전달
}
```

**Backend 로직** (`cp_post_blocker.py`):
```python
@cp_blocker_bp.route('/api/cp/check-post-access/<int:post_id>')
def check_post_access(post_id):
    jwt_token = request.cookies.get('jwt')
    if jwt_token:
        decoded = jwt.decode(jwt_token, options={"verify_signature": False})
        person_id = decoded.get('sub')
        
        # Admin check (person_id=1)
        if person_id == 1:
            logger.info(f"✅ Admin access to post {post_id} - ALLOWED")
            return {"allowed": True}, 200
        
        # Moderator check (can_review_cp=1)
        perms = get_user_permissions_by_person_id(person_id)
        if perms and perms.get('can_review_cp'):
            logger.info(f"✅ Mod access to post {post_id} - ALLOWED")
            return {"allowed": True}, 200
    
    # Check if post is CP hidden
    if post_id in get_blocked_post_ids():
        logger.info(f"❌ Regular user blocked from post {post_id}")
        return {"allowed": False, "reason": "Content unavailable"}, 403
    
    return {"allowed": True}, 200
```

**결과**: 
- ✅ Admin (`person_id=1`): CP hidden post URL 직접 접근 가능
- ✅ Moderator (`can_review_cp=1`): CP hidden post URL 직접 접근 가능
- ❌ 일반 유저: 403 Forbidden (Nginx level 차단)
- ✅ Frontend filtering도 동시 적용 (이중 보호)

#### 3. Ban 로그인 시 남은 일수 표시 ✅
**문제**: Ban된 유저(`cpcp`) 로그인 시 "당신은 사이트에서 추방되었습니다" 토스트만 표시, 해제일과 남은 일수 미표시
**해결**: `login.tsx`에서 ban 에러 발생 시 CP permissions 조회하여 정확한 정보 표시
```typescript
const perms = await checkUserCPPermissions(username);
if (perms && perms.is_banned && perms.ban_end) {
  const daysLeft = Math.ceil((perms.ban_end - now) / 86400);
  const banEndDate = new Date(perms.ban_end * 1000).toISOString().split('T')[0];
  toast(`You are banned from this site until ${banEndDate} (${daysLeft} days remaining)`, "danger");
}
```
**결과**: ✅ "You are banned from this site until 2026-02-12 (79 days remaining)" 형식으로 표시

**배포 완료**: 2025-11-25  
**상세 문서**: `/docs/features/CP/CP_FIXES_2025-11-25.md`

---

## 📝 이전 업데이트 (2025-11-22)

### ✅ 권한 분리 및 안정성 개선

#### 1. Moderator/Admin Content 접근 권한 분리 ✅
**개선사항**:
- Middleware (`cp_post_blocker.py`): Admin(person_id=1) + Moderator(can_review_cp=1) 모두 hidden content 접근 가능
- Frontend (`/api/cp/reported-content-ids`): Admin/Mod는 빈 배열, 일반 유저만 filtering 적용
- **결과**: User/Mod/Admin 3단계 권한 분리 완료

#### 2. Appeal 로직 개선 ✅
**문제**: 이전 appeal이 approved/rejected 되어도 7일 내 재제출 불가
**해결**: Pending appeal만 카운트하도록 수정
```python
# OLD: 모든 appeal 카운트
WHERE user_id = ? AND appeal_type = ? AND created_at > ?

# NEW: pending만 카운트
WHERE ... AND status = 'pending'
```
**결과**: Approved/rejected 후 새 issue에 대해 즉시 재appeal 가능

#### 3. Database Lock 해결 ✅
**문제**: `ERROR: database is locked` 반복 발생 → Background task 실패
**해결**: SQLite WAL mode 활성화
```python
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
```
**결과**: 동시 읽기/쓰기 가능, background task 정상 작동

#### 4. Report Ability Expiry 자동 복원 확인 ✅
- `report_ability_revoked_at` 컬럼 정상 작동
- 만료된 revocation 자동 복원 (background task, 15초 간격)
- 테스트 엔드포인트 추가: `GET /api/cp/permissions/revoked`

#### 5. 사용자 메시지 개선 ✅
- Ban 메시지: "You are currently banned until YYYY-MM-DD (X days remaining)"
- Report ability loss: "Revoked until YYYY-MM-DD (X days remaining). Appeal at /cp/appeal"
- Appeal 에러: "⏰ You already have a pending appeal" (구체적 메시지)

---

## 📝 이전 업데이트 (2025-11-15)

### ✅ Appeal 시스템 및 URL 차단 완료!

#### 1. CP Post 직접 URL 접근 차단 (Nginx Level)
**문제**: CP 확인된 post가 `/post/63`, `/post/131` 등 직접 URL로 접근 가능
**해결**: 
- Nginx `auth_request` 패턴 구현
- `/api/cp/check-post-access/<post_id>` 백엔드 체크 엔드포인트 추가
- Nginx 설정: `location ~ ^/post/(\d+)` → auth_request → 403 차단
- **결과**: ✅ CP post 직접 URL 접근 시 403 Forbidden 반환

**코드 변경**:
```nginx
# nginx_production.conf
location ~ ^/post/(\d+) {
    auth_request /cp-check-internal;
    error_page 403 = @cp_blocked;
    proxy_pass http://oratio-lemmy-ui-1:1234;
}

location /cp-check-internal {
    internal;
    proxy_pass http://bitcoincash-service:8081/api/cp/check-post-access/$post_id;
}
```

#### 2. Ban된 사용자 Appeal 시스템 구현
**기능**: 
- Username만으로 appeal 제출 가능 (person_id 자동 조회)
- 로그인 페이지에 `/cp/appeal` 링크 안내
- Username 입력 시 자동으로:
  - Membership 상태 확인 (`/api/membership/check/<username>`)
  - 해당 사용자의 CP reported posts 표시 (`/api/cp/user-reports/<username>`)
- Non-member는 submit 버튼 비활성화

**추가된 API**:
- `GET /api/membership/check/<username>` - Membership 상태 확인 (public)
- `GET /api/cp/user-reports/<username>` - 사용자의 CP reports 조회 (public)
- `POST /api/cp/appeal` - Appeal 제출 (no auth, ban 상태 자동 검증)

**Nginx 라우팅 추가**:
```nginx
# CP API routing (^~ = high priority prefix match)
location ^~ /api/cp/ {
    proxy_pass http://bitcoincash-service:8081/api/cp/;
}

# Membership API routing
location ^~ /api/membership/ {
    proxy_pass http://bitcoincash-service:8081/api/membership/;
}
```

#### 3. Admin Control Panel - Appeals 탭 구현
**기능**:
- Pending appeals 목록 표시
- Appeal 내용, 제출 시간, 사용자 정보 표시
- Approve/Reject 버튼으로 즉시 처리
- Approve 시 자동으로 ban 해제 및 권한 복구

**추가된 API**:
- `GET /api/cp/appeals/pending` - Pending appeals 목록 (admin only, API key 필요)
- `POST /api/cp/appeals/<appeal_id>/review` - Appeal 처리 (admin only)

**코드 변경**:
```typescript
// admin-control-panel.tsx
async loadAppeals() {
    const response = await fetch('/api/cp/appeals/pending', {
        headers: { 'X-API-Key': getApiKey() }
    });
    // ...
}

renderAppealsTab() {
    // Appeals UI with approve/reject buttons
}
```

**테스트 결과**:
- ✅ cpcp 사용자 appeal 제출 성공
- ✅ Admin panel에서 pending appeals 조회 성공
- ✅ Approve/Reject 처리 정상 작동

---

## 📝 이전 업데이트 (2025-11-14)

### ✅ Ban 시스템 통합 완료!

#### 1. Frontend CP Content Filtering 수정
**문제**: CP로 확인된 post (content_hidden=1, status=reviewed)가 여전히 일부 사용자에게 노출됨
**원인**: `api_get_reported_content_ids()` 쿼리가 `status='pending'` 조건으로 reviewed된 CP report를 제외
**해결**: 
- `routes/cp.py` 수정 (line 269-310)
- 쿼리 조건 변경: `WHERE status = 'pending' AND content_hidden = 1` → `WHERE content_hidden = 1`
- 모든 숨겨진 콘텐츠(pending, reviewed, rejected)를 frontend filtering에 포함
- **결과**: ✅ Post 63 정상적으로 숨김 확인

#### 2. Lemmy Ban API 통합 완료 ✅
**문제**: CP 확인 시 user ban 처리가 되지 않아 신고된 사용자(cpcpcp)가 계속 로그인 가능
**구현**:
- `lemmy_integration.py`에 `ban_person()` 메서드 추가
- `cp_moderation.py`의 `ban_user()` 함수에 `LemmyAPI.ban_person()` 호출 통합
- CP 확인 시 SQLite(user_cp_permissions) + PostgreSQL(person.banned) 동시 업데이트
- **상태**: ✅ **완전 해결! Admin 인증 문제 해결 후 정상 작동 확인**

**테스트 결과**:
- ✅ SQLite `user_cp_permissions`: `is_banned=1`, `ban_count=4`
- ✅ PostgreSQL `person.banned`: `t` (true), `ban_expires=2026-02-12`
- ✅ Lemmy API를 통한 ban 기능 정상 작동

**코드 변경**:
```python
# lemmy_integration.py
def ban_person(self, person_id, ban=True, reason="", expires=None, remove_data=False):
    """Lemmy API를 통해 사용자 ban/unban"""
    if not self.login_as_admin():
        return False
    # ... Lemmy API 호출

# cp_moderation.py - review_cp_report()
if decision == REVIEW_DECISION_CP_CONFIRMED:
    ban_user(...)  # Lemmy ban 포함 - 정상 작동!
```

#### 3. Admin 인증 문제 해결 ✅
**문제**: `refresh_passwords.sh` 실행 후 admin 로그인 실패
- `.env`의 `LEMMY_ADMIN_PASS` 변경 → PostgreSQL `local_user.password_encrypted` (bcrypt hash)와 불일치
- CP ban 테스트 불가 (Lemmy API 호출 시 admin JWT 필요)
- 401 UNAUTHORIZED 에러로 모든 `/payments/api/*` 엔드포인트 실패

**해결 방법**:
1. ✅ Docker container에서 Python bcrypt로 새 패스워드의 hash 생성
2. ✅ PostgreSQL `local_user.password_encrypted` 직접 업데이트
3. ✅ `.env` 파일에 새 패스워드 저장
4. ✅ `refresh_passwords.sh` 스크립트 개선: admin 패스워드 변경 시 PostgreSQL 자동 동기화

**개선된 `refresh_passwords.sh`**:
```bash
# 새 admin 패스워드 생성
NEW_LEMMY_ADMIN_PASS=$(generate_password 24)

# Docker container에서 bcrypt hash 생성
NEW_ADMIN_BCRYPT_HASH=$(docker-compose exec -T bitcoincash-service python3 -c "
import bcrypt
password = b'$NEW_LEMMY_ADMIN_PASS'
salt = bcrypt.gensalt(rounds=12)
hash_bytes = bcrypt.hashpw(password, salt)
print(hash_bytes.decode('utf-8'))
")

# PostgreSQL 자동 업데이트
docker-compose exec -T postgres psql -U lemmy -d lemmy -c \
    "UPDATE local_user SET password_encrypted = '$NEW_ADMIN_BCRYPT_HASH' \
     WHERE person_id = (SELECT id FROM person WHERE name = 'admin');"
```

**현재 상태**: ✅ **완전 해결! Admin 로그인 정상 작동**
- Admin API 로그인 성공 (JWT token 발급)
- CP ban 기능 정상 작동 확인
- 향후 `refresh_passwords.sh` 실행 시 자동으로 PostgreSQL도 동기화됨

---

## 📝 이전 업데이트 (2025-11-11)

### 🔧 Ban 시스템 통합 작업 (당시 진행 중, 2025-11-14에 완료)

**당시 상황**:
- Frontend CP filtering 수정 완료
- Lemmy ban API 코드 구현 완료
- Admin 인증 문제로 ban 기능 테스트 불가

**해결 과정 (2025-11-14)**:
1. Admin 패스워드와 PostgreSQL bcrypt hash 불일치 원인 파악
2. Python bcrypt로 새 패스워드 hash 생성 및 DB 동기화
3. `refresh_passwords.sh` 스크립트 개선 (자동 동기화 로직 추가)
4. Admin API 로그인 성공 및 ban 기능 테스트 완료

---

## 📝 이전 업데이트 (2025-11-10)

### 🐛 버그 수정 및 개선사항

#### 1. Hide/Unhide Post 기능 수정
**문제**: Lemmy의 `HidePost` API로 숨긴 post를 unhide했을 때 feed에 다시 나타나지 않는 버그
**원인**: Frontend가 post list를 refetch하지 않아 hidden post가 계속 표시되지 않음
**해결**: 
- `home.tsx`, `community.tsx`, `post.tsx`의 `handleHidePost()` 수정
- Unhide 시 `fetchData()` 호출하여 posts 다시 불러오기
- 관련 파일: `/lemmy-ui-custom/src/shared/components/home/home.tsx` 등

#### 2. CP Report Review 시 Content Unhiding 자동화
**문제**: Moderator가 "Not CP"로 판정해도 reported content가 모든 users에게 계속 숨겨짐
**원인**: 
1. `content_hidden` DB 필드가 업데이트되지 않음
2. Lemmy의 `post_hide` 테이블 레코드가 삭제되지 않음

**해결**:
- `review_cp_report()` 함수 수정 (`cp_moderation.py`)
  - "Not CP" 판정 시 `content_hidden = 0`으로 업데이트
  - PostgreSQL에 직접 연결하여 `post_hide` 테이블에서 모든 users의 hide 레코드 삭제
  - `psycopg2` 사용하여 Lemmy DB 직접 조작
- Frontend CP filtering이 정상적으로 작동하도록 개선

**코드 변경**:
```python
# cp_moderation.py 수정사항
elif decision == REVIEW_DECISION_NOT_CP or decision == REVIEW_DECISION_ADMIN_APPROVED:
    new_status = REPORT_STATUS_APPROVED
    content_hidden = 0  # Unhide content
    
    # PostgreSQL에서 post_hide 레코드 삭제
    pg_cursor.execute('DELETE FROM post_hide WHERE post_id = %s', (report['content_id'],))
```

#### 3. Language Filtering 이슈 발견
**문제**: 특정 user가 post를 볼 수 없는 문제 발견 (gookjob이 post 62를 볼 수 없음)
**원인**: Lemmy의 `discussion_languages` 설정과 post의 `language_id` 불일치
- User의 discussion_languages: `{37, 0}` (Korean, Undetermined)
- Post 62의 language_id: `84` (다른 언어)
- Lemmy backend가 user의 언어 설정에 없는 post를 자동 필터링

**해결 방안**:
- Post 생성 시 기본 language를 `0` (Undetermined)로 설정하거나
- User의 discussion_languages에 모든 언어 추가
- 또는 community level에서 언어 설정 통일

#### 4. Frontend CP Filtering 최적화
**개선사항**:
- 30초마다 reported content IDs 자동 refresh
- Component mount/unmount lifecycle 관리 개선
- Cache 관리 로직 강화

**관련 파일**:
- `/lemmy-ui-custom/src/shared/components/post/post-listings.tsx`
- `/lemmy-ui-custom/src/shared/utils/cp-moderation.ts`

### 🔧 기술적 개선

1. **PostgreSQL 직접 연결**: `psycopg2-binary` 사용하여 Lemmy DB 직접 조작 가능
2. **Database 필드 업데이트**: `content_hidden` 필드를 review 결과에 따라 자동 업데이트
3. **Frontend Cache 관리**: 30초 간격 자동 refresh로 실시간성 개선

### 📚 학습한 내용

1. **Lemmy의 HidePost API**: Per-user 작업이며, admin이 다른 user를 대신해 unhide 불가능
2. **Lemmy의 Language Filtering**: User의 `discussion_languages` 설정과 맞지 않는 post는 자동으로 숨김
3. **Frontend vs Backend Hiding**: 
   - CP system: Frontend filtering (reportedPostIds)
   - Lemmy system: Backend DB (`post_hide` 테이블)
   - 두 시스템이 혼재되어 복잡도 증가

### ⚠️ 알려진 이슈 및 제한사항

1. **Language Setting 불일치**: User별 language 설정이 다를 경우 일부 posts가 보이지 않을 수 있음
2. **Cache Delay**: 30초 refresh 간격으로 인해 즉시 반영되지 않을 수 있음 (trade-off: 서버 부하 vs 실시간성)
3. **Banned User Login**: Lemmy에서 ban된 유저는 로그인 자체가 불가능 (JWT 발급 안 됨) → 로그인 시 ban 메시지 표시 불가
4. **Nginx Post Blocking**: `location ~ ^/post/(\d+)` rule은 문서에 명시되어 있으나, 실제 nginx 설정 파일에 미적용 상태 (2025-11-22 기준)

---

## 📋 목차

1. [빠른 시작](#-빠른-시작)
2. [시스템 개요](#-시스템-개요)
3. [작동 방식](#-작동-방식)
4. [사용자 가이드](#-사용자-가이드)
5. [기술 구현](#-기술-구현)
6. [API 레퍼런스](#-api-레퍼런스)
7. [데이터베이스 스키마](#-데이터베이스-스키마)
8. [배포](#-배포)
9. [테스트](#-테스트)
10. [문제 해결](#-문제-해결)

---

## 🚀 빠른 시작

### 전체 시스템 배포

```bash
# 1. 백엔드 배포
cd /home/user/Oratio/oratio
bash deploy_cp_system.sh

# 2. CP 관리 컴포넌트가 포함된 UI 재빌드
docker-compose stop lemmy-ui
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui

# 3. 배포 확인
curl -H "X-API-Key: YOUR_KEY" https://oratio.space/payments/api/cp/health
```

### 포함된 기능

✅ **백엔드 (100% 완성)**
- 7개 테이블이 있는 데이터베이스 스키마
- 15개 이상의 API 엔드포인트
- 8가지 규칙에 대한 비즈니스 로직
- 백그라운드 작업 (자동 차단 해제, 자동 삭제)
- 완전한 감사 추적
- 알림 시스템

✅ **프론트엔드 (100% 완성)**
- 게시물/댓글에 CP 신고 버튼
- 모더레이터 검토 패널
- 관리자 제어 패널
- 차단된 사용자를 위한 이의제기 양식
- 콘텐츠 생성 시 권한 확인
- 내비게이션 바 알림 배지
- 완전한 UI/UX 흐름

---

## 🎯 시스템 개요

**CP 관리 시스템**: 자동 숨김, 다단계 검토, 사용자 관리 및 이의제기 프로세스를 통해 CP 콘텐츠 신고를 처리하는 운영 준비가 완료된 프레임워크입니다.

### 핵심 기능

| 기능 | 상태 | 위치 |
|------|------|------|
| **CP 신고** | ✅ 배포 완료 | 게시물/댓글의 점 세개 메뉴 |
| **자동 숨김** | ✅ 배포 완료 | 백엔드 서비스 |
| **모더레이터 검토** | ✅ 배포 완료 | `/cp/moderator-review` |
| **관리자 제어** | ✅ 배포 완료 | `/cp/admin-panel` |
| **사용자 차단** | ✅ 배포 완료 | 자동 3개월 차단 |
| **신고 능력 상실** | ✅ 배포 완료 | 허위 신고 시 자동 박탈 |
| **이의제기 시스템** | ✅ 배포 완료 | `/cp/appeal` |
| **권한 확인** | ✅ 배포 완료 | 게시물/댓글 생성 시 |
| **내비게이션 바 알림** | ✅ 배포 완료 | 빨간 배지 카운터 |
| **자동 차단 해제** | ✅ 배포 완료 | 백그라운드 작업 (15초 간격) |
| **자동 삭제** | ✅ 배포 완료 | 백그라운드 작업 (7일 타임아웃) |

---

## 📖 작동 방식

### 8가지 규칙 (모두 구현 완료)

#### 규칙 1: 누구나 CP 콘텐츠를 신고할 수 있음 ✅

**사용자 경험:**
1. 게시물 또는 댓글 열기
2. 점 세개 메뉴 (⋮) 클릭
3. "Report CP" 클릭 (빨간색 경고 삼각형 아이콘 ⚠️)
4. 모달 대화상자에서 확인
5. 선택적으로 이유 추가
6. 제출

**기술적 흐름:**
```
사용자가 "Report CP" 클릭 → 프론트엔드에서 멤버십 상태 확인 → 
API가 권한 검증 → 신고 생성 → 콘텐츠 즉시 숨김
```

#### 규칙 2: 콘텐츠 즉시 숨김 ✅

**가시성 매트릭스 (신고 직후, 즉시 적용):**
- ❌ 일반 사용자: 숨겨진 콘텐츠 볼 수 없음
- ✅ 모더레이터: 검토를 위해 볼 수 있음 (임시 접근)
- ✅ 관리자: 검토를 위해 볼 수 있음
- ❌ 작성자: 자신이 작성한 숨겨진 콘텐츠 볼 수 없음

설명: 사용자가 CP로 신고하면 콘텐츠는 즉시 "숨김" 상태가 되며, 이 단계에서는 모더레이터가 검토할 수 있도록 임시로 접근 권한을 유지합니다. 이후 모더레이터/관리자 결정에 따라 가시성은 추가로 변경됩니다.

#### 규칙 3: 모더레이터에게 검토 알림 ✅

**모더레이터 경험:**
1. 내비게이션 바에서 빨간 배지 확인 (⚠️ 아이콘)
2. 클릭하여 `/cp/moderator-review`로 이동
3. 대기 중인 신고 목록 보기
4. 콘텐츠 세부정보, 신고자, 작성자 확인
5. "Confirm CP" 또는 "Not CP" 선택

**결과:**
- **Confirm CP (Moderator가 CP로 판정한 경우)** → 작성자 3개월 차단. 중요한 변경: 이 시점부터 해당 콘텐츠는 "모더레이터는 더 이상 볼 수 없음" 상태로 전환되며, 오직 관리자만 검토를 위해 접근할 수 있습니다 (즉, user: 볼 수 없음 / mod: 볼 수 없음 / admin: 볼 수 있음). 관리자 결정 전까지 콘텐츠는 시스템에서 보이지 않지만 영구 삭제되지는 않습니다. 멤버십 사용자는 이 결정에 대해 Admin에게 이의제기를 제출할 수 있습니다.
- **Not CP (Moderator가 CP가 아니라고 판단한 경우)** → 신고자 신고 능력 상실, 콘텐츠 숨김 해제

#### 규칙 4: 모더레이터 결정에는 결과가 따름 ✅

양측 모두 멤버십(골드 배지)이 있으면 이의제기 가능.

#### 규칙 5: 멤버십 사용자는 이의제기 가능 ✅

**이의제기 경험:**
1. 차단된 사용자가 `/cp/appeal`로 이동
2. 시스템이 활성 차단 확인
3. 골드 배지 멤버십 확인
4. 사용자가 이의제기 작성 (최대 2000자)
5. 관리자 검토를 위해 제출
6. 한 번에 하나의 활성 이의제기만 허용

#### 규칙 6: 재신고 에스컬레이션 로직 ✅

**시나리오: 모더레이터가 "Not CP"로 표시**
- 무료 사용자가 재신고 시도 → ❌ 차단됨
- 멤버십 사용자가 재신고 → ✅ 관리자에게 에스컬레이션

**시나리오: 관리자가 승인**
- 누구든 재신고 시도 → ❌ 영구 차단

#### 규칙 7: 검토되지 않은 관리자 사례 자동 삭제 ✅

```
관리자 사례 생성 → 7일 카운트다운 → 검토되지 않음? → 영구 삭제
```

백그라운드 작업에서 15초마다 자동 실행.

중요: 만약 Admin이 해당 사례에서 "Confirm CP"를 최종 결정하면, 그 즉시 콘텐츠는 영구적으로 삭제되고(관리자 포함 아무도 더 접근할 수 없음) 관련 사용자에 대한 차단 및 제재는 최종적이며 해당 결정 이후에는 이의제기(appeal)가 허용되지 않습니다.

#### 규칙 8: 관리자 수동 제어 ✅

**관리자 패널** (`/cp/admin-panel`)에는 3개의 탭이 있음:

**탭 1: 대기 중인 신고**
- 관리자 에스컬레이션 사례
- 승인(Not CP) 또는 거부(Confirm CP) 버튼
- 에스컬레이션 컨텍스트 표시

관리자 결정의 효과:
- "승인 (Not CP)": 콘텐츠는 시스템에서 정상 상태로 복원되며(모든 사용자에게 보임), 관련 모더레이터의 결정으로 인한 제재(예: 신고자 신고 능력 박탈)는 유지 또는 복원할 수 있습니다.
- "거부 (Confirm CP, Admin이 CP로 최종 확정)": 콘텐츠는 즉시 영구 삭제됩니다(관리자 포함 아무도 접근 불가). 작성자에 대한 차단과 제재는 최종 결론으로 간주되며, 이 결정 이후에는 해당 사건에 대한 어떠한 이의제기도 허용되지 않습니다(관리자는 '최종 감독자' 권한 보유).

**탭 2: 사용자 관리**
- 사용자 이름으로 검색
- 전체 권한 상태 보기
- 수동 작업: 차단/차단 해제, 신고 능력 박탈/복원, 모더레이터 권한 부여/철회

> **참고 (2026-03-24)**: Admin이 다른 사용자의 프로필 페이지(username 클릭)에서도 동일한 차단/차단 해제, 신고 능력 박탈/복원 작업을 수행할 수 있음. 프로필 페이지의 관리 액션은 Admin CP Control Panel과 동기화되며, CP DB 상태가 일관되게 유지됨.

**탭 3: 이의제기**
- 멤버십 사용자가 제출한 이의제기(appeal) 목록 표시 및 처리
- 단, Admin이 이미 해당 사례에서 "Confirm CP"를 선택하여 최종 확정한 경우에는 그 사건에 대한 이의제기는 수락되지 않습니다.

---

## 👤 사용자 가이드

### 일반 사용자용

#### CP 콘텐츠 신고 방법

1. **콘텐츠 찾기** - 게시물 또는 댓글로 이동
2. **작업 메뉴 열기** - 콘텐츠의 점 세개 메뉴 (⋮) 클릭
3. **CP 신고** - "Report CP" 클릭 (빨간색 ⚠️ 아이콘)
4. **경고**: 허위 신고는 신고 능력 상실로 이어질 수 있음
5. **확인 및 제출** - 선택적으로 이유 추가, "Yes, Report CP" 클릭

#### 신고 후 일어나는 일

**CP로 확인된 경우:**
- ✅ 작성자 3개월 차단
- ✅ 콘텐츠 영구 숨김
- ✅ 신고 능력 유지

**Not CP로 거부된 경우:**
- ❌ CP 신고 능력 상실
- ℹ️ 멤버십이 있으면 이의제기 가능

### 모더레이터용

#### 검토 패널 접근

1. 내비게이션 바에서 빨간 배지 찾기 (⚠️ 아이콘과 카운트)
2. 클릭하여 `/cp/moderator-review`로 이동

#### 신고 검토

**결정 옵션:**

**🔴 Confirm CP**
- 작성자 자동으로 3개월 차단
- 콘텐츠 숨김 유지
- 멤버십 사용자인 작성자는 이의제기 가능

**🟢 Not CP**
- 신고자 신고 능력 상실
- 콘텐츠 숨김 해제
- 멤버십 사용자인 신고자는 이의제기 가능
- 멤버십 사용자가 재신고하면 관리자에게 에스컬레이션

### 관리자용

#### 관리자 패널 접근

1. 내비게이션 바에서 방패 배지 찾기 (🛡️와 카운트)
2. 클릭하여 `/cp/admin-panel`로 이동

#### 탭 1: 대기 중인 신고

- 관리자 에스컬레이션 사례 (모더레이터가 "Not CP"라고 했지만 멤버십 사용자가 재신고)
- **승인**: 모더레이터가 옳았음
- **거부**: 콘텐츠가 CP임, 작성자 차단

#### 탭 2: 사용자 관리

1. 사용자 이름 검색
2. 권한 보기: 신고 가능, 차단됨, 차단 횟수 등
3. 수동 작업: 차단, 차단 해제, 신고 박탈, 신고 복원

> **참고 (2026-03-24)**: Admin은 프로필 페이지에서도 위 작업 수행 가능 — 사용자 이름 클릭 → 프로필 → CP 관리 버튼 사용. Admin CP와 프로필 간 CP 상태 자동 동기화됨.

---

## 🔧 기술 구현

### 프론트엔드 컴포넌트

#### 1. CP 신고 버튼
**파일**: `content-action-dropdown.tsx`  
**경로**: 게시물/댓글의 점 세개 메뉴  
**기능**: 확인 모달, 멤버십 확인, API 통합

#### 2. 권한 확인
**파일**: `post-form.tsx`, `comment-form.tsx`  
**기능**: 마운트 시 확인, 차단된 경우 차단, 만료일 표시

#### 3. 모더레이터 검토 패널
**파일**: `moderator-review-panel.tsx`  
**경로**: `/cp/moderator-review`  
**기능**: 대기 중인 신고 목록, 검토 버튼, 자동 새로고침

#### 4. 관리자 제어 패널
**파일**: `admin-control-panel.tsx`  
**경로**: `/cp/admin-panel`  
**기능**: 3탭 인터페이스, 사용자 검색, 수동 작업

#### 5. 이의제기 양식
**파일**: `appeal-form.tsx`  
**경로**: `/cp/appeal`  
**기능**: 멤버십 확인, 2000자 제한, 가이드라인

#### 6. CP 유틸리티 모듈
**파일**: `cp-moderation.ts`  
**내보내기**: 1분 캐싱이 있는 모든 API 래퍼 함수

#### 7. 내비게이션 바 통합
**파일**: `navbar.tsx`  
**기능**: 알림 배지 (30초 폴링), 모드/관리자 링크

---

## 📡 API 레퍼런스

### 베이스 URL
```
https://oratio.space/payments/api/cp
```

### 인증
모든 엔드포인트는 `X-API-Key` 헤더 필요.

### 주요 엔드포인트

**사용자 권한**
```http
GET /api/cp/permissions/<username>
```

**CP 신고**
```http
POST /api/cp/report
GET  /api/cp/reports/pending?escalation_level=moderator
POST /api/cp/report/<id>/review
```

**이의제기**
```http
POST /api/cp/appeal
```

**관리자 작업**
```http
POST /api/cp/admin/user/<username>/ban
POST /api/cp/admin/user/<username>/revoke-report
POST /api/cp/admin/user/<username>/restore
```
> **참고 (2026-03-24)**: 위 엔드포인트는 이제 `person_id`/`username` 필드가 body에 없어도 동작함. URL의 `<username>`으로 Lemmy에서 `person_id`를 자동 조회하고, CP DB에 해당 사용자 row가 없으면 `ensure_user_permissions()`로 자동 생성 후 업데이트.

**알림**
```http
GET /api/cp/notifications/<person_id>?unread_only=true
```

---

## 🗄️ 데이터베이스 스키마

### 테이블

- `user_cp_permissions` - 사용자 권한 및 차단 상태
- `cp_reports` - 모든 CP 신고
- `cp_reviews` - 검토 기록
- `cp_appeals` - 사용자 이의제기
- `cp_notifications` - 시스템 알림
- `cp_audit_log` - 완전한 감사 추적
- `moderator_cp_assignments` - 모더레이터 권한

### 유용한 쿼리

```sql
-- 사용자 상태 확인
SELECT username, can_report_cp, is_banned, 
       datetime(ban_end, 'unixepoch') as ban_expires
FROM user_cp_permissions 
WHERE username = 'username';

-- 최근 신고
SELECT content_type, content_id, reporter_username, creator_username,
       status, datetime(created_at, 'unixepoch') as created
FROM cp_reports 
ORDER BY created_at DESC 
LIMIT 10;

-- 활성 차단
SELECT username, ban_count, datetime(ban_end, 'unixepoch') as expires
FROM user_cp_permissions 
WHERE is_banned = 1;
```

---

## 🚀 배포

### 전체 배포

```bash
# 1. 백엔드 배포
cd /home/user/Oratio/oratio
bash deploy_cp_system.sh

# 2. 프론트엔드 재빌드
docker-compose stop lemmy-ui
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui

# 3. BCH 서비스 재시작
docker-compose restart bitcoincash-service

# 4. 확인
curl -H "X-API-Key: YOUR_KEY" https://oratio.space/payments/api/cp/health
```

---

## 🧪 테스트

### 브라우저 테스트

- [ ] 게시물/댓글에 신고 버튼 표시
- [ ] 확인 모달 표시
- [ ] 토스트 알림 작동
- [ ] 차단된 사용자 게시 차단
- [ ] 모더레이터 패널 로드
- [ ] 관리자 패널 3개 탭 로드
- [ ] 이의제기 양식 멤버십 확인
- [ ] 내비게이션 바 배지 업데이트

### 엔드투엔드 시나리오

1. 사용자가 CP 신고 → 콘텐츠 숨김
2. 모더레이터 검토 → CP 확인
3. 작성자 차단 → 알림 받음
4. 작성자 이의제기 (멤버십 있으면)
5. 관리자 검토 → 복원 또는 유지

---

## 🐛 문제 해결

### 신고 버튼이 보이지 않음

```bash
# 하드 새로고침: Ctrl + Shift + R
# 또는 UI 재빌드:
docker-compose stop lemmy-ui
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui
```

### 권한에 대해 API가 404 반환

**첫 사용자에게는 정상입니다!** 백엔드가 이제 기본 권한을 반환합니다.

### 내비게이션 바 배지가 업데이트되지 않음

브라우저 콘솔에서 폴링 확인. 30초마다 폴링해야 합니다.

### 백그라운드 작업이 실행되지 않음 (Database Lock)

```bash
# 증상: ERROR:bch-payment-service:Error in CP background tasks: database is locked
# 해결: WAL mode 활성화 (이미 get_db()에 적용됨)
docker exec bitcoincash-service sqlite3 /data/payments.db "PRAGMA journal_mode"
# 기대 출력: wal

# 로그 확인
docker logs bitcoincash-service | grep "CP background"
# 15초마다 "CP background tasks complete" 표시되어야 함
```

### Report Ability 복원 확인

```bash
# 만료된 revocation 목록 조회
curl -H "X-API-Key: YOUR_KEY" https://oratio.space/payments/api/cp/permissions/revoked

# 특정 유저 상태 확인
docker exec bitcoincash-service sqlite3 /data/payments.db \
  "SELECT username, can_report_cp, datetime(report_ability_revoked_at, 'unixepoch') 
   FROM user_cp_permissions WHERE username='test_user'"
```

---

## 📊 모니터링

### 상태 확인

```bash
curl -H "X-API-Key: YOUR_KEY" https://oratio.space/payments/api/cp/health
```

### 주요 지표

```sql
-- 시스템 개요
SELECT 
  (SELECT COUNT(*) FROM user_cp_permissions WHERE is_banned = 1) as active_bans,
  (SELECT COUNT(*) FROM cp_reports WHERE status = 'pending') as pending_reports,
  (SELECT COUNT(*) FROM cp_appeals WHERE status = 'pending') as pending_appeals;
```

---

## ⚡ 성능 최적화 (2025-11-30)

### 문제: 초기 로딩 시 CP reported post가 잠깐 보였다가 사라지는 현상

**원인**:
1. **프론트엔드 타이밍 이슈**: Lemmy에서 post 목록 먼저 렌더링 → `/api/cp/reported-content-ids` 비동기 호출 → 응답 후 필터링
2. **백엔드 성능 이슈**: 
   - `content_hidden` 컬럼에 인덱스 없음 → 전체 테이블 스캔
   - `SELECT`에 `DISTINCT` 없음 → 중복 ID 반환
   - Admin 체크 시 느린 Lemmy API 동기 호출
   - 서버 사이드 캐싱 없음

### 적용된 최적화

#### 1. SQL 쿼리 최적화 ✅
**파일**: `routes/cp.py` - `api_get_reported_content_ids()`
```python
# BEFORE: 중복 가능, 인덱스 없음
SELECT content_type, content_id FROM cp_reports WHERE content_hidden = 1

# AFTER: DISTINCT로 중복 제거
SELECT DISTINCT content_type, content_id FROM cp_reports WHERE content_hidden = 1
```
**효과**: JSON 페이로드 크기 감소, 클라이언트 처리 시간 단축

#### 2. 복합 인덱스 생성 ✅
**파일**: `models.py` - `init_db()`
```python
# 새 인덱스 추가
cursor.execute('CREATE INDEX IF NOT EXISTS idx_cp_reports_hidden_type_id 
                ON cp_reports(content_hidden, content_type, content_id)')
```
**효과**: `WHERE content_hidden = 1` 쿼리가 전체 테이블 스캔 → 인덱스 스캔으로 변경 (10~100배 빠름)

#### 3. Middleware 캐싱 추가 ✅
**파일**: `middleware/cp_post_blocker.py` - `get_blocked_post_ids()`
```python
# In-memory cache (5초 TTL)
_blocked_cache = {'post_ids': set(), 'timestamp': 0}

def get_blocked_post_ids():
    now = time.time()
    if now - _blocked_cache['timestamp'] < 5:  # 5초 캐시
        return _blocked_cache['post_ids']
    # ... DB 쿼리 및 캐시 갱신
```
**효과**: Nginx auth_request 응답 시간 **5ms 이하**로 단축 (기존 50-200ms)

#### 4. Admin 체크 로직 개선 ✅
**파일**: `routes/cp.py` - `api_get_reported_content_ids()`
```python
# BEFORE: 항상 Lemmy API 호출 (느림)
user_info = lemmy_api.get_user_info(person_id)  # 외부 API 호출

# AFTER: 빠른 로컬 체크 우선
if person_id == 1:  # Admin은 항상 person_id=1
    is_admin = True
else:
    # 로컬 DB에서 moderator 체크 (빠름)
    cursor.execute('SELECT can_review_cp FROM user_cp_permissions WHERE person_id = ?')
```
**효과**: Admin/Mod 체크 시간 **100ms → 5ms** 단축

#### 5. HTTP 캐싱 헤더 추가 ✅
```python
response.headers['Cache-Control'] = 'public, max-age=10'  # 10초 캐시
```
**효과**: 브라우저/CDN 레벨 캐싱으로 서버 부하 감소

#### 6. **SSR Pre-fetch 구현 ✅** (2025-11-30 완료)
**문제**: 위 최적화로 백엔드는 빠름(1ms), 하지만 네트워크 RTT(~354ms)로 여전히 깜빡임 발생  
**해결**: Server-Side Rendering (SSR) 단계에서 CP 데이터를 미리 가져와 HTML에 포함

##### 6.1. 프론트엔드 SSR Pre-fetch
**파일**: `lemmy-ui-custom/src/shared/components/home/home.tsx`
```typescript
// fetchInitialData에서 CP 데이터 병렬 로드
static async fetchInitialData({...}): Promise<HomeData> {
  console.log("🚀 [HOME SSR] fetchInitialData starting...");
  
  // 기존 posts/comments와 병렬로 CP 데이터 가져오기
  let reportedPostIds: Set<number> = new Set();
  try {
    console.log("📡 [HOME SSR] Fetching reported content IDs in parallel...");
    const { getReportedContentIds } = await import("@utils/cp-moderation");
    const { posts } = await getReportedContentIds();
    reportedPostIds = posts;
    console.log(`✅ [HOME SSR] Got ${reportedPostIds.size} reported posts`);
  } catch (error) {
    console.error("❌ [HOME SSR] Failed to fetch reported IDs:", error);
  }
  
  return {
    commentsRes,
    postsRes,
    reportedPostIds: { state: "success", data: reportedPostIds },  // SSR 데이터에 포함
  };
}

// componentWillMount에서 SSR 데이터 로드
async componentWillMount() {
  const ssrReportedIds = this.isoData.routeData.reportedPostIds;
  if (ssrReportedIds?.state === "success" && ssrReportedIds.data) {
    this.setState({ reportedPostIds: ssrReportedIds.data });
    console.log(`💾 [HOME] Loading ${ssrReportedIds.data.size} pre-fetched reported IDs from SSR`);
  }
}
```

##### 6.2. PostListings 컴포넌트 수정
**파일**: `lemmy-ui-custom/src/shared/components/post/post-listings.tsx`
```typescript
interface PostListingsProps {
  // ... 기존 props
  ssrReportedPostIds?: Set<number>;  // SSR에서 전달받은 reported IDs (optional)
}

constructor(props: any, context: any) {
  super(props, context);
  const hasSSRData = !!props.ssrReportedPostIds;
  this.state = {
    reportedPostIds: props.ssrReportedPostIds || new Set(),
    loadingReports: !hasSSRData  // SSR 데이터 있으면 로딩 불필요
  };
  if (hasSSRData) {
    console.log(`💾 [CP Filter] Using ${props.ssrReportedPostIds.size} pre-fetched reported IDs from SSR`);
  }
}

async componentDidMount() {
  // SSR 데이터 있으면 API 호출 생략
  if (this.state.loadingReports) {
    await this.fetchReportedContent();
  } else {
    console.log(`💾 [CP Filter] PostListings mounted - using ${this.state.reportedPostIds.size} SSR-provided reported IDs (no fetch needed)`);
  }
  // 30초마다 주기적 갱신 (변경사항 반영)
  setInterval(() => this.fetchReportedContent(), 30000);
}
```

##### 6.3. API URL 수정 (SSR 환경 지원)
**파일**: `lemmy-ui-custom/src/shared/utils/cp-moderation.ts`
```typescript
function getCPApiUrl(): string {
  // SSR 환경 (Node.js 서버): Docker 내부 서비스 직접 호출
  if (typeof window === 'undefined') {
    return 'http://bitcoincash-service:8081/api/cp';
  }
  // 클라이언트: Nginx 프록시 경유
  return '/payments/api/cp';
}
```

**핵심**: SSR 시 lemmy-ui 컨테이너가 `bitcoincash-service:8081`로 직접 통신 (nginx 우회)

##### 6.4. Home에서 PostListings로 데이터 전달
**파일**: `lemmy-ui-custom/src/shared/components/home/home.tsx` (render 부분)
```typescript
<PostListings
  posts={posts}
  // ... 기존 props
  ssrReportedPostIds={this.state.reportedPostIds}  // SSR 데이터 전달
  onPostEdit={this.handlePostEdit}
  // ... 기타 props
/>
```

**효과**: 
- ✅ **초기 로드 시 깜빡임 완전 제거** - HTML 생성 시점에 이미 필터링 완료
- ✅ **네트워크 지연 무관** - 서버에서 미리 데이터 가져와서 HTML에 포함
- ✅ **클라이언트 API 호출 0회** - 초기 로드 시 추가 요청 불필요
- ✅ **브라우저 콘솔 로그 확인**: `💾 [HOME] Loading 5 pre-fetched reported IDs from SSR`

### 성능 개선 결과

| 지표 | 최적화 전 | 백엔드 최적화 후 | SSR 적용 후 | 최종 개선율 |
|------|----------|----------------|-----------|-----------|
| `/api/cp/reported-content-ids` 응답 시간 | 50-200ms | 5-15ms | N/A (SSR 중 호출) | **90% ↓** |
| Nginx `/_cp_check` 응답 시간 | 50-200ms | < 5ms | < 5ms | **95% ↓** |
| DB 쿼리 시간 (full scan → index) | 10-50ms | < 1ms | < 1ms | **98% ↓** |
| 초기 로드 시 클라이언트 API 대기 시간 | 355ms (네트워크) | 355ms | **0ms** | **100% 제거** |
| "깜빡임" 현상 발생 빈도 | 매번 발생 | 가끔 발생 | **완전 제거** | **100% 해결** |
| 초기 렌더링 시 필터링된 post 표시 | 355ms 후 | 355ms 후 | **즉시 (0ms)** | **즉시 표시** |

### 배포 방법

#### Phase 1: 백엔드 최적화 배포
```bash
# 1. DB 재시작 (새 인덱스 생성)
cd /home/user/Oratio/oratio
docker-compose restart bitcoincash-service

# 2. 인덱스 생성 확인
docker exec bitcoincash-service sqlite3 /data/payments.db \
  "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%hidden%';"
# 출력: idx_cp_reports_hidden_type_id

# 3. 쿼리 성능 확인
docker exec bitcoincash-service sqlite3 /data/payments.db \
  "EXPLAIN QUERY PLAN SELECT DISTINCT content_type, content_id FROM cp_reports WHERE content_hidden = 1;"
# 출력에 "USING INDEX idx_cp_reports_hidden_type_id" 포함되어야 함
```

#### Phase 2: 프론트엔드 SSR 배포
```bash
# 1. lemmy-ui 재빌드 (SSR 코드 포함)
cd /home/user/Oratio/oratio
docker-compose stop lemmy-ui
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui

# 2. 배포 확인 - 브라우저 콘솔 로그 체크
# 성공 시 출력:
# 💾 [HOME] Loading 5 pre-fetched reported IDs from SSR
# 💾 [CP Filter] Using 5 pre-fetched reported IDs from SSR
# 💾 [CP Filter] PostListings mounted - using 5 SSR-provided reported IDs (no fetch needed)

# 3. lemmy-ui 서버 로그 확인 (SSR 실행 확인)
docker-compose logs --tail=50 lemmy-ui | grep "HOME SSR"
# 출력 예시:
# 🚀 [HOME SSR] fetchInitialData starting...
# 📡 [HOME SSR] Fetching reported content IDs in parallel...
# ✅ [HOME SSR] Got 5 reported posts
# ✅ [HOME SSR] fetchInitialData completed in 8ms
```

#### 검증 체크리스트
- ✅ 초기 페이지 로드 시 CP reported post가 **전혀 보이지 않음**
- ✅ 브라우저 Network 탭에서 `/payments/api/cp/reported-content-ids` 호출 **없음** (초기 로드 시)
- ✅ 30초 후 주기적 갱신으로 API 호출 발생 (정상 동작)
- ✅ Admin/Moderator는 여전히 hidden post 접근 가능

### 추가 권장사항 (향후 적용 검토)

1. **Redis 캐싱**: 다중 프로세스 환경에서 통합 캐시 (현재는 프로세스별 in-memory)
2. ~~**SSR 필터링**: 초기 페이지 렌더링 시 서버에서 필터링 완료 후 전송~~ ✅ **완료** (2025-11-30)
3. **전용 테이블**: `hidden_content` 테이블로 분리하여 쿼리 단순화
4. **PostgreSQL 이전**: SQLite 동시성 한계 극복 (트래픽 증가 시)
5. **CDN 캐싱**: CloudFlare 등 CDN에서 `/api/cp/reported-content-ids` 엔드포인트 캐싱 (현재 10초 max-age)

---

## 📝 변경 로그

### v2.6 (2026-03-24)
- ✅ **Admin 프로필 페이지 CP 관리 통합**: Admin이 사용자 프로필(username 클릭)에서 차단/차단 해제, 신고 능력 박탈/복원 가능
- ✅ **Admin CP ↔ 프로필 동기화**: 프로필 액션이 CP DB 및 Admin Control Panel과 일관되게 동작
- ✅ **백엔드 Admin 엔드포인트 강화**: `person_id`/`username` body 필드 누락 시 URL에서 fallback, Lemmy에서 `person_id` 자동 조회
- ✅ **Lemmy Integration 헬퍼 추가**: `get_user_info_by_username()`, `get_person_id_by_username()` — username으로 person_id 조회
- ✅ **ensure_user_permissions() 사전 호출**: Admin 엔드포인트가 UPDATE 전에 row 존재를 보장 (silent no-op 방지)
- ✅ **프론트엔드 profile.tsx 수정**: Admin이 다른 유저 프로필 볼 때 CP 권한 fetch, 관리 버튼 표시, 액션 후 캐시 갱신

### v2.5 (2025-11-30)
- ✅ **성능 최적화**: reported-content-ids API 응답 시간 90% 단축
- ✅ 복합 인덱스 추가 (content_hidden, content_type, content_id)
- ✅ DISTINCT 쿼리로 중복 ID 제거
- ✅ Middleware 5초 TTL 캐싱 추가
- ✅ Admin 체크 로직 개선 (외부 API 호출 최소화)
- ✅ HTTP 캐싱 헤더 추가 (10초 max-age)
- ✅ **SSR Pre-fetch 구현**: 초기 로딩 "깜빡임" 현상 **완전 제거**
- ✅ `home.tsx` fetchInitialData에 CP 데이터 병렬 로드 추가
- ✅ `post-listings.tsx` SSR 데이터 지원 (props.ssrReportedPostIds)
- ✅ `cp-moderation.ts` SSR 환경에서 내부 Docker 서비스 직접 호출
- ✅ 초기 로드 시 클라이언트 API 호출 0회 (네트워크 지연 완전 제거)

### v2.4 (2025-11-27)
- ✅ Ban 로그인 시 남은 일수 표시 완료
- ✅ Lemmy API "incorrect_login" 보안 정책 우회 방법 구현
- ✅ 한글/영어 이중 언어 ban 메시지
- ✅ 모든 로그인 실패 시 CP permissions API 자동 조회
- ✅ 트러블슈팅: Nginx 중첩 location 블록 문제 해결

### v2.3 (2025-11-22)
- ✅ User/Mod/Admin 3단계 권한 분리 완료
- ✅ Appeal 로직 개선 (pending만 카운트)
- ✅ SQLite WAL mode 활성화 (DB lock 해결)
- ✅ Report ability 자동 만료/복원 확인
- ✅ 사용자 메시지에 남은 일수 표시

### v2.2 (2025-11-15)
- ✅ Appeal 시스템 구현 (username 기반)
- ✅ Ban 사용자 Lemmy unban 통합
- ✅ Admin panel에 게시물 링크 추가
- ✅ 7일 appeal window 구현

### v2.1 (2025-11-14)
- ✅ Frontend CP content filtering 수정
- ✅ Lemmy ban API 통합
- ✅ Admin 인증 문제 해결

### v2.0 (2025-11-07)
- ✅ 완전한 프론트엔드 구현
- ✅ 모든 UI 컴포넌트 배포
- ✅ 백엔드 수정: 권한 엔드포인트가 기본값 반환
- ✅ oratio.space에서 운영 테스트 완료

### v1.0 (2025-11-07)
- ✅ 백엔드 완성
- ✅ 데이터베이스 스키마
- ✅ 모든 API 엔드포인트
- ✅ 백그라운드 작업

---

**문서 버전**: 2.6  
**시스템 버전**: v2.6 **운영 중**  
**상태**: ✅ 완전 배포 완료, Admin 프로필 CP 관리 통합 완료  
**마지막 업데이트**: 2026-03-24  
**배포**: oratio.space

---

## 🎉 빠른 링크

- **CP 신고**: 게시물/댓글의 점 세개 메뉴
- **모더레이터 패널**: https://oratio.space/cp/moderator-review
- **관리자 패널**: https://oratio.space/cp/admin-panel
- **이의제기 제출**: https://oratio.space/cp/appeal
- **API 상태**: https://oratio.space/payments/api/cp/health
