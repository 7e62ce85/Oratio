import sqlite3
import time
import logging
import uuid
from config import DB_PATH, logger

def init_db():
    """데이터베이스 초기화"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)  # Add a 30-second timeout
        cursor = conn.cursor()
        
        # 인보이스 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY,
            payment_address TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            paid_at INTEGER,
            user_id TEXT,
            tx_hash TEXT,
            confirmations INTEGER DEFAULT 0
        )
        ''')
        
        # 주소 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS addresses (
            address TEXT PRIMARY KEY,
            created_at INTEGER NOT NULL,
            used BOOLEAN DEFAULT FALSE
        )
        ''')
        
        # 사용자 크레딧 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_credits (
            user_id TEXT PRIMARY KEY,
            credit_balance REAL DEFAULT 0,
            last_updated INTEGER NOT NULL
        )
        ''')
        
        # 거래 기록 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            created_at INTEGER NOT NULL,
            invoice_id TEXT,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id)
        )
        ''')
        
        # PoW related tables removed
        
        # 프라그마 설정 - 외래 키 활성화 및 저널 모드 WAL로 변경
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 30000")  # 30 seconds timeout
        
        conn.commit()
        conn.close()
        logger.info("데이터베이스 초기화 완료")
    except sqlite3.Error as e:
        logger.error(f"데이터베이스 초기화 오류: {e}")
        raise

def get_db_connection():
    """데이터베이스 연결 생성"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    return conn

def save_address(address):
    """새 주소를 데이터베이스에 저장"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO addresses (address, created_at, used) VALUES (?, ?, ?)",
        (address, int(time.time()), False)
    )
    conn.commit()
    conn.close()
    return address

def mark_address_as_used(address):
    """주소를 사용됨으로 표시"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE addresses SET used = ? WHERE address = ?", (True, address))
    conn.commit()
    conn.close()

def create_invoice(payment_address, amount, user_id=""):
    """새 인보이스 생성 및 저장"""
    invoice_id = str(uuid.uuid4())
    now = int(time.time())
    expires_at = now + 3600  # 1시간 후 만료
    
    # Ensure payment address is stored without bitcoincash: prefix
    if payment_address.startswith('bitcoincash:'):
        payment_address = payment_address[12:]  # Remove prefix
    
    # 인보이스 데이터
    invoice_data = {
        "invoice_id": invoice_id,
        "payment_address": payment_address,
        "amount": amount,
        "status": "pending",
        "created_at": now,
        "expires_at": expires_at,
        "user_id": user_id
    }
    
    # 데이터베이스에 저장
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO invoices 
           (id, payment_address, amount, status, created_at, expires_at, user_id) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (invoice_id, payment_address, amount, "pending", now, expires_at, user_id)
    )
    conn.commit()
    conn.close()
    
    logger.info(f"새 인보이스 생성: {invoice_id}, 금액: {amount} BCH, 사용자: {user_id}")
    return invoice_data

def get_invoice(invoice_id):
    """인보이스 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, payment_address, amount, status, created_at, expires_at, paid_at, user_id, tx_hash, confirmations
        FROM invoices WHERE id = ?
    """, (invoice_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return None
    
    # 인보이스 데이터
    invoice = {
        "invoice_id": result[0],
        "payment_address": result[1],
        "amount": result[2],
        "status": result[3],
        "created_at": result[4],
        "expires_at": result[5],
        "paid_at": result[6],
        "user_id": result[7],
        "tx_hash": result[8],
        "confirmations": result[9]
    }
    
    return invoice

def update_invoice_status(invoice_id, status, tx_hash=None, confirmations=None, paid_at=None):
    """인보이스 상태 업데이트"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if status == 'paid' and tx_hash:
        if paid_at is None:
            paid_at = int(time.time())
            
        cursor.execute(
            "UPDATE invoices SET status = ?, paid_at = ?, tx_hash = ?, confirmations = ? WHERE id = ?",
            (status, paid_at, tx_hash, confirmations or 1, invoice_id)
        )
    elif status == 'completed':
        if tx_hash:
            # completed 상태로 변경할 때도 tx_hash와 confirmations 업데이트
            if paid_at is None:
                paid_at = int(time.time())
                
            cursor.execute(
                "UPDATE invoices SET status = ?, paid_at = ?, tx_hash = ?, confirmations = ? WHERE id = ?",
                (status, paid_at, tx_hash, confirmations or 1, invoice_id)
            )
        else:
            # tx_hash가 없는 경우 (기존 paid 상태에서 전환 시)
            cursor.execute("UPDATE invoices SET status = ? WHERE id = ?", (status, invoice_id))
    elif status == 'expired':
        cursor.execute("UPDATE invoices SET status = ? WHERE id = ?", (status, invoice_id))
    else:
        cursor.execute("UPDATE invoices SET status = ? WHERE id = ?", (status, invoice_id))
    
    conn.commit()
    conn.close()
    
    return True

def update_invoice_confirmations(invoice_id, confirmations):
    """인보이스 확인 수 업데이트"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE invoices SET confirmations = ? WHERE id = ?", (confirmations, invoice_id))
    conn.commit()
    conn.close()
    return True

