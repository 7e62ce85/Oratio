from flask import Flask, jsonify, request, render_template, redirect, url_for, session
import uuid
import time
import json
import os
import requests
from datetime import datetime, timedelta
import qrcode
from io import BytesIO
import base64
import sqlite3
import hashlib
import hmac
import threading
import logging
from functools import wraps
from werkzeug.exceptions import BadRequest
from direct_payment import direct_payment_handler

# 로깅 설정 - 먼저 로거를 초기화해야 함
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bch_payment.log')
    ]
)
logger = logging.getLogger('bch_payment')

# 직접 결제 모듈 가져오기
try:
    from direct_payment import direct_payment_handler
    DIRECT_MODE = True
    logger.info("직접 결제 모드 활성화")
except ImportError:
    DIRECT_MODE = False
    logger.warning("직접 결제 모듈을 불러올 수 없습니다. ElectronCash 모드만 사용합니다.")

# 환경 변수에서 지갑 주소 가져오기
PAYOUT_WALLET = os.environ.get('PAYOUT_WALLET', 'bitcoincash:qr3jejs0qn6wnssw8659duv7c3nnx92f6sfsvam05w')

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# 환경 설정
MOCK_MODE = os.environ.get('MOCK_MODE', 'false').lower() == 'true'
ELECTRON_CASH_URL = os.environ.get('ELECTRON_CASH_URL', 'http://electron-cash:7777')
ELECTRON_CASH_USER = os.environ.get('ELECTRON_CASH_USER', 'bchrpc')
ELECTRON_CASH_PASSWORD = os.environ.get('ELECTRON_CASH_PASSWORD', '')
LEMMY_API_URL = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
LEMMY_API_KEY = os.environ.get('LEMMY_API_KEY', '')
TESTNET = os.environ.get('TESTNET', 'true').lower() == 'true'
MIN_CONFIRMATIONS = int(os.environ.get('MIN_CONFIRMATIONS', '1'))
# 환경 변수에서 지갑 주소 가져오기
PAYOUT_WALLET = os.environ.get('PAYOUT_WALLET', 'bitcoincash:qr3jejs0qn6wnssw8659duv7c3nnx92f6sfsvam05w')
MIN_PAYOUT_AMOUNT = float(os.environ.get('MIN_PAYOUT_AMOUNT', '0.01'))  # 최소 출금 금액
FORWARD_PAYMENTS = os.environ.get('FORWARD_PAYMENTS', 'true').lower() == 'true'

# 데이터베이스 설정
DB_PATH = os.environ.get('DB_PATH', '/data/payments.db')

def init_db():
    """데이터베이스 초기화"""
    conn = sqlite3.connect(DB_PATH)
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
    
    conn.commit()
    conn.close()
    logger.info("데이터베이스 초기화 완료")

# 데이터베이스 초기화
init_db()

# API 인증 데코레이터
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != LEMMY_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Electron Cash JSON-RPC 클라이언트
class ElectronCashClient:
    def __init__(self, url=ELECTRON_CASH_URL):
        self.url = url
        self.headers = {'content-type': 'application/json'}
        self.auth = (ELECTRON_CASH_USER, ELECTRON_CASH_PASSWORD)
        self.rpc_id = 0
        
    def call_method(self, method, params=None):
        if params is None:
            params = []
            
        self.rpc_id += 1
        payload = {
            "method": method,
            "params": params,
            "jsonrpc": "2.0",
            "id": self.rpc_id,
        }
        
        try:
            logger.debug(f"RPC 호출: {method} {params}")
            response = requests.post(
                self.url, 
                data=json.dumps(payload), 
                headers=self.headers,
                auth=self.auth,
                timeout=10
            ).json()
            
            if "result" in response:
                return response["result"]
            elif "error" in response:
                logger.error(f"RPC 오류: {response['error']}")
                return None
        except Exception as e:
            logger.error(f"Electron Cash 호출 오류: {str(e)}")
            return None
    
    def get_new_address(self):
        """새 BCH 주소 생성"""
        # 직접 결제 모드에서는 Coinomi 주소를 사용
        if DIRECT_MODE:
            logger.info(f"직접 결제 모드: Coinomi 지갑 주소 사용 ({PAYOUT_WALLET})")
            return PAYOUT_WALLET

        # ElectronCash 실패시 직접 처리기 사용
        direct_address = direct_payment_handler.get_address()
        logger.info(f"직접 결제 주소 사용: {direct_address}")
        return direct_address

    def check_address_balance(self, address):
        """주소의 잔액 확인"""
        try:
            # 직접 결제 모드에서는 API를 통해 잔액 확인
            if DIRECT_MODE:
                return direct_payment_handler.check_address_balance(address)
                
            if MOCK_MODE:
                # Mock 모드: 지불 시뮬레이션
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, amount, created_at FROM invoices WHERE payment_address = ? AND status = 'pending'", 
                    (address,)
                )
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    invoice_id, amount, created_at = result
                    # 1분 후 지불 시뮬레이션
                    if time.time() - created_at > 60:
                        return amount
                return 0.0
            else:
                # 실제 잔액 확인
                result = self.call_method("getaddressbalance", [address])
                if result and "confirmed" in result:
                    # satoshi를 BCH로 변환
                    return float(result["confirmed"]) / 100000000.0
                return 0.0
                    
        except Exception as e:
            logger.error(f"잔액 확인 오류: {str(e)}")
            return 0.0    

    def get_transaction_confirmations(self, tx_hash):
        """트랜잭션 확인 수 확인"""
        # 직접 결제 모드에서는 API를 통해 확인
        if DIRECT_MODE:
            return direct_payment_handler.get_transaction_confirmations(tx_hash)
    
        # ElectronCash 실패시 직접 처리기 사용
        return direct_payment_handler.get_transaction_confirmations(tx_hash)

