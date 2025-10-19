"""
PoW Validator Service - Python Implementation
Lemmy 회원가입 시 Proof of Work 검증 프록시 서비스

Rust 백엔드 수정 없이 PoW 검증 기능 추가!
"""

from flask import Flask, request, jsonify
import requests
import hashlib
import time
from typing import Optional, Dict, Any

app = Flask(__name__)

# 설정
POW_DIFFICULTY = 20  # 기본 난이도
POW_MAX_AGE_SECONDS = 600  # 10분
LEMMY_BACKEND_URL = "http://lemmy:8536"  # Docker 네트워크 내부

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
            
            return jsonify({
                'error': 'invalid_proof_of_work',
                'message': error_messages.get(result, 'Invalid Proof of Work')
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
        
        # Lemmy 응답 그대로 반환
        return response.content, response.status_code, response.headers.items()
    
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
            
            return jsonify({
                'error': 'invalid_proof_of_work',
                'message': error_messages.get(result, 'Invalid Proof of Work')
            }), 400
        
        # ✅ PoW 검증 성공!
        # Lemmy는 PoW 필드를 모르므로 제거
        lemmy_data = data.copy()
        lemmy_data.pop('pow_challenge', None)
        lemmy_data.pop('pow_nonce', None)
        lemmy_data.pop('pow_hash', None)
        
        # Lemmy 백엔드로 전달
        response = requests.post(
            f"{LEMMY_BACKEND_URL}/api/v3/post",
            json=lemmy_data,
            headers=dict(request.headers),  # 인증 헤더 등을 그대로 전달
            timeout=30
        )
        
        # Lemmy 응답 그대로 반환
        return response.content, response.status_code, response.headers.items()
    
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
        'difficulty': POW_DIFFICULTY
    })


if __name__ == '__main__':
    # 개발용
    app.run(host='0.0.0.0', port=5001, debug=True)
