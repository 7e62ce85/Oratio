// 결제 확인 클라이언트
class PaymentVerifier {
  constructor(paymentId, userToken, difficulty = 4) {
    this.paymentId = paymentId;
    this.userToken = userToken;
    this.difficulty = difficulty; // 앞자리 0의 개수 (난이도)
    this.worker = null;
    this.statusElement = document.getElementById('verification-status');
    this.progressElement = document.getElementById('verification-progress');
  }
  
  // PoW 계산 시작
  startProofOfWork() {
    this.updateStatus('Starting calculation...');
    
    // Web Worker 사용하여 브라우저 차단 방지
    this.worker = new Worker('/static/js/proof-of-work-worker.js');
    
    this.worker.onmessage = (e) => {
      if (e.data.success) {
        this.updateStatus(`Proof of work completed! (${e.data.timeMs/1000} seconds elapsed)`);
        // 서버에 결과 제출
        this.submitProof(e.data.nonce, e.data.hash);
      } else if (e.data.status === 'working') {
        // 진행 상황 업데이트
        const percent = Math.min(100, e.data.timeMs / (60 * 1000) * 100).toFixed(1);
        this.updateProgress(percent);
        this.updateStatus(`Verifying payment... approximately ${percent}% complete`);
      }
    };
    
    // 작업 시작
    this.worker.postMessage({
      paymentId: this.paymentId,
      userToken: this.userToken,
      difficulty: this.difficulty
    });
  }
  
  // 서버에 증명 제출
  async submitProof(nonce, hash) {
    try {
      this.updateStatus('Submitting proof to server...');
      
      const response = await fetch('/verify-payment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paymentId: this.paymentId,
          userToken: this.userToken,
          nonce: nonce,
          hash: hash
        })
      });
      
      const result = await response.json();
      
      if (result.verified) {
        // 결제 확인 성공
        this.updateStatus('Payment verified! Redirecting...');
        setTimeout(() => {
          window.location.href = `/payment-success?id=${this.paymentId}`;
        }, 2000);
      } else if (result.powVerified) {
        // PoW는 확인됐지만 블록체인 확인은 안 됨
        this.updateStatus('Proof of work verified, but payment not yet confirmed on blockchain. Will check again shortly...');
        setTimeout(() => this.checkPaymentStatus(), 10000);
      } else {
        // 결제 확인 실패
        this.updateStatus(`Payment verification failed: ${result.reason || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('결제 확인 중 오류 발생:', error);
      this.updateStatus('Error occurred while connecting to server. Will retry shortly.');
      setTimeout(() => this.checkPaymentStatus(), 5000);
    }
  }
  
  // 결제 상태 확인
  async checkPaymentStatus() {
    try {
      const response = await fetch(`/check_payment/${this.paymentId}`);
      const result = await response.json();
      
      if (result.status === 'completed') {
        this.updateStatus('Payment verified! Redirecting...');
        setTimeout(() => {
          window.location.href = `/payment-success?id=${this.paymentId}`;
        }, 2000);
      } else if (result.status === 'paid' || result.status === 'pending') {
        this.updateStatus('Waiting for payment confirmation...');
        setTimeout(() => this.checkPaymentStatus(), 10000);
      } else {
        this.updateStatus(`Payment status: ${result.status}`);
      }
    } catch (error) {
      console.error('결제 상태 확인 중 오류 발생:', error);
    }
  }
  
  stopProofOfWork() {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
    }
  }
  
  updateStatus(message) {
    if (this.statusElement) {
      this.statusElement.textContent = message;
    }
    console.log(message);
  }
  
  updateProgress(percent) {
    if (this.progressElement) {
      this.progressElement.style.width = `${percent}%`;
      this.progressElement.setAttribute('aria-valuenow', percent);
    }
  }
}
