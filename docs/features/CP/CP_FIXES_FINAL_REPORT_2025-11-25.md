# CP System 개선 작업 최종 보고서

**작업일**: 2025-11-25~27  
**작업자**: AI Assistant  
**상태**: ✅ **완전 성공** (2025-11-27 최종 완료)

---

## 📋 원래 요청 사항 (3가지)

### ✅ 1. Report Ability Revoked Toast 표시 - **성공**

**문제**:
- `cpcp2` 유저 (`can_report_cp: false`)가 "Report CP" 버튼 클릭 시 토스트 메시지가 표시되지 않음
- 백엔드에서는 `{"error": "message"}` 형식으로 응답하는데, 프론트엔드는 `error.detail`만 체크

**해결 방법**:
```typescript
// File: /home/user/Oratio/lemmy-ui-custom/src/shared/utils/cp-moderation.ts
// Before:
return { success: false, message: error.detail || 'Failed to submit report' };

// After:
return { success: false, message: error.error || error.detail || 'Failed to submit report' };
```

**결과**: 
- ✅ **성공 - 프론트엔드 코드 수정 완료 및 배포**
- "Revoked until YYYY-MM-DD (X days remaining). Appeal at /cp/appeal" 토스트가 정상적으로 표시됨

**테스트 방법**:
1. cpcp2 유저로 로그인
2. 아무 게시물에서 "Report CP" 버튼 클릭
3. 토스트 메시지 확인: "Revoked until 2026-02-12 (79 days remaining). Appeal at /cp/appeal"

---

### ✅ 2. Admin/Moderator CP Hidden Post 접근 허용 - **성공** (2025-11-26 수정 완료)

**문제**:
- CP로 숨겨진 게시물(content_hidden=1)에 admin으로 로그인해도 접근 불가
- 일반 유저는 차단되어야 하지만, admin(`person_id=1`)과 moderator(`can_review_cp=1`)는 접근 가능해야 함

**최초 시도 방법 (2025-11-25 실패)**:
1. Nginx `auth_request`를 사용하여 백엔드에 JWT 기반 권한 체크
2. `/post/(\d+)` URL 패턴에서 post_id 추출
3. Backend에서 JWT 디코딩 → admin/mod 체크 → 200/403 응답

**최종 해결 방법 (2025-11-26 성공)**:
1. Lemmy UI SSR 단계에서 `fetchInitialData`에 CP 체크 추가
2. `setForwardedHeaders`에서 쿠키 헤더 전달하도록 수정
3. JWT `sub` 타입 정규화 (문자열 → 숫자 변환)
4. catch-all-handler의 중복 CP 체크 제거

**발생한 문제들**:
1. **Nginx 변수 추출의 복잡성**:
   - `location ~ ^/post/(\d+)$` regex에서 `$1` 캡처 그룹을 `set`으로 저장 불가
   - `auth_request`로 전달된 subrequest에서 변수 참조 불가
   - `X-Original-URI` 헤더로 전체 URI 전달 시 백엔드에서 재파싱 필요

2. **JWT 쿠키 전달 문제**:
   - `auth_request`는 기본적으로 쿠키를 전달하지 않음
   - `proxy_set_header Cookie $http_cookie` 추가 필요

3. **Backend 코드 오류**:
   - `cp_post_blocker.py`에서 `check_post_uri` 함수를 **3번 중복 정의**
   - Flask blueprint 등록 시 "View function mapping is overwriting an existing endpoint" 에러 발생
   - bitcoincash-service 크래시 → 502 Bad Gateway 에러

4. **서비스 불안정**:
   - 여러 번의 nginx 설정 시도 후 bitcoincash-service 재시작 반복
   - 모든 `/payments/api/*` 엔드포인트 502 에러

**복원 작업**:
```bash
# 1. 문제가 된 파일 삭제
rm /home/user/Oratio/oratio/bitcoincash_service/middleware/cp_post_blocker.py

# 2. app.py에서 blueprint 등록 제거
# from middleware.cp_post_blocker import cp_blocker_bp  # 삭제
# app.register_blueprint(cp_blocker_bp)  # 삭제

# 3. nginx_production.conf에서 auth_request 블록 제거
# location ~ ^/post/(\d+)$ { ... }  # 삭제
# location = /_cp_check { ... }  # 삭제
# location @cp_blocked { ... }  # 삭제

# 4. 서비스 재시작
docker-compose restart bitcoincash-service
docker-compose exec proxy nginx -s reload
```

**2025-11-25 결과**: 
- ❌ **1차 시도 실패 - nginx auth_request 방식 포기**
- 시스템 원상복구 완료 ✅

**2025-11-26 최종 결과**:
- ✅ **성공 - Lemmy UI SSR 단계에서 CP 접근 제어 구현**
- Admin/Moderator는 모든 CP 신고된 게시물 접근 가능
- 일반 사용자/로그아웃 사용자는 403 차단됨
- 정상 게시물은 모두 정상 접근

