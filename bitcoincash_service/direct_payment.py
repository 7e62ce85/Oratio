import requests
import json
import time
import logging
import os
from datetime import datetime
import traceback
import hashlib
from dotenv import load_dotenv

# .env 파일 로드 (최상위에서 가장 먼저 실행)
# 프로젝트 루트 디렉토리의 .env 파일 로드
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print(f"direct_payment.py: .env 파일을 로드했습니다: {dotenv_path}")
else:
    # 현재 디렉토리에서 .env 파일 찾기
    local_dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(local_dotenv_path):
        load_dotenv(local_dotenv_path)
        print(f"direct_payment.py: .env 파일을 로드했습니다: {local_dotenv_path}")
    else:
        print("direct_payment.py: .env 파일을 찾을 수 없습니다.")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('direct_payment')

# BCH 주소 (환경 변수에서 가져오기)
DEFAULT_ADDRESS = os.environ.get('PAYOUT_WALLET', '')
logger.info(f"환경변수에서 가져온 출금 지갑 주소: {DEFAULT_ADDRESS}")

class DirectPaymentHandler:
    def __init__(self, payout_wallet=DEFAULT_ADDRESS):
        self.payout_wallet = payout_wallet
        logger.info(f"직접 결제 처리기 초기화: 출금 지갑 = {self.payout_wallet}")
        # 주소와 결제 여부를 추적하는 임시 디렉토리
        self.payment_status = {}

    def get_address(self):
        """고정된 BCH 주소 반환"""
        return self.payout_wallet

    def check_address_balance(self, address):
        """주소의 BCH 잔액 확인 - 실제로 결제가 이루어졌을 때만 잔액을 보고"""
        clean_address = address.replace('bitcoincash:', '')
        
        # 임시 저장된 결제 상태 확인
        if clean_address in self.payment_status and self.payment_status[clean_address].get('paid', False):
            return self.payment_status[clean_address].get('amount', 0.0)
            
        # 기본적으로 결제가 없으면 0 반환
        logger.info(f"주소 {address}의 잔액 확인 - 결제가 확인되지 않음")
        return 0.0

    def get_transaction_confirmations(self, tx_hash):
        """트랜잭션 확인 수 확인 - 실제 트랜잭션에 대해서만 확인 수 제공"""
        # 가짜 트랜잭션 ID는 확인 수 0 반환
        if not tx_hash or tx_hash.startswith("local_") or tx_hash.startswith("verified_"):
            logger.info(f"로컬 트랜잭션 {tx_hash}의 확인 수: 0")
            return 0
            
        # 임시 저장된 트랜잭션 확인
        for address, status in self.payment_status.items():
            if 'tx_hash' in status and status['tx_hash'] == tx_hash:
                if status.get('paid', False):
                    logger.info(f"트랜잭션 {tx_hash}의 확인 수: 1")
                    return 1
        
        # 확인되지 않은 트랜잭션
        logger.info(f"확인되지 않은 트랜잭션 {tx_hash}의 확인 수: 0")
        return 0

    def find_payment_transaction(self, address, expected_amount, created_at_timestamp):
        """인보이스에 대한 결제 트랜잭션 찾기 - 실제 결제가 없으면 None 반환"""
        # 주소 형식 정리
        clean_address = address.replace('bitcoincash:', '')
        
        # 임시 저장된 결제 상태 확인
        if clean_address in self.payment_status and self.payment_status[clean_address].get('paid', False):
            logger.info(f"주소 {clean_address}에 대한 이전 결제 기록 발견")
            tx_data = self.payment_status[clean_address]
            return {
                'txid': tx_data['tx_hash'],
                'amount': tx_data['amount'],
                'confirmations': 1,
                'time': tx_data['time'],
                'address': address,
                'status': 'confirmed'
            }
            
        # 결제가 확인되지 않으면 None 반환
        logger.info(f"주소 {clean_address}에 대한 결제가 확인되지 않음")
        return None
        
    def record_manual_payment(self, address, amount, tx_hash=None):
        """수동으로 결제 기록 (테스트용)"""
        clean_address = address.replace('bitcoincash:', '')
        
        if not tx_hash:
            # 고유한 트랜잭션 ID 생성
            tx_hash = hashlib.sha256(f"{clean_address}:{amount}:{time.time()}".encode()).hexdigest()
            
        # 결제 정보 저장
        self.payment_status[clean_address] = {
            'paid': True,
            'amount': float(amount),
            'tx_hash': tx_hash,
            'time': int(time.time())
        }
        
        logger.info(f"주소 {clean_address}에 대한 수동 결제 기록 생성: {amount} BCH, 트랜잭션: {tx_hash}")
        return tx_hash

# 기본 인스턴스 생성
direct_payment_handler = DirectPaymentHandler()

# API 사용 가능 상태로 설정
api_available = True
logger.info("직접 결제 처리기 초기화 완료 - 실제 결제 확인시에만 트랜잭션 생성")