# Electron Cash 클라이언트 초기화
electron_cash = ElectronCashClient()

@app.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html')

@app.route('/health')
def health_check():
    """서비스 상태 확인"""
    return jsonify({
        "status": "ok", 
        "service": "bch-payment-service",
        "mock_mode": MOCK_MODE,
        "testnet": TESTNET
    })

@app.route('/generate_invoice', methods=['GET'])
def generate_invoice():
    """새 인보이스 생성"""
    # 파라미터 가져오기
    amount = request.args.get('amount', type=float)
    user_id = request.args.get('user_id', '')
    
    if not amount or amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400
    
    # 최소 금액 확인 (실제 구현 시 조정)
    min_amount = 0.0001  # BCH
    if amount < min_amount:
        return jsonify({"error": f"Amount must be at least {min_amount} BCH"}), 400
    
    # 새 인보이스 생성
    invoice_id = str(uuid.uuid4())
    payment_address = electron_cash.get_new_address()
    
    # 타임스탬프
    now = int(time.time())
    expires_at = now + 3600  # 1시간 후 만료
    
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
    conn = sqlite3.connect(DB_PATH)
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
    
    # 응답 반환
    if request.headers.get('Accept', '').find('application/json') != -1:
        return jsonify(invoice_data)
    else:
        return redirect(url_for('view_invoice', invoice_id=invoice_id))

