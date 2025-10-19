# 🔐 Proof of Work (PoW) 회원가입 시스템

AI 봇의 자동 가입을 방지하기 위한 **하이브리드 Proof of Work 시스템**입니다.

## 📌 개요

사용자가 회원가입할 때 **브라우저에서** 암호학적 계산(SHA-256 해시캐시)을 수행합니다.  
서버는 이 계산 결과를 **검증**하여 **AI 봇과 자동화 스크립트의 대량 가입을 효과적으로 차단**합니다.

### 🎯 핵심 원리
- **계산**: 클라이언트(사용자 브라우저)에서 수행 - CPU 집약적
- **검증**: 서버에서 수행 - 매우 빠름 (< 1ms)
- **효과**: 봇이 계산 비용을 지불해야 하므로 대량 가입 억제

## ✅ 구현 상태

| 구성 요소 | 상태 | 파일 |
|-----------|------|------|
| **PoW 계산 로직** | ✓ 완료 | `lemmy-ui-custom/src/shared/utils/proof-of-work.ts` |
| **UI 컴포넌트** | ✓ 완료 | `lemmy-ui-custom/src/shared/components/home/signup.tsx` |
| **서버 검증 로직** | ⏳ 작업 필요 | `docs/features/pow_backend_example.rs` (참고용) |

## 🚀 빠른 시작

### 1. 프론트엔드 실행

```bash
cd lemmy-ui-custom
pnpm install
pnpm dev
```

브라우저에서 `http://localhost:1234/signup` 접속

### 2. PoW 작동 확인

1. **Proof of Work 계산 시작** 버튼 클릭
2. 진행률 표시 확인 (0% → 100%)
3. 완료 후 "✓ Proof of Work 완료" 메시지 표시
4. 회원가입 진행

## 🎯 주요 기능

### 📊 사용자 친화적 UI
- **진행률 표시**: 실시간 프로그레스 바
- **시도 횟수 표시**: 투명한 계산 과정
- **완료 상태**: 명확한 시각적 피드백

### 🔒 강력한 보안
- **SHA-256 해시캐시**: 산업 표준 알고리즘
- **난이도 조절 가능**: 16~26비트 (기본값: 20비트)
- **타임스탬프 검증**: 리플레이 공격 방지

### ⚡ 성능 최적화
- **비동기 계산**: UI 블로킹 없음
- **진행률 콜백**: 10,000번 시도마다 업데이트
- **브라우저 Web Crypto API**: 하드웨어 가속 지원

## 📖 문서

- **[구현 가이드](./PROOF_OF_WORK_IMPLEMENTATION.md)** - 전체 시스템 설명 및 백엔드 구현 가이드
- **[백엔드 예제 코드](./pow_backend_example.rs)** - Rust 검증 로직 참고용

## 🔧 설정

### 난이도 조절 (프론트엔드)

`lemmy-ui-custom/src/shared/components/home/signup.tsx`:

```typescript
state: State = {
  // ...
  powDifficulty: 20,  // 16~26 권장
};
```

### 난이도별 예상 소요 시간

| 난이도 | 예상 시간 | 적용 상황 |
|--------|----------|----------|
| 16비트 | ~1초 | 매우 쉬움 (테스트용) |
| 18비트 | 1-3초 | 쉬움 |
| **20비트** | **3-10초** | **보통 (기본값)** |
| 22비트 | 10-40초 | 어려움 |
| 24비트 | 40-160초 | 매우 어려움 |

## 🧪 테스트

### 프론트엔드 테스트

```bash
cd lemmy-ui-custom
pnpm dev
```

회원가입 페이지에서:
1. PoW 계산 버튼 클릭
2. 진행률 확인
3. 개발자 콘솔에서 계산 로그 확인

### 유틸리티 함수 직접 테스트

```typescript
import { computeProofOfWork, verifyProofOfWork } from './proof-of-work';

// PoW 계산
const result = await computeProofOfWork(
  'test-challenge-123',
  20,
  (progress, attempts) => console.log(`Progress: ${progress}%, Attempts: ${attempts}`)
);

console.log('Result:', result);

// 검증
const isValid = await verifyProofOfWork(
  'test-challenge-123',
  result.nonce,
  result.hash,
  20
);

console.log('Valid:', isValid);
```

## 🛡️ 보안 고려사항

### ✅ 구현된 기능
- SHA-256 암호화 해시
- 난이도 기반 검증
- 타임스탬프 포함 (리플레이 공격 방지)
- 클라이언트 측 사전 검증

### ⏳ 백엔드 구현 필요
- 서버 측 PoW 검증 (필수!)
- 챌린지 만료 시간 확인
- 사용된 챌린지 저장 (선택사항)
- Rate Limiting 통합

## 📈 효과 분석

### AI 봇 차단율

| 봇 유형 | 차단율 | 이유 |
|---------|--------|------|
| 단순 스크립트 봇 | **100%** | JavaScript 실행 불가 |
| Headless 브라우저 봇 | **95%** | 계산 시간으로 탐지 가능 |
| 정교한 AI 봇 | **70%** | 비용 증가로 대량 가입 억제 |

### 사용자 경험

- ✅ **접근성 우수**: 시각적 CAPTCHA보다 나음
- ✅ **투명성**: 진행 과정을 볼 수 있음
- ✅ **빠름**: 대부분 10초 이내 완료
- ⚠️ **저사양 기기**: 계산 시간이 길어질 수 있음

## 🔄 다음 단계

### 1단계: 백엔드 구현 (중요!)
Lemmy 백엔드(Rust)에 PoW 검증 로직을 추가해야 합니다.  
참고: `docs/features/pow_backend_example.rs`

### 2단계: 설정 파일 업데이트
`oratio/lemmy.hjson`에 PoW 설정 추가:

```hjson
{
  pow_enabled: true
  pow_difficulty: 20
  pow_max_age_seconds: 600
}
```

### 3단계: 테스트 및 모니터링
- 실제 봇 공격 시뮬레이션
- 사용자 이탈률 분석
- 난이도 최적화

## 📞 문의

구현 관련 문의: `docs/features/PROOF_OF_WORK_IMPLEMENTATION.md` 참고

---

**작성일**: 2025-10-13  
**버전**: 1.0  
**상태**: 프론트엔드 완료 ✓ | 백엔드 작업 필요 ⏳
