# Gold Badge F5 Refresh Display Fix

## 문제 상황 (Problem Description)

### 증상 (Symptoms)
- 처음 internet address에 URL 입력 시: Gold badge 안 보임
- SIGNIN 후: Gold badge 보임
- 내부 button click (게시글 제목 등)으로 페이지 이동: Gold badge 계속 보임
- 새로고침(F5) 후: Gold badge 다시 안 보임
- 로그인하지 않은 상태에서도 내부 button click 시 badge 보임 (캐시된 경우)

### 근본 원인 (Root Cause)
`checkUserHasGoldBadgeSync()` 함수가 동기 함수로 설계되어 있어:
1. 캐시에 데이터가 없으면 즉시 `false`를 반환
2. 백그라운드에서 비동기 API 호출을 트리거
3. API 응답이 돌아와도 컴포넌트가 자동으로 재렌더링되지 않음

따라서 F5 새로고침이나 첫 페이지 로드 시:
- 캐시가 비어있음
- 컴포넌트들이 렌더링될 때 `false`를 받음
- Gold badge가 표시되지 않음
- Navbar가 나중에 크레딧을 가져와도 이미 렌더링된 컴포넌트는 업데이트되지 않음

## 해결 방법 (Solution)

### 이벤트 기반 캐시 업데이트 시스템 (Event-Based Cache Update System)

크레딧 캐시가 업데이트될 때 커스텀 이벤트를 발송하여 모든 관련 컴포넌트가 자동으로 재렌더링되도록 구현했습니다.

### 수정된 파일들 (Modified Files)

#### 1. `/lemmy-ui-custom/src/shared/utils/bch-payment.ts`

**변경사항:**
- `CREDIT_CACHE_UPDATE_EVENT` 상수 추가
- `updateCreditCache()` 함수에서 이벤트 발송
- `checkUserHasGoldBadge()` 함수에서도 캐시 업데이트 시 이벤트 발송

```typescript
// Event name for credit cache updates
const CREDIT_CACHE_UPDATE_EVENT = 'bch-credit-cache-updated';

// Function to manually update the credit cache (for use by other components)
export function updateCreditCache(userId: number, credit: number) {
  creditCache.set(userId, { credit, timestamp: Date.now() });
  
  // Dispatch custom event to notify components that cache was updated
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(CREDIT_CACHE_UPDATE_EVENT, { 
      detail: { userId, credit } 
    }));
  }
}
```

#### 2. `/lemmy-ui-custom/src/shared/components/post/post-listing.tsx`

**변경사항:**
- `creditUpdateListener` 속성 추가
- `componentWillMount()`에서 이벤트 리스너 등록
- `componentWillUnmount()`에서 이벤트 리스너 제거

```typescript
creditUpdateListener?: () => void;

componentWillMount(): void {
  // ... existing code ...
  
  // Listen for credit cache updates to refresh gold badge display
  this.creditUpdateListener = () => {
    this.forceUpdate();
  };
  
  if (typeof window !== 'undefined') {
    window.addEventListener('bch-credit-cache-updated', this.creditUpdateListener);
  }
}

componentWillUnmount(): void {
  this.unlisten();
  
  // Remove credit update listener
  if (typeof window !== 'undefined' && this.creditUpdateListener) {
    window.removeEventListener('bch-credit-cache-updated', this.creditUpdateListener);
  }
}
```

#### 3. `/lemmy-ui-custom/src/shared/components/comment/comment-node.tsx`

PostListing과 동일한 패턴으로 이벤트 리스너 추가.

#### 4. `/lemmy-ui-custom/src/shared/components/person/profile.tsx`

PostListing과 동일한 패턴으로 이벤트 리스너 추가.

#### 5. `/lemmy-ui-custom/src/shared/components/common/modal/view-votes-modal.tsx`

PostListing과 동일한 패턴으로 이벤트 리스너 추가.

#### 6. `/lemmy-ui-custom/src/shared/components/app/navbar.tsx`

**변경사항:**
- `creditUpdateListener` 속성 추가
- `componentWillMount()`에서 이벤트 리스너 등록
- `componentWillUnmount()`에서 이벤트 리스너 제거

Navbar도 다른 컴포넌트가 캐시를 업데이트할 때 자동으로 재렌더링되도록 개선.

## 작동 원리 (How It Works)

### 시나리오 1: F5 새로고침 또는 첫 페이지 로드

