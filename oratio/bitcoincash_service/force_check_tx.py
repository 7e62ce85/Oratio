#!/usr/bin/env python3
"""
트랜잭션 강제 확인 스크립트
특정 인보이스 ID에 대한 트랜잭션을 강제로 다시 확인합니다.
"""

import sys
import json
import time
import logging
from config import logger
from models import get_db_connection, get_invoice_by_id
from services.electron_cash import electron_cash

def force_check_transaction(invoice_id):
    """특정 인보이스 ID에 대한 트랜잭션을 강제로 확인합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 인보이스 가져오기
    invoice = get_invoice_by_id(invoice_id)
    if not invoice:
        logger.error(f"인보이스를 찾을 수 없습니다: {invoice_id}")
        return False
    
    logger.info(f"인보이스 정보: {json.dumps(invoice, indent=2)}")
    
    # 주소 잔액 확인
    address = invoice["payment_address"]
    balance = electron_cash.check_address_balance(address)
    logger.info(f"주소 {address}의 잔액: {balance} BCH")
    
    if balance >= invoice["amount"]:
        logger.info(f"잔액이 충분합니다: {balance} BCH >= {invoice['amount']} BCH")
        
        # 트랜잭션 찾기 시도
        tx = electron_cash.find_transaction_for_invoice(invoice)
        if tx:
            logger.info(f"트랜잭션을 찾았습니다: {json.dumps(tx, indent=2)}")
            
            # 인보이스 상태 업데이트
            cursor.execute(
                "UPDATE invoices SET status = 'paid', tx_hash = ?, paid_at = ? WHERE id = ?",
                (tx["txid"], int(time.time()), invoice_id)
            )
            conn.commit()
            logger.info(f"인보이스 {invoice_id}가 결제 완료 상태로 업데이트되었습니다.")
            
            # 주소의 완전한 거래 내역 가져오기 (디버깅 용도)
            try:
                history = electron_cash.call_method("history")
                if history:
                    logger.info(f"지갑 거래 내역 (최대 3개): {json.dumps(history[:3], indent=2)}")
            except Exception as e:
                logger.error(f"거래 내역 가져오기 실패: {str(e)}")
            
            return True
        else:
            logger.warning(f"잔액은 충분하지만 트랜잭션을 찾지 못했습니다.")
            
            # 트랜잭션이 없어도 잔액이 충분하면 결제로 간주할지 결정
            force_confirm = input("잔액이 충분하지만 트랜잭션을 찾지 못했습니다. 강제로 결제 완료 처리하시겠습니까? (y/n): ")
            if force_confirm.lower() == 'y':
                # 고유한 트랜잭션 ID 생성
                import hashlib
                unique_string = f"{invoice_id}:{address}:{invoice['amount']}:{time.time()}"
                hash_object = hashlib.sha256(unique_string.encode())
                local_txid = f"manual_{hash_object.hexdigest()[:32]}"
                
                # 인보이스 상태 업데이트
                cursor.execute(
                    "UPDATE invoices SET status = 'paid', tx_hash = ?, paid_at = ? WHERE id = ?",
                    (local_txid, int(time.time()), invoice_id)
                )
                conn.commit()
                logger.info(f"인보이스 {invoice_id}가 수동으로 결제 완료 처리되었습니다.")
                return True
    else:
        logger.warning(f"잔액이 부족합니다: {balance} BCH < {invoice['amount']} BCH")
    
    conn.close()
    return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: python3 force_check_tx.py <invoice_id>")
        sys.exit(1)
    
    invoice_id = sys.argv[1]
    result = force_check_transaction(invoice_id)
    
    if result:
        print(f"인보이스 {invoice_id}가 결제 완료 처리되었습니다.")
    else:
        print(f"인보이스 {invoice_id}의 결제를 확인할 수 없습니다.")