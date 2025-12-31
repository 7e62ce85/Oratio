# CP Hidden Post 접근 제어 수정 완료

**작업일**: 2025-11-26  
**최종 수정**: 2025-12-02  
**상태**: ✅ **성공** (2025-12-02 Moderator 접근 제어 개선 포함)

---

## 📋 문제 요약

**초기 증상**:
- CP로 신고된 게시물(`content_hidden=1`)에 **logout 사용자**뿐만 아니라 **admin도 접근 불가**
- "This content has been hidden due to moderation." 메시지 표시

**요구사항 (2025-11-26)**:
- ❌ Logout/일반 사용자 → CP 신고된 게시물 접근 차단 (403)
- ✅ Admin (`person_id=1`) → 모든 게시물 접근 가능
- ✅ Moderator (`can_review_cp=1`) → 모든 게시물 접근 가능

**요구사항 변경 (2025-12-02)**:
- ❌ Logout/일반 사용자 → CP 신고된 게시물 접근 차단 (403)
- ✅ Admin (`person_id=1`) → 모든 게시물 접근 가능 (항상)
- ⚠️ Moderator (`can_review_cp=1`) → **조건부 접근**:
  - ✅ `escalation_level='moderator'` + `status='pending'` → 검토 대기 중인 포스트 접근 가능
  - ❌ Moderator가 CP로 확인 후 (`escalation_level='admin'`) → Mod 접근 불가, Admin만 가능

---

## 🆕 2025-12-02 업데이트: Moderator 접근 권한 세분화

### 문제
이전 로직에서는 Moderator가 **모든** hidden CP 포스트에 접근 가능했음. 하지만 새로운 정책에 따르면:
1. 신고 직후 (`escalation_level='moderator'`): User ❌ / Mod ✅ / Admin ✅
2. Mod가 CP 확인 후 (`escalation_level='admin'`): User ❌ / Mod ❌ / Admin ✅
3. Admin이 최종 확인 후: 콘텐츠 영구 삭제 (User ❌ / Mod ❌ / Admin ❌)

### 해결
`cp_post_blocker.py`에 **Mod용 접근 가능 포스트 캐시** 추가:

```python
# 새로운 캐시 - Mod가 접근 가능한 포스트 (pending at moderator level)
_mod_accessible_cache = {'post_ids': set(), 'timestamp': 0}

def get_mod_accessible_post_ids():
    """Moderator가 접근 가능한 포스트 ID 목록.
    
    조건:
    - content_hidden = 1 (신고됨)
    - escalation_level = 'moderator' (아직 Mod 검토 단계)
    - status = 'pending'
    
    Mod가 CP 확인 후 (escalation_level='admin')에는 Mod도 접근 불가.
    """
    cursor.execute('''
        SELECT DISTINCT content_id FROM cp_reports 
        WHERE content_type = 'post' 
          AND content_hidden = 1 
          AND escalation_level = 'moderator'
          AND status = 'pending'
    ''')
    # ...
```

### Moderator 접근 로직 변경
```python
if row and row[0]:  # can_review_cp = 1
    mod_accessible_posts = get_mod_accessible_post_ids()
    blocked_posts = get_blocked_post_ids()
    
    if post_id in mod_accessible_posts:
        # 아직 Mod 검토 대기중 → 접근 허용
        return jsonify({"allowed": True, "moderator": True}), 200
    elif post_id in blocked_posts:
        # Admin 에스컬레이션됨 또는 이미 reviewed → Mod 접근 거부
        return jsonify({
            "allowed": False,
            "reason": "Content under admin review - moderator access revoked"
        }), 403
    else:
        # 차단 안 됨 → 일반 접근 허용
        return jsonify({"allowed": True, "moderator": True}), 200
```

### 가시성 매트릭스 (최종)

| 단계 | 상태 | User | Mod | Admin |
|------|------|------|-----|-------|
| 신고 직후 | `escalation_level='moderator'`, `status='pending'` | ❌ | ✅ | ✅ |
| Mod가 CP 확인 | `escalation_level='admin'`, `status='pending'` | ❌ | ❌ | ✅ |
| Mod가 Not CP 판정 | `content_hidden=0` | ✅ | ✅ | ✅ |
| Admin이 최종 CP 확인 | 콘텐츠 영구 삭제 | ❌ | ❌ | ❌ |
| Admin이 Not CP 판정 | `content_hidden=0` | ✅ | ✅ | ✅ |

