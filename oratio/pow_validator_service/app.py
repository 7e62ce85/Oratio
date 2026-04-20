"""
PoW Validator Service - Python Implementation
Lemmy 회원가입 시 Proof of Work 검증 프록시 서비스

Rust 백엔드 수정 없이 PoW 검증 기능 추가!
+ 스팸 필터: 보이지 않는 유니코드 문자(soft hyphen 등)를 벗겨낸 뒤 키워드 매칭
"""

from flask import Flask, request, jsonify
import requests
import hashlib
import time
import re
import unicodedata
import json
from typing import Optional, Dict, Any, List, Tuple

app = Flask(__name__)

# 설정 (환경변수 우선, 없으면 기본값 사용)
import os
POW_DIFFICULTY = int(os.environ.get('POW_DIFFICULTY', '16'))  # 최소 난이도 (적응형 난이도: 클라이언트가 16~18 사이에서 결정)
POW_MAX_AGE_SECONDS = int(os.environ.get('POW_MAX_AGE_SECONDS', '600'))  # 10분
LEMMY_BACKEND_URL = os.environ.get('LEMMY_BACKEND_URL', 'http://lemmy:8536')  # Docker 네트워크 내부


# ============================================================
# 스팸 필터 시스템
# ============================================================
# 봇이 "P­a­y­A­t­H­o­m­e" 처럼 글자 사이에 보이지 않는 문자를 
# 끼워넣어 필터를 우회하므로, 먼저 숨겨진 문자를 벗겨낸 뒤 검사한다.
# ============================================================

# 스팸 키워드 목록 (대소문자 무시, 정규식 지원)
# 새 스팸 패턴이 보이면 여기에 추가하면 됨
SPAM_KEYWORD_PATTERNS: List[str] = [
    # --- 돈벌기 스캠 사이트 ---
    r'payathome\d*\.com',
    r'workathome\d*\.com',
    r'earnathome\d*\.com',
    r'makemoneyathome\d*\.com',
    r'jobathome\d*\.com',
    r'homejobs?\d*\.com',
    r'easymoney\d*\.com',
    r'smartjob\d*\.com',
    r'dollartree\d*\.com',      # 스캠에서 자주 사용되는 도메인
    # --- 돈벌기 스캠 문구 패턴 ---
    r'i\s*(basically\s*)?make\s*(about\s*)?\$\d[\d,]*.*?a\s*month\s*online',
    r'enough\s*to\s*(comfortably\s*)?replace\s*my\s*(old\s*)?jobs?\s*income',
    # ❌ 제거됨: 'only work N hours a week from home' → 정상 재택근무 글에 오탐
    # ❌ 제거됨: 'amazed how easy it was' → 일상 표현이라 오탐 위험 높음
    r'you\s*can\s*check\s*more\s*[.=>\-]+',
]

# 환경변수로 추가 패턴 로드 (docker-compose.yml에서 설정 가능)
_extra_patterns = os.environ.get('SPAM_EXTRA_PATTERNS', '')
if _extra_patterns:
    try:
        SPAM_KEYWORD_PATTERNS.extend(json.loads(_extra_patterns))
        app.logger.info(f"Loaded {len(json.loads(_extra_patterns))} extra spam patterns from env")
    except json.JSONDecodeError:
        # 단일 패턴이면 그냥 추가
        SPAM_KEYWORD_PATTERNS.append(_extra_patterns)

# 미리 컴파일 (서버 시작 시 1회)
SPAM_COMPILED_PATTERNS = []
for pat in SPAM_KEYWORD_PATTERNS:
    try:
        SPAM_COMPILED_PATTERNS.append(re.compile(pat, re.IGNORECASE | re.DOTALL))
    except re.error as e:
        print(f"[WARN] Invalid spam pattern skipped: {pat!r} ({e})")


def strip_invisible_chars(text: str) -> str:
    """
    텍스트에서 보이지 않는/조작용 유니코드 문자를 모두 제거한다.
    
    제거 대상:
      - Soft Hyphen (U+00AD)  ← 이번 스팸봇이 사용
      - Zero-Width Space (U+200B)
      - Zero-Width Non-Joiner (U+200C)
      - Zero-Width Joiner (U+200D)
      - Left/Right-to-Left marks (U+200E, U+200F)
      - 기타 유니코드 "Format" 카테고리(Cf) 문자들
    
    Returns:
        눈에 보이는 문자만 남긴 깨끗한 텍스트
    """
    return ''.join(
        ch for ch in text
        if unicodedata.category(ch) != 'Cf'
    )


