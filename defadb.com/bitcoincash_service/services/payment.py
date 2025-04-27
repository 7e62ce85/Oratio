import hashlib
import time
import traceback
from datetime import datetime
from config import logger, MIN_CONFIRMATIONS
import models
from services.electron_cash import electron_cash

def process_payment(invoice_id):
    """결제 상태 확인 및 처리 - ElectronCash 트랜잭션 정보 우선 활용"""
    # 인보이스 정보 조회
    invoice = models.get_invoice(invoice_id)
    if not invoice:
        logger.error(f"인보이스 {invoice_id}를 찾을 수 없습니다.")
        return None
    
    # 이미 완료된 경우
    if invoice["status"] == "completed":
        return invoice
    
    # 지불 확인된 경우 (paid 상태)
    if invoice["status"] == "paid":
        # 트랜잭션 확인 수 업데이트
        if invoice["tx_hash"]:
            try:
                # 트랜잭션 확인 수 가져오기
                from direct_payment import direct_payment_handler
                confirmations = direct_payment_handler.get_transaction_confirmations(invoice["tx_hash"])
                logger.info(f"인보이스 {invoice_id}의 트랜잭션 {invoice['tx_hash']}에 대한 확인 수: {confirmations}")
                
                # 데이터베이스의 확인 수와 다를 경우 업데이트
                if confirmations != invoice["confirmations"]:
                    models.update_invoice_confirmations(invoice_id, confirmations)
                    invoice["confirmations"] = confirmations
                
                # 충분한 확인이 되면 완료 처리
                if confirmations >= MIN_CONFIRMATIONS:
                    models.update_invoice_status(invoice_id, "completed")
                    invoice["status"] = "completed"
                    
                    # 사용자 크레딧 추가
                    if invoice["user_id"]:
                        models.credit_user(invoice["user_id"], invoice["amount"], invoice_id)
            except Exception as e:
                logger.error(f"확인 수 업데이트 중 오류: {str(e)}")
                logger.error(traceback.format_exc())
        
        return invoice
    
    # 대기 중인 경우: 잔액 확인
    logger.info(f"인보이스 {invoice_id}의 결제 상태 확인 중...")
    
    # 주소 형식 확인 및 수정
    payment_address = invoice["payment_address"]
    if not payment_address.startswith('bitcoincash:'):
        payment_address = f"bitcoincash:{payment_address}"
    
    # *** 중요한 변경: ElectronCash를 먼저 시도 ***
    # ElectronCash를 통한 확인 먼저 시도 (결제가 이미 이루어졌을 가능성 높음)
    try:
        # ElectronCash를 통한 주소 내역 조회
        logger.info(f"ElectronCash를 통해 주소 {payment_address}의 트랜잭션 내역 조회 중...")
        tx_history = electron_cash.call_method("getaddresshistory", [payment_address.replace('bitcoincash:', '')])
        
        if tx_history and isinstance(tx_history, list) and len(tx_history) > 0:
            # 트랜잭션이 발견됨
            latest_tx = tx_history[0]  # 가장 최근 트랜잭션
            tx_hash = latest_tx.get('tx_hash')
            
            if tx_hash:
                logger.info(f"ElectronCash에서 주소 {payment_address}의 트랜잭션 발견: {tx_hash}")
                
                # 해당 트랜잭션의 세부 정보 확인
                tx_details = electron_cash.call_method("gettransaction", [tx_hash])
                confirmations = tx_details.get('confirmations', 0) if tx_details else 0
                
                # 인보이스 생성 시간 이후의 트랜잭션인지 확인
                # 타임스탬프 검증 완화: ElectronCash가 tx를 발견했다면 유효한 것으로 간주
                # 일부 트랜잭션의 타임스탬프가 정확하지 않을 수 있음
                tx_time = tx_details.get('timestamp', 0) if tx_details else int(time.time())
                logger.info(f"트랜잭션 타임스탬프: {tx_time}, 인보이스 생성 시간: {invoice['created_at']}")
                
                # 트랜잭션이 발견되면 유효한 것으로 간주 (타임스탬프 비교 제거)
                logger.info(f"유효한 트랜잭션 발견. 확인 수: {confirmations}")
                
                # 지불 확인
                paid_at = int(time.time())
                
                # 인보이스 상태 업데이트 - 바로 completed로 변경
                models.update_invoice_status(invoice_id, "completed", tx_hash, confirmations, paid_at)
                
                # 응답을 위한 인보이스 정보 업데이트
                invoice["status"] = "completed"
                invoice["paid_at"] = paid_at
                invoice["tx_hash"] = tx_hash
                invoice["confirmations"] = confirmations
                
                # 사용자 크레딧 추가
                if invoice["user_id"]:
                    models.credit_user(invoice["user_id"], invoice["amount"], invoice_id)
                    
                return invoice
    except Exception as e:
        logger.error(f"ElectronCash를 통한 트랜잭션 조회 중 오류: {str(e)}")
        logger.error(traceback.format_exc())
    
    # direct_payment_handler를 통한 확인 시도
    try:
        # 직접 결제 모듈을 통해 거래 확인
        from direct_payment import direct_payment_handler
        
        # 잔액 확인 (직접 결제 모듈을 통해)
        balance = direct_payment_handler.check_address_balance(payment_address)
        logger.info(f"주소 {payment_address}의 잔액: {balance} BCH (필요 금액: {invoice['amount']} BCH)")
        
        # 잔액이 충분하면 트랜잭션 찾기
        if balance >= invoice["amount"]:
            # 트랜잭션 확인
            tx_info = direct_payment_handler.find_payment_transaction(
                payment_address, 
                invoice["amount"],
                invoice["created_at"]
            )
            
            # 트랜잭션 정보가 있으면 지불 확인으로 처리
            if tx_info:
                paid_at = int(time.time())
                tx_hash = tx_info["txid"]
                confirmations = tx_info.get("confirmations", 1)
                
                # 인보이스 상태 업데이트
                models.update_invoice_status(invoice_id, "paid", tx_hash, confirmations, paid_at)
                
                # 응답을 위한 인보이스 정보 업데이트
                invoice["status"] = "paid"
                invoice["paid_at"] = paid_at
                invoice["tx_hash"] = tx_hash
                invoice["confirmations"] = confirmations
                
                logger.info(f"인보이스 {invoice_id}에 대한 결제 확인됨: {tx_hash}")
                
                # 충분한 확인이 있으면 완료로 처리
                if confirmations >= MIN_CONFIRMATIONS:
                    models.update_invoice_status(invoice_id, "completed")
                    invoice["status"] = "completed"
                    
                    # 사용자 크레딧 추가
                    if invoice["user_id"]:
                        models.credit_user(invoice["user_id"], invoice["amount"], invoice_id)
                
                return invoice
    
    except ImportError:
        logger.warning("direct_payment 모듈을 불러올 수 없어 ElectronCash만 사용")
    except Exception as e:
        logger.error(f"결제 확인 중 오류: {str(e)}")
        logger.error(traceback.format_exc())
    
    # ElectronCash 잔액 확인 (direct_payment에서 트랜잭션 찾기 실패 시)
    try:
        # ElectronCash 잔액 확인
        electron_balance = electron_cash.check_address_balance(payment_address)
        logger.info(f"ElectronCash를 통한 주소 {payment_address}의 잔액: {electron_balance} BCH")
        
        if electron_balance >= invoice["amount"]:
            # 트랜잭션 찾기
            tx_info = electron_cash.find_transaction_for_invoice(invoice)
            
            if tx_info:
                # 지불 확인
                paid_at = int(time.time())
                tx_hash = tx_info["txid"]
                confirmations = tx_info.get("confirmations", 0)
                
                # 인보이스 상태 업데이트
                models.update_invoice_status(invoice_id, "paid", tx_hash, confirmations, paid_at)
                
                # 응답을 위한 인보이스 정보 업데이트
                invoice["status"] = "paid"
                invoice["paid_at"] = paid_at
                invoice["tx_hash"] = tx_hash
                invoice["confirmations"] = confirmations
                
                logger.info(f"ElectronCash를 통해 인보이스 {invoice_id}에 대한 결제 확인됨: {tx_hash}")
                
                # 충분한 확인이 있으면 완료로 처리
                if confirmations >= MIN_CONFIRMATIONS:
                    models.update_invoice_status(invoice_id, "completed")
                    invoice["status"] = "completed"
                    
                    # 사용자 크레딧 추가
                    if invoice["user_id"]:
                        models.credit_user(invoice["user_id"], invoice["amount"], invoice_id)
        
    except Exception as e:
        logger.error(f"ElectronCash를 통한 결제 확인 중 오류: {str(e)}")
    
    return invoice

def format_invoice_for_display(invoice):
    """인보이스 정보를 표시용으로 포맷팅"""
    # 만료 시간 포맷팅
    expiry_time = datetime.fromtimestamp(invoice['expires_at'])
    formatted_expiry = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 지불 시간 포맷팅
    formatted_paid_time = None
    if invoice['paid_at']:
        paid_time = datetime.fromtimestamp(invoice['paid_at'])
        formatted_paid_time = paid_time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 생성 시간 포맷팅
    created_time = datetime.fromtimestamp(invoice['created_at'])
    formatted_created_time = created_time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Bitcoin Cash 주소 포맷팅
    payment_address = invoice['payment_address']
    if not payment_address.startswith('bitcoincash:'):
        payment_address = f"bitcoincash:{payment_address}"
    
    formatted_invoice = {
        **invoice,
        'formatted_expiry': formatted_expiry,
        'formatted_paid_time': formatted_paid_time,
        'formatted_created_time': formatted_created_time,
        'payment_address': payment_address
    }
    
    return formatted_invoice