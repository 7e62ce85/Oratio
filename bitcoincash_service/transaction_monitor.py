#!/usr/bin/env python3
import os
import sys
import sqlite3
import time
import json
import argparse
from datetime import datetime
import logging

# 직접 결제 처리 모듈 임포트
try:
    from direct_payment import direct_payment_handler
    DIRECT_MODE = True
except ImportError:
    DIRECT_MODE = False

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('tx_monitor')

# 환경 변수 설정
DB_PATH = os.environ.get('DB_PATH', '/data/payments.db')
MIN_CONFIRMATIONS = int(os.environ.get('MIN_CONFIRMATIONS', '1'))

def get_db_connection():
    """데이터베이스 연결 생성"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 결과를 딕셔너리 형태로 반환
    return conn

def list_invoices(status=None, limit=50, days=None):
    """인보이스 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM invoices"
    params = []
    
    conditions = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    
    if days:
        # days일 이내의 인보이스만 조회
        time_threshold = int(time.time()) - (days * 24 * 60 * 60)
        conditions.append("created_at > ?")
        params.append(time_threshold)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    invoices = cursor.fetchall()
    conn.close()
    
    if not invoices:
        print("조건에 맞는 인보이스가 없습니다.")
        return
    
    print(f"{'인보이스 ID':<36} | {'상태':<10} | {'금액(BCH)':<12} | {'생성 시간':<20} | {'사용자 ID':<10} | {'확인 수':<8}")
    print("-" * 105)
    
    for invoice in invoices:
        created_time = datetime.fromtimestamp(invoice['created_at']).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{invoice['id']:<36} | {invoice['status']:<10} | {invoice['amount']:<12.6f} | {created_time:<20} | {invoice['user_id'] or 'N/A':<10} | {invoice['confirmations'] or 0:<8}")

