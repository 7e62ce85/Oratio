#!/usr/bin/env python3
# manual_tx_check.py - 트랜잭션 수동 확인 및 처리 도구
import requests
import json
import sqlite3
import os
import time
import argparse
from datetime import datetime

# 환경 변수에 따른 설정
DB_PATH = os.environ.get('DB_PATH', '/data/payments.db')

def connect_db():
    """데이터베이스 연결"""
    return sqlite3.connect(DB_PATH)

def check_invoice(invoice_id):
    """인보이스 정보 확인"""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, payment_address, amount, status, created_at, expires_at, user_id 
        FROM invoices WHERE id = ?
    """, (invoice_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print(f"인보이스 없음: {invoice_id}")
        return None
        
    invoice = {
        "id": result[0],
        "payment_address": result[1],
        "amount": result[2],
        "status": result[3],
        "created_at": datetime.fromtimestamp(result[4]).strftime('%Y-%m-%d %H:%M:%S'),
        "expires_at": datetime.fromtimestamp(result[5]).strftime('%Y-%m-%d %H:%M:%S'),
        "user_id": result[6]
    }
    
    print("\n인보이스 정보:")
    for key, value in invoice.items():
        print(f"  {key}: {value}")
    
    return invoice

def check_transaction(address, tx_id=None):
    """블록체인에서 트랜잭션 확인"""
    # API URL 목록 (여러 API 시도)
    apis = [
        f"https://bch-chain.api.btc.com/v3/address/{address}",
        f"https://api.blockchair.com/bitcoin-cash/dashboards/address/{address}"
    ]
    
    for api_url in apis:
        try:
            print(f"\n{api_url} 확인 중...")
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                print("API 연결 성공!")
                data = response.json()
                print(f"응답: {json.dumps(data)[:200]}...")
                return True
        except Exception as e:
            print(f"API 오류: {str(e)}")
    
    return False

def manual_confirm(invoice_id, tx_hash=None):
    """인보이스 수동 확인 처리"""
    if not tx_hash:
        tx_hash = f"manual_{invoice_id}"
    
    conn = connect_db()
    cursor = conn.cursor()
    
    now = int(time.time())
    
    # 인보이스 상태 업데이트
    cursor.execute("""
        UPDATE invoices 
        SET status = 'paid', paid_at = ?, tx_hash = ?, confirmations = ? 
        WHERE id = ?
    """, (now, tx_hash, 1, invoice_id))
    
    # 인보이스 다시 조회
    cursor.execute("""
        SELECT user_id, amount FROM invoices WHERE id = ?
    """, (invoice_id,))
    result = cursor.fetchone()
    
    if result:
        user_id, amount = result
        
        # 크레딧 추가
        cursor.execute("""
            INSERT INTO user_credits (user_id, credit_balance, last_updated) 
            VALUES (?, ?, ?) 
            ON CONFLICT(user_id) DO UPDATE 
            SET credit_balance = credit_balance + ?, last_updated = ?
        """, (user_id, amount, now, amount, now))
        
        # 트랜잭션 기록
        transaction_id = f"manual_{invoice_id}"
        cursor.execute("""
            INSERT INTO transactions 
            (id, user_id, amount, type, description, created_at, invoice_id) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (transaction_id, user_id, amount, "credit", "수동 확인 처리", now, invoice_id))
    
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"\n인보이스 {invoice_id} 수동 확인 처리 완료")
    print(f"영향받은 레코드: {rows_affected}")
    if result:
        print(f"사용자 {user_id}에게 {amount} BCH 크레딧 추가됨")
    
    return rows_affected > 0

def list_pending_invoices():
    """미결 인보이스 목록 조회"""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, payment_address, amount, status, created_at, expires_at, user_id 
        FROM invoices 
        WHERE status IN ('pending', 'expired') 
        ORDER BY created_at DESC 
        LIMIT 20
    """)
    results = cursor.fetchall()
    conn.close()
    
    print("\n미결 인보이스 목록:")
    print(f"{'ID':<36} | {'상태':<8} | {'금액':<10} | {'주소':<45} | {'생성일시':<20} | {'사용자'}")
    print("-" * 130)
    
    for row in results:
        invoice_id, address, amount, status, created_at, expires_at, user_id = row
        print(f"{invoice_id} | {status:<8} | {amount:<10.8f} | {address} | {datetime.fromtimestamp(created_at).strftime('%Y-%m-%d %H:%M:%S')} | {user_id}")
    
    return results

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="BCH 결제 시스템 관리 도구")
    parser.add_argument("--db", help="데이터베이스 경로")
    
    subparsers = parser.add_subparsers(dest="command", help="명령")
    
    # 인보이스 확인 명령
    check_parser = subparsers.add_parser("check", help="인보이스 확인")
    check_parser.add_argument("invoice_id", help="인보이스 ID")
    
    # 트랜잭션 확인 명령
    tx_parser = subparsers.add_parser("tx", help="트랜잭션 확인")
    tx_parser.add_argument("address", help="지갑 주소")
    tx_parser.add_argument("--tx_id", help="트랜잭션 ID")
    
    # 수동 확인 명령
    confirm_parser = subparsers.add_parser("confirm", help="인보이스 수동 확인")
    confirm_parser.add_argument("invoice_id", help="인보이스 ID")
    confirm_parser.add_argument("--tx_hash", help="트랜잭션 해시")
    
    # 목록 명령
    list_parser = subparsers.add_parser("list", help="미결 인보이스 목록")
    
    args = parser.parse_args()
    
    # 데이터베이스 경로 설정
    if args.db:
        global DB_PATH
        DB_PATH = args.db
    
    # 명령 처리
    if args.command == "check":
        check_invoice(args.invoice_id)
    elif args.command == "tx":
        check_transaction(args.address, args.tx_id)
    elif args.command == "confirm":
        manual_confirm(args.invoice_id, args.tx_hash)
    elif args.command == "list":
        list_pending_invoices()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()