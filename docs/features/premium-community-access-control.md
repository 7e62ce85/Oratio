# Premium Community Access Control Implementation

## 개요 (Overview)

골드 뱃지(0.0001 BCH 이상 크레딧 보유) 사용자만 특정 커뮤니티에 접근할 수 있도록 제한하는 기능을 구현했습니다.

## 구현 완료 사항 (Implementation Completed)

### 1. 유틸리티 함수 (Utility Functions)

#### `bch-payment.ts`에 추가된 함수들:

```typescript
// 프리미엄 커뮤니티 목록 (설정 가능)
const PREMIUM_COMMUNITIES = ['test']; // 나중에 변경 가능

// 커뮤니티가 프리미엄인지 확인
export function isPremiumCommunity(communityName: string): boolean

// 사용자가 프리미엄 커뮤니티에 접근 가능한지 확인 (비동기)
export async function canAccessPremiumCommunity(communityName: string, person?: Person): Promise<boolean>

// 사용자가 프리미엄 커뮤니티에 접근 가능한지 확인 (동기)
export function canAccessPremiumCommunitySync(communityName: string, person?: Person): boolean
```

### 2. 커뮤니티 페이지 접근 제어 (`community.tsx`)

- 커뮤니티 페이지 렌더링 전에 접근 권한 확인
- 권한이 없는 경우 경고 메시지 표시:
  - 🔒 아이콘과 함께 "프리미엄 커뮤니티 접근 필요" 메시지
  - 로그인하지 않은 경우: 로그인 링크 제공
  - 로그인했으나 크레딧 부족: 결제 페이지 링크 제공

### 3. 게시글 페이지 접근 제어 (`post.tsx`)

- 게시글이 속한 커뮤니티가 프리미엄인지 확인
- 권한이 없는 경우 동일한 경고 메시지 표시
- 메인 화면에서 프리미엄 커뮤니티의 게시글 클릭 시에도 접근 차단

### 4. 시각적 표시 (`community-link.tsx`)

- 프리미엄 커뮤니티 이름 옆에 🔒 아이콘 표시
- 사용자가 클릭하기 전에 프리미엄 커뮤니티임을 알 수 있음

## 작동 방식 (How It Works)

### 접근 제어 로직

```typescript
// 1. 커뮤니티 이름 확인
const communityName = "test";
const isPremium = isPremiumCommunity(communityName);

// 2. 현재 사용자 정보 가져오기
const currentUser = UserService.Instance.myUserInfo?.local_user_view.person;

// 3. 접근 권한 확인 (캐시 사용)
const hasAccess = canAccessPremiumCommunitySync(communityName, currentUser);

// 4. 접근 거부 시 경고 메시지 표시
if (isPremium && !hasAccess) {
  return <AccessDeniedMessage />;
}
```

### 캐싱 메커니즘

- 기존 골드 뱃지 시스템과 동일한 `creditCache` 사용
- 5분간 캐시 유지
- 캐시가 없을 경우 백그라운드에서 API 호출하여 업데이트
- 초기 로드 시 `false` 반환 후, 캐시 업데이트 시 자동 리렌더링

## 설정 방법 (Configuration)

### 프리미엄 커뮤니티 목록 변경

`/lemmy-ui-custom/src/shared/utils/bch-payment.ts` 파일에서 수정:

```typescript
// 원하는 커뮤니티 이름 추가
const PREMIUM_COMMUNITIES = ['test', 'premium', 'vip'];
```

### 최소 크레딧 요구사항 변경

현재는 `0.0001 BCH`로 하드코딩되어 있습니다. 필요시 함수 내부의 비교 값을 수정:

```typescript
// bch-payment.ts 내부
return cached.credit >= 0.0001; // 이 값을 변경
```

## 테스트 시나리오 (Test Scenarios)

### ✅ 테스트 완료

