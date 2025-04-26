import os
import logging
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

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bch_payment.log')
    ]
)
logger = logging.getLogger('bch_payment')

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
PAYOUT_WALLET = os.environ.get('PAYOUT_WALLET', '')

# Flask 설정
FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# 데이터베이스 설정
DB_PATH = os.environ.get('DB_PATH', '/data/payments.db')

# ElectronCash 모듈 가용성 체크
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

# 직접 결제 모드 설정
try:
    from direct_payment import direct_payment_handler
    DIRECT_MODE = False
    logger.info("직접 결제 모드 활성화")
except ImportError:
    DIRECT_MODE = False
    logger.warning("직접 결제 모듈을 불러올 수 없습니다. ElectronCash 모드만 사용합니다.")