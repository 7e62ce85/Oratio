# Gold Badge & Premium Community Access System

## 개요

Oratio 플랫폼의 Gold Badge 시스템은 BCH(Bitcoin Cash) 크레딧 기반의 프리미엄 기능 제공 시스템입니다. 사용자가 일정 금액 이상의 BCH 크레딧을 보유하면 다음과 같은 혜택을 받을 수 있습니다:

1. **Gold Badge (💰)** - 사용자 이름 옆에 표시되는 프리미엄 배지
2. **Premium Community Access** - 제한된 커뮤니티에 대한 접근 권한
3. **광고 제거** - 충분한 크레딧 보유 시 광고 비노출

## 시스템 구성

### 1. Gold Badge (골드 배지)

#### 조건
- **최소 크레딧**: `0.0001 BCH` 이상

#### 표시 위치
- 게시글 작성자 이름 옆
- 댓글 작성자 이름 옆
- 프로필 페이지
- 투표 목록 (View Votes Modal)
- 네비게이션 바 (로그인한 사용자)

#### 구현 파일
- `/lemmy-ui-custom/src/shared/utils/bch-payment.ts`
  - `checkUserHasGoldBadge()` - 비동기 크레딧 확인
  - `checkUserHasGoldBadgeSync()` - 동기 캐시 기반 확인
  - `creditCache` - 5분간 유효한 크레딧 캐시

- `/lemmy-ui-custom/src/shared/components/common/user-badges.tsx`
  - Gold Badge 렌더링 컴포넌트

### 2. Premium Community Access (프리미엄 커뮤니티 접근 제어)

#### 조건
- **최소 크레딧**: `0.0001 BCH` 이상 (Gold Badge와 동일)

#### 제한 커뮤니티 설정
현재 설정된 프리미엄 커뮤니티:
```typescript
const PREMIUM_COMMUNITIES = ['test'];
```

#### 접근 제어 위치
1. **커뮤니티 페이지** (`/c/{community_name}`)
   - 권한 없는 사용자에게 경고 메시지 표시
   - 로그인/결제 링크 제공

2. **게시글 페이지** (`/post/{post_id}`)
   - 프리미엄 커뮤니티의 게시글 직접 접근 차단
   - 메인 페이지에서 게시글 클릭 시에도 동일하게 차단

3. **커뮤니티 링크**
   - 프리미엄 커뮤니티 이름 옆에 자물쇠 아이콘 (🔒) 표시

#### 구현 파일
- `/lemmy-ui-custom/src/shared/utils/bch-payment.ts`
  - `isPremiumCommunity()` - 커뮤니티 프리미엄 여부 확인
  - `canAccessPremiumCommunity()` - 비동기 접근 권한 확인
  - `canAccessPremiumCommunitySync()` - 동기 접근 권한 확인

- `/lemmy-ui-custom/src/shared/components/community/community.tsx`
  - 커뮤니티 페이지 접근 제어

- `/lemmy-ui-custom/src/shared/components/post/post.tsx`
  - 게시글 페이지 접근 제어

- `/lemmy-ui-custom/src/shared/components/community/community-link.tsx`
  - 프리미엄 커뮤니티 시각적 표시 (자물쇠 아이콘)

### 3. 광고 제거

#### 조건
- **최소 크레딧**: `0.0003 BCH` 이상

#### 구현
- `/lemmy-ui-custom/src/shared/components/common/ad-banner.tsx`
  - 크레딧 확인 후 광고 렌더링 여부 결정

## 기술 구현

### 캐싱 시스템

모든 크레딧 확인은 5분간 유효한 캐시를 사용합니다:

```typescript
export const creditCache = new Map<number, { credit: number; timestamp: number }>();
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
```

#### 캐시 업데이트 전략

1. **Navbar의 fetchUserCredit()**
   - 사용자 로그인 시 크레딧 API 호출
   - 응답 받으면 `updateCreditCache()` 호출하여 공유 캐시 업데이트
   - **중요**: 0 값은 캐시하지 않음 (API의 간헐적 0 반환 방지)

2. **checkUserHasGoldBadge()**
   - 캐시 확인 → 있으면 반환
   - 없으면 API 호출 → 결과 캐시 저장

