from flask import Blueprint, jsonify, request
from datetime import datetime
from functools import wraps
from config import logger, LEMMY_API_KEY
import models
from services.payment import verify_payment_pow

# Blueprint 생성
api_bp = Blueprint('api', __name__)

# API 인증 데코레이터
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != LEMMY_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

@api_bp.route('/api/user_credit/<user_id>', methods=['GET'])
@require_api_key
def get_user_credit(user_id):
    """사용자 크레딧 조회 API"""
    credit_balance = models.get_user_credit(user_id)
    return jsonify({"user_id": user_id, "credit_balance": credit_balance})

@api_bp.route('/api/transactions/<user_id>', methods=['GET'])
@require_api_key
def get_user_transactions(user_id):
    """사용자 거래 내역 조회 API"""
    transactions = models.get_user_transactions(user_id)
    
    # 날짜 포맷팅 추가
    for tx in transactions:
        tx["date"] = datetime.fromtimestamp(tx["created_at"]).strftime('%Y-%m-%d %H:%M:%S')
    
    return jsonify({"user_id": user_id, "transactions": transactions})

@api_bp.route('/verify-payment', methods=['POST'])
def verify_payment_pow_route():
    """작업 증명을 통한 결제 검증 API"""
    data = request.json
    
    if not data:
        return jsonify({"verified": False, "reason": "데이터가 제공되지 않았습니다"}), 400
        
    payment_id = data.get('paymentId')
    user_token = data.get('userToken')
    nonce = data.get('nonce')
    claimed_hash = data.get('hash')
    
    if not all([payment_id, user_token, nonce, claimed_hash]):
        return jsonify({"verified": False, "reason": "필수 파라미터가 누락되었습니다"}), 400
    
    # 결제 검증 로직 실행
    result = verify_payment_pow(payment_id, user_token, nonce, claimed_hash)
    return jsonify(result)

@api_bp.route('/health')
def health_check():
    """서비스 상태 확인 API"""
    return jsonify({
        "status": "ok", 
        "service": "bch-payment-service",
        "timestamp": datetime.now().isoformat()
    })