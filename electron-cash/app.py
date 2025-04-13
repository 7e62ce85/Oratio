from flask import Flask, jsonify, request, render_template, redirect, url_for, session
from flask import send_from_directory
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
import traceback
from functools import wraps
from werkzeug.exceptions import BadRequest
from direct_payment import direct_payment_handler

# Electron-Cash specific imports
try:
    from electroncash.simple_config import SimpleConfig
    from electroncash.daemon import Daemon
    from electroncash.wallet import Wallet
    from electroncash.util import NotEnoughFunds, InvalidPassword
    from electroncash.address import Address
    import electroncash.commands as commands
    EC_AVAILABLE = True
except ImportError:
    EC_AVAILABLE = False
    logging.warning("Electron-Cash modules not available. Some features will be limited.")

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
    DIRECT_MODE = False
    logger.info("직접 결제 모드 활성화")
except ImportError:
    DIRECT_MODE = False
    logger.warning("직접 결제 모듈을 불러올 수 없습니다. ElectronCash 모드만 사용합니다.")

# ElectronCash 인스턴스
electron_cash_instance = None
electron_cash_wallet = None

def init_electron_cash():
    """ElectronCash 초기화"""
    global electron_cash_instance, electron_cash_wallet
    
    if not EC_AVAILABLE:
        logger.warning("ElectronCash 모듈을 사용할 수 없어 초기화를 건너뜁니다.")
        return False
        
    try:
        logger.info("ElectronCash 초기화 중...")
        # 환경 설정
        config = SimpleConfig()
        config.set_key('server', ELECTRON_CASH_URL)
        config.set_key('rpcuser', ELECTRON_CASH_USER)
        config.set_key('rpcpassword', ELECTRON_CASH_PASSWORD)
        
        # 데몬 초기화
        electron_cash_instance = Daemon(config)
        
        # 지갑 로드
        wallet_path = config.get('wallet_path', 'default_wallet')
        electron_cash_wallet = Wallet(wallet_path, config)
        
        logger.info("ElectronCash 초기화 완료")
        return True
    except Exception as e:
        logger.error(f"ElectronCash 초기화 오류: {str(e)}")
        return False

# ElectronCash 인증 설정
def setup_electron_cash_auth():
    """ElectronCash 인증 설정"""
    # 환경 변수에서 설정 가져오기
    rpc_user = os.environ.get('ELECTRON_CASH_USER', 'bchrpc')
    rpc_password = os.environ.get('ELECTRON_CASH_PASSWORD', '')
    
    # 인증 정보 설정
    if not rpc_password:
        # 무작위 비밀번호 생성
        import random
        import string
        rpc_password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
        logger.info(f"ElectronCash RPC 인증을 위한 무작위 비밀번호 생성: {rpc_password}")
    
    # 환경 변수 설정
    os.environ['ELECTRON_CASH_USER'] = rpc_user
    os.environ['ELECTRON_CASH_PASSWORD'] = rpc_password
    
    # 글로벌 변수 업데이트
    global ELECTRON_CASH_USER, ELECTRON_CASH_PASSWORD
    ELECTRON_CASH_USER = rpc_user
    ELECTRON_CASH_PASSWORD = rpc_password
    
    return rpc_user, rpc_password