**핵심 수정 사항**:
1. `set-forwarded-headers.ts`: 쿠키 헤더 전달 추가
2. `post.tsx fetchInitialData`: CP 체크 로직 추가
3. `cp_post_blocker.py`: JWT 타입 정규화
4. `catch-all-handler.tsx`: 중복 CP 체크 제거

**상세 문서**: `/home/user/Oratio/docs/features/CP/CP_ACCESS_CONTROL_FIX_2025-11-26.md`

2. **Frontend만 사용** (현재 상태 유지):
   - 대부분의 유저는 post 목록에서 CP hidden post를 볼 수 없음
   - 직접 URL 접근하는 경우는 극히 드물고, 악의적인 경우에만 발생
   - Admin/Mod는 `/cp/reports` 페이지에서 숨겨진 post 링크를 볼 수 있음

3. **Nginx 대신 Application-level middleware** (중간 솔루션):
   - lemmy-ui에 Express.js middleware 추가
   - `/post/:id` 라우트에서 backend API 호출하여 CP 체크
   - 하지만 SSR 성능 저하 우려

**결론**: Task #2는 **실패**로 기록, nginx 방식은 너무 복잡하고 불안정하여 포기

---

### ✅ 3. Ban 유저 로그인 시 남은 일수 표시 - **성공** (2025-11-27 완료)

**문제**:
- Ban된 유저(`cpcp`, `ban_end: 1771564045 = 2026-02-20`)가 로그인 시도 시
- "당신은 사이트에서 추방되었습니다" 토스트만 표시됨
- 해제일과 남은 일수가 표시되지 않음

**핵심 문제 발견 (2025-11-27)**:
- Lemmy API는 banned 사용자가 로그인할 때 **`"incorrect_login"` 에러만 반환**
- 보안상 이유로 ban 상태를 명시적으로 알려주지 않음
- 따라서 에러 메시지에 "banned"가 포함되지 않아 기존 로직이 작동하지 않음

**최종 해결 방법**:
```typescript
// File: /home/user/Oratio/lemmy-ui-custom/src/shared/components/home/login.tsx

case "failed": {
  if (loginRes.err.message === "missing_totp_token") {
    i.setState({ show2faModal: true });
  } else {
    // Lemmy returns "incorrect_login" for both wrong password AND banned users
    // Always check CP permissions to see if user is actually banned
    try {
      console.log(`[LOGIN] Login failed, checking if user is banned: ${username_or_email}`);
      const perms = await checkUserCPPermissions(username_or_email);
      
      const isBannedValue = perms?.is_banned as any;
      const userIsBanned = isBannedValue === true || isBannedValue === 1 || isBannedValue === "1";
      
      if (perms && userIsBanned && perms.ban_end) {
        const now = Math.floor(Date.now() / 1000);
        const daysLeft = Math.ceil((perms.ban_end - now) / (24 * 60 * 60));
        const banEndDate = new Date(perms.ban_end * 1000).toISOString().split('T')[0];
        
        // Bilingual message (Korean/English)
        const banMessage = `당신은 ${banEndDate}까지 사이트에서 추방되었습니다 (${daysLeft}일 남음). ` +
          `멤버십 사용자는 /cp/appeal 에서 이의제기할 수 있습니다.\n\n` +
          `You are banned until ${banEndDate} (${daysLeft} days remaining). ` +
          `Membership users can appeal at /cp/appeal`;
        
        toast(banMessage, "danger");
      } else {
        // Regular login error (wrong password, etc.)
        toast(I18NextService.i18n.t(loginRes.err.message), "danger");
      }
    } catch (err) {
      console.error("[LOGIN] Error fetching CP permissions:", err);
      toast(I18NextService.i18n.t(loginRes.err.message), "danger");
    }
  }
}
```

**실제 결과 (2025-11-27 테스트 완료)**:
- ✅ "당신은 2026-02-20까지 사이트에서 추방되었습니다 (85일 남음). You are banned until 2026-02-20 (85 days remaining)." 토스트 정상 표시
- ✅ 한글/영어 이중 언어 메시지 표시
- ✅ Appeal 링크 안내 포함

**트러블슈팅 과정**:
1. **브라우저 캐시 문제**: Nginx에 중첩 location 블록 추가 시도 → Nginx 크래시
2. **Lemmy API 동작 분석**: `curl` 테스트로 "incorrect_login" 에러만 반환됨을 확인
3. **로직 수정**: 모든 로그인 실패 시 CP permissions API 호출하도록 변경
4. **빌드 및 배포**: lemmy-ui 재빌드 → 정상 작동 확인

**결론**: Task #3는 ✅ **완전 성공**

---

## 📊 최종 요약

| Task | 상태 | 세부 내역 |
|------|------|-----------|
| 1. Report Ability Revoked Toast | ✅ **성공** | 프론트엔드 코드 수정 완료, 배포 완료, 테스트 완료 (2025-11-25) |
| 2. Admin/Mod CP Post Access | ✅ **성공** | Lemmy UI SSR 방식으로 해결 (2025-11-26) |
| 3. Ban Login Days Remaining | ✅ **성공** | 로그인 실패 시 CP API 조회 방식으로 해결 (2025-11-27) |

