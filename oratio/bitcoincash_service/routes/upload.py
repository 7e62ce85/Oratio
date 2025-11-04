"""
Upload Quota API Routes
Handles upload quota validation, usage tracking, and credit charging.

Version: 1.0
Created: 2025-11-04
"""

from flask import Blueprint, request, jsonify
from functools import wraps
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.upload_quota_service import UploadQuotaService
from config import DB_PATH, LEMMY_API_KEY

logger = logging.getLogger(__name__)

upload_bp = Blueprint('upload', __name__, url_prefix='/api/upload')

# Initialize service
upload_service = UploadQuotaService(DB_PATH)

def require_api_key(f):
    """Decorator to require API key for certain endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != LEMMY_API_KEY:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

@upload_bp.route('/quota/<user_identifier>', methods=['GET'])
@require_api_key
def get_user_quota(user_identifier):
    """Get user's upload quota information
    
    Args:
        user_identifier: User ID or username
        
    Returns:
        JSON with quota details
    """
    try:
        quota = upload_service.get_user_quota(user_identifier, user_identifier)
        return jsonify({
            'success': True,
            'quota': quota
        }), 200
    except Exception as e:
        logger.error(f"Failed to get quota for {user_identifier}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@upload_bp.route('/validate', methods=['POST'])
@require_api_key
def validate_upload():
    """Validate if an upload is allowed and calculate charges
    
    Request body:
        {
            "user_id": "string",
            "username": "string (optional)",
            "file_size_bytes": int,
            "filename": "string (optional)"
        }
        
    Returns:
        JSON with validation result
    """
    try:
        data = request.get_json()
        
        if not data or 'user_id' not in data or 'file_size_bytes' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: user_id, file_size_bytes'
            }), 400
        
        user_id = data['user_id']
        file_size_bytes = int(data['file_size_bytes'])
        filename = data.get('filename', 'unknown')
        username = data.get('username', user_id)
        
        validation = upload_service.validate_upload(
            user_id=user_id,
            file_size_bytes=file_size_bytes,
            filename=filename,
            username=username
        )
        
        return jsonify({
            'success': True,
            'validation': validation
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to validate upload: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@upload_bp.route('/record', methods=['POST'])
@require_api_key
def record_upload():
    """Record an upload transaction
    
    Request body:
        {
            "user_id": "string",
            "username": "string",
            "filename": "string",
            "file_size_bytes": int,
            "file_type": "string (optional)",
            "upload_url": "string (optional)",
            "post_id": int (optional),
            "comment_id": int (optional),
            "use_credit": bool (default: false)
        }
        
    Returns:
        JSON with transaction details
    """
    try:
        data = request.get_json()
        
        required_fields = ['user_id', 'username', 'filename', 'file_size_bytes']
        if not data or not all(field in data for field in required_fields):
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(required_fields)}'
            }), 400
        
        result = upload_service.record_upload(
            user_id=data['user_id'],
            username=data['username'],
            filename=data['filename'],
            file_size_bytes=int(data['file_size_bytes']),
            file_type=data.get('file_type'),
            upload_url=data.get('upload_url'),
            post_id=data.get('post_id'),
            comment_id=data.get('comment_id'),
            use_credit=data.get('use_credit', False)
        )
        
        return jsonify(result), 200
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        logger.error(f"Failed to record upload: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@upload_bp.route('/history/<user_identifier>', methods=['GET'])
@require_api_key
def get_upload_history(user_identifier):
    """Get user's upload history
    
    Args:
        user_identifier: User ID or username
        
    Query params:
        limit: Maximum number of records (default: 50)
        
    Returns:
        JSON with upload history
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        
        if limit < 1 or limit > 200:
            limit = 50
        
        uploads = upload_service.get_user_uploads(user_identifier, limit)
        
        return jsonify({
            'success': True,
            'uploads': uploads,
            'count': len(uploads)
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get upload history for {user_identifier}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@upload_bp.route('/pricing', methods=['GET'])
def get_pricing_config():
    """Get current upload pricing configuration
    
    Returns:
        JSON with pricing details
    """
    try:
        config = upload_service.get_pricing_config()
        
        return jsonify({
            'success': True,
            'pricing': config
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to get pricing config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@upload_bp.route('/reset-quota/<user_id>', methods=['POST'])
@require_api_key
def reset_user_quota(user_id):
    """Reset user's quota if expired (admin only)
    
    Args:
        user_id: User ID
        
    Returns:
        JSON with result
    """
    try:
        was_reset = upload_service.reset_quota_if_expired(user_id)
        
        return jsonify({
            'success': True,
            'was_reset': was_reset,
            'message': 'Quota reset successfully' if was_reset else 'Quota not expired or user not found'
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to reset quota for {user_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
