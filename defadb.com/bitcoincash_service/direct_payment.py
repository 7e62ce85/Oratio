import os
import time
import logging
import requests
import json
from datetime import datetime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('direct_payment')

class DirectPaymentHandler:
    """ElectronCash 없이 실제 BCH 결제를 처리하는 클래스"""
    
    def __init__(self):
        # Coinomi 지갑 주소 설정
        self.payout_wallet = os.environ.get('PAYOUT_WALLET', 'bitcoincash:qz394b323707f3488f84112542799648')
        
        # Bitcoin.com REST API 사용
        # self.api_base_url = "https://rest.bitcoin.com/v2"
        
        # 대체 API 사용 옵션 (Blockchain.info 또는 Bitpay)
        # self.api_base_url = "https://bch-chain.api.btc.com/v3"
        self.api_base_url = "https://api.blockchair.com/bitcoin-cash"
        
        # 로그 출력
        logger.info(f"직접 결제 처리기 초기화: 출금 지갑 = {self.payout_wallet}")
    
    def get_address(self):
        """결제용 주소 반환 - 항상 Coinomi 주소 사용"""
        return self.payout_wallet
    
    def check_address_balance(self, address):
        """주소 잔액 확인 - Bitcoin.com API 사용"""
        try:
            # 주소 형식 정리
            clean_address = address
            if address.startswith("bitcoincash:"):
                clean_address = address[12:]
            
            # API 호출
            url = f"{self.api_base_url}/dashboards/address/{clean_address}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("context", {}).get("code") == 200:
                    # satoshis를 BCH로 변환 (1 BCH = 100,000,000 satoshis)
                    balance = data.get("data", {}).get(clean_address, {}).get("address", {}).get("balance", 0) / 100000000.0
                    logger.info(f"주소 {address}의 잔액: {balance} BCH")
                    return balance
                else:
                    logger.error(f"API 응답 오류: {data}")
            else:
                logger.error(f"API 호출 실패: {response.status_code}")
                return 0.0
        except Exception as e:
            logger.error(f"잔액 확인 오류: {str(e)}")
            return 0.0
    
    def get_transaction_confirmations(self, tx_hash):
        """트랜잭션 확인 수 확인 - BTC.com API 사용"""
        try:
            url = f"{self.api_base_url}/dashboards/transaction/{tx_hash}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("context", {}).get("code") == 200:
                    confirmations = data.get("data", {}).get(tx_hash, {}).get("transaction", {}).get("confirmations", 0)
                    logger.info(f"트랜잭션 {tx_hash}의 확인 수: {confirmations}")
                    return confirmations
                else:
                    logger.error(f"API 응답 오류: {data}")
            else:
                logger.error(f"트랜잭션 API 호출 실패: {response.status_code}")
            return 0
        except Exception as e:
            logger.error(f"트랜잭션 확인 오류: {str(e)}")
            return 0
        
    def get_recent_transactions(self, address, since_timestamp=None):
        """주소의 최근 트랜잭션 조회"""
        try:
            # 주소 형식 정리
            clean_address = address
            if address.startswith("bitcoincash:"):
                clean_address = address[12:]
            
            # API 호출
            url = f"{self.api_base_url}/address/transactions/{clean_address}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                txs = data.get("txs", [])
                
                # 시간 필터링
                if since_timestamp and txs:
                    filtered_txs = [tx for tx in txs if tx.get("time", 0) > since_timestamp]
                    return filtered_txs
                return txs
            else:
                logger.error(f"트랜잭션 목록 API 호출 실패: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"트랜잭션 조회 오류: {str(e)}")
            return []
    
    def find_payment_transaction(self, address, expected_amount, since_timestamp=None):
        """특정 주소로 들어온 결제 트랜잭션 찾기- BTC.com API 사용"""
        try:
            # 주소 형식 정리
            clean_address = address
            if address.startswith("bitcoincash:"):
                clean_address = address[12:]
                
            # API 호출
            url = f"{self.api_base_url}/dashboards/address/{clean_address}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("context", {}).get("code") == 200:
                    # 트랜잭션 목록 추출
                    transactions = data.get("data", {}).get(clean_address, {}).get("transactions", [])
                
                    if transactions:
                        logger.info(f"주소 {address}에 대한 {len(transactions)} 트랜잭션 발견")
                    
                        # 가장 최근 트랜잭션의 세부 정보 확인
                        for tx_hash in transactions[:5]:  # 최근 5개만 확인
                            tx_url = f"{self.api_base_url}/dashboards/transaction/{tx_hash}"
                            try:
                                tx_response = requests.get(tx_url, timeout=10)
                            
                                if tx_response.status_code == 200:
                                    tx_data = tx_response.json()
                                
                                    if tx_data.get("context", {}).get("code") == 200:
                                        # 트랜잭션 시간 확인
                                        tx_info = tx_data.get("data", {}).get(tx_hash, {}).get("transaction", {})
                                        tx_time = tx_info.get("time", 0)
                                    
                                        if since_timestamp and tx_time < since_timestamp:
                                            continue
                                    
                                        # 출력 목록에서 우리 주소로의 전송 확인
                                        outputs = tx_data.get("data", {}).get(tx_hash, {}).get("outputs", [])
                                    
                                        for output in outputs:
                                            # 출력 주소와 금액 확인
                                            recipient = output.get("recipient", "")
                                            value = output.get("value", 0) / 100000000.0  # satoshi to BCH
                                        
                                            # 주소와 금액이 일치하는지 확인
                                            if (recipient == clean_address or recipient == address) and abs(value - expected_amount) < 0.00001:
                                                confirmations = tx_info.get("confirmations", 0)
                                                logger.info(f"결제 트랜잭션 발견: {tx_hash} - 금액: {value} BCH, 확인 수: {confirmations}")
                                            
                                                return {
                                                    "txid": tx_hash,
                                                    "amount": value,
                                                    "confirmations": confirmations,
                                                    "time": tx_time
                                                }
                            except Exception as e:
                                logger.error(f"트랜잭션 세부 정보 조회 오류: {str(e)}")
                else:
                    logger.error(f"API 응답 오류: {data}")
            else:
                logger.error(f"트랜잭션 API 호출 실패: {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"결제 트랜잭션 검색 오류: {str(e)}")
            return None
    
# 전역 인스턴스 생성
direct_payment_handler = DirectPaymentHandler()