# 서비스 시작 시 인증 설정
setup_electron_cash_auth()

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
    
    # PoW 검증 테이블 추가
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pow_verifications (
        id TEXT PRIMARY KEY,
        invoice_id TEXT NOT NULL,
        nonce TEXT NOT NULL,
        hash TEXT NOT NULL,
        verified INTEGER DEFAULT 0,
        verified_at INTEGER NOT NULL,
        user_token TEXT NOT NULL,
        FOREIGN KEY(invoice_id) REFERENCES invoices(id)
    )
    ''')
    
    # PoW 크레딧 테이블 추가
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pow_credits (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        invoice_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        amount REAL NOT NULL,
        created_at INTEGER NOT NULL,
        used BOOLEAN DEFAULT FALSE,
        FOREIGN KEY(invoice_id) REFERENCES invoices(id)
    )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("데이터베이스 초기화 완료")

# 데이터베이스 초기화
init_db()

def add_verified_column():
    """필요한 경우 verified 컬럼 추가"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # pow_verifications 테이블의 컬럼 확인
        cursor.execute("PRAGMA table_info(pow_verifications)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # verified 컬럼이 없는 경우 추가
        if 'verified' not in columns:
            logger.info("pow_verifications 테이블에 verified 컬럼 추가 중...")
            cursor.execute("ALTER TABLE pow_verifications ADD COLUMN verified INTEGER DEFAULT 1")
            conn.commit()
            logger.info("verified 컬럼이 성공적으로 추가되었습니다.")
        
        conn.close()
    except Exception as e:
        logger.error(f"verified 컬럼 추가 중 오류: {str(e)}")

# API 인증 데코레이터
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != LEMMY_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Enhance ElectronCashClient to handle authentication errors
class ElectronCashClient:
    def __init__(self, url=ELECTRON_CASH_URL):
        self.url = url
        self.headers = {'content-type': 'application/json'}
        self.auth = (ELECTRON_CASH_USER, ELECTRON_CASH_PASSWORD)
        self.rpc_id = 0
        self.auth_retries = 0
        self.max_retries = 3
        
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
            )
            
            # Check for authentication errors
            if response.status_code == 401 and self.auth_retries < self.max_retries:
                logger.warning(f"RPC 인증 실패 (시도 {self.auth_retries + 1}/{self.max_retries}). 자격 증명 재설정 중...")
                self.auth_retries += 1
                
                # Re-setup authentication and update credentials
                rpc_user, rpc_password = setup_electron_cash_auth()
                self.auth = (rpc_user, rpc_password)
                
                # Retry the call
                time.sleep(1)  # Small delay before retry
                return self.call_method(method, params)
                
            # Reset retry counter on success
            if response.status_code == 200:
                self.auth_retries = 0
            
            try:
                json_response = response.json()
                if "result" in json_response:
                    return json_response["result"]
                elif "error" in json_response:
                    logger.error(f"RPC 오류: {json_response['error']}")
                    return None
            except ValueError:
                logger.error(f"RPC 응답이 유효한 JSON이 아닙니다: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            if "401" in str(e) and self.auth_retries < self.max_retries:
                logger.warning(f"RPC 인증 실패 예외 (시도 {self.auth_retries + 1}/{self.max_retries}). 자격 증명 재설정 중...")
                self.auth_retries += 1
                
                # Re-setup authentication and update credentials
                rpc_user, rpc_password = setup_electron_cash_auth()
                self.auth = (rpc_user, rpc_password)
                
                # Retry the call
                time.sleep(1)  # Small delay before retry
                return self.call_method(method, params)
            
            logger.error(f"Electron Cash 호출 오류: {str(e)}")
            return None
        
    # Rest of the methods remain unchanged
    def get_new_address(self):
        """새 BCH 주소 생성"""
        # 직접 결제 모드에서는 Coinomi 주소를 사용
        if DIRECT_MODE:
            logger.info(f"직접 결제 모드: Coinomi 지갑 주소 사용 ({PAYOUT_WALLET})")
            return PAYOUT_WALLET
        
        try:
            # ElectronCash에서 새 주소 생성 시도
            logger.info("ElectronCash에서 새 주소 생성 중...")
            result = self.call_method("createnewaddress")
            
            if result:
                logger.info(f"새 주소 생성 성공: {result}")
                
                # 주소 데이터베이스에 저장
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO addresses (address, created_at, used) VALUES (?, ?, ?)",
                    (result, int(time.time()), False)
                )
                conn.commit()
                conn.close()
                
                return result
            else:
                logger.error("ElectronCash에서 주소 생성 실패")
        except Exception as e:
            logger.error(f"주소 생성 오류: {str(e)}")
        

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
                # ElectronCash를 통한 잔액 확인
                logger.info(f"ElectronCash를 통해 주소 {address}의 잔액 확인 중...")
                result = self.call_method("getaddressbalance", [address])
                
                if result is not None:
                    # ElectronCash의 응답 형식은 {"confirmed": X, "unconfirmed": Y}
                    confirmed = result.get("confirmed", 0)
                    unconfirmed = result.get("unconfirmed", 0)
                    
                    # satoshi를 BCH로 변환 (1 BCH = 100,000,000 satoshis)
                    confirmed_bch = float(confirmed) / 100000000.0
                    unconfirmed_bch = float(unconfirmed) / 100000000.0
                    
                    logger.info(f"주소 {address}의 잔액: 확인됨 {confirmed_bch} BCH, 미확인 {unconfirmed_bch} BCH")
                    
                    # 인보이스의 경우 미확인 거래도 포함하여 반환
                    return confirmed_bch + unconfirmed_bch
                else:
                    logger.error(f"ElectronCash에서 주소 {address}의 잔액을 가져오지 못했습니다.")
                    # ElectronCash 실패 시 직접 처리기로 시도
                    return direct_payment_handler.check_address_balance(address)

        except Exception as e:
            logger.error(f"잔액 확인 오류: {str(e)}")
            # 오류 발생 시 직접 처리기로 시도
            return direct_payment_handler.check_address_balance(address)   

    def get_transaction_confirmations(self, tx_hash):
        """트랜잭션 확인 수 확인"""
        # 직접 결제 모드에서는 API를 통해 확인
        if DIRECT_MODE:
            return direct_payment_handler.get_transaction_confirmations(tx_hash)
    
        try:
            # ElectronCash를 통한 트랜잭션 확인 수 조회
            logger.info(f"ElectronCash를 통해 트랜잭션 {tx_hash}의 확인 수 확인 중...")
            result = self.call_method("gettransaction", [tx_hash])
            
            if result is not None:
                confirmations = result.get("confirmations", 0)
                logger.info(f"트랜잭션 {tx_hash}의 확인 수: {confirmations}")
                return confirmations
            else:
                logger.error(f"ElectronCash에서 트랜잭션 {tx_hash}의 정보를 가져오지 못했습니다.")
                # ElectronCash 실패 시 직접 처리기로 시도
                return direct_payment_handler.get_transaction_confirmations(tx_hash)
                
        except Exception as e:
            logger.error(f"트랜잭션 확인 수 조회 오류: {str(e)}")
        # ElectronCash 실패시 직접 처리기 사용
        return direct_payment_handler.get_transaction_confirmations(tx_hash)

    def list_transactions(self, address=None, count=10):
        """주소 또는 지갑의 최근 트랜잭션 목록 조회"""
        if DIRECT_MODE:
            if address:
                return direct_payment_handler.get_recent_transactions(address)
            return []
            
        try:
            # ElectronCash를 통한 트랜잭션 목록 조회
            params = [count]
            if address:
                params.append(address)
                
            logger.info(f"ElectronCash를 통해 {'주소 ' + address if address else '지갑'}의 최근 트랜잭션 조회 중...")
            result = self.call_method("listtransactions", params)
            
            if result is not None:
                return result
            else:
                logger.error("ElectronCash에서 트랜잭션 목록을 가져오지 못했습니다.")
                return []
                
        except Exception as e:
            logger.error(f"트랜잭션 목록 조회 오류: {str(e)}")
            return []

    def find_transaction_for_invoice(self, invoice):
        """인보이스에 대한 트랜잭션 찾기"""
        if DIRECT_MODE:
            return direct_payment_handler.find_payment_transaction(
                invoice["payment_address"], 
                invoice["amount"],
                invoice["created_at"]
            )
            
        try:
            # 주소 관련 트랜잭션 조회
            transactions = self.list_transactions(invoice["payment_address"], 20)
            
            if not transactions:
                logger.info(f"주소 {invoice['payment_address']}에 대한 트랜잭션이 없습니다.")
                return None
                
            # 인보이스 생성 시간 이후의 트랜잭션 필터링
            for tx in transactions:
                tx_time = tx.get("time", 0)
                
                if tx_time < invoice["created_at"]:
                    continue
                    
                # 금액 확인 (BCH 단위로 변환)
                tx_amount = abs(tx.get("amount", 0))
                
                # 금액이 일치하는지 확인 (약간의 오차 허용)
                if abs(tx_amount - invoice["amount"]) < 0.00001:
                    logger.info(f"인보이스 {invoice['id']}에 대한 트랜잭션 발견: {tx.get('txid')}")
                    
                    return {
                        "txid": tx.get("txid"),
                        "amount": tx_amount,
                        "confirmations": tx.get("confirmations", 0),
                        "time": tx_time
                    }
                    
            logger.info(f"인보이스 {invoice['id']}에 대한 적절한 트랜잭션을 찾을 수 없습니다.")
            return None
            
        except Exception as e:
            logger.error(f"인보이스 트랜잭션 조회 오류: {str(e)}")
            return None        
        
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
        "testnet": TESTNET,
        "direct_mode": DIRECT_MODE,
        "api": "blockchair.com"  # 사용 중인 API 표시
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
    
    # BCH URI 스키마 - 주소 형식 개선
    payment_address = invoice['payment_address']
    
    # Remove bitcoincash: prefix if already present to avoid duplication
    cleaned_address = payment_address.replace('bitcoincash:', '')
    
    # Add proper prefix - ensure consistent format
    if not cleaned_address.startswith('q'):
        logger.warning(f"Invalid BCH address format: {payment_address}")
        # Try to use a default address if available
        cleaned_address = PAYOUT_WALLET.replace('bitcoincash:', '')
    
    formatted_address = f"bitcoincash:{cleaned_address}"
    
    # Create URI with amount
    qr_content = f"{formatted_address}?amount={invoice['amount']}"
    logger.info(f"생성된 QR 코드 내용: {qr_content}")
    
    qr.add_data(qr_content)
    
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
    logger.info(f"인보이스 {invoice_id}의 결제 상태 확인 중...")
    # balance = electron_cash.check_address_balance(invoice["payment_address"])
    
    # ElectronCash 모드
    if not DIRECT_MODE:
        # 1. 주소 잔액 확인
        balance = electron_cash.check_address_balance(invoice["payment_address"])
        logger.info(f"주소 {invoice['payment_address']}의 잔액: {balance} BCH (필요 금액: {invoice['amount']} BCH)")
        
        # 잔액이 충분하면 트랜잭션 찾기
        if balance >= invoice["amount"]:
            # 트랜잭션 찾기
            tx_info = electron_cash.find_transaction_for_invoice(invoice)
            
            if tx_info:
                # 지불 확인
                paid_at = int(time.time())
                tx_hash = tx_info["txid"]
                confirmations = tx_info["confirmations"]
                
                cursor.execute(
                    "UPDATE invoices SET status = 'paid', paid_at = ?, tx_hash = ?, confirmations = ? WHERE id = ?",
                    (paid_at, tx_hash, confirmations, invoice_id)
                )
                
                invoice["status"] = "paid"
                invoice["paid_at"] = paid_at
                invoice["tx_hash"] = tx_hash
                invoice["confirmations"] = confirmations
                
                # 충분한 확인이 있으면 완료로 처리
                if confirmations >= MIN_CONFIRMATIONS:
                    cursor.execute(
                        "UPDATE invoices SET status = 'completed' WHERE id = ?",
                        (invoice_id,)
                    )
                    invoice["status"] = "completed"
                    
                    # 사용자 크레딧 추가
                    if invoice["user_id"]:
                        credit_user(invoice["user_id"], invoice["amount"], invoice_id)
    # 직접 결제 모드
    else:
        # 트랜잭션 검색
        # Attempt to find a payment transaction for the given address, amount, and timestamp
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

@app.route('/verify-payment', methods=['POST'])
def verify_payment_pow():
    """작업 증명을 통한 결제 검증"""
    data = request.json
    payment_id = data.get('paymentId')
    user_token = data.get('userToken')
    nonce = data.get('nonce')
    claimed_hash = data.get('hash')
    
    logger.info(f"작업 증명 검증 요청: 인보이스 {payment_id}, 토큰 {user_token}")
    
    # 1. 결제 ID 유효성 확인
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, payment_address, amount, status, created_at, user_id
        FROM invoices WHERE id = ?
    """, (payment_id,))
    
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        logger.warning(f"작업 증명 검증 실패: 인보이스 {payment_id} 없음")
        return jsonify({'verified': False, 'reason': '인보이스를 찾을 수 없습니다'})
    
    invoice = {
        "id": result[0],
        "payment_address": result[1],
        "amount": result[2],
        "status": result[3],
        "created_at": result[4],
        "user_id": result[5]
    }
    
    # 이미 완료된 경우
    if invoice["status"] == "completed":
        conn.close()
        return jsonify({'verified': True})
    
    # 만료된 경우
    if invoice["status"] == "expired":
        conn.close()
        logger.warning(f"작업 증명 검증 실패: 인보이스 {payment_id} 만료됨")
        return jsonify({'verified': False, 'reason': '인보이스가 만료되었습니다'})
    
    # 2. PoW 해시 검증
    difficulty = 4  # 서버에서 설정한 난이도
    target = '0' * difficulty
    
    # 해시 재계산하여 검증
    data_string = f"{payment_id}:{user_token}:{nonce}"
    computed_hash = hashlib.sha256(data_string.encode()).hexdigest()
    
    if computed_hash != claimed_hash or not computed_hash.startswith(target):
        conn.close()
        logger.warning(f"작업 증명 검증 실패: 유효하지 않은 해시 {computed_hash}")
        return jsonify({'verified': False, 'reason': '유효하지 않은 작업 증명입니다'})
    
    logger.info(f"작업 증명 해시 검증 성공: {computed_hash}")
    
    # 3. 블록체인 결제 확인 시도
    try:
        # 직접 결제 모드
        if DIRECT_MODE:
            tx_info = direct_payment_handler.find_payment_transaction(
                invoice["payment_address"], 
                invoice["amount"],
                invoice["created_at"]
            )
        else:
            # ElectronCash 모드
            balance = electron_cash.check_address_balance(invoice["payment_address"])
            if balance >= invoice["amount"]:
                tx_info = electron_cash.find_transaction_for_invoice(invoice)
            else:
                tx_info = None
        
        if tx_info:
            # 결제 확인됨, 인보이스 상태 업데이트
            now = int(time.time())
            cursor.execute(
                "UPDATE invoices SET status = 'paid', paid_at = ?, tx_hash = ?, confirmations = ? WHERE id = ?",
                (now, tx_info["txid"], tx_info["confirmations"], payment_id)
            )
            
            # 충분한 확인이 있으면 완료로 처리
            if tx_info["confirmations"] >= MIN_CONFIRMATIONS:
                cursor.execute(
                    "UPDATE invoices SET status = 'completed' WHERE id = ?",
                    (payment_id,)
                )
                
                # 사용자 크레딧 추가
                if invoice["user_id"]:
                    credit_user(invoice["user_id"], invoice["amount"], payment_id)
            
            conn.commit()
            conn.close()
            logger.info(f"블록체인 결제 확인 성공: 인보이스 {payment_id}, 트랜잭션 {tx_info['txid']}")
            return jsonify({'verified': True})
        else:
            # PoW는 성공했지만 실제 결제는 확인되지 않음
            # 작업 증명 정보 저장
            pow_id = str(uuid.uuid4())
            cursor.execute(
                """INSERT INTO pow_verifications 
                   (id, invoice_id, nonce, hash, verified_at, user_token) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pow_id, payment_id, nonce, computed_hash, int(time.time()), user_token)
            )
            conn.commit()
            
            logger.info(f"작업 증명은 성공했으나 블록체인 결제 미확인: 인보이스 {payment_id}")
            return jsonify({'verified': False, 'reason': '결제가 아직 확인되지 않았습니다'})
            
    except Exception as e:
        logger.error(f"결제 검증 중 오류 발생: {str(e)}")
        logger.error(traceback.format_exc())
        conn.rollback()
        return jsonify({'verified': False, 'reason': '검증 과정에서 오류가 발생했습니다'})
    finally:
        conn.close()

# Add error handling middleware
@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler for the app"""
    logger.error(f"Unhandled exception: {str(e)}")
    logger.error(traceback.format_exc())
    
    if isinstance(e, requests.exceptions.RequestException):
        # Handle connection errors to ElectronCash
        error_message = str(e)
        if "401" in error_message:
            logger.error("ElectronCash authentication failed. Check RPC username and password.")
            # Try to re-setup authentication
            setup_electron_cash_auth()
            return jsonify({"error": "Authentication to payment service failed. Please try again."}), 503
        return jsonify({"error": "Service temporarily unavailable, please try again later"}), 503
    
    if isinstance(e, werkzeug.exceptions.NotFound):
        return jsonify({"error": "The requested resource was not found"}), 404
    
    return jsonify({"error": "An unexpected error occurred"}), 500

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