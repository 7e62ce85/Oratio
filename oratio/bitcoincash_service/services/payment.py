import hashlib
import time
import traceback
from datetime import datetime
from config import (
    logger, MIN_CONFIRMATIONS, ZERO_CONF_ENABLED, 
    ZERO_CONF_DELAY_SECONDS, ZERO_CONF_MIN_FEE_PERCENT,
    ZERO_CONF_DOUBLE_SPEND_CHECK
)
import models
from services.electron_cash import electron_cash
from zero_conf_validator import get_validator

def process_payment(invoice_id):
    """결제 상태 확인 및 처리 - ElectronCash 트랜잭션 정보 우선 활용"""
    # 인보이스 정보 조회
    invoice = models.get_invoice(invoice_id)
    if not invoice:
        logger.error(f"인보이스 {invoice_id}를 찾을 수 없습니다.")
        return None
    
    # 이미 완료된 경우
    if invoice["status"] == "completed":
        logger.info(f"인보이스 {invoice_id}는 이미 completed 상태입니다. 스킵합니다.")
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
                    # ★ Race Condition 방지: 상태 업데이트 전 DB에서 최신 상태 재확인
                    fresh_invoice = models.get_invoice(invoice_id)
                    if fresh_invoice and fresh_invoice["status"] == "completed":
                        logger.warning(f"⚠️ Race Condition 방지 (paid→completed): 인보이스 {invoice_id}가 이미 completed. 스킵.")
                        return fresh_invoice
                    
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
    
    # *** Zero-Confirmation 검증 ***
    # ElectronCash를 통한 확인 먼저 시도
    try:
        # ElectronCash를 통한 주소 내역 조회
        logger.info(f"ElectronCash를 통해 주소 {payment_address}의 트랜잭션 내역 조회 중...")
        tx_history = electron_cash.call_method("getaddresshistory", [payment_address.replace('bitcoincash:', '')])
        
        if tx_history and isinstance(tx_history, list) and len(tx_history) > 0:
            # 트랜잭션이 발견됨
            latest_tx = tx_history[0]  # 가장 최근 트랜잭션
            tx_hash = latest_tx.get('tx_hash')
            tx_height = latest_tx.get('height', 0)  # height가 0이면 unconfirmed
            
            if tx_hash:
                logger.info(f"ElectronCash에서 주소 {payment_address}의 트랜잭션 발견: {tx_hash}")
                logger.info(f"트랜잭션 높이: {tx_height} (0 = unconfirmed)")
                
                # 확인 수 계산 (height가 0이면 unconfirmed)
                confirmations = 0 if tx_height == 0 else 1  # 간단하게 처리
                
                logger.info(f"트랜잭션 확인 수: {confirmations} (최소 요구: {MIN_CONFIRMATIONS})")
                
                # Zero-Conf 검증 실행
                if ZERO_CONF_ENABLED and confirmations < MIN_CONFIRMATIONS:
                    logger.info(f"🔍 Zero-Conf 검증 시작 (딜레이: {ZERO_CONF_DELAY_SECONDS}초)")
                    
                    # 선택적 딜레이 (이중지불 초기 체크)
                    if ZERO_CONF_DELAY_SECONDS > 0:
                        logger.info(f"이중지불 초기 체크를 위해 {ZERO_CONF_DELAY_SECONDS}초 대기 중...")
                        time.sleep(ZERO_CONF_DELAY_SECONDS)
                        
                        # 딜레이 후 다시 확인 (이중지불 시도가 있었는지)
                        tx_history_recheck = electron_cash.call_method("getaddresshistory", [payment_address.replace('bitcoincash:', '')])
                        if not tx_history_recheck or len(tx_history_recheck) == 0:
                            logger.error(f"딜레이 후 트랜잭션을 찾을 수 없음: {tx_hash}")
                            return invoice
                        # 트랜잭션이 여전히 존재하는지 확인
                        found = any(tx.get('tx_hash') == tx_hash for tx in tx_history_recheck)
                        if not found:
                            logger.error(f"딜레이 후 트랜잭션이 사라짐 (이중지불 가능성): {tx_hash}")
                            return invoice
                    
                    # Zero-Conf Validator로 검증 (단순화된 버전 - ElectronCash 한계로 인해)
                    # ElectronCash가 getrawtransaction을 지원하지 않으므로 기본 체크만 수행
                    try:
                        # 주소 잔액 확인으로 대체
                        balance = electron_cash.check_address_balance(payment_address)
                        logger.info(f"주소 잔액 확인: {balance} BCH (예상: {invoice['amount']} BCH)")
                        
                        if balance >= invoice['amount'] * 0.99999:  # 0.001% 오차 허용
                            logger.info(f"✅ Zero-Conf 기본 검증 성공: 충분한 잔액")
                        else:
                            logger.error(f"❌ Zero-Conf 검증 실패: 잔액 부족 ({balance} < {invoice['amount']})")
                            return invoice
                        
                    except Exception as e:
                        logger.error(f"Zero-Conf 검증 중 오류: {str(e)}")
                        logger.error(traceback.format_exc())
                        # 검증 오류 시 안전하게 pending 유지
                        return invoice
                
                # 지불 확인 (Zero-Conf 검증 통과 또는 충분한 확인 수)
                paid_at = int(time.time())
                
                # 확인 수에 따라 상태 결정
                if confirmations >= MIN_CONFIRMATIONS or (ZERO_CONF_ENABLED and confirmations == 0):
                    # 즉시 완료 처리
                    status = "completed"
                    logger.info(f"✅ 결제 완료 처리: {tx_hash} (confirmations={confirmations})")
                else:
                    # 확인 대기 상태
                    status = "paid"
                    logger.info(f"⏳ 확인 대기 상태: {tx_hash} (confirmations={confirmations}/{MIN_CONFIRMATIONS})")
                
                # ★ Race Condition 방지: 상태 업데이트 전 DB에서 최신 상태 재확인
                fresh_invoice = models.get_invoice(invoice_id)
                if fresh_invoice and fresh_invoice["status"] == "completed":
                    logger.warning(f"⚠️ Race Condition 방지: 인보이스 {invoice_id}가 이미 다른 스레드에서 completed 처리됨. 중복 크레딧 방지.")
                    return fresh_invoice
                
                # 인보이스 상태 업데이트
                models.update_invoice_status(invoice_id, status, tx_hash, confirmations, paid_at)
                
                # 응답을 위한 인보이스 정보 업데이트
                invoice["status"] = status
                invoice["paid_at"] = paid_at
                invoice["tx_hash"] = tx_hash
                invoice["confirmations"] = confirmations
                
                # completed 상태이면 크레딧 추가
                if status == "completed" and invoice["user_id"]:
                    models.credit_user(invoice["user_id"], invoice["amount"], invoice_id)
                    logger.info(f"💰 사용자 크레딧 추가: {invoice['amount']} BCH")
                    
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
                
                # ★ Race Condition 방지: 상태 업데이트 전 DB에서 최신 상태 재확인
                fresh_invoice = models.get_invoice(invoice_id)
                if fresh_invoice and fresh_invoice["status"] == "completed":
                    logger.warning(f"⚠️ Race Condition 방지 (direct_payment): 인보이스 {invoice_id}가 이미 completed. 스킵.")
                    return fresh_invoice
                
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
                
                # ★ Race Condition 방지: 상태 업데이트 전 DB에서 최신 상태 재확인
                fresh_invoice = models.get_invoice(invoice_id)
                if fresh_invoice and fresh_invoice["status"] == "completed":
                    logger.warning(f"⚠️ Race Condition 방지 (electron_cash fallback): 인보이스 {invoice_id}가 이미 completed. 스킵.")
                    return fresh_invoice
                
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