def check_spam(text: str) -> Tuple[bool, Optional[str]]:
    """
    텍스트가 스팸인지 검사한다.
    
    1) 보이지 않는 문자를 벗겨냄
    2) 스팸 키워드 패턴 매칭
    
    Returns:
        (is_spam, matched_pattern_or_None)
    """
    if not text:
        return False, None
    
    cleaned = strip_invisible_chars(text)
    
    for pattern in SPAM_COMPILED_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            return True, match.group(0)
    
    return False, None


def check_content_for_spam(data: dict, content_type: str) -> Optional[Tuple]:
    """
    게시글/댓글/회원가입 데이터에서 텍스트 필드를 추출하여 스팸 검사.
    
    Args:
        data: 요청 JSON 데이터
        content_type: 'comment', 'post', 'register' 중 하나
    
    Returns:
        None이면 스팸 아님, (field, matched) 튜플이면 스팸
    """
    fields_to_check = []
    
    if content_type == 'comment':
        fields_to_check = ['content']
    elif content_type == 'post':
        fields_to_check = ['name', 'body', 'url']
    elif content_type == 'register':
        fields_to_check = ['username', 'answer']  # 가입 시 답변란도 검사
    
    for field in fields_to_check:
        value = data.get(field)
        if value and isinstance(value, str):
            is_spam, matched = check_spam(value)
            if is_spam:
                return (field, matched)
    
    return None

# PoW 검증 결과
class PowVerificationResult:
    VALID = "valid"
    INVALID_HASH = "invalid_hash"
    INVALID_DIFFICULTY = "invalid_difficulty"
    EXPIRED = "expired"
    MISSING = "missing"


def sha256(text: str) -> str:
    """SHA-256 해시 계산"""
    return hashlib.sha256(text.encode()).hexdigest()


def check_difficulty(hash_hex: str, difficulty: int) -> bool:
    """
    해시의 앞 N비트가 0인지 확인
    
    Args:
        hash_hex: 16진수 해시 문자열
        difficulty: 앞에서부터 0이어야 하는 비트 수
    
    Returns:
        조건 만족 여부
    """
    bits_checked = 0
    
    for hex_char in hash_hex:
        if bits_checked >= difficulty:
            return True
        
        # 16진수를 4비트 2진수로 변환
        try:
            nibble = int(hex_char, 16)
        except ValueError:
            return False
        
        # 각 비트 확인 (MSB부터)
        for i in range(3, -1, -1):
            if bits_checked >= difficulty:
                return True
            
            bit = (nibble >> i) & 1
            if bit != 0:
                return False
            
            bits_checked += 1
    
    return bits_checked >= difficulty


def is_challenge_valid(challenge: str, max_age_seconds: int = POW_MAX_AGE_SECONDS) -> bool:
    """
    챌린지 유효성 검증 (타임스탬프 확인)
    
    Args:
        challenge: 챌린지 문자열 (형식: "timestamp-randomstring")
        max_age_seconds: 최대 유효 시간 (초)
    
    Returns:
        유효 여부
    """
    try:
        parts = challenge.split('-')
        if not parts:
            return False
        
        timestamp_str = parts[0]
        timestamp_ms = int(timestamp_str)
        
        # 현재 시간과 비교
        now_ms = int(time.time() * 1000)
        age_seconds = (now_ms - timestamp_ms) / 1000
        
        return age_seconds <= max_age_seconds
    
    except (ValueError, IndexError):
        return False


def filter_hop_by_hop_headers(response_headers):
    """
    프록시 응답에서 hop-by-hop 헤더를 제거.
    Content-Encoding, Transfer-Encoding 등이 남으면
    ERR_CONTENT_DECODING_FAILED 오류 발생.
    """
    hop_by_hop = {
        'content-encoding', 'transfer-encoding', 'connection',
        'keep-alive', 'proxy-authenticate', 'proxy-authorization',
        'te', 'trailers', 'upgrade'
    }
    return [
        (key, value) for key, value in response_headers.items()
        if key.lower() not in hop_by_hop
    ]