### 수정된 파일
- `/home/user/Oratio/oratio/bitcoincash_service/middleware/cp_post_blocker.py`
  - `get_mod_accessible_post_ids()` 함수 추가
  - `check_post_access()` 엔드포인트 Mod 접근 로직 수정
  - `check_post_uri()` 엔드포인트 Mod 접근 로직 수정

---

## 🔍 근본 원인 분석

### 1단계: Nginx 라우팅 문제 (해결됨)
**문제**: 여러 nginx 설정 시도 실패
- `/api/v3/post` GET 요청에 `auth_request` 적용 시도
- PoW 시스템과 충돌
- 쿠키 전달 문제

**해결**: Nginx 접근 제어 포기, Lemmy UI SSR 단계에서 처리

### 2단계: Lemmy UI SSR 아키텍처 이해
**발견**:
- 브라우저는 `/api/v3/post` API를 직접 호출하지 않음
- Lemmy UI가 **Server-Side Rendering (SSR)**로 미리 데이터를 가져옴
- `fetchInitialData` static 메서드에서 Lemmy 백엔드에 직접 요청

**핵심 플로우**:
```
브라우저 → Nginx → Lemmy UI (SSR)
                        ↓
                   getHttpBaseInternal()
                        ↓
                 Lemmy Backend (Docker 내부)
```

### 3단계: JWT 타입 불일치 (해결됨)
**문제**: 
- JWT의 `sub` 필드가 **문자열 `"1"`**
- Python 코드에서 **숫자 `1`**과 비교
- `"1" == 1` → `False` (타입 불일치)

**해결**:
```python
# File: /home/user/Oratio/oratio/bitcoincash_service/middleware/cp_post_blocker.py
person_id = decoded.get('sub')

# JWT 'sub' can be either int or str, normalize to int
if isinstance(person_id, str):
    person_id = int(person_id) if person_id.isdigit() else None

if person_id == 1:  # Now works!
    return jsonify({"allowed": True, "admin": True}), 200
```

### 4단계: 중복 CP 체크 충돌 (해결됨)
**문제**:
- `catch-all-handler.tsx`에서 URL 기반 CP 체크 (쿠키 있음)
- `post.tsx fetchInitialData`에서도 CP 체크 (쿠키 없음)
- catch-all이 먼저 실행되어 차단, fetchInitialData는 실행 안 됨

**로그 분석**:
```
[CATCH-ALL CP CHECK] Checking post 135, cookies present: true
[CATCH-ALL CP CHECK] Post 135 response: 200
[CATCH-ALL CP CHECK] Allowing access to post 135
[CP CHECK] Checking post 135 with cookies: none  ← 쿠키 없음!
[CP CHECK] Post 135 blocked - CP report hidden
```

**해결**: catch-all-handler의 CP 체크 제거

### 5단계: 헤더 전달 문제 (최종 해결)
**문제**:
- `setForwardedHeaders()` 함수가 **쿠키를 JWT로 변환만** 하고 원본 쿠키 헤더는 제거
- `fetchInitialData`로 전달되는 `headers` 객체에 `cookie` 필드 없음

**로그 증거**:
```javascript
[CP CHECK] Headers keys: [ 'host', 'x-real-ip', 'x-forwarded-for' ]
[CP CHECK] Headers.cookie: undefined  ← 쿠키 없음!
```

**해결**:
```typescript
// File: /home/user/Oratio/lemmy-ui-custom/src/server/utils/set-forwarded-headers.ts
export function setForwardedHeaders(headers: IncomingHttpHeaders) {
  const out: { [key: string]: string } = {};
  
  // ... existing code ...
  
  // Also forward the raw cookie header for CP checks and other services
  if (headers.cookie) {
    out.cookie = headers.cookie as string;
  }
  
  return out;
}
```

---

## 🛠️ 최종 수정 사항

