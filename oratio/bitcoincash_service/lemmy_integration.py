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
    
    def login_as_admin(self, max_retries: int = 3) -> bool:
        """관리자로 로그인하여 JWT 토큰 획득
        
        Args:
            max_retries: Maximum number of retry attempts for duplicate key errors
        """
        logger.info("🔐 [LEMMY LOGIN] Starting admin login process...")
        
        if not self.admin_credentials:
            logger.error("❌ [LEMMY LOGIN] 관리자 인증 정보가 설정되지 않았습니다")
            return False
        
        logger.info(f"🔐 [LEMMY LOGIN] Admin credentials: username={self.admin_credentials.get('username_or_email')}, password={'*' * len(self.admin_credentials.get('password', ''))}")
        
        url = f"{self.base_url}/api/v3/user/login"
        logger.info(f"🔐 [LEMMY LOGIN] Login URL: {url}")
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Wait before retry to avoid duplicate key collision
                    wait_time = 0.5 * (attempt + 1)
                    logger.info(f"🔐 [LEMMY LOGIN] Retry attempt {attempt + 1}/{max_retries}, waiting {wait_time}s...")
                    time.sleep(wait_time)
                
                logger.info(f"🔐 [LEMMY LOGIN] Sending POST request...")
                response = requests.post(url, json=self.admin_credentials, timeout=10)
                logger.info(f"🔐 [LEMMY LOGIN] Response status: {response.status_code}")
                logger.info(f"🔐 [LEMMY LOGIN] Response body: {response.text[:500]}")
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"🔐 [LEMMY LOGIN] Response JSON keys: {data.keys()}")
                    if "jwt" in data:
                        self.jwt_token = data["jwt"]
                        logger.info(f"✅ [LEMMY LOGIN] 관리자 로그인 성공! JWT token length: {len(self.jwt_token)}")
                        return True
                    else:
                        logger.error(f"❌ [LEMMY LOGIN] JWT 토큰을 찾을 수 없습니다. Response: {data}")
                elif response.status_code == 400:
                    # Check for duplicate key error - this happens when login tokens collide
                    try:
                        error_data = response.json()
                        if 'duplicate key' in error_data.get('message', '').lower() or 'login_token_pkey' in error_data.get('message', ''):
                            logger.warning(f"⚠️ [LEMMY LOGIN] Duplicate key error, will retry... (attempt {attempt + 1}/{max_retries})")
                            continue  # Retry with delay
                    except:
                        pass
                    logger.error(f"❌ [LEMMY LOGIN] 로그인 실패: {response.status_code} - {response.text}")
                else:
                    logger.error(f"❌ [LEMMY LOGIN] 로그인 실패: {response.status_code} - {response.text}")
                    break  # Don't retry for other errors
            except requests.exceptions.Timeout:
                logger.error(f"❌ [LEMMY LOGIN] 로그인 요청 타임아웃")
            except requests.exceptions.ConnectionError as e:
                logger.error(f"❌ [LEMMY LOGIN] 연결 오류: {str(e)}")
            except Exception as e:
                logger.error(f"❌ [LEMMY LOGIN] 로그인 요청 중 오류 발생: {str(e)}")
                import traceback
                logger.error(f"❌ [LEMMY LOGIN] Traceback: {traceback.format_exc()}")
        
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
    
    def get_username_by_id(self, user_id: int) -> Optional[str]:
        """사용자 ID로 사용자명 조회"""
        user_info = self.get_user_info(user_id)
        if user_info and "person" in user_info:
            return user_info["person"]["name"]
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

    def get_post(self, post_id: int) -> Optional[Dict[str, Any]]:
        """
        게시글 정보 조회 (community 정보 포함)
        
        Args:
            post_id: 게시글 ID
            
        Returns:
            게시글 정보 dict 또는 None
            반환값 예시: {
                "post_view": {
                    "post": {...},
                    "community": {"id": 1, "name": "banmal", "title": "반말"},
                    ...
                }
            }
        """
        url = f"{self.base_url}/api/v3/post"
        params = {"id": post_id}
        
        try:
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"게시글 정보 조회 실패: post_id={post_id}, status={response.status_code}")
        except Exception as e:
            logger.error(f"게시글 정보 요청 중 오류 발생: post_id={post_id}, error={str(e)}")
        
        return None

    def get_community_by_post_id(self, post_id: int) -> Optional[Dict[str, str]]:
        """
        게시글 ID로 커뮤니티 정보 조회 (광고 타겟팅용)
        
        Args:
            post_id: 게시글 ID
            
        Returns:
            {"name": "banmal", "title": "반말"} 형태 또는 None
        """
        post_data = self.get_post(post_id)
        if post_data and "post_view" in post_data:
            community = post_data["post_view"].get("community", {})
            if community:
                return {
                    "name": community.get("name", ""),
                    "title": community.get("title", "")
                }
        return None

    def remove_post(self, post_id: int, removed: bool = True, reason: Optional[str] = None) -> bool:
        """게시글 제거/복원 (관리자/모더레이터 권한 필요)"""
        logger.info(f"🔧 [LEMMY API] remove_post called: post_id={post_id}, removed={removed}, reason={reason}")
        logger.info(f"🔧 [LEMMY API] JWT token present: {bool(self.jwt_token)}")
        
        if not self.jwt_token and not self.login_as_admin():
            logger.error("❌ [LEMMY API] JWT 토큰이 없습니다. 관리자 로그인이 필요합니다.")
            return False
        
        url = f"{self.base_url}/api/v3/post/remove"
        data = {
            "post_id": post_id,
            "removed": removed
        }
        
        if reason:
            data["reason"] = reason
        
        logger.info(f"🔧 [LEMMY API] Request URL: {url}")
        logger.info(f"🔧 [LEMMY API] Request data: {data}")
        
        try:
            response = requests.post(url, json=data, headers=self.get_headers())
            logger.info(f"🔧 [LEMMY API] Response status: {response.status_code}")
            logger.info(f"🔧 [LEMMY API] Response body: {response.text[:500]}")
            
            if response.status_code == 200:
                action = "제거" if removed else "복원"
                logger.info(f"✅ [LEMMY API] 게시글 {post_id} {action}됨")
                return True
            else:
                logger.error(f"❌ [LEMMY API] 게시글 제거 실패: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"❌ [LEMMY API] 게시글 제거 요청 중 오류 발생: {str(e)}")
            import traceback
            logger.error(f"❌ [LEMMY API] Traceback: {traceback.format_exc()}")
        
        return False
    
    def remove_comment(self, comment_id: int, removed: bool = True, reason: Optional[str] = None) -> bool:
        """댓글 제거/복원 (관리자/모더레이터 권한 필요)"""
        logger.info(f"🔧 [LEMMY API] remove_comment called: comment_id={comment_id}, removed={removed}, reason={reason}")
        logger.info(f"🔧 [LEMMY API] JWT token present: {bool(self.jwt_token)}")
        
        if not self.jwt_token and not self.login_as_admin():
            logger.error("❌ [LEMMY API] JWT 토큰이 없습니다. 관리자 로그인이 필요합니다.")
            return False
        
        url = f"{self.base_url}/api/v3/comment/remove"
        data = {
            "comment_id": comment_id,
            "removed": removed
        }
        
        if reason:
            data["reason"] = reason
        
        logger.info(f"🔧 [LEMMY API] Request URL: {url}")
        logger.info(f"🔧 [LEMMY API] Request data: {data}")
        
        try:
            response = requests.post(url, json=data, headers=self.get_headers())
            logger.info(f"🔧 [LEMMY API] Response status: {response.status_code}")
            logger.info(f"🔧 [LEMMY API] Response body: {response.text[:500]}")
            
            if response.status_code == 200:
                action = "제거" if removed else "복원"
                logger.info(f"✅ [LEMMY API] 댓글 {comment_id} {action}됨")
                return True
            else:
                logger.error(f"❌ [LEMMY API] 댓글 제거 실패: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"❌ [LEMMY API] 댓글 제거 요청 중 오류 발생: {str(e)}")
            import traceback
            logger.error(f"❌ [LEMMY API] Traceback: {traceback.format_exc()}")
        
        return False

    def purge_post(self, post_id: int, reason: Optional[str] = None) -> bool:
        """게시글 영구 삭제 (관리자 권한 필요) - 완전히 삭제되어 누구도 볼 수 없음"""
        logger.info(f"🔧 [LEMMY API] purge_post called: post_id={post_id}, reason={reason}")
        logger.info(f"🔧 [LEMMY API] JWT token present: {bool(self.jwt_token)}")
        
        if not self.jwt_token and not self.login_as_admin():
            logger.error("❌ [LEMMY API] JWT 토큰이 없습니다. 관리자 로그인이 필요합니다.")
            return False
        
        url = f"{self.base_url}/api/v3/admin/purge/post"
        data = {"post_id": post_id}
        
        if reason:
            data["reason"] = reason
        
        logger.info(f"🔧 [LEMMY API] Request URL: {url}")
        logger.info(f"🔧 [LEMMY API] Request data: {data}")
        
        try:
            response = requests.post(url, json=data, headers=self.get_headers())
            logger.info(f"🔧 [LEMMY API] Response status: {response.status_code}")
            logger.info(f"🔧 [LEMMY API] Response body: {response.text[:500]}")
            
            if response.status_code == 200:
                logger.info(f"✅ [LEMMY API] 게시글 {post_id} 영구 삭제됨 (purged)")
                return True
            else:
                logger.error(f"❌ [LEMMY API] 게시글 영구 삭제 실패: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"❌ [LEMMY API] 게시글 영구 삭제 요청 중 오류 발생: {str(e)}")
            import traceback
            logger.error(f"❌ [LEMMY API] Traceback: {traceback.format_exc()}")
        
        return False

    def purge_comment(self, comment_id: int, reason: Optional[str] = None) -> bool:
        """댓글 영구 삭제 (관리자 권한 필요) - 완전히 삭제되어 누구도 볼 수 없음"""
        logger.info(f"🔧 [LEMMY API] purge_comment called: comment_id={comment_id}, reason={reason}")
        logger.info(f"🔧 [LEMMY API] JWT token present: {bool(self.jwt_token)}")
        
        if not self.jwt_token and not self.login_as_admin():
            logger.error("❌ [LEMMY API] JWT 토큰이 없습니다. 관리자 로그인이 필요합니다.")
            return False
        
        url = f"{self.base_url}/api/v3/admin/purge/comment"
        data = {"comment_id": comment_id}
        
        if reason:
            data["reason"] = reason
        
        logger.info(f"🔧 [LEMMY API] Request URL: {url}")
        logger.info(f"🔧 [LEMMY API] Request data: {data}")
        
        try:
            response = requests.post(url, json=data, headers=self.get_headers())
            logger.info(f"🔧 [LEMMY API] Response status: {response.status_code}")
            logger.info(f"🔧 [LEMMY API] Response body: {response.text[:500]}")
            
            if response.status_code == 200:
                logger.info(f"✅ [LEMMY API] 댓글 {comment_id} 영구 삭제됨 (purged)")
                return True
            else:
                logger.error(f"❌ [LEMMY API] 댓글 영구 삭제 실패: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"❌ [LEMMY API] 댓글 영구 삭제 요청 중 오류 발생: {str(e)}")
            import traceback
            logger.error(f"❌ [LEMMY API] Traceback: {traceback.format_exc()}")
        
        return False

    def ban_person(self, person_id: int, ban: bool = True, reason: Optional[str] = None, 
                   expires: Optional[int] = None, remove_data: bool = False) -> bool:
        """
        사용자 차단/차단 해제 (관리자 권한 필요)
        
        Args:
            person_id: 차단할 사용자 ID (Lemmy person_id)
            ban: True=차단, False=차단 해제
            reason: 차단 사유
            expires: 차단 만료 시간 (Unix timestamp, None=영구)
            remove_data: 사용자 데이터 삭제 여부
        
        Returns:
            성공 여부
        """
        logger.info(f"🔧 [LEMMY API] ban_person called: person_id={person_id}, ban={ban}, reason={reason}, expires={expires}")
        logger.info(f"🔧 [LEMMY API] JWT token present: {bool(self.jwt_token)}")
        
        if not self.jwt_token and not self.login_as_admin():
            logger.error("❌ [LEMMY API] JWT 토큰이 없습니다. 관리자 로그인이 필요합니다.")
            return False
        
        url = f"{self.base_url}/api/v3/user/ban"
        data = {
            "person_id": person_id,
            "ban": ban,
            "remove_data": remove_data
        }
        
        if reason:
            data["reason"] = reason
        
        if expires:
            data["expires"] = expires
        
        logger.info(f"🔧 [LEMMY API] Request URL: {url}")
        logger.info(f"🔧 [LEMMY API] Request data: {data}")
        
        try:
            response = requests.post(url, json=data, headers=self.get_headers())
            logger.info(f"🔧 [LEMMY API] Response status: {response.status_code}")
            logger.info(f"🔧 [LEMMY API] Response body: {response.text[:500]}")
            
            if response.status_code == 200:
                action = "차단" if ban else "차단 해제"
                logger.info(f"✅ [LEMMY API] 사용자 {person_id} {action}됨")
                return True
            else:
                logger.error(f"❌ [LEMMY API] 사용자 차단 실패: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"❌ [LEMMY API] 사용자 차단 요청 중 오류 발생: {str(e)}")
            import traceback
            logger.error(f"❌ [LEMMY API] Traceback: {traceback.format_exc()}")
        
        return False

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