def verify_proof_of_work(
    challenge: str,
    nonce: int,
    user_hash: str,
    difficulty: int = POW_DIFFICULTY
) -> str:
    """
    PoW 검증
    
    Args:
        challenge: 챌린지 문자열
        nonce: 계산된 nonce
        user_hash: 사용자가 제출한 해시
        difficulty: 난이도
    
    Returns:
        검증 결과 (PowVerificationResult)
    """
    # 1. 해시 재계산
    input_str = f"{challenge}:{nonce}"
    computed_hash = sha256(input_str)
    
    # 2. 해시 일치 확인
    if computed_hash != user_hash:
        return PowVerificationResult.INVALID_HASH
    
    # 3. 난이도 조건 확인
    if not check_difficulty(computed_hash, difficulty):
        return PowVerificationResult.INVALID_DIFFICULTY
    
    # 4. 타임스탬프 검증 (리플레이 공격 방지)
    if not is_challenge_valid(challenge):
        return PowVerificationResult.EXPIRED
    
    return PowVerificationResult.VALID


@app.route('/api/v3/user/register', methods=['POST'])
def register_with_pow():
    """
    PoW 검증 후 Lemmy 백엔드로 회원가입 요청 전달
    """
    try:
        data = request.get_json()
        
        # 🛡️ 스팸 필터 검사 (PoW 전에 먼저 — 스팸이면 계산 낭비할 필요 없음)
        spam_result = check_content_for_spam(data, 'register')
        if spam_result:
            field, matched = spam_result
            app.logger.warning(
                f"SPAM BLOCKED (register): field={field}, matched={matched!r}, "
                f"IP={request.remote_addr}, username={data.get('username', '?')}"
            )
            return jsonify({
                'error': 'spam_detected',
                'message': 'Your registration was flagged as spam.'
            }), 403
        
        # PoW 필드 추출
        pow_challenge = data.get('pow_challenge')
        pow_nonce = data.get('pow_nonce')
        pow_hash = data.get('pow_hash')
        
        # PoW 필드 존재 확인
        if not all([pow_challenge, pow_nonce is not None, pow_hash]):
            return jsonify({
                'error': 'proof_of_work_required',
                'message': 'Proof of Work is required for registration'
            }), 400
        
        # PoW 검증
        result = verify_proof_of_work(
            pow_challenge,
            int(pow_nonce),
            pow_hash,
            POW_DIFFICULTY
        )
        
        # 검증 실패 처리
        if result != PowVerificationResult.VALID:
            error_messages = {
                PowVerificationResult.INVALID_HASH: 'Invalid Proof of Work: hash mismatch',
                PowVerificationResult.INVALID_DIFFICULTY: 'Invalid Proof of Work: difficulty not met',
                PowVerificationResult.EXPIRED: 'Invalid Proof of Work: challenge expired',
            }
            reason_map = {
                PowVerificationResult.INVALID_HASH: 'hash_mismatch',
                PowVerificationResult.INVALID_DIFFICULTY: 'difficulty_not_met',
                PowVerificationResult.EXPIRED: 'expired',
            }
            
            app.logger.warning(f"PoW verification failed for register: reason={result}, challenge={pow_challenge[:20]}...")
            
            return jsonify({
                'error': 'invalid_proof_of_work',
                'message': error_messages.get(result, 'Invalid Proof of Work'),
                'reason': reason_map.get(result, 'unknown')
            }), 400
        
        # ✅ PoW 검증 성공!
        # Lemmy는 PoW 필드를 모르므로 제거
        lemmy_data = data.copy()
        lemmy_data.pop('pow_challenge', None)
        lemmy_data.pop('pow_nonce', None)
        lemmy_data.pop('pow_hash', None)
        
        # Lemmy 백엔드로 전달
        response = requests.post(
            f"{LEMMY_BACKEND_URL}/api/v3/user/register",
            json=lemmy_data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        # Lemmy 응답 반환 (hop-by-hop 헤더 제거로 ERR_CONTENT_DECODING_FAILED 방지)
        return response.content, response.status_code, filter_hop_by_hop_headers(response.headers)
    
    except requests.RequestException as e:
        app.logger.error(f"Lemmy backend request failed: {e}")
        return jsonify({
            'error': 'backend_error',
            'message': 'Failed to connect to backend'
        }), 503
    
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")
        return jsonify({
            'error': 'internal_error',
            'message': 'Internal server error'
        }), 500


@app.route('/api/v3/post', methods=['POST'])
def create_post_with_pow():
    """
    PoW 검증 후 Lemmy 백엔드로 게시글 작성 요청 전달
    """
    try:
        data = request.get_json()
        
        # 🛡️ 스팸 필터 검사
        spam_result = check_content_for_spam(data, 'post')
        if spam_result:
            field, matched = spam_result
            app.logger.warning(
                f"SPAM BLOCKED (post): field={field}, matched={matched!r}, "
                f"IP={request.remote_addr}"
            )
            return jsonify({
                'error': 'spam_detected',
                'message': 'Your post was flagged as spam.'
            }), 403
        
        # PoW 필드 추출
        pow_challenge = data.get('pow_challenge')
        pow_nonce = data.get('pow_nonce')
        pow_hash = data.get('pow_hash')
        
        # PoW 필드 존재 확인
        if not all([pow_challenge, pow_nonce is not None, pow_hash]):
            return jsonify({
                'error': 'proof_of_work_required',
                'message': 'Proof of Work is required for creating posts'
            }), 400
        
        # PoW 검증
        result = verify_proof_of_work(
            pow_challenge,
            int(pow_nonce),
            pow_hash,
            POW_DIFFICULTY
        )
        
        # 검증 실패 처리
        if result != PowVerificationResult.VALID:
            error_messages = {
                PowVerificationResult.INVALID_HASH: 'Invalid Proof of Work: hash mismatch',
                PowVerificationResult.INVALID_DIFFICULTY: 'Invalid Proof of Work: difficulty not met',
                PowVerificationResult.EXPIRED: 'Invalid Proof of Work: challenge expired',
            }
            # reason 필드를 추가하여 클라이언트가 실패 유형을 구분할 수 있게 함
            reason_map = {
                PowVerificationResult.INVALID_HASH: 'hash_mismatch',
                PowVerificationResult.INVALID_DIFFICULTY: 'difficulty_not_met',
                PowVerificationResult.EXPIRED: 'expired',
            }
            
            app.logger.warning(f"PoW verification failed for post: reason={result}, challenge={pow_challenge[:20]}...")
            
            return jsonify({
                'error': 'invalid_proof_of_work',
                'message': error_messages.get(result, 'Invalid Proof of Work'),
                'reason': reason_map.get(result, 'unknown')
            }), 400
        
        # ✅ PoW 검증 성공!
        # Lemmy는 PoW 필드를 모르므로 제거
        lemmy_data = data.copy()
        lemmy_data.pop('pow_challenge', None)
        lemmy_data.pop('pow_nonce', None)
        lemmy_data.pop('pow_hash', None)
        
        # Lemmy 백엔드로 전달 (Accept-Encoding 제거: requests가 자동 디코딩하므로 gzip 응답 받으면 안됨)
        forward_headers = {
            k: v for k, v in request.headers
            if k.lower() not in ('host', 'content-length', 'accept-encoding', 'transfer-encoding')
        }
        forward_headers['Content-Type'] = 'application/json'
        response = requests.post(
            f"{LEMMY_BACKEND_URL}/api/v3/post",
            json=lemmy_data,
            headers=forward_headers,
            timeout=30
        )
        
        # Lemmy 응답 반환 (hop-by-hop 헤더 제거로 ERR_CONTENT_DECODING_FAILED 방지)
        return response.content, response.status_code, filter_hop_by_hop_headers(response.headers)
    
    except requests.RequestException as e:
        app.logger.error(f"Lemmy backend request failed: {e}")
        return jsonify({
            'error': 'backend_error',
            'message': 'Failed to connect to backend'
        }), 503
    
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")
        return jsonify({
            'error': 'internal_error',
            'message': 'Internal server error'
        }), 500


# 댓글 PoW 최소 난이도 (댓글은 게시글/회원가입보다 낮은 난이도)
COMMENT_POW_DIFFICULTY = int(os.environ.get('COMMENT_POW_DIFFICULTY', '13'))

# 멤버십 서비스 URL (Docker 내부)
MEMBERSHIP_SERVICE_URL = os.environ.get('MEMBERSHIP_SERVICE_URL', 'http://bitcoincash-service:8081')
LEMMY_API_KEY = os.environ.get('LEMMY_API_KEY', '')


def check_membership_from_auth(auth_header: Optional[str]) -> bool:
    """
    Authorization 헤더(Bearer JWT)로 Lemmy에서 유저 정보를 가져온 뒤,
    멤버십 서비스에서 Gold Badge 여부를 확인한다.
    멤버십이 활성화되어 있으면 True를 반환.
    """
    if not auth_header:
        return False

    try:
        # 1) Lemmy API로 현재 유저 정보 조회
        resp = requests.get(
            f"{LEMMY_BACKEND_URL}/api/v3/site",
            headers={"Authorization": auth_header},
            timeout=5,
        )
        if resp.status_code != 200:
            return False

        site_data = resp.json()
        my_user = site_data.get("my_user")
        if not my_user:
            return False

        username = my_user["local_user_view"]["person"]["name"]

        # 2) 멤버십 서비스에서 활성 여부 확인
        mem_resp = requests.get(
            f"{MEMBERSHIP_SERVICE_URL}/api/membership/status/{username}",
            headers={"X-API-Key": LEMMY_API_KEY},
            timeout=5,
        )
        if mem_resp.status_code != 200:
            return False

        mem_data = mem_resp.json()
        is_active = mem_data.get("membership", {}).get("is_active", False)

        if is_active:
            app.logger.info(f"Membership ACTIVE for user={username} — comment PoW exempted")
        return is_active

    except Exception as e:
        app.logger.error(f"Membership check failed: {e}")
        return False


@app.route('/api/v3/comment', methods=['POST'])
def create_comment_with_pow():
    """
    PoW 검증 후 Lemmy 백엔드로 댓글 작성 요청 전달
    
    댓글은 즉시성이 중요하므로 낮은 난이도(기본 13)를 사용.
    PoW 필드가 없으면 거부 (스팸봇 API 직접 호출 차단).
    멤버십 유저는 프론트엔드에서 PoW 면제되지만, API 직접 호출 시에는 PoW 필수.
    내부 서비스(content-importer 등)는 Docker 내부에서 Lemmy로 직접 연결하므로 영향 없음.
    """
    try:
        data = request.get_json()
        
        # 🛡️ 스팸 필터 검사 (PoW 전에 먼저!)
        spam_result = check_content_for_spam(data, 'comment')
        if spam_result:
            field, matched = spam_result
            app.logger.warning(
                f"SPAM BLOCKED (comment): field={field}, matched={matched!r}, "
                f"IP={request.remote_addr}"
            )
            return jsonify({
                'error': 'spam_detected',
                'message': 'Your comment was flagged as spam.'
            }), 403
        
        # PoW 필드 추출
        pow_challenge = data.get('pow_challenge')
        pow_nonce = data.get('pow_nonce')
        pow_hash = data.get('pow_hash')
        
        # PoW 필드 존재 확인 — 없으면 멤버십 체크 후 면제 or 거부
        if not all([pow_challenge, pow_nonce is not None, pow_hash]):
            # 멤버십 유저인지 확인 (Authorization 헤더로 판별)
            auth_header = request.headers.get('Authorization')
            if check_membership_from_auth(auth_header):
                # ✅ 멤버십 유저 — PoW 면제, 바로 Lemmy로 전달
                app.logger.info(
                    f"Comment PoW EXEMPTED (membership): IP={request.remote_addr}"
                )
                lemmy_data = data.copy()
                lemmy_data.pop('pow_challenge', None)
                lemmy_data.pop('pow_nonce', None)
                lemmy_data.pop('pow_hash', None)

                forward_headers = {
                    k: v for k, v in request.headers
                    if k.lower() not in ('host', 'content-length', 'accept-encoding', 'transfer-encoding')
                }
                forward_headers['Content-Type'] = 'application/json'
                response = requests.post(
                    f"{LEMMY_BACKEND_URL}/api/v3/comment",
                    json=lemmy_data,
                    headers=forward_headers,
                    timeout=30,
                )
                return response.content, response.status_code, filter_hop_by_hop_headers(response.headers)

            app.logger.warning(
                f"Comment REJECTED: missing PoW fields from IP={request.remote_addr}"
            )
            return jsonify({
                'error': 'proof_of_work_required',
                'message': 'Proof of Work is required for comment creation',
            }), 403
        
        # PoW 검증 (댓글용 낮은 난이도)
        result = verify_proof_of_work(
            pow_challenge,
            int(pow_nonce),
            pow_hash,
            COMMENT_POW_DIFFICULTY
        )
        
        # 검증 실패 처리
        if result != PowVerificationResult.VALID:
            error_messages = {
                PowVerificationResult.INVALID_HASH: 'Invalid Proof of Work: hash mismatch',
                PowVerificationResult.INVALID_DIFFICULTY: 'Invalid Proof of Work: difficulty not met',
                PowVerificationResult.EXPIRED: 'Invalid Proof of Work: challenge expired',
            }
            reason_map = {
                PowVerificationResult.INVALID_HASH: 'hash_mismatch',
                PowVerificationResult.INVALID_DIFFICULTY: 'difficulty_not_met',
                PowVerificationResult.EXPIRED: 'expired',
            }
            
            app.logger.warning(
                f"Comment PoW verification failed: reason={result}, "
                f"challenge={pow_challenge[:20]}..., IP={request.remote_addr}"
            )
            
            return jsonify({
                'error': 'invalid_proof_of_work',
                'message': error_messages.get(result, 'Invalid Proof of Work'),
                'reason': reason_map.get(result, 'unknown')
            }), 400
        
        # ✅ PoW 검증 성공!
        app.logger.info(
            f"Comment PoW verified: IP={request.remote_addr}, "
            f"nonce={pow_nonce}, difficulty>={COMMENT_POW_DIFFICULTY}"
        )
        
        # Lemmy는 PoW 필드를 모르므로 제거
        lemmy_data = data.copy()
        lemmy_data.pop('pow_challenge', None)
        lemmy_data.pop('pow_nonce', None)
        lemmy_data.pop('pow_hash', None)
        
        # Lemmy 백엔드로 전달
        forward_headers = {
            k: v for k, v in request.headers
            if k.lower() not in ('host', 'content-length', 'accept-encoding', 'transfer-encoding')
        }
        forward_headers['Content-Type'] = 'application/json'
        response = requests.post(
            f"{LEMMY_BACKEND_URL}/api/v3/comment",
            json=lemmy_data,
            headers=forward_headers,
            timeout=30
        )
        
        return response.content, response.status_code, filter_hop_by_hop_headers(response.headers)
    
    except requests.RequestException as e:
        app.logger.error(f"Lemmy backend request failed (comment): {e}")
        return jsonify({
            'error': 'backend_error',
            'message': 'Failed to connect to backend'
        }), 503
    
    except Exception as e:
        app.logger.error(f"Unexpected error (comment): {e}")
        return jsonify({
            'error': 'internal_error',
            'message': 'Internal server error'
        }), 500


@app.route('/api/pow/challenge', methods=['GET'])
def get_pow_challenge():
    """
    PoW 챌린지 생성 (선택사항)
    프론트엔드에서 생성해도 되지만, 서버에서 제공할 수도 있음
    """
    import random
    import string
    
    timestamp = int(time.time() * 1000)
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    challenge = f"{timestamp}-{random_str}"
    
    return jsonify({
        'challenge': challenge,
        'difficulty': POW_DIFFICULTY,
        'max_age_seconds': POW_MAX_AGE_SECONDS
    })


@app.route('/api/pow/verify', methods=['POST'])
def verify_pow_endpoint():
    """
    PoW 검증 테스트용 엔드포인트
    """
    data = request.get_json()
    
    result = verify_proof_of_work(
        data.get('challenge'),
        int(data.get('nonce')),
        data.get('hash'),
        data.get('difficulty', POW_DIFFICULTY)
    )
    
    return jsonify({
        'valid': result == PowVerificationResult.VALID,
        'result': result
    })


@app.route('/health', methods=['GET'])
def health_check():
    """헬스 체크"""
    return jsonify({
        'status': 'healthy',
        'service': 'pow-validator',
        'difficulty': POW_DIFFICULTY,
        'comment_difficulty': COMMENT_POW_DIFFICULTY,
        'spam_filter': {
            'enabled': True,
            'pattern_count': len(SPAM_COMPILED_PATTERNS)
        }
    })


@app.route('/api/spam/test', methods=['POST'])
def test_spam_filter():
    """
    스팸 필터 테스트 엔드포인트 (관리자용)
    
    요청 예시:
      POST /api/spam/test
      {"text": "I basically make about $8,000 a month online..."}
    
    응답 예시:
      {"is_spam": true, "matched": "make about $8,000...a month online", "cleaned_text": "..."}
    """
    data = request.get_json()
    text = data.get('text', '')
    
    cleaned = strip_invisible_chars(text)
    is_spam, matched = check_spam(text)
    
    return jsonify({
        'is_spam': is_spam,
        'matched': matched,
        'original_length': len(text),
        'cleaned_length': len(cleaned),
        'invisible_chars_removed': len(text) - len(cleaned),
        'cleaned_text': cleaned[:500]  # 미리보기 (최대 500자)
    })


@app.route('/api/spam/patterns', methods=['GET'])
def list_spam_patterns():
    """현재 등록된 스팸 패턴 목록 (관리자용)"""
    return jsonify({
        'pattern_count': len(SPAM_KEYWORD_PATTERNS),
        'patterns': SPAM_KEYWORD_PATTERNS
    })


if __name__ == '__main__':
    # 개발용
    app.run(host='0.0.0.0', port=5001, debug=True)
