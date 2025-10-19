# AdBanner BCH 잔고 새로고침 문제 해결

## 📋 문제 개요
**날짜**: 2025-10-06  
**증상**: 로그인 직후 AdBanner 컴포넌트에서 BCH 임계값이 제대로 적용되지 않고, 페이지 새로고침(F5) 후에야 정상 작동함  
**영향 범위**: 모든 광고 배너 (헤더, 사이드바, 피드, 댓글 섹션)

## 🔍 원인 분석

### **근본 원인**
Navbar와 동일한 문제: 로그인 직후 `UserService.Instance.myUserInfo`가 즉시 설정되지 않아 BCH 크레딧 체크가 실행되지 않음

### **상세 분석**

1. **로그인 프로세스의 비동기 특성**
   ```typescript
   // UserService.login() - JWT 토큰만 설정
   public login({ res }: { res: LoginResponse }) {
     setAuthCookie(res.jwt);
     this.#setAuthInfo(); // authInfo만 설정, myUserInfo는 설정 안됨
   }
   ```

2. **AdBanner의 타이밍 문제**
   ```typescript
   // componentDidMount에서 실행
   componentDidMount() {
     this.checkUserCredit(); // ← UserService.myUserInfo가 null이면 실행 안됨
   }
   
   async checkUserCredit() {
     const userInfo = UserService.Instance.myUserInfo;
     if (!userInfo) {
       this.setState({ showAd: true }); // ← 광고 표시
       return; // ← 여기서 종료
     }
     // ... BCH 크레딧 체크 로직
   }
   ```

3. **새로고침이 필요했던 이유**
   - 페이지 새로고침 시 서버사이드 렌더링(SSR)에서 이미 `myUserInfo`가 설정된 상태로 시작
   - 따라서 `checkUserCredit()`가 정상 실행됨

## 🛠️ 해결 방법

### **적용된 수정사항**

#### **1. componentDidMount 재시도 로직 추가**
```typescript
componentDidMount() {
  console.log("[AdBanner] componentDidMount called");
  
  // Check user credit if already logged in
  if (UserService.Instance.myUserInfo) {
    this.checkUserCredit();
  } else {
    // If user info not available yet, retry after a short delay
    setTimeout(() => {
      if (UserService.Instance.myUserInfo && this.state.creditBalance === null) {
        console.log("[AdBanner] Retrying credit check after initial delay");
        this.checkUserCredit();
      }
    }, 1000);
  }
}
```

#### **2. componentDidUpdate 추가**
```typescript
componentDidUpdate(_prevProps: AdBannerProps) {
  // Check if user info became available in UserService
  if (UserService.Instance.myUserInfo && 
      this.state.isCheckingCredit === false && 
      this.state.creditBalance === null) {
    console.log("[AdBanner] User info detected in componentDidUpdate, rechecking credit");
    this.checkUserCredit();
  }
}
```

#### **3. checkUserCredit 내부 재시도**
```typescript
async checkUserCredit() {
  const userInfo = UserService.Instance.myUserInfo;
  
  if (!userInfo) {
    console.log("[AdBanner] No user info - showing ads");
    
    // Retry once after a short delay in case login is still in progress
    setTimeout(() => {
      const retryUserInfo = UserService.Instance.myUserInfo;
      if (retryUserInfo && this.state.creditBalance === null) {
        console.log("[AdBanner] Retrying credit check after delay");
        this.checkUserCredit();
      } else {
        this.setState({ showAd: true, isCheckingCredit: false });
      }
    }, 2000);
    
    return;
  }
  
  // ... BCH 크레딧 체크 로직
}
```

## 📊 수정된 파일

**파일**: `/home/user/Oratio/lemmy-ui-custom/src/shared/components/common/ad-banner.tsx`

**변경 사항**:
1. `componentDidMount()` - 재시도 로직 추가 (1초 지연)
2. `componentDidUpdate()` - 새로 추가 (사용자 정보 감지)
3. `checkUserCredit()` - 내부 재시도 로직 추가 (2초 지연)

## ✅ 기대 효과

### **사용자 경험 개선**
1. **로그인 직후 즉시 BCH 임계값 적용** - 새로고침 불필요
2. **광고 숨김 기능 즉시 작동** - 0.0003 BCH 이상 보유시
3. **모든 광고 배너에 일관된 동작** - 헤더, 사이드바, 피드, 댓글

### **기술적 개선**
1. **다층 재시도 메커니즘**:
   - 1차: componentDidMount (1초 후)
   - 2차: componentDidUpdate (즉시)
   - 3차: checkUserCredit 내부 (2초 후)

2. **로그인 과정의 비동기 특성 대응**
3. **네트워크 지연 상황 대응**

## 🔍 디버깅 방법

### **브라우저 콘솔 로그 확인**
```javascript
// 정상 작동시 로그 순서:
[AdBanner] Constructor called with props: {...}
[AdBanner] Initial ad content set in constructor
[AdBanner] componentDidMount called
[AdBanner] checkUserCredit - userInfo: exists
[AdBanner] Attempting to fetch credit for user ID 1
[AdBanner] API URL: http://localhost:8081/api/user_credit/1
[AdBanner] Using API key: J4P...
[AdBanner] API response status: 200
[AdBanner] Response data: {credit_balance: 0.0005}
[AdBanner] Credit balance: 0.0005 BCH
[AdBanner] Credit check: 0.0005 BCH >= 0.0003 BCH threshold
[AdBanner] Decision: HIDE ads
```

### **재시도 로직 작동시 로그**
```javascript
// 로그인 진행 중일 때:
[AdBanner] componentDidMount called
[AdBanner] checkUserCredit - userInfo: null
[AdBanner] No user info - showing ads
// 1초 후:
[AdBanner] Retrying credit check after initial delay
[AdBanner] checkUserCredit - userInfo: exists
// ... 정상 크레딧 체크 진행
```

## 🧪 테스트 방법

### **1. 로그인 시나리오 테스트**
```bash
1. 로그아웃 상태에서 시작
2. 개발자 도구 콘솔 열기
3. 로그인 수행
4. 광고 배너가 즉시 사라지는지 확인 (0.0003 BCH 이상 보유시)
5. 콘솔 로그에서 [AdBanner] 메시지 확인
```

### **2. 수동 테스트**
```javascript
// 브라우저 콘솔에서 실행
console.log("User Info:", UserService.Instance.myUserInfo);
console.log("BCH Config:", window.__BCH_CONFIG__);
```

## 📝 관련 문서

- [Navbar BCH Balance Fix](./electron-cash-fix-2025-08.md) - 동일한 문제의 Navbar 버전
- [Environment Variables Flow](../deployment/environment-variables-flow.md) - 환경변수 전달 체계
- [BCH Payment System](../features/bch-payment-system.md) - BCH 결제 시스템 전체 문서
- [Advertisement Feasibility Analysis](/home/user/Oratio/lemmy-ui-custom/ADVERTISEMENT_FEASIBILITY_ANALYSIS.md) - 광고 시스템 분석

## 🎯 요약

**문제**: 로그인 직후 AdBanner의 BCH 임계값이 적용되지 않고 새로고침 필요  
**원인**: `UserService.Instance.myUserInfo`가 로그인 직후 즉시 설정되지 않음  
**해결**: 3단계 재시도 로직으로 비동기 로그인 과정 대응  
**결과**: 새로고침 없이 로그인 직후 즉시 BCH 임계값 적용 ✅

---

**작성일**: 2025-10-06  
**버전**: 1.0  
**마지막 업데이트**: 2025-10-06  
**관련 이슈**: Navbar BCH Balance Refresh 문제와 동일 근본 원인