@app.route('/invoice/<invoice_id>')
def view_invoice(invoice_id):
    """인보이스 조회 페이지"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, payment_address, amount, status, created_at, expires_at, paid_at, user_id, tx_hash, confirmations
        FROM invoices WHERE id = ?
    """, (invoice_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return render_template('error.html', message="인보이스를 찾을 수 없습니다"), 404
    
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
    
    # QR 코드 생성
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    
    # BCH URI 스키마
    qr_content = f"{invoice['payment_address']}?amount={invoice['amount']}"
    qr.add_data(qr_content)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    # 만료 시간 포맷팅
    expiry_time = datetime.fromtimestamp(invoice['expires_at'])
    formatted_expiry = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template(
        'invoice.html', 
        invoice=invoice,
        qr_code=img_str,
        formatted_expiry=formatted_expiry,
        min_confirmations=MIN_CONFIRMATIONS,
        testnet=TESTNET
    )

@app.route('/check_payment/<invoice_id>', methods=['GET'])
def check_payment(invoice_id):
    """결제 상태 확인"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, payment_address, amount, status, created_at, expires_at, paid_at, user_id, tx_hash, confirmations
        FROM invoices WHERE id = ?
    """, (invoice_id,))
    
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return jsonify({"error": "Invoice not found"}), 404
    
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
    
    # 이미 완료된 경우
    if invoice["status"] == "completed":
        conn.close()
        return jsonify(invoice)
    
    # 지불 확인된 경우
    if invoice["status"] == "paid":
        # 트랜잭션 확인 수 업데이트
        if invoice["tx_hash"]:
            confirmations = electron_cash.get_transaction_confirmations(invoice["tx_hash"])
            if confirmations != invoice["confirmations"]:
                cursor.execute(
                    "UPDATE invoices SET confirmations = ? WHERE id = ?",
                    (confirmations, invoice_id)
                )
                invoice["confirmations"] = confirmations
                
            # 충분한 확인이 되면 완료 처리
            if confirmations >= MIN_CONFIRMATIONS:
                cursor.execute(
                    "UPDATE invoices SET status = 'completed' WHERE id = ?",
                    (invoice_id,)
                )
                invoice["status"] = "completed"
                
                # 사용자 크레딧 추가
                if invoice["user_id"]:
                    credit_user(invoice["user_id"], invoice["amount"], invoice_id)
        
        conn.commit()
        conn.close()
        return jsonify(invoice)
    
    # 대기 중인 경우: 잔액 확인
    balance = electron_cash.check_address_balance(invoice["payment_address"])
    
    # 직접 결제 모드에서 트랜잭션 확인
    if DIRECT_MODE and invoice["status"] == "pending":
    # 트랜잭션 검색
        tx_info = direct_payment_handler.find_payment_transaction(
            invoice["payment_address"], 
            invoice["amount"],
            invoice["created_at"]
        )
    
    if tx_info:
        # 지불 확인
        paid_at = int(time.time())
        tx_hash = tx_info["txid"]
        
        cursor.execute(
            "UPDATE invoices SET status = 'paid', paid_at = ?, tx_hash = ?, confirmations = ? WHERE id = ?",
            (paid_at, tx_hash, tx_info["confirmations"], invoice_id)
        )
        
        invoice["status"] = "paid"
        invoice["paid_at"] = paid_at
        invoice["tx_hash"] = tx_hash
        invoice["confirmations"] = tx_info["confirmations"]
        
        # 충분한 확인이 있으면 완료로 처리
        if tx_info["confirmations"] >= MIN_CONFIRMATIONS:
            cursor.execute(
                "UPDATE invoices SET status = 'completed' WHERE id = ?",
                (invoice_id,)
            )
            invoice["status"] = "completed"
            
            # 사용자 크레딧 추가
            if invoice["user_id"]:
                credit_user(invoice["user_id"], invoice["amount"], invoice_id)

    if balance >= invoice["amount"]:
        # 지불 확인
        paid_at = int(time.time())
        tx_hash = "mock_tx_" + invoice_id if MOCK_MODE else None  # 실제에서는 트랜잭션 해시 확인 필요
        
        cursor.execute(
            "UPDATE invoices SET status = 'paid', paid_at = ?, tx_hash = ? WHERE id = ?",
            (paid_at, tx_hash, invoice_id)
        )
        
        invoice["status"] = "paid"
        invoice["paid_at"] = paid_at
        invoice["tx_hash"] = tx_hash
        
    conn.commit()
    conn.close()
    return jsonify(invoice)

def credit_user(user_id, amount, invoice_id):
    """사용자 계정에 크레딧 추가"""
    if not user_id:
        return False
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 현재 시간
    now = int(time.time())
    
    # 사용자 크레딧 업데이트
    cursor.execute(
        "INSERT INTO user_credits (user_id, credit_balance, last_updated) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET credit_balance = credit_balance + ?, last_updated = ?",
        (user_id, amount, now, amount, now)
    )
    
    # 트랜잭션 기록 저장
    transaction_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO transactions (id, user_id, amount, type, description, created_at, invoice_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (transaction_id, user_id, amount, "credit", "Bitcoin Cash 충전", now, invoice_id)
    )
    
    conn.commit()
    conn.close()
    
    # Lemmy API 통합 (실제 구현 필요)
    if LEMMY_API_KEY:
        try:
            # Lemmy API를 통해 사용자 포인트 증가 처리
            logger.info(f"Lemmy API 호출: 사용자 {user_id}에게 {amount} 크레딧 추가")
            # TODO: Lemmy API 호출 구현
        except Exception as e:
            logger.error(f"Lemmy API 호출 오류: {str(e)}")
    
    logger.info(f"사용자 {user_id}에게 {amount} BCH 크레딧 추가됨, 인보이스: {invoice_id}")
    return True

