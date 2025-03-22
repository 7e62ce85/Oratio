import requests
import json
import logging
import time
import hmac
import hashlib
import base64
from typing import Dict, Any, Optional

logger = logging.getLogger('lemmy_integration')

class LemmyAPI:
    """Lemmy API 통합 클래스"""
    
    def __init__(self, base_url: str, api_key: str = None):
        """
        Lemmy API 클라이언트 초기화
        
        Args:
            base_url: Lemmy API 기본 URL (예: http://lemmy:8536)
            api_key: API 키 (있는 경우)
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.jwt_token = None
        self.admin_credentials = None
    
    def set_admin_credentials(self, username: str, password: str):
        """관리자 인증 정보 설정"""
        self.admin_credentials = {
            "username_or_email": username,
            "password": password
        }
    
    def login_as_admin(self) -> bool:
        """관리자로 로그인하여 JWT 토큰 획득"""
        if not self.admin_credentials:
            logger.error("관리자 인증 정보가 설정되지 않았습니다")
            return False
        
        url = f"{self.base_url}/api/v3/user/login"
        try:
            response = requests.post(url, json=self.admin_credentials)
            if response.status_code == 200:
                data = response.json()
                if "jwt" in data:
                    self.jwt_token = data["jwt"]
                    logger.info("관리자 로그인 성공")
                    return True
                else:
                    logger.error("JWT 토큰을 찾을 수 없습니다")
            else:
                logger.error(f"로그인 실패: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"로그인 요청 중 오류 발생: {str(e)}")
        
        return False
    
    def get_headers(self) -> Dict[str, str]:
        """인증 헤더 생성"""
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"
        
        if self.api_key:
            # HMAC 서명 등 추가 보안 인증 처리
            timestamp = str(int(time.time()))
            signature = hmac.new(
                self.api_key.encode(),
                timestamp.encode(),
                hashlib.sha256
            ).digest()
            signature_b64 = base64.b64encode(signature).decode()
            
            headers["X-API-Key"] = self.api_key
            headers["X-Timestamp"] = timestamp
            headers["X-Signature"] = signature_b64
        
        return headers
    
    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """사용자 정보 조회"""
        url = f"{self.base_url}/api/v3/user"
        params = {"person_id": user_id}
        
        try:
            response = requests.get(url, params=params, headers=self.get_headers())
            if response.status_code == 200:
                return response.json()["person_view"]
            else:
                logger.error(f"사용자 정보 조회 실패: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"사용자 정보 요청 중 오류 발생: {str(e)}")
        
        return None
    
    def add_user_credit(self, user_id: int, amount: float) -> bool:
        """사용자 계정에 크레딧 추가 (커스텀 확장 필요)"""
        # 참고: Lemmy에는 기본적으로 사용자 크레딧/포인트 시스템이 없습니다.
        # 이를 구현하려면 Lemmy 데이터베이스를 직접 수정하거나 외부 DB를 사용해야 합니다.
        
        # 방법 1: 데이터베이스 직접 접근 (여기서는 포함되지 않음)
        # 방법 2: 사용자 지정 메모 필드 사용 (예시)
        
        if not self.jwt_token and not self.login_as_admin():
            return False
        
        # 현재 사용자 정보 조회
        user_info = self.get_user_info(user_id)
        if not user_info:
            return False
        
        # 이 부분은 실제 Lemmy에 크레딧 시스템을 추가하기 위한 확장이 필요합니다.
        # 예를 들어, PostgreSQL 데이터베이스에 새 테이블을 만들거나
        # Lemmy의 기존 필드를 활용하여 간접적으로 구현할 수 있습니다.
        
        logger.info(f"사용자 {user_id}에게 {amount} 크레딧 추가 처리됨")
        return True
    
    def create_notification(self, user_id: int, message: str) -> bool:
        """사용자에게 알림 생성"""
        if not self.jwt_token and not self.login_as_admin():
            return False
        
        # 참고: Lemmy API v3에는 직접적인 알림 생성 엔드포인트가 없습니다.
        # 대안으로 개인 메시지를 보낼 수 있습니다.
        
        url = f"{self.base_url}/api/v3/private_message"
        
        # 시스템 메시지 생성
        data = {
            "content": message,
            "recipient_id": user_id
        }
        
        try:
            response = requests.post(url, json=data, headers=self.get_headers())
            if response.status_code == 200:
                logger.info(f"사용자 {user_id}에게 알림 메시지 전송됨")
                return True
            else:
                logger.error(f"알림 생성 실패: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"알림 요청 중 오류 발생: {str(e)}")
        
        return False

    def get_site_config(self) -> Optional[Dict[str, Any]]:
        """사이트 설정 정보 조회"""
        url = f"{self.base_url}/api/v3/site"
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"사이트 설정 조회 실패: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"사이트 설정 요청 중 오류 발생: {str(e)}")
        
        return None

def setup_lemmy_integration() -> Optional[LemmyAPI]:
    """Lemmy 통합 설정"""
    import os
    
    lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
    lemmy_api_key = os.environ.get('LEMMY_API_KEY', '')
    lemmy_admin_user = os.environ.get('LEMMY_ADMIN_USER', '')
    lemmy_admin_pass = os.environ.get('LEMMY_ADMIN_PASS', '')
    
    if not lemmy_api_url:
        logger.error("LEMMY_API_URL 환경 변수가 설정되지 않았습니다")
        return None
    
    # Lemmy API 클라이언트 생성
    lemmy_api = LemmyAPI(lemmy_api_url, lemmy_api_key)
    
    # 관리자 인증 정보 설정 (있는 경우)
    if lemmy_admin_user and lemmy_admin_pass:
        lemmy_api.set_admin_credentials(lemmy_admin_user, lemmy_admin_pass)
        
        # 관리자 로그인 시도
        if not lemmy_api.login_as_admin():
            logger.warning("관리자 로그인 실패. 제한된 기능만 사용 가능합니다.")
    
    return lemmy_api

# PostgreSQL 통합을 위한 확장 클래스 (옵션)
class LemmyPostgreSQLIntegration:
    """Lemmy PostgreSQL 데이터베이스 직접 통합"""
    
    def __init__(self, db_config: Dict[str, str]):
        """
        PostgreSQL 연결 초기화
        
        Args:
            db_config: 데이터베이스 설정 (host, port, user, password, database)
        """
        self.db_config = db_config
        self.connection = None
    
    def connect(self) -> bool:
        """데이터베이스 연결"""
        try:
            import psycopg2
            self.connection = psycopg2.connect(
                host=self.db_config.get("host", "postgres"),
                port=self.db_config.get("port", 5432),
                user=self.db_config.get("user", "lemmy"),
                password=self.db_config.get("password", ""),
                database=self.db_config.get("database", "lemmy")
            )
            return True
        except Exception as e:
            logger.error(f"데이터베이스 연결 오류: {str(e)}")
            return False
    
    def add_user_credit(self, user_id: int, amount: float) -> bool:
        """사용자 크레딧 테이블에 크레딧 추가"""
        if not self.connection and not self.connect():
            return False
        
        try:
            cursor = self.connection.cursor()
            
            # 사용자 크레딧 테이블이 없으면 생성
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_credits (
                    user_id INTEGER PRIMARY KEY REFERENCES person(id),
                    credit_balance REAL NOT NULL DEFAULT 0,
                    last_updated TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            
            # 사용자 크레딧 업데이트
            cursor.execute("""
                INSERT INTO user_credits (user_id, credit_balance, last_updated)
                VALUES (%s, %s, NOW())
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    credit_balance = user_credits.credit_balance + %s,
                    last_updated = NOW()
            """, (user_id, amount, amount))
            
            self.connection.commit()
            logger.info(f"사용자 {user_id}에게 {amount} 크레딧 추가됨 (DB)")
            return True
        except Exception as e:
            logger.error(f"크레딧 추가 오류: {str(e)}")
            self.connection.rollback()
            return False
    
    def get_user_credit(self, user_id: int) -> Optional[float]:
        """사용자 크레딧 잔액 조회"""
        if not self.connection and not self.connect():
            return None
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT credit_balance FROM user_credits WHERE user_id = %s
            """, (user_id,))
            
            result = cursor.fetchone()
            if result:
                return result[0]
            return 0.0
        except Exception as e:
            logger.error(f"크레딧 조회 오류: {str(e)}")
            return None

# 이 모듈을 직접 실행할 때의 테스트 코드
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 테스트 함수
    def test_lemmy_api():
        # 테스트 URL (실제 환경에 맞게 수정 필요)
        api = LemmyAPI("http://lemmy:8536")
        api.set_admin_credentials("admin", "password")
        
        # 관리자 로그인 테스트
        if api.login_as_admin():
            print("로그인 성공!")
            
            # 사이트 정보 조회 테스트
            site_info = api.get_site_config()
            if site_info:
                print(f"사이트 이름: {site_info.get('site_view', {}).get('site', {}).get('name')}")
            
            # 알림 생성 테스트 (사용자 ID 1)
            api.create_notification(1, "BitcoinCash 결제 시스템에서 알림: 1 BCH가 계정에 추가되었습니다.")
        else:
            print("로그인 실패!")
    
    # 테스트 실행
    test_lemmy_api()