### 1. JWT 타입 정규화
**파일**: `/home/user/Oratio/oratio/bitcoincash_service/middleware/cp_post_blocker.py`

```python
def check_post_access(post_id):
    jwt_token = request.cookies.get('jwt')
    
    if jwt_token:
        try:
            import jwt as pyjwt
            decoded = pyjwt.decode(jwt_token, options={"verify_signature": False})
            person_id = decoded.get('sub')
            
            # JWT 'sub' can be either int or str, normalize to int
            if isinstance(person_id, str):
                person_id = int(person_id) if person_id.isdigit() else None
            
            logger.info(f"👤 [CP POST BLOCKER] Decoded person_id: {person_id} (type: {type(person_id).__name__})")
            
            if person_id == 1:
                logger.info(f"✅ [CP POST BLOCKER] Admin access to post {post_id} - ALLOWED")
                return jsonify({"allowed": True, "admin": True}), 200
            
            # Check moderator permissions...
        except Exception as e:
            logger.error(f"Error decoding JWT: {e}")
    
    # Check if post is blocked...
```

### 2. catch-all-handler CP 체크 제거
**파일**: `/home/user/Oratio/lemmy-ui-custom/src/server/handlers/catch-all-handler.tsx`

```typescript
// CP check moved to fetchInitialData in post.tsx to ensure headers are properly passed
// Keeping this commented for reference
// const postUriMatch = req.path.match(/^\/post\/(\d+)/);
// if (postUriMatch) { ... }
```

### 3. 쿠키 헤더 전달
**파일**: `/home/user/Oratio/lemmy-ui-custom/src/server/utils/set-forwarded-headers.ts`

```typescript
export function setForwardedHeaders(headers: IncomingHttpHeaders): {
  [key: string]: string;
} {
  const out: { [key: string]: string } = {};

  if (headers.host) {
    out.host = headers.host;
  }

  const realIp = headers["x-real-ip"];
  if (realIp) {
    out["x-real-ip"] = realIp as string;
  }

  const forwardedFor = headers["x-forwarded-for"];
  if (forwardedFor) {
    out["x-forwarded-for"] = forwardedFor as string;
  }

  const auth = getJwtCookie(headers);
  if (auth) {
    out["Authorization"] = `Bearer ${auth}`;
  }

  // Also forward the raw cookie header for CP checks and other services
  if (headers.cookie) {
    out.cookie = headers.cookie as string;
  }

  return out;
}
```

### 4. fetchInitialData에서 CP 체크
**파일**: `/home/user/Oratio/lemmy-ui-custom/src/shared/components/post/post.tsx`