def get_pending_invoices():
    """대기 중인 인보이스 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM invoices WHERE status = 'pending'")
    result = cursor.fetchall()
    conn.close()
    return [row[0] for row in result]

def get_paid_invoices():
    """지불 확인된 인보이스 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, tx_hash FROM invoices WHERE status = 'paid'")
    result = cursor.fetchall()
    conn.close()
    return [(row[0], row[1]) for row in result]

def expire_pending_invoices():
    """만료된 인보이스 처리"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    now = int(time.time())
    cursor.execute(
        "UPDATE invoices SET status = 'expired' WHERE status = 'pending' AND expires_at < ?", 
        (now,)
    )
    
    count = cursor.rowcount
    conn.commit()
    conn.close()
    
    if count > 0:
        logger.info(f"{count}개의 만료된 인보이스 처리됨")
    
    return count

def credit_user(user_id, amount, invoice_id):
    """사용자 계정에 크레딧 추가 - username 기반으로 저장"""
    if not user_id:
        return False
    
    # person_id를 username으로 변환
    username = user_id  # 기본값
    try:
        user_id_int = int(user_id)
        # person_id인 경우 username으로 변환
        from lemmy_integration import setup_lemmy_integration
        lemmy_api = setup_lemmy_integration()
        if lemmy_api:
            username_from_api = lemmy_api.get_username_by_id(user_id_int)
            if username_from_api:
                username = username_from_api
                logger.info(f"person_id {user_id}를 username {username}으로 변환")
    except (ValueError, TypeError):
        # 이미 username 형식인 경우
        pass
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 현재 시간
    now = int(time.time())
    
    # 사용자 크레딧 업데이트 (username으로 저장)
    cursor.execute(
        "INSERT INTO user_credits (user_id, credit_balance, last_updated) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET credit_balance = credit_balance + ?, last_updated = ?",
        (username, amount, now, amount, now)
    )
    
    # 트랜잭션 기록 저장 (username으로 저장)
    transaction_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO transactions (id, user_id, amount, type, description, created_at, invoice_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (transaction_id, username, amount, "credit", "Bitcoin Cash 충전", now, invoice_id)
    )
    
    conn.commit()
    conn.close()
    
    logger.info(f"사용자 {username} (원본 ID: {user_id})에게 {amount} BCH 크레딧 추가됨, 인보이스: {invoice_id}")
    return True

def get_user_credit(user_id):
    """사용자 크레딧 조회 - person_id를 username으로 변환하여 조회"""
    username = user_id  # 기본값
    
    # person_id인 경우 username으로 변환
    try:
        user_id_int = int(user_id)
        from lemmy_integration import setup_lemmy_integration
        lemmy_api = setup_lemmy_integration()
        if lemmy_api:
            username_from_api = lemmy_api.get_username_by_id(user_id_int)
            if username_from_api:
                username = username_from_api
                logger.info(f"크레딧 조회: person_id {user_id}를 username {username}으로 변환")
    except (ValueError, TypeError):
        # 이미 username 형식인 경우
        pass
    
    # username으로 크레딧 조회
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT credit_balance FROM user_credits WHERE user_id = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        logger.info(f"사용자 {username}의 크레딧 정보 없음 (조회된 잔액: 0)")
        return 0
    
    logger.info(f"사용자 {username}의 크레딧 조회: {result[0]} BCH")
    return result[0]

def get_user_transactions(user_id, limit=50):
    """사용자 거래 내역 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, amount, type, description, created_at FROM transactions "
        "WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", 
        (user_id, limit)
    )
    results = cursor.fetchall()
    conn.close()
    
    transactions = [
        {
            "id": row[0],
            "amount": row[1],
            "type": row[2],
            "description": row[3],
            "created_at": row[4]
        }
        for row in results
    ]
    
    return transactions

def get_user_credit_by_username(username):
    """사용자명으로 크레딧 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT credit_balance FROM user_credits WHERE user_id = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return 0
    
    return result[0]

def get_user_transactions_by_username(username, limit=50):
    """사용자명으로 거래 내역 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, amount, type, description, created_at FROM transactions "
        "WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", 
        (username, limit)
    )
    results = cursor.fetchall()
    conn.close()
    
    transactions = [
        {
            "id": row[0],
            "amount": row[1],
            "type": row[2],
            "description": row[3],
            "created_at": row[4]
        }
        for row in results
    ]
    
    return transactions

def has_user_made_payment(user_id):
    """사용자가 결제한 적이 있는지 확인"""
    try:
        # 직접 user_id로 결제 내역 확인 (Lemmy API 호출 없이)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND type = 'credit' AND amount > 0", 
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        
        return result[0] > 0 if result else False
    except Exception as e:
        logger.error(f"사용자 {user_id}의 결제 내역 확인 중 오류: {str(e)}")
        return False

def has_user_made_payment_by_username(username):
    """사용자명으로 결제한 적이 있는지 확인"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND type = 'credit' AND amount > 0", 
            (username,)
        )
        result = cursor.fetchone()
        conn.close()
        
        return result[0] > 0 if result else False
    except Exception as e:
        logger.error(f"사용자 {username}의 결제 내역 확인 중 오류: {str(e)}")
        return False

# 데이터베이스 초기화 함수 호출
init_db()