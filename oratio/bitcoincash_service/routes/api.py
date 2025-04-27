from flask import Blueprint, jsonify, request
from datetime import datetime
from functools import wraps
from config import logger, LEMMY_API_KEY
import models

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

@api_bp.route('/health')
def health_check():
    """서비스 상태 확인 API"""
    return jsonify({
        "status": "ok", 
        "service": "bch-payment-service",
        "timestamp": datetime.now().isoformat()
    })