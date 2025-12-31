"""
Membership API Routes
Handles annual membership purchases and status checks
"""
from flask import Blueprint, jsonify, request
from flask_cors import CORS
from functools import wraps
import time
from config import logger, LEMMY_API_KEY
import models
from services.price_service import get_membership_price, calculate_bch_amount

# Blueprint 생성
membership_bp = Blueprint('membership', __name__)
CORS(membership_bp)

# API 인증 데코레이터
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != LEMMY_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

@membership_bp.route('/api/membership/price', methods=['GET'])
def get_price():
    """
    Get current annual membership price in BCH (~5 USD)
    """
    try:
        price_info = get_membership_price()
        
        if not price_info:
            return jsonify({
                "error": "Unable to fetch current BCH price"
            }), 503
        
        return jsonify({
            "success": True,
            "price": price_info
        })
    except Exception as e:
        logger.error(f"Error getting membership price: {str(e)}")
        return jsonify({
            "error": "Internal server error"
        }), 500

@membership_bp.route('/api/membership/status/<username>', methods=['GET'])
@require_api_key
def get_status(username):
    """
    Check user's membership status
    Returns: active status, expiration date, days remaining
    """
    try:
        status = models.get_membership_status(username)
        
        return jsonify({
            "success": True,
            "username": username,
            "membership": status
        })
    except Exception as e:
        logger.error(f"Error getting membership status for {username}: {str(e)}")
        return jsonify({
            "error": "Internal server error"
        }), 500

@membership_bp.route('/api/membership/check/<username>', methods=['GET'])
def check_membership(username):
    """
    Public endpoint to check if user has active membership (no auth required)
    Used for appeal form validation
    Returns: simple boolean is_active status
    """
    try:
        status = models.get_membership_status(username)
        
        return jsonify({
            "success": True,
            "username": username,
            "is_active": status.get('is_active', False),
            "expires_at": status.get('expires_at') if status.get('is_active') else None
        })
    except Exception as e:
        logger.error(f"Error checking membership for {username}: {str(e)}")
        return jsonify({
            "success": False,
            "username": username,
            "is_active": False
        }), 200  # Return 200 even on error, with is_active=False

@membership_bp.route('/api/membership/purchase', methods=['POST'])
@require_api_key
def purchase_membership():
    """
    Purchase annual membership
    Request body:
    {
        "username": "user123",
        "from_address": "bitcoincash:...",  # Optional: user's BCH address
        "payment_method": "credit"  # "credit" = use existing credits, "transfer" = BCH transfer
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'username' not in data:
            return jsonify({
                "error": "Missing username"
            }), 400
        
        username = data['username']
        payment_method = data.get('payment_method', 'credit')
        
        # Get current membership price
        price_info = get_membership_price()
        if not price_info:
            return jsonify({
                "error": "Unable to fetch current BCH price"
            }), 503
        
        required_bch = price_info['bch_amount']
        
        # Check payment method
        if payment_method == 'credit':
            # Deduct from user's credit balance and transfer to admin wallet
            current_credit = models.get_user_credit_by_username(username)
            
            if current_credit < required_bch:
                return jsonify({
                    "error": "Insufficient credits",
                    "required": required_bch,
                    "available": current_credit
                }), 400
            
            # Get admin username from config (default to 'admin')
            from config import LEMMY_ADMIN_USER
            admin_username = LEMMY_ADMIN_USER or 'admin'
            
            # Deduct from user and add to admin in a transaction
            conn = models.get_db_connection()
            cursor = conn.cursor()
            
            try:
                # Deduct from user
                cursor.execute('''
                    UPDATE user_credits 
                    SET credit_balance = credit_balance - ?, 
                        last_updated = ?
                    WHERE user_id = ?
                ''', (required_bch, int(time.time()), username))
                
                # Add to admin wallet
                cursor.execute('''
                    INSERT INTO user_credits (user_id, credit_balance, last_updated)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        credit_balance = credit_balance + ?,
                        last_updated = ?
                ''', (admin_username, required_bch, int(time.time()), required_bch, int(time.time())))
                
                conn.commit()
                logger.info(f"Transferred {required_bch} BCH from {username} to {admin_username}")
                
            except Exception as e:
                conn.rollback()
                conn.close()
                logger.error(f"Error transferring credits: {str(e)}")
                return jsonify({
                    "error": "Failed to process payment"
                }), 500
            
            conn.close()
            
            # Create membership
            success = models.create_membership(
                user_id=username,
                amount_paid=required_bch,
                tx_hash=None  # No on-chain transaction for credit payment
            )
            
            if success:
                logger.info(f"Membership purchased by {username} using credits: {required_bch} BCH")
                return jsonify({
                    "success": True,
                    "message": "Membership activated successfully",
                    "membership": models.get_membership_status(username)
                })
            else:
                # Refund: add back to user, deduct from admin
                conn = models.get_db_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE user_credits 
                    SET credit_balance = credit_balance + ?
                    WHERE user_id = ?
                ''', (required_bch, username))
                cursor.execute('''
                    UPDATE user_credits 
                    SET credit_balance = credit_balance - ?
                    WHERE user_id = ?
                ''', (required_bch, admin_username))
                conn.commit()
                conn.close()
                
                return jsonify({
                    "error": "Failed to create membership"
                }), 500
        
        elif payment_method == 'transfer':
            # Direct BCH transfer from user to admin wallet
            # This would require user to sign a transaction
            # For now, return instructions
            return jsonify({
                "error": "Direct BCH transfer not yet implemented",
                "message": "Please use credit balance to purchase membership",
                "required_bch": required_bch
            }), 501
        
        else:
            return jsonify({
                "error": "Invalid payment method",
                "supported_methods": ["credit", "transfer"]
            }), 400
            
    except Exception as e:
        logger.error(f"Error processing membership purchase: {str(e)}")
        return jsonify({
            "error": "Internal server error"
        }), 500

@membership_bp.route('/api/membership/transactions/<username>', methods=['GET'])
@require_api_key
def get_transactions(username):
    """
    Get user's membership transaction history
    """
    try:
        transactions = models.get_membership_transactions(username)
        
        return jsonify({
            "success": True,
            "username": username,
            "transactions": transactions
        })
    except Exception as e:
        logger.error(f"Error getting membership transactions for {username}: {str(e)}")
        return jsonify({
            "error": "Internal server error"
        }), 500

@membership_bp.route('/api/membership/check-expiry', methods=['POST'])
@require_api_key
def check_expiry():
    """
    Manual trigger to check and expire memberships
    (Usually called by background task)
    """
    try:
        expired_count = models.check_and_expire_memberships()
        
        return jsonify({
            "success": True,
            "expired_count": expired_count,
            "message": f"Checked and expired {expired_count} memberships"
        })
    except Exception as e:
        logger.error(f"Error checking membership expiry: {str(e)}")
        return jsonify({
            "error": "Internal server error"
        }), 500
