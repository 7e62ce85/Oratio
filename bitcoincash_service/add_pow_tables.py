import sqlite3
import os

# 데이터베이스 경로
DB_PATH = '/data/payments.db'

def add_pow_tables():
    """PoW 관련 테이블 추가"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print(f"데이터베이스 연결 성공: {DB_PATH}")
    
    # PoW 검증 정보 테이블
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pow_verifications (
        id TEXT PRIMARY KEY,
        invoice_id TEXT NOT NULL,
        nonce TEXT NOT NULL,
        hash TEXT NOT NULL,
        verified_at INTEGER NOT NULL,
        user_token TEXT NOT NULL,
        FOREIGN KEY(invoice_id) REFERENCES invoices(id)
    )
    ''')
    
    # PoW 기반 크레딧 테이블 (블록체인 검증 전 임시 크레딧)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pow_credits (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        invoice_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        amount REAL NOT NULL,
        created_at INTEGER NOT NULL,
        confirmed BOOLEAN DEFAULT FALSE,
        FOREIGN KEY(invoice_id) REFERENCES invoices(id)
    )
    ''')
    
    conn.commit()
    conn.close()
    print("PoW 관련 테이블이 추가되었습니다.")

if __name__ == "__main__":
    try:
        add_pow_tables()
    except Exception as e:
        print(f"오류 발생: {str(e)}")