def check_invoice(invoice_id):
    """특정 인보이스 상세 정보 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    invoice = cursor.fetchone()
    conn.close()
    
    if not invoice:
        print(f"인보이스 ID {invoice_id}를 찾을 수 없습니다.")
        return
    
    print("\n=== 인보이스 상세 정보 ===")
    print(f"인보이스 ID: {invoice['id']}")
    print(f"상태: {invoice['status']}")
    print(f"금액: {invoice['amount']} BCH")
    print(f"수신 주소: {invoice['payment_address']}")
    print(f"생성 시간: {datetime.fromtimestamp(invoice['created_at']).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"만료 시간: {datetime.fromtimestamp(invoice['expires_at']).strftime('%Y-%m-%d %H:%M:%S')}")
    
    if invoice['paid_at']:
        print(f"결제 시간: {datetime.fromtimestamp(invoice['paid_at']).strftime('%Y-%m-%d %H:%M:%S')}")
    
    print(f"사용자 ID: {invoice['user_id'] or 'N/A'}")
    print(f"트랜잭션 해시: {invoice['tx_hash'] or 'N/A'}")
    print(f"확인 수: {invoice['confirmations'] or 0} (최소 요구: {MIN_CONFIRMATIONS})")
    
    # 트랜잭션 해시가 있으면 추가 정보 조회
    if DIRECT_MODE and invoice['tx_hash'] and not invoice['tx_hash'].startswith("mock_tx_"):
        print("\n트랜잭션 상태 확인 중...")
        confirmations = direct_payment_handler.get_transaction_confirmations(invoice['tx_hash'])
        print(f"현재 확인 수: {confirmations} (API에서 조회)")
        
        # 트랜잭션 세부 정보 조회
        tx_info = direct_payment_handler.get_info_from_tx_hash(invoice['tx_hash'])
        if tx_info:
            print(f"트랜잭션 금액: {tx_info.get('amount')} BCH")
            print(f"트랜잭션 시간: {datetime.fromtimestamp(tx_info.get('time')).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 트랜잭션 확인 수 업데이트
        if confirmations != invoice['confirmations']:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE invoices SET confirmations = ? WHERE id = ?",
                (confirmations, invoice_id)
            )
            conn.commit()
            conn.close()
            print(f"확인 수가 {invoice['confirmations']}에서 {confirmations}로 업데이트되었습니다.")

def check_tx(tx_hash):
    """트랜잭션 상태 확인"""
    if not DIRECT_MODE:
        print("직접 결제 모드가 활성화되지 않았습니다.")
        return
    
    print(f"트랜잭션 {tx_hash} 상태 확인 중...")
    
    # 트랜잭션 확인 수 조회
    confirmations = direct_payment_handler.get_transaction_confirmations(tx_hash)
    if confirmations is not None:
        print(f"확인 수: {confirmations}")
    else:
        print("트랜잭션 정보를 조회할 수 없습니다.")
        return
    
    # 트랜잭션 세부 정보 조회
    tx_info = direct_payment_handler.get_info_from_tx_hash(tx_hash)
    if tx_info:
        print(f"트랜잭션 금액: {tx_info.get('amount')} BCH")
        print(f"트랜잭션 시간: {datetime.fromtimestamp(tx_info.get('time')).strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 이 트랜잭션과 연결된 인보이스 확인
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, status, amount, user_id FROM invoices WHERE tx_hash = ?", (tx_hash,))
    invoice = cursor.fetchone()
    conn.close()
    
    if invoice:
        print(f"\n연결된 인보이스: {invoice['id']}")
        print(f"인보이스 상태: {invoice['status']}")
        print(f"인보이스 금액: {invoice['amount']} BCH")
        print(f"사용자 ID: {invoice['user_id'] or 'N/A'}")
    else:
        print("\n이 트랜잭션과 연결된 인보이스가 없습니다.")

def check_address(address):
    """주소 잔액 및 트랜잭션 확인"""
    if not DIRECT_MODE:
        print("직접 결제 모드가 활성화되지 않았습니다.")
        return
    
    print(f"주소 {address} 확인 중...")
    
    # 주소 잔액 조회
    balance = direct_payment_handler.check_address_balance(address)
    print(f"현재 잔액: {balance} BCH")
    
    # 이 주소와 연결된 인보이스 확인
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE payment_address = ?", (address,))
    invoices = cursor.fetchall()
    conn.close()
    
    if invoices:
        print(f"\n이 주소와 연결된 인보이스: {len(invoices)}개")
        for idx, invoice in enumerate(invoices, 1):
            created_time = datetime.fromtimestamp(invoice['created_at']).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{idx}. 인보이스 ID: {invoice['id']}")
            print(f"   상태: {invoice['status']}")
            print(f"   금액: {invoice['amount']} BCH")
            print(f"   생성 시간: {created_time}")
            print(f"   트랜잭션 해시: {invoice['tx_hash'] or 'N/A'}")
            print()
    else:
        print("\n이 주소와 연결된 인보이스가 없습니다.")

def manual_confirm(invoice_id):
    """수동으로 인보이스 승인"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 인보이스 조회
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    invoice = cursor.fetchone()
    
    if not invoice:
        print(f"인보이스 ID {invoice_id}를 찾을 수 없습니다.")
        conn.close()
        return
    
    print("\n=== 인보이스 정보 ===")
    print(f"인보이스 ID: {invoice['id']}")
    print(f"상태: {invoice['status']}")
    print(f"금액: {invoice['amount']} BCH")
    print(f"사용자 ID: {invoice['user_id'] or 'N/A'}")
    
    if invoice['status'] == 'completed':
        print("이미 완료된 인보이스입니다.")
        conn.close()
        return
    
    confirm = input("\n이 인보이스를 수동으로 완료 처리하시겠습니까? (y/n): ")
    if confirm.lower() != 'y':
        print("작업이 취소되었습니다.")
        conn.close()
        return
    
    now = int(time.time())
    
    # 인보이스 상태 업데이트
    if invoice['status'] == 'pending':
        # 직접 paid 상태로 변경
        cursor.execute(
            "UPDATE invoices SET status = 'paid', paid_at = ? WHERE id = ?",
            (now, invoice_id)
        )
        print("인보이스 상태가 'paid'로 변경되었습니다.")
    
    # 다시 인보이스 조회
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    invoice = cursor.fetchone()
    
    # 완료 처리
    cursor.execute(
        "UPDATE invoices SET status = 'completed', confirmations = ? WHERE id = ?",
        (MIN_CONFIRMATIONS, invoice_id)
    )
    print("인보이스 상태가 'completed'로 변경되었습니다.")
    
    # 사용자 크레딧 추가
    if invoice['user_id']:
        # 현재 시간
        now = int(time.time())
        
        # 사용자 크레딧 업데이트
        cursor.execute(
            "INSERT INTO user_credits (user_id, credit_balance, last_updated) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET credit_balance = credit_balance + ?, last_updated = ?",
            (invoice['user_id'], invoice['amount'], now, invoice['amount'], now)
        )
        
        print(f"사용자 {invoice['user_id']}에게 {invoice['amount']} BCH 크레딧이 추가되었습니다.")
    
    conn.commit()
    conn.close()
    print("인보이스가 성공적으로 처리되었습니다.")

