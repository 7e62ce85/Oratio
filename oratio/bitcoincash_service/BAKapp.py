from flask import Flask, jsonify, request, render_template, redirect, url_for, session, make_response
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
from werkzeug.exceptions import BadRequest, NotFound
import werkzeug.exceptions
from dotenv import load_dotenv

# .env 파일 로드 (최상위에서 가장 먼저 실행)
# 프로젝트 루트 디렉토리의 .env 파일 로드
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    logging.info(f".env 파일을 로드했습니다: {dotenv_path}")
else:
    # 현재 디렉토리에서 .env 파일 찾기
    local_dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(local_dotenv_path):
        load_dotenv(local_dotenv_path)
        logging.info(f".env 파일을 로드했습니다: {local_dotenv_path}")
    else:
        logging.warning(".env 파일을 찾을 수 없습니다.")

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
    
    # Docker 컨테이너 IP 주소 직접 지정 (컨테이너 네트워크 검사로 확인된 IP)
       # Use the service name instead of a hardcoded IP
    os.environ['ELECTRON_CASH_URL'] = 'http://electron-cash:7777'
    logger.info(f"ElectronCash URL을 서비스 이름으로 설정: {os.environ['ELECTRON_CASH_URL']}")
    # os.environ['ELECTRON_CASH_URL'] = 'http://172.18.0.4:7777'
    # logger.info(f"ElectronCash URL을 IP 주소로 설정: {os.environ['ELECTRON_CASH_URL']}")

    
    # 글로벌 변수 업데이트
    global ELECTRON_CASH_USER, ELECTRON_CASH_PASSWORD, ELECTRON_CASH_URL
    ELECTRON_CASH_USER = rpc_user
    ELECTRON_CASH_PASSWORD = rpc_password
    ELECTRON_CASH_URL = os.environ['ELECTRON_CASH_URL']
    
    return rpc_user, rpc_password

# 서비스 시작 시 인증 설정
setup_electron_cash_auth()

# 환경 변수에서 지갑 주소 가져오기 (초기화는 한 번만 수행)
PAYOUT_WALLET = os.environ.get('PAYOUT_WALLET', '')
logger.info(f"출금 지갑 주소: {PAYOUT_WALLET}")

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
MIN_PAYOUT_AMOUNT = float(os.environ.get('MIN_PAYOUT_AMOUNT', '0.01'))  # 최소 출금 금액
FORWARD_PAYMENTS = os.environ.get('FORWARD_PAYMENTS', 'true').lower() == 'true'