@app.route('/api/user_credit/<user_id>', methods=['GET'])
@require_api_key
def get_user_credit(user_id):
    """사용자 크레딧 조회 API"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT credit_balance FROM user_credits WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return jsonify({"user_id": user_id, "credit_balance": 0})
    
    return jsonify({"user_id": user_id, "credit_balance": result[0]})

@app.route('/api/transactions/<user_id>', methods=['GET'])
@require_api_key
def get_user_transactions(user_id):
    """사용자 거래 내역 조회 API"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, amount, type, description, created_at FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", 
        (user_id,)
    )
    results = cursor.fetchall()
    conn.close()
    
    transactions = [
        {
            "id": row[0],
            "amount": row[1],
            "type": row[2],
            "description": row[3],
            "created_at": row[4],
            "date": datetime.fromtimestamp(row[4]).strftime('%Y-%m-%d %H:%M:%S')
        }
        for row in results
    ]
    
    return jsonify({"user_id": user_id, "transactions": transactions})

# 만료된 인보이스 정리 함수
def cleanup_expired_invoices():
    """만료된 인보이스 처리"""
    conn = sqlite3.connect(DB_PATH)
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

def forward_to_payout_wallet():
    """수신된 자금을 출금 지갑으로 전송"""
    if not FORWARD_PAYMENTS:
        logger.info("자금 전송 기능이 비활성화되어 있습니다.")
        return
    
    try:
        # 전송 가능한 잔액 확인
        if MOCK_MODE:
            logger.info(f"Mock 모드: 출금 지갑({PAYOUT_WALLET})으로 자금 전송 시뮬레이션")
            return
        
        # 실제 잔액 확인
        balance = electron_cash.call_method("getbalance")
        if not balance or not isinstance(balance, dict):
            logger.error("잔액 확인 실패")
            return
        
        # 확인된 잔액 (satoshis 단위)
        confirmed_sats = balance.get("confirmed", 0)
        
        # BCH로 변환 (1 BCH = 100,000,000 satoshis)
        confirmed_bch = confirmed_sats / 100000000.0
        
        logger.info(f"현재 잔액: {confirmed_bch} BCH")
        
        # 최소 출금 금액보다 많을 경우에만 전송
        if confirmed_bch >= MIN_PAYOUT_AMOUNT:
            # 수수료 계산 (예상 0.00001 BCH)
            fee = 0.00001
            amount_to_send = confirmed_bch - fee
            
            # 출금 지갑으로 전송
            result = electron_cash.call_method("payto", [PAYOUT_WALLET, str(amount_to_send)])
            
            if result:
                # 트랜잭션 서명 및 브로드캐스트
                signed = electron_cash.call_method("signtransaction", [result])
                if signed:
                    broadcast = electron_cash.call_method("broadcast", [signed])
                    if broadcast:
                        logger.info(f"전송 성공: {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송했습니다. TX: {broadcast}")
                        return True
            
            logger.error("전송 실패")
        else:
            logger.info(f"잔액이 최소 출금 금액({MIN_PAYOUT_AMOUNT} BCH)보다 적습니다.")
    
    except Exception as e:
        logger.error(f"자금 전송 중 오류 발생: {str(e)}")
    
    return False

# 주기적 작업 스레드
def background_tasks():
    """백그라운드 작업 처리"""
    while True:
        try:
            # 만료된 인보이스 처리
            cleanup_expired_invoices()
            
            # 대기 중인 인보이스 상태 확인
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM invoices WHERE status = 'pending'"
            )
            pending_invoices = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            for invoice_id in pending_invoices:
                check_payment(invoice_id)
                
            # 지불 확인된 인보이스의 트랜잭션 확인 수 업데이트
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, tx_hash FROM invoices WHERE status = 'paid'"
            )
            paid_invoices = [(row[0], row[1]) for row in cursor.fetchall()]
            conn.close()
            
            for invoice_id, tx_hash in paid_invoices:
                if tx_hash and not tx_hash.startswith("mock_tx_"):
                    confirmations = electron_cash.get_transaction_confirmations(tx_hash)
                    
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE invoices SET confirmations = ? WHERE id = ?",
                        (confirmations, invoice_id)
                    )
                    
                    # 충분한 확인이 되면 완료 처리
                    if confirmations >= MIN_CONFIRMATIONS:
                        cursor.execute(
                            "SELECT user_id, amount FROM invoices WHERE id = ?",
                            (invoice_id,)
                        )
                        result = cursor.fetchone()
                        
                        if result:
                            user_id, amount = result
                            cursor.execute(
                                "UPDATE invoices SET status = 'completed' WHERE id = ?",
                                (invoice_id,)
                            )
                            
                            # 사용자 크레딧 추가
                            if user_id:
                                credit_user(user_id, amount, invoice_id)
                    
                    conn.commit()
                    conn.close()
            
        except Exception as e:
            logger.error(f"백그라운드 작업 오류: {str(e)}")
        
        # 5분마다 실행
        time.sleep(300)