3. **checkUserHasGoldBadgeSync()**
   - 캐시 확인 → 있으면 즉시 반환
   - 없으면 백그라운드에서 `checkUserHasGoldBadge()` 호출
   - 첫 렌더링에서는 `false` 반환, 캐시 업데이트 후 재렌더링 시 `true` 표시

### API 통신

#### 엔드포인트
```
GET {BCH_API_URL}/{user_id}
Header: X-API-Key: {LEMMY_API_KEY}
```

#### 응답 형식
```json
{
  "credit_balance": 0.0001
}
```

#### 환경 변수
- `LEMMY_BCH_API_URL`: BCH API 서버 URL (기본값: `http://localhost:8081/api/user_credit`)
- `LEMMY_API_KEY`: API 인증 키
- `LEMMY_BCH_PAYMENT_URL`: BCH 결제 페이지 URL (기본값: `http://localhost:8081/`)

클라이언트에서는 `window.__BCH_CONFIG__`를 통해 접근:
```typescript
window.__BCH_CONFIG__ = {
  API_URL: process.env.LEMMY_BCH_API_URL,
  API_KEY: process.env.LEMMY_API_KEY,
  PAYMENT_URL: process.env.LEMMY_BCH_PAYMENT_URL
};
```

### 접근 제어 UI

#### 권한 없는 사용자에게 표시되는 메시지

```tsx
<div className="alert alert-warning" role="alert">
  <h4 className="alert-heading">
    <Icon icon="lock" classes="icon-inline me-2" />
    This is a Premium Community
  </h4>
  <p>
    Access to this community requires a Gold Badge (💰). 
    You need at least 0.0001 BCH in credits to access premium communities.
  </p>
  <hr />
  <p className="mb-0">
    {!isLoggedIn && (
      <>
        Please <Link to="/login">log in</Link> and{" "}
      </>
    )}
    <a href={getBCHPaymentUrl()} target="_blank" rel="noopener noreferrer">
      charge your account
    </a>{" "}
    to gain access.
  </p>
</div>
```

## 문제 해결 가이드

### 골드 배지가 표시되지 않을 때

1. **캐시 확인**
   - 브라우저 콘솔에서 에러 확인
   - 페이지 새로고침으로 캐시 갱신

2. **API 응답 확인**
   - BCH API 서버 상태 확인
   - API 키 환경 변수 설정 확인

3. **크레딧 확인**
   - 실제 사용자 크레딧이 0.0001 BCH 이상인지 확인
   - API가 간헐적으로 0을 반환할 수 있음 (새로고침으로 해결)

### 프리미엄 커뮤니티 접근이 안 될 때

1. **Gold Badge 확인**
   - 사용자 이름 옆에 💰 배지가 있는지 확인

2. **커뮤니티 설정 확인**
   - `bch-payment.ts`의 `PREMIUM_COMMUNITIES` 배열 확인

3. **로그인 상태 확인**
   - 로그인하지 않은 사용자는 항상 접근 불가

## 프리미엄 커뮤니티 추가 방법

`/lemmy-ui-custom/src/shared/utils/bch-payment.ts` 파일을 수정:

```typescript
// 변경 전
const PREMIUM_COMMUNITIES = ['test'];

// 변경 후 (예시)
const PREMIUM_COMMUNITIES = ['test', 'premium', 'vip'];
```

빌드 및 배포:
```bash
cd /home/user/Oratio/oratio
docker-compose stop lemmy-ui
docker-compose rm -f lemmy-ui
docker rmi lemmy-ui-custom:latest
docker-compose build lemmy-ui
docker-compose up -d lemmy-ui
```

## 관련 문서

- [Premium Community Access Control](./premium-community-access-control.md) - 프리미엄 커뮤니티 접근 제어 상세 구현
- [BCH Payment Integration](../../bitcoincash_service/TECHNICAL_REPORT.md) - BCH 결제 시스템 기술 문서

## 버전 이력

### 2025-10-06
- Gold Badge 시스템 구현
- Premium Community Access 기능 추가
- 캐시 시스템 개선 (0 값 캐싱 방지)
- 디버그 로그 제거

### 이전
- BCH 크레딧 기반 광고 제거 기능
- BCH Payment Button 통합
