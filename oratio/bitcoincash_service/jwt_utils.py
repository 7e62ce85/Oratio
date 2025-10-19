"""JWT 토큰 처리 유틸리티"""
import jwt
from flask import request
from config import logger
from typing import Optional, Dict


def extract_user_info_from_jwt() -> Optional[Dict[str, str]]:
    """
    HTTP 요청의 쿠키에서 JWT 토큰을 추출하고 사용자 정보를 반환
    
    Returns:
        dict or None: {'person_id': str, 'username': str}, 실패 시 None
    """
    try:
        # 쿠키에서 jwt 토큰 가져오기 (lemmy-ui가 사용하는 쿠키 이름)
        jwt_token = request.cookies.get('jwt')
        
        if not jwt_token:
            logger.debug("JWT 토큰이 쿠키에 없음")
            return None
        
        # JWT 디코드 (검증 없이 - 서명 검증은 lemmy 서버에서 이미 했음)
        # Lemmy의 JWT는 HS256 알고리즘을 사용하지만, 여기서는 검증 없이 디코드만 함
        decoded = jwt.decode(jwt_token, options={"verify_signature": False})
        
        # Lemmy JWT 구조: {"sub": person_id, "iss": "lemmy", "iat": timestamp}
        person_id = decoded.get('sub')
        
        if not person_id:
            logger.warning("JWT에 'sub' 필드가 없음")
            return None
        
        # person_id로 username 조회
        username = get_username_from_lemmy(person_id)
        
        user_info = {
            'person_id': str(person_id),
            'username': username or f"User#{person_id}"
        }
        
        logger.info(f"JWT에서 사용자 정보 추출 성공: person_id={person_id}, username={username}")
        return user_info
            
    except jwt.DecodeError as e:
        logger.error(f"JWT 디코드 실패: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"JWT 처리 중 예외 발생: {str(e)}")
        return None


def get_username_from_lemmy(person_id: int) -> Optional[str]:
    """
    Lemmy API를 호출하여 person_id로 username을 조회
    
    Args:
        person_id: 사용자의 person_id
    
    Returns:
        str or None: username, 실패 시 None
    """
    try:
        from lemmy_integration import setup_lemmy_integration
        
        lemmy_api = setup_lemmy_integration()
        if lemmy_api:
            username = lemmy_api.get_username_by_id(int(person_id))
            if username:
                logger.info(f"Lemmy API에서 username 조회 성공: {username}")
                return username
            else:
                logger.warning(f"person_id {person_id}에 대한 username을 찾을 수 없음")
        else:
            logger.warning("Lemmy API 초기화 실패")
    except Exception as e:
        logger.error(f"username 조회 중 오류: {str(e)}")
    
    return None


def extract_user_id_from_jwt():
    """
    HTTP 요청의 쿠키에서 JWT 토큰을 추출하고 사용자 ID를 반환 (하위 호환성)
    
    Returns:
        str or None: 사용자 ID (person_id), 실패 시 None
    """
    user_info = extract_user_info_from_jwt()
    return user_info['person_id'] if user_info else None


def get_user_id_from_request():
    """
    요청에서 사용자 ID를 가져옴 (JWT 또는 파라미터)
    
    우선순위:
    1. URL 파라미터의 user_id (수동 입력된 경우)
    2. JWT 토큰에서 추출한 person_id
    
    Returns:
        str: 사용자 ID, 없으면 빈 문자열
    """
    # URL 파라미터 확인
    user_id = request.args.get('user_id', '').strip()
    
    if user_id:
        logger.info(f"URL 파라미터에서 사용자 ID 사용: {user_id}")
        return user_id
    
    # JWT에서 추출 시도
    jwt_user_id = extract_user_id_from_jwt()
    
    if jwt_user_id:
        logger.info(f"JWT에서 추출한 사용자 ID 사용: {jwt_user_id}")
        return jwt_user_id
    
    logger.warning("사용자 ID를 찾을 수 없음 (파라미터도 없고 JWT도 없음)")
    return ''
