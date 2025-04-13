# test_transaction_search.py
import logging
import requests
import json
import sys
import time
from datetime import datetime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_api_connection(address):
    """API 연결 테스트"""
    logging.info(f"Blockchair API 연결 테스트 - 주소: {address}")
    
    try:
        response = requests.get(f"https://api.blockchair.com/bitcoin-cash/dashboards/address/{address}")
        data = response.json()
        
        if 'data' in data and address in data['data']:
            logging.info("API 연결 성공!")
            logging.info(f"트랜잭션 수: {len(data['data'][address]['transactions'])}")
            return True
        else:
            logging.error(f"API 응답 오류: {json.dumps(data, indent=2)}")
            return False
    except Exception as e:
        logging.error(f"API 연결 오류: {str(e)}")
        return False

def fetch_and_parse_transaction(tx_hash):
    """트랜잭션 세부 정보 가져오기 및 파싱"""
    logging.info(f"트랜잭션 정보 조회: {tx_hash}")
    
    try:
        response = requests.get(f"https://api.blockchair.com/bitcoin-cash/raw/transaction/{tx_hash}")
        data = response.json()
        
        if 'data' in data and tx_hash in data['data']:
            tx_data = data['data'][tx_hash]
            
            # 타임스탬프 처리 테스트
            tx_time_raw = tx_data.get('time', 0)
            logging.info(f"원본 타임스탬프: {tx_time_raw} (타입: {type(tx_time_raw).__name__})")
            
            # 문자열에서 정수로 변환 테스트
            if isinstance(tx_time_raw, str):
                tx_time = int(tx_time_raw)
            else:
                tx_time = tx_time_raw
                
            logging.info(f"변환된 타임스탬프: {tx_time} (타입: {type(tx_time).__name__})")
            logging.info(f"사람이 읽을 수 있는 시간: {datetime.fromtimestamp(tx_time).strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 수신 금액 계산 테스트
            vouts = tx_data.get('vout', [])
            logging.info(f"vout 항목 수: {len(vouts)}")
            
            for i, vout in enumerate(vouts):
                scriptPubKey = vout.get('scriptPubKey', {})
                addresses = scriptPubKey.get('addresses', [])
                value = vout.get('value', 0)
                
                logging.info(f"vout #{i} - 주소: {addresses}, 금액: {value}")
                
            return tx_data
        else:
            logging.error(f"트랜잭션 데이터 없음: {json.dumps(data, indent=2)}")
            return None
    except Exception as e:
        logging.error(f"트랜잭션 조회 오류: {str(e)}")
        return None

def main():
    """메인 테스트 함수"""
    if len(sys.argv) < 2:
        print("사용법: python test_transaction_search.py <BCH_주소>")
        return
        
    address = sys.argv[1]
    
    # API 연결 테스트
    if not test_api_connection(address):
        logging.error("API 연결 실패. 테스트를 중단합니다.")
        return
        
    # 주소의 트랜잭션 목록 가져오기
    try:
        response = requests.get(f"https://api.blockchair.com/bitcoin-cash/dashboards/address/{address}")
        data = response.json()
        
        if 'data' in data and address in data['data']:
            transactions = data['data'][address]['transactions']
            
            if not transactions:
                logging.info(f"주소 {address}에 트랜잭션이 없습니다.")
                return
                
            logging.info(f"총 {len(transactions)}개의 트랜잭션이 있습니다.")
            
            # 최근 트랜잭션 3개만 확인
            for tx_hash in transactions[:3]:
                fetch_and_parse_transaction(tx_hash)
                time.sleep(1)  # API 호출 제한 방지
        else:
            logging.error("트랜잭션 목록을 가져오는데 실패했습니다.")
    except Exception as e:
        logging.error(f"테스트 중 오류 발생: {str(e)}")

if __name__ == "__main__":
    main()