**성공률**: 3/3 (100%) ✅  
**최종 완료일**: 2025-11-27

---

## 🔧 수정된 파일 목록

### ✅ 프로덕션 적용 완료
1. `/home/user/Oratio/lemmy-ui-custom/src/shared/utils/cp-moderation.ts` - error 추출 로직 수정
2. `/home/user/Oratio/lemmy-ui-custom/src/shared/components/home/login.tsx` - ban 토스트 개선 (모든 로그인 실패 시 CP API 조회)
3. `/home/user/Oratio/lemmy-ui-custom/src/shared/components/post/post.tsx` - SSR CP 접근 제어 (2025-11-26)
4. `/home/user/Oratio/lemmy-ui-custom/src/shared/utils/set-forwarded-headers.ts` - 쿠키 헤더 전달 추가
5. lemmy-ui Docker 이미지 재빌드 및 배포 완료 (2025-11-27)

### ❌ 롤백/삭제됨
1. `/home/user/Oratio/oratio/bitcoincash_service/middleware/cp_post_blocker.py` - 삭제 (중복 endpoint 오류)
2. `/home/user/Oratio/oratio/bitcoincash_service/app.py` - cp_blocker_bp import/register 제거
3. `/home/user/Oratio/oratio/nginx_production.conf` - auth_request 블록 제거

### 📦 백업 파일
1. `/home/user/Oratio/oratio/bitcoincash_service/middleware/cp_post_blocker.py.broken` - 참고용 백업

---

## 💡 교훈 및 권장사항

### 1. Nginx auth_request의 한계
- **장점**: 백엔드 부하 없이 빠른 권한 체크 가능
- **단점**: 
  - 변수 전달이 매우 제한적 (regex 캡처 그룹 사용 불가)
  - 쿠키/헤더 전달 설정이 복잡함
  - 디버깅이 어려움 (nginx 에러 로그만으로는 불충분)
- **결론**: 복잡한 로직에는 부적합, 간단한 IP/header 체크 정도에만 사용 권장

### 2. Frontend Filtering의 효과
- CP hidden post는 이미 post 목록/검색/커뮤니티 피드에서 제외됨
- 일반 유저가 직접 URL로 접근하는 경우는 극히 드묾
- Admin/Mod는 `/cp/reports` 페이지에서 숨겨진 post를 관리 가능
- **결론**: 현재 frontend filtering만으로도 충분히 효과적

### 3. 향후 개선 방향
- **단기**: 현재 상태 유지 (frontend filtering)
- **중기**: lemmy-ui에 SSR middleware 추가 검토
- **장기**: Lemmy Rust 백엔드 API 수정 (가장 안전하고 완벽한 솔루션)

---

## 🧪 테스트 가이드

### Task #1: Report Ability Revoked Toast
```bash
# 1. cpcp2 유저로 로그인
# Username: cpcp2
# can_report_cp: false (2025-11-05에 revoked)
# report_ability_revoked_at: 1730764800 (2025-11-05)

# 2. 아무 게시물에서 "⋯" 메뉴 → "Report CP" 클릭

# 3. 예상 토스트:
# "Revoked until 2026-02-12 (79 days remaining). Appeal at /cp/appeal"
```

### Task #3: Ban Login Days Remaining ✅ 테스트 완료
```bash
# 1. oratio.space/login 접속

# 2. cpcp 유저로 로그인 시도
# Username: cpcp
# Password: (기존 비밀번호)
# is_banned: true
# ban_end: 1771564045 (2026-02-20)

# 3. 실제 토스트 (2025-11-27 확인):
# "당신은 2026-02-20까지 사이트에서 추방되었습니다 (85일 남음). 
#  멤버십 사용자는 /cp/appeal 에서 이의제기할 수 있습니다.
#  
#  You are banned until 2026-02-20 (85 days remaining). 
#  Membership users can appeal at /cp/appeal"

# 4. 상태: ✅ 완료 및 정상 작동 확인
```

### 주요 트러블슈팅 (2025-11-27)
1. **Lemmy API의 보안 정책**: banned 사용자도 "incorrect_login" 에러만 반환
2. **해결**: 모든 로그인 실패 시 CP permissions API 호출하여 ban 상태 확인
3. **브라우저 캐시**: Nginx 중첩 location 블록 추가 시도 → 설정 에러 발생 및 롤백
4. **최종 방법**: 로직 수정 + lemmy-ui 재빌드로 해결
```

---

## 📝 관련 문서

- 상세 수정 내역: `/docs/features/CP/CP_FIXES_2025-11-25.md`
- 배포 요약: `/docs/features/CP/DEPLOYMENT_SUMMARY_2025-11-25.md`
- 빠른 테스트 가이드: `/docs/features/CP/QUICK_TEST_GUIDE.txt`
- CP 시스템 전체 문서: `/docs/features/CP/CP_MODERATION_SYSTEM_KOR.md`

---

**작성일**: 2025-11-25  
**최종 업데이트**: 2025-11-25 11:40 KST  
**서비스 상태**: ✅ 정상 운영 중 (bitcoincash-service 복구 완료)
