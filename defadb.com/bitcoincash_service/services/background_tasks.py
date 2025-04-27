import threading
import time
from config import logger, FORWARD_PAYMENTS
import models
from services.electron_cash import electron_cash
from services.payment import process_payment

def cleanup_expired_invoices():
    """만료된 인보이스 처리"""
    count = models.expire_pending_invoices()
    return count

def update_paid_invoices():
    """지불 확인된 인보이스의 상태 업데이트"""
    # 지불 확인된 인보이스 목록 조회
    paid_invoices = models.get_paid_invoices()
    
    for invoice_id, tx_hash in paid_invoices:
        # 모의 트랜잭션은 건너뛰기
        if tx_hash and not tx_hash.startswith("mock_tx_"):
            # 결제 처리 로직 실행
            process_payment(invoice_id)

def check_pending_invoices():
    """대기 중인 인보이스 상태 확인"""
    # 대기 중인 인보이스 목록 조회
    pending_invoices = models.get_pending_invoices()
    
    for invoice_id in pending_invoices:
        process_payment(invoice_id)

def run_background_tasks():
    """백그라운드 작업 처리"""
    while True:
        try:
            # 만료된 인보이스 처리
            cleanup_expired_invoices()
            
            # 대기 중인 인보이스 상태 확인
            check_pending_invoices()
            
            # 지불 확인된 인보이스 업데이트
            update_paid_invoices()
            
            # 주기적으로 자금 전송 시도 (설정에 따라)
            if FORWARD_PAYMENTS:
                electron_cash.forward_to_payout_wallet()
                
        except Exception as e:
            logger.error(f"백그라운드 작업 오류: {str(e)}")
        
        # 5분마다 실행
        time.sleep(300)

def start_background_tasks():
    """백그라운드 작업 시작"""
    # 백그라운드 스레드 시작
    background_thread = threading.Thread(target=run_background_tasks)
    background_thread.daemon = True
    background_thread.start()
    
    logger.info("백그라운드 작업 시작됨")
    return background_thread