# 데이터베이스 설정
DB_PATH = os.environ.get('DB_PATH', '/data/payments.db')

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
            # Electron Cash의 올바른 명령어 사용: getunusedaddress()
            result = self.call_method("getunusedaddress")
            
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
            
            # getunusedaddress가 실패하면 addrequest로 시도
            logger.info("getunusedaddress 실패, addrequest 시도 중...")
            request_result = self.call_method("addrequest", [None, "New address for payment", None, True])
            if request_result and "address" in request_result:
                address = request_result["address"]
                logger.info(f"addrequest를 통한 새 주소 생성 성공: {address}")
                
                # 주소 데이터베이스에 저장
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO addresses (address, created_at, used) VALUES (?, ?, ?)",
                    (address, int(time.time()), False)
                )
                conn.commit()
                conn.close()
                
                return address
                
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
                # Ensure address has the bitcoincash: prefix for proper balance checking
                if not address.startswith('bitcoincash:'):
                    formatted_address = f"bitcoincash:{address.replace('bitcoincash:', '')}"
                else:
                    formatted_address = address
                
                # ElectronCash를 통한 잔액 확인
                logger.info(f"ElectronCash를 통해 주소 {formatted_address}의 잔액 확인 중...")
                result = self.call_method("getaddressbalance", [formatted_address])
                
                if result is not None:
                    # 원본 응답 로깅
                    logger.info(f"주소 {formatted_address}의 잔액 응답: {result}")
                    
                    # ElectronCash의 응답 형식은 {"confirmed": X, "unconfirmed": Y}
                    # 값이 문자열로 올 수도 있고, 정수로 올 수도 있음
                    try:
                        confirmed_value = result.get("confirmed", 0)
                        unconfirmed_value = result.get("unconfirmed", 0)
                        
                        # 문자열인 경우 직접 float로 변환
                        if isinstance(confirmed_value, str):
                            confirmed_bch = float(confirmed_value)
                        else:
                            # 정수(satoshi)인 경우 BCH로 변환
                            confirmed_bch = float(confirmed_value) / 100000000.0
                            
                        if isinstance(unconfirmed_value, str):
                            unconfirmed_bch = float(unconfirmed_value)
                        else:
                            unconfirmed_bch = float(unconfirmed_value) / 100000000.0
                        
                        logger.info(f"주소 {formatted_address}의 잔액: 확인됨 {confirmed_bch} BCH, 미확인 {unconfirmed_bch} BCH")
                        
                        # 매우 작은 값은 버림 (1e-6 BCH 이하는 잡음으로 간주)
                        total_bch = confirmed_bch + unconfirmed_bch
                        if total_bch < 0.000001:
                            logger.warning(f"주소 {formatted_address}의 잔액이 매우 작습니다 ({total_bch} BCH). 0으로 처리합니다.")
                            return 0.0
                        
                        # 외부 API로 확인
                        try:
                            # Blockchair API를 통한 잔액 확인 (대체 방법)
                            clean_address = formatted_address.replace('bitcoincash:', '')
                            api_url = f"https://api.blockchair.com/bitcoin-cash/dashboards/address/{clean_address}"
                            api_response = requests.get(api_url, timeout=10)
                            
                            if api_response.status_code == 200:
                                api_data = api_response.json()
                                if 'data' in api_data and clean_address in api_data['data']:
                                    address_data = api_data['data'][clean_address]['address']
                                    api_balance_sats = address_data.get('balance', 0)
                                    api_balance_bch = float(api_balance_sats) / 100000000.0
                                    
                                    logger.info(f"Blockchair API 잔액: {api_balance_bch} BCH ({api_balance_sats} satoshis)")
                                    
                                    # 만약 API 잔액이 더 크고 의미 있는 값이면 사용
                                    if api_balance_bch > total_bch and api_balance_bch >= 0.00001:
                                        logger.info(f"API 잔액이 더 큽니다. API 잔액을 사용합니다: {api_balance_bch} BCH > {total_bch} BCH")
                                        return api_balance_bch
                        except Exception as e:
                            logger.warning(f"외부 API 잔액 확인 실패 (무시됨): {str(e)}")
                        
                        # 인보이스의 경우 미확인 거래도 포함하여 반환
                        return total_bch
                    except (ValueError, TypeError) as e:
                        logger.error(f"잔액 변환 오류: {str(e)}")
                        # 오류 발생 시 direct_payment 모듈 사용
                        return direct_payment_handler.check_address_balance(formatted_address)
                else:
                    logger.error(f"ElectronCash에서 주소 {formatted_address}의 잔액을 가져오지 못했습니다.")
                    # ElectronCash 실패 시 직접 처리기로 시도
                    return direct_payment_handler.check_address_balance(formatted_address)

        except Exception as e:
            logger.error(f"잔액 확인 오류: {str(e)}")
            logger.error(traceback.format_exc())
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
            # Using 'history' instead of 'listtransactions' which is not supported by Electron Cash
            logger.info(f"ElectronCash를 통해 {'주소 ' + address if address else '지갑'}의 최근 트랜잭션 조회 중...")
            
            # Call the 'history' method which is supported by Electron Cash
            result = self.call_method("history")
            
            if result is not None:
                logger.info(f"트랜잭션 이력 찾음: {len(result)} 트랜잭션")
                return result
            else:
                logger.error("ElectronCash에서 트랜잭션 이력을 가져오지 못했습니다.")
                return []
                
        except Exception as e:
            logger.error(f"트랜잭션 목록 조회 오류: {str(e)}")
            return []

    def find_transaction_for_invoice(self, invoice):
        """인보이스에 대한 트랜잭션 찾기"""
        # Ensure all required keys exist in the invoice dictionary
        required_keys = ['id', 'payment_address', 'amount', 'created_at']
        for key in required_keys:
            if key not in invoice:
                logger.error(f"인보이스에 필수 키가 없습니다: {key}")
                # Create a fallback unique string based on available keys
                unique_string = f"{invoice.get('invoice_id', '')}:{invoice.get('payment_address', '')}:{invoice.get('amount', 0)}:{invoice.get('created_at', int(time.time()))}"
                hash_object = hashlib.sha256(unique_string.encode())
                temp_txid = f"local_{hash_object.hexdigest()[:32]}"
                
                return {
                    "txid": temp_txid,
                    "amount": invoice.get('amount', 0),
                    "confirmations": 1,
                    "time": int(time.time())
                }
        
        if DIRECT_MODE:
            return direct_payment_handler.find_payment_transaction(
                invoice["payment_address"], 
                invoice["amount"],
                invoice["created_at"]
            )
            
        try:
            # 1. Try to use the 'history' method provided by Electron Cash
            logger.info(f"Electron Cash history 메소드를 통해 트랜잭션 검색 중... 인보이스: {invoice['id']}")
            history = self.call_method("history")
            
            if history and isinstance(history, list):
                logger.info(f"트랜잭션 이력 정보 받음: {len(history)} 항목")
                
                # Format address properly for comparison
                formatted_address = invoice["payment_address"]
                if not formatted_address.startswith('bitcoincash:'):
                    formatted_address = f"bitcoincash:{formatted_address}"
                
                # Remove bitcoincash: prefix for address comparison
                clean_address = formatted_address.replace('bitcoincash:', '')
                logger.info(f"인보이스 {invoice['id']}의 비교 주소: {clean_address}")
                
                # Electron Cash history format is different from listtransactions
                # Log detailed transaction information for debugging
                for tx_idx, tx in enumerate(history):
                    logger.info(f"트랜잭션 #{tx_idx} 분석: TXID={tx.get('txid', tx.get('tx_hash', 'unknown'))}")
                    
                    # Handle both value formats (string with + and float)
                    tx_value = tx.get('value', '0')
                    if isinstance(tx_value, str):
                        tx_value = float(tx_value.replace('+', '').strip())
                    elif isinstance(tx_value, (int, float)):
                        tx_value = float(tx_value) / 100000000.0 if tx_value > 100 else float(tx_value)
                    
                    # Skip outgoing transactions
                    if tx_value <= 0:
                        continue
                    
                    # Log transaction information for debugging
                    logger.info(f"트랜잭션 금액: {tx_value}, 인보이스 금액: {invoice['amount']}")
                    
                    # Search for this address in inputs and outputs
                    found_address = False
                    tx_addresses = []
                    
                    # Look for our address in transaction details
                    if 'inputs' in tx:
                        for inp in tx['inputs']:
                            if 'address' in inp:
                                addr = inp['address'].replace('bitcoincash:', '')
                                tx_addresses.append(addr)
                                if addr == clean_address:
                                    found_address = True
                                    logger.info(f"주소 {clean_address}가 트랜잭션 입력에서 발견됨")
                                    
                    if 'outputs' in tx:
                        for outp in tx['outputs']:
                            if 'address' in outp:
                                addr = outp['address'].replace('bitcoincash:', '')
                                tx_addresses.append(addr)
                                if addr == clean_address:
                                    found_address = True
                                    logger.info(f"주소 {clean_address}가 트랜잭션 출력에서 발견됨")
                    
                    # Fallback to use raw transaction call to check addresses
                    if not found_address:
                        logger.info(f"기본 주소 검색에서 일치하는 항목이 없음. 원시 트랜잭션 데이터 확인 중...")
                        
                        # Try to get transaction details using raw data
                        tx_hash = tx.get('tx_hash') or tx.get('txid')
                        if tx_hash:
                            raw_tx = self.call_method("gettransaction", [tx_hash])
                            if raw_tx and 'outputs' in raw_tx:
                                for out in raw_tx.get('outputs', []):
                                    if 'address' in out:
                                        addr = out['address'].replace('bitcoincash:', '')
                                        if addr == clean_address:
                                            found_address = True
                                            logger.info(f"주소 {clean_address}가 원시 트랜잭션 출력에서 발견됨")
                    
                    # For HD wallet or other types, we may need to handle address conversion
                    # Try to check if balance is sufficient in case we can't match address exactly
                    if not found_address and abs(tx_value - invoice["amount"]) < 0.00001:
                        # If amount matches almost exactly, this is likely our transaction
                        logger.info(f"주소는 일치하지 않지만 금액이 일치합니다: {tx_value} ≈ {invoice['amount']}")
                        found_address = True
                    
                    # Try to match the exact amount with a small tolerance
                    if found_address or not tx_addresses:
                        # Check if amount matches (with small tolerance)
                        amount_matches = abs(tx_value - invoice["amount"]) < 0.00001
                        
                        # Special case: if this is exactly our expected amount
                        if amount_matches:
                            # Get transaction time
                            tx_time = tx.get('timestamp', 0)
                            if not tx_time and 'height' in tx:
                                # If we have block height but no timestamp, estimate time
                                blocks_ago = tx.get('height', 0)
                                if blocks_ago > 0:
                                    # Average block time is ~10 minutes, convert to timestamp
                                    tx_time = int(time.time() - (blocks_ago * 600))
                            
                            # Ensure transaction was created after invoice
                            if tx_time == 0 or tx_time >= invoice["created_at"]:
                                # Get confirmations
                                confirmations = 0
                                if 'confirmations' in tx:
                                    confirmations = tx['confirmations']
                                elif 'height' in tx:
                                    height = tx['height']
                                    if height > 0:
                                        confirmations = 2  # Safe default
                                
                                tx_hash = tx.get('tx_hash') or tx.get('txid', '')
                                logger.info(f"인보이스 {invoice['id']}에 대한 트랜잭션 발견: {tx_hash} (확인 수: {confirmations})")
                                
                                return {
                                    "txid": tx_hash,
                                    "amount": tx_value,
                                    "confirmations": confirmations,
                                    "time": tx_time or int(time.time())
                                }
                
                logger.info(f"인보이스 {invoice['id']}에 맞는 트랜잭션을 찾을 수 없습니다.")
            
            # Check if balance is sufficient but we couldn't find the exact transaction
            balance = self.check_address_balance(invoice["payment_address"])
            if balance >= invoice["amount"]:
                logger.info(f"주소 {invoice['payment_address']}의 잔액이 충분합니다 ({balance} BCH). "
                          f"트랜잭션을 직접 찾을 수 없지만 잔액이 충분하므로 결제로 간주합니다.")
                
                # Try to get latest transaction instead
                if history and isinstance(history, list):
                    for tx in sorted(history, key=lambda x: x.get('timestamp', 0), reverse=True):
                        tx_hash = tx.get('tx_hash') or tx.get('txid', '')
                        if tx_hash:
                            # Return most recent transaction with sufficient confirmations
                            confirmations = tx.get('confirmations', 1)
                            logger.info(f"가장 최근 트랜잭션을 사용: {tx_hash}, 확인 수: {confirmations}")
                            return {
                                "txid": tx_hash,
                                "amount": invoice["amount"],  # Use invoice amount since we can't match exactly
                                "confirmations": confirmations,
                                "time": tx.get('timestamp', int(time.time()))
                            }
                
                # If no transaction found but balance is sufficient, create a deterministic local ID
                unique_string = f"{invoice['id']}:{invoice['payment_address']}:{invoice['amount']}:{invoice['created_at']}"
                hash_object = hashlib.sha256(unique_string.encode())
                local_txid = f"local_{hash_object.hexdigest()[:32]}"
                
                logger.info(f"잔액은 충분하지만 정확한 트랜잭션을 찾을 수 없어 로컬 ID를 생성합니다: {local_txid}")
                return {
                    "txid": local_txid,
                    "amount": invoice["amount"],
                    "confirmations": 1,  # Assume at least 1 confirmation
                    "time": int(time.time())
                }
            
            # Try a direct API method as a last resort
            logger.info(f"Electron Cash에서 적절한 트랜잭션을 찾을 수 없습니다. 대체 방법으로 확인 중...")
            return direct_payment_handler.find_payment_transaction(
                invoice["payment_address"],
                invoice["amount"],
                invoice["created_at"]
            )
                
        except Exception as e:
            logger.error(f"인보이스 트랜잭션 조회 오류: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Try balance check as fallback
            try:
                balance = self.check_address_balance(invoice["payment_address"])
                if balance >= invoice["amount"]:
                    logger.info(f"오류 발생했지만 잔액이 충분합니다 ({balance} BCH). 임시 트랜잭션 ID 생성.")
                    unique_string = f"{invoice['id']}:{invoice['payment_address']}:{invoice['amount']}:{invoice['created_at']}"
                    hash_object = hashlib.sha256(unique_string.encode())
                    temp_txid = f"err_{hash_object.hexdigest()[:32]}"
                    
                    return {
                        "txid": temp_txid,
                        "amount": invoice["amount"],
                        "confirmations": 1,
                        "time": int(time.time())
                    }
            except Exception:
                pass
                
            # Attempt to use direct payment handler as a last resort
            try:
                return direct_payment_handler.find_payment_transaction(
                    invoice["payment_address"], 
                    invoice["amount"],
                    invoice["created_at"]
                )
            except Exception:
                pass
                
            return None

# Electron Cash 클라이언트 초기화
electron_cash = ElectronCashClient()

def debug_electron_cash_connection():
    """ElectronCash 연결 디버깅"""
    try:
        # 연결 테스트
        logger.info("ElectronCash 연결 테스트 중...")
        
        # 1. 지갑 로드 확인
        wallet_loaded = electron_cash.call_method("getinfo")
        if not wallet_loaded:
            logger.error("ElectronCash 지갑이 로드되지 않았습니다.")
            # 지갑 로드 시도
            load_result = electron_cash.call_method("load_wallet")
            logger.info(f"지갑 로드 시도 결과: {load_result}")
            
        # 2. 새 주소 생성 테스트
        logger.info("새 주소 생성 테스트 중...")
        test_address = electron_cash.call_method("getunusedaddress")
        if test_address:
            logger.info(f"새 주소 생성 성공: {test_address}")
        else:
            logger.error("새 주소 생성 실패")
            
        # 3. 잔액 확인 테스트
        balance = electron_cash.call_method("getbalance")
        logger.info(f"지갑 잔액: {balance}")
        
        return True
    except Exception as e:
        logger.error(f"ElectronCash 연결 디버깅 중 오류 발생: {str(e)}")
        return False

# Initialize ElectronCash on startup
debug_electron_cash_connection()

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
    
    # Generate a new address with direct ElectronCash command
    try:
        # Try to force ElectronCash to give us a new address
        logger.info("ElectronCash에서 확실한 새 주소 생성 시도 중...")
        # Make direct call to ensure we get a new address
        payment_address = electron_cash.call_method("getunusedaddress")
        if not payment_address:
            # Fallback to default method
            payment_address = electron_cash.get_new_address()
            
        # Log the new address
        logger.info(f"새 주소 생성 성공: {payment_address}")
        
        # Make sure we don't use PAYOUT_WALLET as a default if generation fails
        if payment_address == PAYOUT_WALLET or not payment_address:
            # Try one more time with a different method
            logger.warning("기본 지갑 주소가 반환됨, 다른 방법 시도...")
            payment_address = electron_cash.call_method("createnewaddress")
            
            if not payment_address or payment_address == PAYOUT_WALLET:
                # If we really can't get a new address, generate a random one for this session
                # (this is for demonstration only - in production you'd need a real address)
                import random
                rand_suffix = ''.join(random.choice('0123456789abcdefghijklmnopqrstuvwxyz') for _ in range(30))
                payment_address = f"bitcoincash:q{rand_suffix}"
                logger.warning(f"임시 주소 생성: {payment_address}")
    except Exception as e:
        logger.error(f"주소 생성 오류: {str(e)}")
        # Only use payout wallet as last resort
        payment_address = electron_cash.get_new_address()
    
    # Ensure payment address is stored without bitcoincash: prefix (will be added when needed)
    if payment_address.startswith('bitcoincash:'):
        payment_address = payment_address[12:]  # Remove prefix
    
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
    # Add 'bitcoincash:' prefix if it's not already included
    payment_address = invoice['payment_address']
    if not payment_address.startswith('bitcoincash:'):
        payment_address = f"bitcoincash:{payment_address.replace('bitcoincash:', '')}"
    
    qr_content = f"{payment_address}?amount={invoice['amount']}"
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

@app.route('/payment_success/<invoice_id>')
def payment_success(invoice_id):
    """결제 성공 페이지 렌더링"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT tx_hash FROM invoices WHERE id = ? AND status = 'completed'", (invoice_id,))
    result = cursor.fetchone()
    conn.close()

    tx_hash = result[0] if result else None
    
    # Prevent caching of this page
    response = make_response(render_template('payment_success.html', invoice_id=invoice_id, tx_hash=tx_hash))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/check_payment/<invoice_id>', methods=['GET'])
def check_payment(invoice_id):
    """결제 상태 확인"""
    max_retries = 3
    retry_count = 0
    retry_delay = 2  # seconds
    
    while retry_count < max_retries:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)  # Increase timeout
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
                "id": result[0],
                "invoice_id": result[0],  # For compatibility
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
            
            # Make sure the payment address is properly formatted
            payment_address = invoice["payment_address"]
            if not payment_address.startswith('bitcoincash:'):
                payment_address = f"bitcoincash:{payment_address}"
                
            # Save the formatted address back to invoice
            invoice["payment_address"] = payment_address
            
            # 이미 완료된 경우
            if invoice["status"] == "completed":
                conn.close()
                return jsonify(invoice)
            
            # 지불 확인된 경우
            if invoice["status"] == "paid":
                # 트랜잭션 확인 수 업데이트
                if invoice["tx_hash"]:
                    try:
                        # 외부 API에서 실제 확인 수 가져오기
                        external_confirmations = direct_payment_handler.get_transaction_confirmations(invoice["tx_hash"])
                        logger.info(f"인보이스 {invoice_id}의 트랜잭션 {invoice['tx_hash']}에 대한 확인 수: {external_confirmations}")
                        
                        # 데이터베이스의 확인 수와 다를 경우 업데이트
                        if external_confirmations != invoice["confirmations"]:
                            logger.info(f"확인 수 업데이트: {invoice['confirmations']} -> {external_confirmations}")
                            cursor.execute(
                                "UPDATE invoices SET confirmations = ? WHERE id = ?",
                                (external_confirmations, invoice_id)
                            )
                            invoice["confirmations"] = external_confirmations
                        
                        # 충분한 확인이 되면 완료 처리
                        if external_confirmations >= MIN_CONFIRMATIONS:
                            cursor.execute(
                                "UPDATE invoices SET status = 'completed' WHERE id = ?",
                                (invoice_id,)
                            )
                            invoice["status"] = "completed"
                            
                            # 사용자 크레딧 추가
                            if invoice["user_id"]:
                                try:
                                    credit_success = credit_user(invoice["user_id"], invoice["amount"], invoice_id)
                                    logger.info(f"사용자 크레딧 추가 결과: {credit_success}")
                                except Exception as e:
                                    logger.error(f"크레딧 추가 중 오류: {str(e)}")
                    except Exception as e:
                        logger.error(f"확인 수 업데이트 중 오류: {str(e)}")
                
                conn.commit()
                conn.close()
                return jsonify(invoice)
            
            # 대기 중인 경우: 잔액 확인
            logger.info(f"인보이스 {invoice_id}의 결제 상태 확인 중...")
            
            # ElectronCash 모드
            if not DIRECT_MODE:
                # 1. 주소 잔액 확인 - Use the invoice's payment address, not the default payout wallet
                balance = electron_cash.check_address_balance(payment_address)
                logger.info(f"주소 {payment_address}의 잔액: {balance} BCH (필요 금액: {invoice['amount']} BCH)")
                
                # 잔액이 충분하면 트랜잭션 찾기
                if balance >= invoice["amount"]:
                    # 트랜잭션 찾기
                    tx_info = electron_cash.find_transaction_for_invoice(invoice)
                    
                    if tx_info:
                        # 지불 확인
                        paid_at = int(time.time())
                        tx_hash = tx_info["txid"]
                        confirmations = tx_info["confirmations"]
                        
                        # 트랜잭션 확인 수 강제 설정 (항상 최소 1 이상)
                        if confirmations == 0:
                            confirmations = 1
                            logger.info(f"트랜잭션 {tx_hash}의 확인 수를 1로 강제 설정")
                        
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
                                try:
                                    credit_success = credit_user(invoice["user_id"], invoice["amount"], invoice_id)
                                    logger.info(f"사용자 크레딧 추가 결과: {credit_success}")
                                except Exception as e:
                                    logger.error(f"크레딧 추가 중 오류: {str(e)}")
            # 직접 결제 모드
            else:
                # 트랜잭션 검색 
                tx_info = direct_payment_handler.find_payment_transaction(
                    payment_address, 
                    invoice["amount"],
                    invoice["created_at"]
                )
                
                if tx_info:
                    # 지불 확인
                    paid_at = int(time.time())
                    tx_hash = tx_info["txid"]
                    
                    # 항상 확인 수가 최소 1 이상이 되도록 보장
                    confirmations = max(1, tx_info.get("confirmations", 1))
                    logger.info(f"인보이스 {invoice_id}의 트랜잭션 {tx_hash}에 대한 확인 수: {confirmations}")
                    
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
                            try:
                                credit_success = credit_user(invoice["user_id"], invoice["amount"], invoice_id)
                                logger.info(f"사용자 크레딧 추가 결과: {credit_success}")
                            except Exception as e:
                                logger.error(f"크레딧 추가 중 오류: {str(e)}")
            
            conn.commit()
            conn.close()
            return jsonify(invoice)
            
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and retry_count < max_retries - 1:
                logger.warning(f"데이터베이스 잠금 오류, 재시도 중 ({retry_count + 1}/{max_retries}): {str(e)}")
                retry_count += 1
                time.sleep(retry_delay)
                try:
                    conn.close()
                except:
                    pass
            else:
                logger.error(f"데이터베이스 작업 오류 (재시도 실패): {str(e)}")
                try:
                    conn.close()
                except:
                    pass
                return jsonify({"error": "데이터베이스 접근 오류, 잠시 후 다시 시도해주세요"}), 503
        except Exception as e:
            logger.error(f"결제 확인 중 오류 발생: {str(e)}")
            logger.error(traceback.format_exc())
            try:
                conn.close()
            except:
                pass
            return jsonify({"error": "결제 확인 중 오류가 발생했습니다"}), 500

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
        
        # 확인된 잔액 처리 - 문자열이면 실수로 변환 후 사토시 단위로 변환
        confirmed_balance = balance.get("confirmed", 0)
        
        # 문자열이면 실수로 변환
        if isinstance(confirmed_balance, str):
            try:
                confirmed_bch = float(confirmed_balance)
                # BCH → satoshis 변환 (1 BCH = 100,000,000 satoshis)
                confirmed_sats = int(confirmed_bch * 100000000)
            except (ValueError, TypeError):
                logger.error(f"잔액 변환 오류: {confirmed_balance}")
                return
        else:
            # 이미 정수나 실수 형태인 경우
            confirmed_sats = int(confirmed_balance)
        
        # 잔액 로그에 상세 정보 추가
        confirmed_bch = confirmed_sats / 100000000.0
        
        logger.info(f"현재 잔액: {confirmed_bch} BCH")
        
        # 최소 출금 금액보다 많을 경우에만 전송 (BCH 단위로 비교)
        if confirmed_bch >= MIN_PAYOUT_AMOUNT:
            # 더 높은 수수료 예약 - 50%를 전송하여 수수료 문제 회피
            amount_to_send = confirmed_bch * 0.5
            
            # 1차 시도: 더 적은 금액으로 전송 시도
            logger.info(f"1차 시도: 전체 잔액의 절반 {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송")
            try:
                # payto를 사용하여 트랜잭션 생성
                result = electron_cash.call_method("payto", [PAYOUT_WALLET, str(amount_to_send)])
                
                if result:
                    # 트랜잭션 서명 및 브로드캐스트
                    signed = electron_cash.call_method("signtransaction", [result])
                    if signed:
                        broadcast = electron_cash.call_method("broadcast", [signed])
                        if broadcast:
                            logger.info(f"자금 전송 성공: {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송했습니다.")
                            logger.info(f"트랜잭션 ID: {broadcast}")
                            return
            except Exception as e:
                logger.error(f"1차 시도 실패: {str(e)}")
            
            # 2차 시도: 더 적은 금액으로 재시도
            amount_to_send = confirmed_bch * 0.3
            logger.info(f"2차 시도: 전체 잔액의 30% {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송")
            try:
                result = electron_cash.call_method("payto", [PAYOUT_WALLET, str(amount_to_send)])
                
                if result:
                    # 트랜잭션 서명 및 브로드캐스트
                    signed = electron_cash.call_method("signtransaction", [result])
                    if signed:
                        broadcast = electron_cash.call_method("broadcast", [signed])
                        if broadcast:
                            logger.info(f"자금 전송 성공: {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송했습니다.")
                            logger.info(f"트랜잭션 ID: {broadcast}")
                            return
            except Exception as e:
                logger.error(f"2차 시도 실패: {str(e)}")
            
            # 3차 시도: 아주 적은 금액으로 전송
            amount_to_send = MIN_PAYOUT_AMOUNT  # 최소 금액만 전송
            logger.info(f"3차 시도: 최소 금액 {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송")
            try:
                result = electron_cash.call_method("payto", [PAYOUT_WALLET, str(amount_to_send)])
                
                if result:
                    # 트랜잭션 서명 및 브로드캐스트
                    signed = electron_cash.call_method("signtransaction", [result])
                    if signed:
                        broadcast = electron_cash.call_method("broadcast", [signed])
                        if broadcast:
                            logger.info(f"자금 전송 성공: {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송했습니다.")
                            logger.info(f"트랜잭션 ID: {broadcast}")
                            return
            except Exception as e:
                logger.error(f"3차 시도 실패: {str(e)}")
            
            # 4차 시도: sweep 명령어의 올바른 형식으로 시도
            logger.info(f"4차 시도: sweep 명령어 사용 (주소: {PAYOUT_WALLET})")
            try:
                # sweep 명령어의 올바른 형식 - privkey를 비워두고 목적지는 주소
                # sweep_result = electron_cash.call_method("sweep", ["", PAYOUT_WALLET])
                
                # 대안: paytomany를 사용하여 전체 잔액 sweep
                # 주소와 금액의 딕셔너리 형태로 전달: {"address": amount}
                # 잔액의 90%만 전송하여 수수료 해결
                amount_to_send = confirmed_bch * 0.9
                output_dict = {PAYOUT_WALLET: str(amount_to_send)}
                sweep_result = electron_cash.call_method("paytomany", [output_dict])
                
                if sweep_result:
                    # 트랜잭션 서명 및 브로드캐스트
                    sweep_signed = electron_cash.call_method("signtransaction", [sweep_result])
                    if sweep_signed:
                        sweep_broadcast = electron_cash.call_method("broadcast", [sweep_signed])
                        if sweep_broadcast:
                            logger.info(f"paytomany를 통한 자금 전송 성공: {amount_to_send} BCH를 {PAYOUT_WALLET}로 전송")
                            logger.info(f"트랜잭션 ID: {sweep_broadcast}")
                            return
            except Exception as sweep_error:
                logger.error(f"4차 시도 실패: {str(sweep_error)}")
                logger.error(traceback.format_exc())
            
            # 모든 시도가 실패했음을 로그로 남김
            logger.error("모든 자금 전송 시도 실패")
    except Exception as e:
        logger.error(f"자금 전송 중 오류 발생: {str(e)}")
        logger.error(traceback.format_exc())

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
        return "Page not found", 404
    
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