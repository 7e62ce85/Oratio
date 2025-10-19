from flask import Blueprint, jsonify, request
from flask_cors import CORS 
from datetime import datetime
from functools import wraps
from config import logger, LEMMY_API_KEY
import models

# Blueprint 생성
api_bp = Blueprint('api', __name__)
CORS(api_bp)

# API 인증 데코레이터
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != LEMMY_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

@api_bp.route('/api/user_credit/<int:user_id>', methods=['GET'])
@require_api_key
def get_user_credit_by_id(user_id):
    """사용자 크레딧 조회 API (사용자 ID 기반)"""
    credit_balance = models.get_user_credit(str(user_id))
    return jsonify({"user_id": str(user_id), "credit_balance": credit_balance})

@api_bp.route('/api/user_credit/<username>', methods=['GET'])
@require_api_key
def get_user_credit(username):
    """사용자 크레딧 조회 API (사용자명 기반)"""
    credit_balance = models.get_user_credit_by_username(username)
    return jsonify({"username": username, "credit_balance": credit_balance})

@api_bp.route('/api/transactions/<int:user_id>', methods=['GET'])
@require_api_key
def get_user_transactions_by_id(user_id):
    """사용자 거래 내역 조회 API (사용자 ID 기반)"""
    transactions = models.get_user_transactions(str(user_id))
    
    # 날짜 포맷팅 추가
    for tx in transactions:
        tx["date"] = datetime.fromtimestamp(tx["created_at"]).strftime('%Y-%m-%d %H:%M:%S')
    
    return jsonify({"user_id": str(user_id), "transactions": transactions})

@api_bp.route('/api/transactions/<username>', methods=['GET'])
@require_api_key
def get_user_transactions(username):
    """사용자 거래 내역 조회 API (사용자명 기반)"""
    transactions = models.get_user_transactions_by_username(username)
    
    # 날짜 포맷팅 추가
    for tx in transactions:
        tx["date"] = datetime.fromtimestamp(tx["created_at"]).strftime('%Y-%m-%d %H:%M:%S')
    
    return jsonify({"username": username, "transactions": transactions})

@api_bp.route('/api/has_payment/<int:user_id>', methods=['GET'])
@require_api_key
def has_user_payment_by_id(user_id):
    """사용자가 결제한 적이 있는지 확인 API (사용자 ID 기반)"""
    has_payment = models.has_user_made_payment(str(user_id))
    return jsonify({"user_id": str(user_id), "has_payment": has_payment})

@api_bp.route('/api/has_payment/<username>', methods=['GET'])
@require_api_key
def has_user_payment(username):
    """사용자가 결제한 적이 있는지 확인 API (사용자명 기반)"""
    has_payment = models.has_user_made_payment_by_username(username)
    return jsonify({"username": username, "has_payment": has_payment})

@api_bp.route('/health')
def health_check():
    """서비스 상태 확인 API"""
    return jsonify({
        "status": "ok", 
        "service": "bch-payment-service",
        "timestamp": datetime.now().isoformat()
    })