/**
 * Proof of Work (PoW) 유틸리티
 * SHA-256 기반 해시캐시 알고리즘 구현
 * 
 * 작동 원리:
 * 1. 서버에서 챌린지(난수) 받음
 * 2. nonce를 0부터 증가시키며 해시 계산
 * 3. 해시가 난이도 조건을 만족할 때까지 반복
 * 4. 조건: 해시의 앞 N개 비트가 0이어야 함
 */

/**
 * SHA-256 해시 계산 (Web Crypto API 사용)
 */
async function sha256(message: string): Promise<string> {
  const msgBuffer = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  return hashHex;
}

/**
 * 해시의 앞 N비트가 0인지 확인
 * @param hash - 16진수 해시 문자열
 * @param difficulty - 앞에서부터 0이어야 하는 비트 수
 */
function checkDifficulty(hash: string, difficulty: number): boolean {
  // 16진수를 2진수로 변환
  const binary = hash
    .split('')
    .map(hex => parseInt(hex, 16).toString(2).padStart(4, '0'))
    .join('');
  
  // 앞 difficulty 비트가 모두 0인지 확인
  return binary.substring(0, difficulty).split('').every(bit => bit === '0');
}

/**
 * PoW 계산
 * @param challenge - 서버에서 받은 챌린지 문자열
 * @param difficulty - 난이도 (앞에서부터 0이어야 하는 비트 수, 기본값: 19)
 * @param onProgress - 진행률 콜백 함수 (0-100)
 * @returns nonce와 해시 솔루션
 */
export async function computeProofOfWork(
  challenge: string,
  difficulty: number = 20,
  onProgress?: (progress: number, attemptCount: number) => void
): Promise<{ nonce: number; hash: string; attempts: number }> {
  
  let nonce = 0;
  // 난이도 20 기준: 평균 1,048,576번 시도 필요
  // 최대 시도 횟수를 평균의 5배로 제한 (운이 매우 나쁜 경우도 커버)
  // 5배 초과 시 새 챌린지로 재시도하는 게 더 빠름
  const expectedAttempts = Math.pow(2, difficulty);
  const maxAttempts = Math.min(expectedAttempts * 5, 10000000);
  const progressInterval = 10000; // 진행률 업데이트 간격
  
  // UI 블로킹 방지: 일정 간격으로 이벤트 루프에 제어권 반환
  const yieldInterval = 50000; // 50,000번마다 yield
  
  while (nonce < maxAttempts) {
    // 챌린지 + nonce를 합쳐서 해시 계산
    const input = `${challenge}:${nonce}`;
    const hash = await sha256(input);
    
    // 난이도 조건 확인
    if (checkDifficulty(hash, difficulty)) {
      // 성공! 솔루션 발견
      if (onProgress) {
        onProgress(100, nonce);
      }
      return { nonce, hash, attempts: nonce };
    }
    
    nonce++;
    
    // 진행률 업데이트
    if (onProgress && nonce % progressInterval === 0) {
      const progress = Math.min(95, (nonce / maxAttempts) * 100);
      onProgress(progress, nonce);
    }
    
    // UI 블로킹 방지: 주기적으로 이벤트 루프에 제어권 반환
    if (nonce % yieldInterval === 0) {
      await new Promise(resolve => setTimeout(resolve, 0));
    }
  }
  
  // 최대 시도 횟수 초과 - 새 챌린지로 재시도 권장
  throw new Error(`PoW computation exceeded maximum attempts (${maxAttempts}). Please try again with a new challenge.`);
}

/**
 * PoW 솔루션 검증 (클라이언트 측 사전 검증)
 * @param challenge - 챌린지 문자열
 * @param nonce - 계산된 nonce
 * @param hash - 계산된 해시
 * @param difficulty - 난이도
 */
export async function verifyProofOfWork(
  challenge: string,
  nonce: number,
  hash: string,
  difficulty: number = 20
): Promise<boolean> {
  // 1. 해시 재계산
  const input = `${challenge}:${nonce}`;
  const computedHash = await sha256(input);
  
  // 2. 해시 일치 확인
  if (computedHash !== hash) {
    return false;
  }
  
  // 3. 난이도 조건 확인
  return checkDifficulty(hash, difficulty);
}

/**
 * 난이도에 따른 예상 소요 시간 계산 (초 단위)
 * @param difficulty - 난이도 (비트 수)
 * @returns 예상 소요 시간 (초)
 */
export function estimateComputationTime(difficulty: number): number {
  // 평균 해시 속도: 약 100,000 hashes/sec (브라우저 기준)
  const hashesPerSecond = 100000;
  const expectedAttempts = Math.pow(2, difficulty);
  return expectedAttempts / hashesPerSecond;
}

/**
 * 난이도 레벨 프리셋
 */
export const POW_DIFFICULTY_PRESETS = {
  VERY_EASY: 16,    // ~0.65ms
  EASY: 18,         // ~2.6ms
  MEDIUM: 20,       // ~10ms
  HARD: 22,         // ~40ms
  VERY_HARD: 24,    // ~160ms
  EXTREME: 26,      // ~640ms
} as const;

/**
 * 난이도 레벨에 따른 설명
 */
export function getDifficultyDescription(difficulty: number): string {
  if (difficulty <= 16) return '매우 쉬움 (1초 이하)';
  if (difficulty <= 18) return '쉬움 (1-3초)';
  if (difficulty <= 20) return '보통 (3-10초)';
  if (difficulty <= 22) return '어려움 (10-40초)';
  if (difficulty <= 24) return '매우 어려움 (40-160초)';
  return '극한 (160초 이상)';
}