# 주기적으로 자금을 출금 지갑으로 전송
if FORWARD_PAYMENTS:
    forward_to_payout_wallet()

if __name__ == "__main__":
    # 데이터 디렉토리 생성
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # 백그라운드 작업 시작
    cleanup_thread = threading.Thread(target=background_tasks)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    # 앱 실행
    debug_mode = os.environ.get('FLASK_ENV', 'production') == 'development'
    app.run(host="0.0.0.0", port=8081, debug=debug_mode)



# from flask import Flask, jsonify, request, render_template, redirect, url_for
# import uuid
# import time
# import json
# import os
# import requests
# from datetime import datetime, timedelta
# import qrcode
# from io import BytesIO
# import base64

# app = Flask(__name__)

# # In-memory storage for invoices (replace with database in production)
# invoices = {}

# # Electron Cash JSON-RPC client
# class ElectronCashClient:
#     def __init__(self, url="http://electron-cash:7777"):
#         self.url = url
#         self.headers = {'content-type': 'application/json'}
#         self.rpc_id = 0
        
#     def call_method(self, method, params=None):
#         if params is None:
#             params = []
            
#         self.rpc_id += 1
#         payload = {
#             "method": method,
#             "params": params,
#             "jsonrpc": "2.0",
#             "id": self.rpc_id,
#         }
        
#         try:
#             response = requests.post(
#                 self.url, 
#                 data=json.dumps(payload), 
#                 headers=self.headers
#             ).json()
            
#             if "result" in response:
#                 return response["result"]
#             elif "error" in response:
#                 print(f"RPC Error: {response['error']}")
#                 return None
#         except Exception as e:
#             print(f"Error calling Electron Cash: {str(e)}")
#             return None
    
#     def get_new_address(self):
#         # For testing, return a mock address if Electron Cash is not available
#         result = self.call_method("createnewaddress")
#         if result:
#             return result
#         return f"bitcoincash:qz{uuid.uuid4().hex[:30]}"
    
#     def check_address_balance(self, address):
#         # For testing, simulate checking balance
#         try:
#             # Strip the 'bitcoincash:' prefix if present
#             if address.startswith("bitcoincash:"):
#                 addr = address[12:]
#             else:
#                 addr = address
                
#             result = self.call_method("getaddressbalance", [addr])
#             if result and "confirmed" in result:
#                 # Convert satoshis to BCH
#                 return float(result["confirmed"]) / 100000000.0
#         except Exception as e:
#             print(f"Error checking balance: {str(e)}")
        
#         # For mock mode, randomly return some balance
#         if app.config.get("MOCK_MODE", True):
#             # Check if we should simulate payment based on invoice id
#             invoice_id = None
#             for inv_id, inv in invoices.items():
#                 if inv["payment_address"] == address:
#                     invoice_id = inv_id
#                     break
                    
#             if invoice_id and invoice_id in invoices:
#                 invoice = invoices[invoice_id]
#                 # If invoice was created more than 1 minute ago, simulate payment
#                 if time.time() - invoice["created_at"] > 60:
#                     return invoice["amount"]
        
#         return 0.0

# # Initialize Electron Cash client
# electron_cash = ElectronCashClient()

# # Configure app
# #app.config["MOCK_MODE"] = os.environ.get("MOCK_MODE", "true").lower() == "true"
# app.config["MOCK_MODE"] = True

# @app.route('/')
# def index():
#     return render_template('index.html')

# @app.route('/health')
# def health_check():
#     return jsonify({"status": "ok", "service": "bch-payment-service"})

# @app.route('/generate_invoice', methods=['GET'])
# def generate_invoice():
#     # Get amount from query parameter
#     amount = request.args.get('amount', type=float)
#     user_id = request.args.get('user_id', '')
    
#     if not amount or amount <= 0:
#         return jsonify({"error": "Invalid amount"}), 400
    
#     # Create new invoice
#     invoice_id = str(uuid.uuid4())
#     payment_address = electron_cash.get_new_address()
    