1. 페이지 로드 → 모든 컴포넌트 마운트
2. 각 컴포넌트가 `'bch-credit-cache-updated'` 이벤트 리스너 등록
3. 컴포넌트들이 렌더링 (캐시 없어서 badge 안 보임)
4. Navbar가 `fetchUserCredit()` 호출
5. API 응답 받음 → `updateCreditCache()` 호출
6. `updateCreditCache()`가 커스텀 이벤트 발송
7. **모든 리스너가 이벤트 받고 `forceUpdate()` 호출**
8. **모든 컴포넌트 재렌더링 → Gold badge 표시됨!**

### 시나리오 2: 내부 네비게이션 (Button Click)

1. 사용자가 게시글 제목 클릭
2. 새 페이지 컴포넌트 마운트
3. 컴포넌트가 `checkUserHasGoldBadgeSync()` 호출
4. **캐시에 데이터 있음 → 즉시 `true` 반환**
5. 첫 렌더링부터 Gold badge 표시됨 ✓

### 시나리오 3: 로그인 후

1. 사용자 로그인
2. Navbar의 `componentDidUpdate()` 트리거
3. `fetchUserCredit()` 호출
4. API 응답 → `updateCreditCache()` → 이벤트 발송
5. 모든 컴포넌트 재렌더링
6. Gold badge 표시됨 ✓

## 장점 (Benefits)

1. **반응성 (Reactivity)**: 크레딧 변경 시 모든 컴포넌트가 자동으로 업데이트
2. **일관성 (Consistency)**: 모든 위치에서 동일한 badge 상태 표시
3. **확장성 (Scalability)**: 새로운 컴포넌트도 쉽게 이벤트 리스너 추가 가능
4. **성능 (Performance)**: 필요할 때만 재렌더링, 불필요한 API 호출 없음
5. **디버깅 (Debugging)**: 이벤트 기반이라 흐름 추적 쉬움

## 테스트 시나리오 (Test Scenarios)

### 테스트 1: F5 새로고침
1. oratio.space 접속 (로그인된 상태)
2. F5 눌러 새로고침
3. **예상**: 페이지 로드 후 약 1초 내에 Gold badge 표시됨

### 테스트 2: 직접 URL 접속
1. 브라우저 주소창에 `https://oratio.space/post/123` 입력
2. Enter
3. **예상**: 페이지 로드 후 Gold badge 표시됨

### 테스트 3: 내부 네비게이션
1. 홈 페이지에서 게시글 제목 클릭
2. **예상**: 즉시 Gold badge 표시됨 (캐시 사용)

### 테스트 4: 로그아웃/로그인
1. 로그아웃
2. **예상**: Gold badge 사라짐
3. 로그인
4. **예상**: Gold badge 나타남

### 테스트 5: 비로그인 상태
1. 로그아웃 또는 시크릿 모드
2. 페이지 접속
3. **예상**: Gold badge 안 보임 (정상)

## 주의사항 (Notes)

1. **브라우저 호환성**: `CustomEvent` API는 모던 브라우저에서만 지원됨 (IE는 폴리필 필요)
2. **메모리 누수 방지**: 모든 컴포넌트가 `componentWillUnmount()`에서 리스너 제거 필수
3. **이벤트 이름**: `'bch-credit-cache-updated'`는 전역 이벤트명이므로 충돌 주의

## 관련 파일 (Related Files)

- `/lemmy-ui-custom/src/shared/utils/bch-payment.ts` - 캐시 관리 및 이벤트 발송
- `/lemmy-ui-custom/src/shared/components/post/post-listing.tsx` - 게시글 목록
- `/lemmy-ui-custom/src/shared/components/comment/comment-node.tsx` - 댓글
- `/lemmy-ui-custom/src/shared/components/person/profile.tsx` - 프로필 페이지
- `/lemmy-ui-custom/src/shared/components/common/modal/view-votes-modal.tsx` - 투표 모달
- `/lemmy-ui-custom/src/shared/components/app/navbar.tsx` - 네비게이션 바
- `/lemmy-ui-custom/src/shared/components/common/user-badges.tsx` - Badge 렌더링

## 이전 문제 해결 방법과의 차이 (Comparison with Previous Approach)

### 이전 방법
- Navbar만 크레딧 가져옴
- 다른 컴포넌트는 캐시만 읽음
- 캐시 없으면 badge 안 보임

### 현재 방법
- Navbar가 크레딧 가져옴
- **이벤트로 모든 컴포넌트에 알림**
- 모든 컴포넌트 자동 재렌더링
- badge 항상 정확하게 표시됨

---

**수정일**: 2025-10-19  
**버전**: 1.0  
**상태**: ✅ 적용 완료
