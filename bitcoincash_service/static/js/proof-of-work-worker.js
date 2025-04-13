// 해시 계산용 Web Worker
self.importScripts('/static/js/sha256.js'); // SHA256 라이브러리 가져오기

self.onmessage = function(e) {
  const { paymentId, userToken, difficulty } = e.data;
  const target = '0'.repeat(difficulty); // 목표 해시값 (앞자리 0의 개수)
  
  let nonce = 0;
  let hash = '';
  const startTime = Date.now();
  
  // 작업 증명 계산
  while (true) {
    // 데이터 조합
    const data = `${paymentId}:${userToken}:${nonce}`;
    
    // 해시 계산
    hash = sha256(data);
    
    // 목표 달성 확인 (앞자리 0의 개수)
    if (hash.startsWith(target)) {
      // 성공
      self.postMessage({
        success: true,
        nonce: nonce,
        hash: hash,
        timeMs: Date.now() - startTime
      });
      break;
    }
    
    // 작업량 조정 - 1분 정도 소요되도록
    if (nonce % 10000 === 0) {
      // 주기적으로 상태 보고
      self.postMessage({
        success: false,
        status: 'working',
        progress: nonce,
        timeMs: Date.now() - startTime
      });
    }
    
    nonce++;
  }
};