```typescript
static async fetchInitialData({
  headers,
  match,
  query: { sort },
}: InitialFetchRequest<PostPathProps, PostProps>): Promise<PostData> {
  const client = wrapClient(
    new LemmyHttp(getHttpBaseInternal(), { headers }),
  );
  const postId = getIdFromProps({ match });
  const commentId = getCommentIdFromProps({ match });

  // CP check: Block access to CP-reported posts for non-admin/non-mod users
  try {
    const cpCheckUrl = `http://bitcoincash-service:8081/api/cp/check-post-access/${postId}`;
    const cpCheckHeaders: HeadersInit = {};
    
    // Try both lowercase and uppercase Cookie
    const cookieHeader = headers?.cookie || headers?.['Cookie'] || headers?.['cookie'];
    if (cookieHeader) {
      cpCheckHeaders.Cookie = cookieHeader;
    }
    
    console.log(`[CP CHECK] Checking post ${postId} with cookies: ${cookieHeader ? 'present' : 'none'}`);
    const cpResp = await fetch(cpCheckUrl, { headers: cpCheckHeaders });
    
    // Only block if we get explicit 403 response
    if (cpResp.status === 403) {
      console.log(`[CP CHECK] Post ${postId} blocked - CP report hidden`);
      throw new Error("Forbidden: This post has been hidden due to CP report");
    }
    
    console.log(`[CP CHECK] Post ${postId} access allowed (status: ${cpResp.status})`);
  } catch (err: any) {
    // Check if this is our intentional 403 error
    if (err?.message?.includes("Forbidden") && err.message.includes("CP report")) {
      throw err; // Re-throw our 403 errors to block access
    }
    
    // Log other errors but don't block access (service might be down)
    console.error("[CP CHECK] Error checking post access:", err);
  }

  // Continue with normal post fetching...
  const postForm: GetPost = {
    id: postId,
    comment_id: commentId,
  };

  const commentsForm: GetComments = {
    post_id: postId,
    parent_id: commentId,
    max_depth: commentTreeMaxDepth,
    sort,
    type_: "All",
    saved_only: false,
  };

  const [postRes, commentsRes] = await Promise.all([
    client.getPost(postForm),
    client.getComments(commentsForm),
  ]);

  return {
    postRes,
    commentsRes,
  };
}
```

---

## ✅ 테스트 결과

### Logout 사용자
```bash
$ curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" "https://oratio.space/post/135"
HTTP Status: 403
```
✅ **성공** - CP 신고된 게시물 차단됨

### Admin 사용자
**로그**:
```
bitcoincash-service | INFO: 🔍 [CP POST BLOCKER] Checking access to post 135
bitcoincash-service | INFO: 🍪 [CP POST BLOCKER] Cookies: ImmutableMultiDict([('jwt', 'eyJ0eXAi...')])
bitcoincash-service | INFO: 🔑 [CP POST BLOCKER] JWT token present: True
bitcoincash-service | INFO: 👤 [CP POST BLOCKER] Decoded person_id: 1 (type: int)
bitcoincash-service | INFO: ✅ [CP POST BLOCKER] Admin access to post 135 - ALLOWED
```
✅ **성공** - Admin은 CP 신고된 게시물에 접근 가능

### 정상 게시물
```bash
$ curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" "https://oratio.space/post/36"
HTTP Status: 200
```
✅ **성공** - CP 신고되지 않은 게시물은 모두 접근 가능

---

## 🎓 배운 교훈

### 1. Lemmy UI SSR 아키텍처
- **브라우저는 `/api/v3/*` 엔드포인트를 직접 호출하지 않음**
- SSR 단계에서 `fetchInitialData`가 Docker 내부 네트워크로 Lemmy 백엔드 직접 호출
- Nginx 라우팅으로 API 호출 차단 불가능

### 2. JWT 타입 주의
- JWT 라이브러리마다 `sub` 필드 타입이 다를 수 있음
- Python에서는 **항상 타입 확인 후 정규화** 필요
- `isinstance()` 체크로 안전하게 처리

### 3. 헤더 전달 메커니즘
- `setForwardedHeaders()`가 **쿠키를 JWT로 변환**하여 Authorization 헤더로 전달
- **원본 쿠키 헤더도 유지**해야 다른 서비스(CP 체크)에서 사용 가능
- SSR 환경에서 헤더 전달은 신중하게 설계 필요

### 4. 다층 체크의 위험성
- catch-all-handler와 fetchInitialData에서 **중복 체크**는 충돌 가능
- **단일 책임 원칙**: 한 곳에서만 체크하도록 설계
- 로그를 통한 디버깅이 필수

---

## 📦 배포 상태

- ✅ `bitcoincash-service` 재시작 완료
- ✅ `lemmy-ui` 재빌드 및 재시작 완료
- ✅ 프로덕션 환경 테스트 완료

**현재 운영 중**:
- Admin/Moderator는 모든 CP 신고된 게시물 접근 가능
- 일반 사용자/로그아웃 사용자는 차단됨
- 정상 게시물은 모두 정상 접근

---

## 🔗 관련 파일

1. `/home/user/Oratio/oratio/bitcoincash_service/middleware/cp_post_blocker.py`
2. `/home/user/Oratio/lemmy-ui-custom/src/server/handlers/catch-all-handler.tsx`
3. `/home/user/Oratio/lemmy-ui-custom/src/server/utils/set-forwarded-headers.ts`
4. `/home/user/Oratio/lemmy-ui-custom/src/shared/components/post/post.tsx`

---

**작성일**: 2025-11-26  
**작성자**: AI Assistant  
**최종 상태**: ✅ 완료