1. **로그인하지 않은 사용자**
   - `/c/test` 접근 시 → 접근 거부 + 로그인 링크
   - 테스트 커뮤니티의 게시글 클릭 → 접근 거부

2. **크레딧이 없는 로그인 사용자**
   - `/c/test` 접근 시 → 접근 거부 + 결제 페이지 링크
   - 테스트 커뮤니티의 게시글 클릭 → 접근 거부

3. **골드 뱃지 사용자 (0.0001 BCH 이상)**
   - `/c/test` 접근 시 → 정상 접근
   - 테스트 커뮤니티의 게시글 클릭 → 정상 접근
   - 게시글 작성, 댓글 작성 가능

4. **일반 커뮤니티**
   - 모든 사용자가 정상 접근 가능
   - 기존 동작에 영향 없음

5. **시각적 표시**
   - 커뮤니티 목록에서 'test' 옆에 🔒 아이콘 표시

## 기술 세부사항 (Technical Details)

### 수정된 파일 목록

1. `/lemmy-ui-custom/src/shared/utils/bch-payment.ts`
   - `isPremiumCommunity()` 추가
   - `canAccessPremiumCommunity()` 추가
   - `canAccessPremiumCommunitySync()` 추가

2. `/lemmy-ui-custom/src/shared/components/community/community.tsx`
   - Import: `isPremiumCommunity`, `canAccessPremiumCommunitySync`, `Link`
   - `render()` 메서드에 접근 제어 로직 추가

3. `/lemmy-ui-custom/src/shared/components/post/post.tsx`
   - Import: `isPremiumCommunity`, `canAccessPremiumCommunitySync`, `Link`
   - `renderPostRes()` 메서드에 접근 제어 로직 추가

4. `/lemmy-ui-custom/src/shared/components/community/community-link.tsx`
   - Import: `isPremiumCommunity`, `Icon`
   - `avatarAndName()` 메서드에 🔒 아이콘 표시 로직 추가

### 환경 변수

기존 골드 뱃지 시스템과 동일한 환경 변수 사용:
- `LEMMY_API_KEY` - BCH API 인증 키
- `LEMMY_BCH_API_URL` - BCH 크레딧 조회 API URL
- `LEMMY_BCH_PAYMENT_URL` - BCH 결제 페이지 URL

## 향후 개선 사항 (Future Improvements)

1. **설정 파일 기반 관리**
   - 하드코딩 대신 설정 파일에서 프리미엄 커뮤니티 목록 관리
   - 관리자 인터페이스를 통한 동적 관리

2. **다단계 접근 레벨**
   - Bronze (0.0001 BCH): 일부 커뮤니티 접근
   - Silver (0.001 BCH): 더 많은 커뮤니티 접근
   - Gold (0.01 BCH): 모든 프리미엄 커뮤니티 접근

3. **세밀한 권한 제어**
   - 읽기 전용 vs 쓰기 권한 분리
   - 게시글 작성은 허용하되 댓글만 제한 등

4. **알림 시스템**
   - 사용자가 접근하려는 커뮤니티가 프리미엄일 때 사전 알림
   - 크레딧 부족 시 자동 충전 유도

5. **통계 및 분석**
   - 프리미엄 커뮤니티 접근 시도 통계
   - 전환율 분석 (접근 거부 → 크레딧 충전)

## 골드 뱃지와의 연동

이 기능은 기존 골드 뱃지 시스템과 완벽하게 통합되어 있습니다:
- 동일한 크레딧 캐시 사용
- 동일한 API 엔드포인트 호출
- 동일한 최소 크레딧 기준 (0.0001 BCH)

골드 뱃지가 사용자 이름 옆에 표시되는 사용자는 자동으로 프리미엄 커뮤니티 접근 권한을 갖습니다.

---

**작성일**: 2025-10-06  
**버전**: 1.0  
**참조 문서**: [GOLD_BADGE_SYSTEM.md](./GOLD_BADGE_SYSTEM.md)