#     # Store invoice data
#     now = int(time.time())
#     expires_at = now + 3600  # 1 hour expiry
    
#     invoice_data = {
#         "invoice_id": invoice_id,
#         "payment_address": payment_address,
#         "amount": amount,
#         "status": "pending",
#         "created_at": now,
#         "expires_at": expires_at,
#         "user_id": user_id
#     }
    
#     invoices[invoice_id] = invoice_data
    
#     # Redirect to view invoice page or return JSON based on accept header
#     if request.headers.get('Accept', '').find('application/json') != -1:
#         return jsonify(invoice_data)
#     else:
#         return redirect(url_for('view_invoice', invoice_id=invoice_id))

# @app.route('/invoice/<invoice_id>')
# def view_invoice(invoice_id):
#     # Get invoice data
#     invoice = invoices.get(invoice_id)
#     if not invoice:
#         return render_template('error.html', message="Invoice not found"), 404
    
#     # Generate QR code
#     qr = qrcode.QRCode(
#         version=1,
#         error_correction=qrcode.constants.ERROR_CORRECT_L,
#         box_size=10,
#         border=4,
#     )
    
#     # Format for Bitcoin Cash URI scheme
#     qr_content = f"bitcoincash:{invoice['payment_address']}?amount={invoice['amount']}"
#     qr.add_data(qr_content)
#     qr.make(fit=True)
    
#     img = qr.make_image(fill_color="black", back_color="white")
#     buffered = BytesIO()
#     img.save(buffered)
#     img_str = base64.b64encode(buffered.getvalue()).decode()
    
#     # Format expiry time
#     expiry_time = datetime.fromtimestamp(invoice['expires_at'])
#     formatted_expiry = expiry_time.strftime('%Y-%m-%d %H:%M:%S')
    
#     return render_template(
#         'invoice.html', 
#         invoice=invoice,
#         qr_code=img_str,
#         formatted_expiry=formatted_expiry
#     )

# @app.route('/check_payment/<invoice_id>', methods=['GET'])
# def check_payment(invoice_id):
#     # Get invoice data
#     invoice = invoices.get(invoice_id)
#     if not invoice:
#         return jsonify({"error": "Invoice not found"}), 404
    
#     # If already paid, return immediately
#     if invoice["status"] == "paid":
#         return jsonify(invoice)
    
#     # Check payment status with Electron Cash
#     balance = electron_cash.check_address_balance(invoice["payment_address"])
    
#     # Update status if payment received
#     if balance >= invoice["amount"]:
#         invoice["status"] = "paid"
#         invoice["paid_at"] = int(time.time())
        
#         # Here you would integrate with Lemmy to credit the user's account
#         # This is where you would call Lemmy's API or update the database
        
#     return jsonify(invoice)

# @app.route('/payment_callback', methods=['POST'])
# def payment_callback():
#     # This endpoint would be called by an external service
#     # to notify about payment confirmation
#     data = request.json
#     if not data or "invoice_id" not in data or "status" not in data:
#         return jsonify({"error": "Invalid callback data"}), 400
    
#     invoice_id = data["invoice_id"]
#     status = data["status"]
    
#     # Update invoice status
#     if invoice_id in invoices:
#         if status == "paid":
#             invoices[invoice_id]["status"] = "paid"
#             invoices[invoice_id]["paid_at"] = int(time.time())
#             return jsonify({"success": True})
    
#     return jsonify({"error": "Invoice not found or invalid status"}), 404

# # Cleanup job to remove expired invoices
# def cleanup_expired_invoices():
#     now = int(time.time())
#     expired = []
    
#     for invoice_id, invoice in invoices.items():
#         if invoice["status"] == "pending" and invoice["expires_at"] < now:
#             expired.append(invoice_id)
    
#     for invoice_id in expired:
#         invoices.pop(invoice_id, None)

# # Start cleanup job in a background thread
# import threading
# def start_cleanup_thread():
#     while True:
#         cleanup_expired_invoices()
#         time.sleep(300)  # Run every 5 minutes

# # Start background thread when running in production
# if __name__ == "__main__":
#     # Start cleanup thread
#     cleanup_thread = threading.Thread(target=start_cleanup_thread)
#     cleanup_thread.daemon = True
#     cleanup_thread.start()
    
#     # Run the application
#     app.run(host="0.0.0.0", port=8081, debug=True)