def search_tx_for_invoice(invoice_id):
    """인보이스에 대한 트랜잭션 검색"""
    if not DIRECT_MODE:
        print("직접 결제 모드가 활성화되지 않았습니다.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 인보이스 조회
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    invoice = cursor.fetchone()
    
    if not invoice:
        print(f"인보이스 ID {invoice_id}를 찾을 수 없습니다.")
        conn.close()
        return
    
    print("\n=== 인보이스 정보 ===")
    print(f"인보이스 ID: {invoice['id']}")
    print(f"상태: {invoice['status']}")
    print(f"금액: {invoice['amount']} BCH")
    print(f"수신 주소: {invoice['payment_address']}")
    print(f"생성 시간: {datetime.fromtimestamp(invoice['created_at']).strftime('%Y-%m-%d %H:%M:%S')}")
    
    if invoice['tx_hash']:
        print(f"이미 트랜잭션 해시가 있습니다: {invoice['tx_hash']}")
        conn.close()
        
        confirm = input("\n새 트랜잭션을 다시 검색하시겠습니까? (y/n): ")
        if confirm.lower() != 'y':
            return
    
    print("\n트랜잭션 검색 중...")
    tx_info = direct_payment_handler.find_payment_transaction(
        invoice['payment_address'], 
        invoice['amount'],
        invoice['created_at']
    )
    
    if tx_info:
        print(f"트랜잭션을 찾았습니다!")
        print(f"트랜잭션 해시: {tx_info['txid']}")
        print(f"금액: {tx_info['amount']} BCH")
        print(f"확인 수: {tx_info['confirmations']}")
        print(f"시간: {datetime.fromtimestamp(tx_info['time']).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 인보이스 업데이트
        confirm = input("\n이 트랜잭션으로 인보이스를 업데이트하시겠습니까? (y/n): ")
        if confirm.lower() != 'y':
            conn.close()
            return
        
        # 지불 확인
        paid_at = int(time.time())
        tx_hash = tx_info['txid']
        
        cursor.execute(
            "UPDATE invoices SET status = 'paid', paid_at = ?, tx_hash = ?, confirmations = ? WHERE id = ?",
            (paid_at, tx_hash, tx_info['confirmations'], invoice_id)
        )
        
        # 충분한 확인이 있으면 완료로 처리
        if tx_info['confirmations'] >= MIN_CONFIRMATIONS:
            cursor.execute(
                "UPDATE invoices SET status = 'completed' WHERE id = ?",
                (invoice_id,)
            )
            
            # 사용자 크레딧 추가
            if invoice['user_id']:
                # 현재 시간
                now = int(time.time())
                
                # 사용자 크레딧 업데이트
                cursor.execute(
                    "INSERT INTO user_credits (user_id, credit_balance, last_updated) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET credit_balance = credit_balance + ?, last_updated = ?",
                    (invoice['user_id'], invoice['amount'], now, invoice['amount'], now)
                )
                
                print(f"사용자 {invoice['user_id']}에게 {invoice['amount']} BCH 크레딧이 추가되었습니다.")
        
        conn.commit()
        print("인보이스가 업데이트되었습니다.")
    else:
        print("트랜잭션을 찾을 수 없습니다.")
    
    conn.close()

def main():
    parser = argparse.ArgumentParser(description='Bitcoin Cash 결제 모니터링 도구')
    
    subparsers = parser.add_subparsers(dest='command', help='명령어')
    
    # 인보이스 목록 조회
    list_parser = subparsers.add_parser('list', help='인보이스 목록 조회')
    list_parser.add_argument('--status', choices=['pending', 'paid', 'completed', 'expired'], help='인보이스 상태 필터')
    list_parser.add_argument('--limit', type=int, default=50, help='최대 결과 수 (기본값: 50)')
    list_parser.add_argument('--days', type=int, help='최근 n일 데이터만 조회')
    
    # 특정 인보이스 조회
    invoice_parser = subparsers.add_parser('invoice', help='특정 인보이스 상세 정보 조회')
    invoice_parser.add_argument('invoice_id', help='인보이스 ID')
    
    # 트랜잭션 조회
    tx_parser = subparsers.add_parser('tx', help='트랜잭션 상태 확인')
    tx_parser.add_argument('tx_hash', nargs='?', help='트랜잭션 해시')
    
    # 주소 조회
    address_parser = subparsers.add_parser('address', help='주소 잔액 및 트랜잭션 확인')
    address_parser.add_argument('address', help='Bitcoin Cash 주소')
    
    # 수동 확인
    confirm_parser = subparsers.add_parser('confirm', help='인보이스 수동 확인')
    confirm_parser.add_argument('invoice_id', help='인보이스 ID')
    
    # 인보이스에 대한 트랜잭션 검색
    search_parser = subparsers.add_parser('search', help='인보이스에 대한 트랜잭션 검색')
    search_parser.add_argument('invoice_id', help='인보이스 ID')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 명령어 실행
    if args.command == 'list':
        list_invoices(args.status, args.limit, args.days)
    elif args.command == 'invoice':
        check_invoice(args.invoice_id)
    elif args.command == 'tx':
        if args.tx_hash:
            check_tx(args.tx_hash)
        else:
            print("트랜잭션 해시를 입력해주세요.")
    elif args.command == 'address':
        check_address(args.address)
    elif args.command == 'confirm':
        manual_confirm(args.invoice_id)
    elif args.command == 'search':
        search_tx_for_invoice(args.invoice_id)

if __name__ == "__main__":
    main()