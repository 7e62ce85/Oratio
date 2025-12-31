"""
CP (Child Pornography) Moderation API Routes
========================================
Flask Blueprint for CP reporting, moderation, appeals, and permissions management.
"""

from flask import Blueprint, request, jsonify
from flask_cors import CORS
from functools import wraps
from config import logger, LEMMY_API_KEY
import os
from services.cp_moderation import (
    # User permissions
    ensure_user_permissions, get_user_permissions, get_user_permissions_by_username, can_user_report_cp,
    ban_user, revoke_report_ability, restore_user_privileges,
    # CP reports
    create_cp_report, get_cp_report, get_pending_reports, check_existing_report,
    # CP reviews
    review_cp_report,
    # Appeals
    create_appeal, get_appeal, review_appeal,
    # Notifications
    get_user_notifications, mark_notification_read,
    # Background tasks
    run_cp_background_tasks,
)
from jwt_utils import extract_user_info_from_jwt
import traceback

cp_bp = Blueprint('cp', __name__, url_prefix='/api/cp')

# Enable CORS for the CP blueprint (allows cookies from same origin)
CORS(cp_bp, supports_credentials=True)


# ==========================================
# Authentication Decorators
# ==========================================

def require_api_key(f):
    """API key authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != LEMMY_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function


def require_jwt_auth(f):
    """JWT authentication decorator for regular users"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.info(f"JWT Auth check - Cookies: {request.cookies}")
        logger.info(f"JWT Auth check - Headers: {dict(request.headers)}")
        user_info = extract_user_info_from_jwt()
        if not user_info:
            logger.warning("JWT authentication failed - no user info extracted")
            return jsonify({"error": "Authentication required - please log in"}), 401
        logger.info(f"JWT authentication successful: {user_info}")
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# Helper Functions
# ==========================================

def get_current_user():
    """Extract current user from JWT"""
    user_info = extract_user_info_from_jwt()
    if not user_info:
        return None, None, None
    return user_info.get('username'), user_info.get('person_id'), user_info.get('username')


def require_auth():
    """Require authentication"""
    username, person_id, _ = get_current_user()
    if not username or not person_id:
        return jsonify({"error": "Authentication required"}), 401
    return None


def is_user_admin():
    """Check if current user is admin"""
    # TODO: Implement proper admin check from Lemmy database
    # For now, check environment variable or configuration
    user_info = extract_user_info_from_jwt()
    if not user_info:
        return False
    # Placeholder: check if user is in admin list
    return user_info.get('is_admin', False)


def is_user_moderator(community_id: int):
    """Check if current user is moderator of community"""
    # TODO: Implement proper moderator check from Lemmy database
    return False


# ==========================================
# User Permissions Endpoints
# ==========================================

@cp_bp.route('/permissions/by-username/<username>', methods=['GET'])
def api_get_user_permissions_by_username(username):
    """Get user CP permissions by username (public, no auth required - for ban status check)"""
    try:
        perms = get_user_permissions_by_username(username)
        if not perms:
            # Return default permissions for new users
            return jsonify({
                "username": username,
                "can_report_cp": True,
                "can_review_cp": False,
                "is_banned": False,
                "ban_start": None,
                "ban_end": None,
                "ban_count": 0,
                "has_cp_review_permission": False,
                "last_violation": None,
                "report_ability_revoked_at": None
            }), 200
        
        return jsonify(perms), 200
    except Exception as e:
        logger.error(f"Error getting user permissions by username: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/permissions/<user_id>', methods=['GET'])
@require_api_key
def api_get_user_permissions(user_id):
    """Get user CP permissions by user_id (requires API key)"""
    try:
        perms = get_user_permissions(user_id)
        if not perms:
            # Return default permissions for new users
            # They will be created when they first report CP
            return jsonify({
                "user_id": user_id,
                "username": user_id,  # Assuming user_id is username
                "can_report_cp": True,
                "can_review_cp": False,
                "is_banned": False,
                "ban_start": None,
                "ban_end": None,
                "ban_count": 0,
                "has_cp_review_permission": False,
                "last_violation": None
            }), 200
        
        return jsonify(perms), 200
    except Exception as e:
        logger.error(f"Error getting user permissions: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/permissions/revoked', methods=['GET'])
@require_api_key
def api_get_revoked_report_abilities():
    """Return list of users with revoked report ability (for admin/testing)"""
    try:
        from models import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, report_ability_revoked_at
            FROM user_cp_permissions
            WHERE report_ability_revoked_at IS NOT NULL
            ORDER BY report_ability_revoked_at DESC
            LIMIT 200
        ''')
        rows = cursor.fetchall()
        conn.close()

        result = []
        for r in rows:
            result.append({
                'user_id': r[0],
                'username': r[1],
                'report_ability_revoked_at': r[2]
            })

        return jsonify({'revoked': result, 'count': len(result)}), 200
    except Exception as e:
        logger.error(f"Error getting revoked report abilities: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/permissions/can-report/<user_id>', methods=['GET'])
@require_api_key
def api_can_report(user_id):
    """Check if user can report CP"""
    try:
        can_report, error_msg = can_user_report_cp(user_id)
        return jsonify({"can_report": can_report, "message": error_msg}), 200
    except Exception as e:
        logger.error(f"Error checking report permission: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/user-reports/<username>', methods=['GET'])
def api_get_user_reports(username):
    """Get CP reports for a specific user's content (no auth required for appeal context)"""
    try:
        from models import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get reports where this user is the content creator and content is hidden
        cursor.execute("""
            SELECT 
                r.id,
                r.content_type,
                r.content_id,
                r.reason,
                r.status,
                r.created_at,
                r.content_hidden
            FROM cp_reports r
            WHERE r.creator_username = ? 
            AND r.content_hidden = 1
            ORDER BY r.created_at DESC
            LIMIT 10
        """, (username,))
        
        reports = []
        for row in cursor.fetchall():
            reports.append({
                'report_id': row[0],
                'content_type': row[1],
                'content_id': row[2],
                'reason': row[3],
                'status': row[4],
                'created_at': row[5],
                'content_hidden': bool(row[6])
            })
        
        conn.close()
        
        return jsonify({'reports': reports}), 200
    except Exception as e:
        logger.error(f"Error getting user reports: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/permissions/initialize', methods=['POST'])
@require_api_key
def api_initialize_user_permissions():
    """Initialize permissions for a user"""
    try:
        data = request.json
        user_id = data.get('user_id')
        person_id = data.get('person_id')
        username = data.get('username')
        
        if not all([user_id, person_id, username]):
            return jsonify({"error": "Missing required fields"}), 400
        
        perms = ensure_user_permissions(user_id, person_id, username)
        return jsonify(perms), 200
    except Exception as e:
        logger.error(f"Error initializing permissions: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# CP Report Endpoints
# ==========================================

@cp_bp.route('/report', methods=['POST'])
@require_jwt_auth  # Changed from require_api_key to require_jwt_auth
def api_create_report():
    """Create a new CP report"""
    logger.info("=" * 80)
    logger.info("🚨 [CP REPORT API] NEW CP REPORT REQUEST RECEIVED")
    logger.info("=" * 80)
    
    try:
        data = request.json
        logger.info(f"📥 [CP REPORT API] Request data: {data}")
        logger.info(f"🍪 [CP REPORT API] Cookies: {request.cookies}")
        logger.info(f"📋 [CP REPORT API] Headers: {dict(request.headers)}")
        
        # Required fields
        content_type = data.get('content_type')  # 'post' or 'comment'
        content_id = data.get('content_id')
        community_id = data.get('community_id')
        reporter_user_id = data.get('reporter_user_id')
        reporter_person_id = data.get('reporter_person_id')
        reporter_username = data.get('reporter_username')
        # Derive membership status server-side using direct DB query (avoid self-HTTP call timeout)
        reporter_is_member = False
        try:
            from models import get_membership_status
            membership_info = get_membership_status(reporter_username)
            if membership_info and membership_info.get('is_active', False):
                reporter_is_member = True
                logger.info(f"📡 [CP REPORT API] Membership check (direct): reporter_is_member=True")
            else:
                logger.info(f"📡 [CP REPORT API] Membership check (direct): reporter_is_member=False")
        except Exception as e:
            # If membership lookup fails, fall back to client-supplied value (or False)
            logger.warning(f"📡 [CP REPORT API] Membership lookup error: {e}")
            reporter_is_member = data.get('reporter_is_member', False)
        creator_user_id = data.get('creator_user_id')
        creator_person_id = data.get('creator_person_id')
        creator_username = data.get('creator_username')
        reason = data.get('reason', '')
        
        logger.info(f"📝 [CP REPORT API] Parsed fields:")
        logger.info(f"   - content_type: {content_type}")
        logger.info(f"   - content_id: {content_id}")
        logger.info(f"   - community_id: {community_id}")
        logger.info(f"   - reporter: {reporter_username} (ID: {reporter_person_id})")
        logger.info(f"   - creator: {creator_username} (ID: {creator_person_id})")
        logger.info(f"   - reporter_is_member: {reporter_is_member}")
        
        if not all([content_type, content_id is not None, community_id, reporter_user_id,
                   reporter_person_id, reporter_username, creator_user_id,
                   creator_person_id, creator_username]):
            logger.warning(f"❌ [CP REPORT API] Missing required fields in CP report")
            return jsonify({"error": "Missing required fields"}), 400
        
        if content_type not in ['post', 'comment']:
            logger.warning(f"❌ [CP REPORT API] Invalid content_type: {content_type}")
            return jsonify({"error": "Invalid content_type"}), 400
        
        logger.info(f"✅ [CP REPORT API] Validation passed, calling create_cp_report()...")
        report = create_cp_report(
            content_type, content_id, community_id,
            reporter_user_id, reporter_person_id, reporter_username, reporter_is_member,
            creator_user_id, creator_person_id, creator_username, reason
        )
        
        logger.info(f"✅ [CP REPORT API] CP report created successfully!")
        logger.info(f"📄 [CP REPORT API] Report details: {report}")
        logger.info("=" * 80)
        return jsonify(report), 201
    
    except PermissionError as e:
        logger.error(f"❌ [CP REPORT API] Permission error: {e}")
        logger.info("=" * 80)
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        logger.error(f"❌ [CP REPORT API] Error creating CP report: {e}")
        logger.error(f"❌ [CP REPORT API] Traceback: {traceback.format_exc()}")
        logger.info("=" * 80)
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/report/<report_id>', methods=['GET'])
@require_api_key
def api_get_report(report_id):
    """Get CP report by ID"""
    try:
        report = get_cp_report(report_id)
        if not report:
            return jsonify({"error": "Report not found"}), 404
        return jsonify(report), 200
    except Exception as e:
        logger.error(f"Error getting report: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/reports/pending', methods=['GET'])
@require_api_key
def api_get_pending_reports():
    """Get pending CP reports for moderation"""
    try:
        community_id = request.args.get('community_id', type=int)
        escalation_level = request.args.get('escalation_level', 'moderator')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        reports = get_pending_reports(community_id, escalation_level, limit, offset)
        return jsonify({"reports": reports, "count": len(reports)}), 200
    except Exception as e:
        logger.error(f"Error getting pending reports: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/reported-content-ids', methods=['GET'])
def api_get_reported_content_ids():
    """Get IDs of all pending reported content (for frontend filtering)
    
    Public endpoint - no API key required.
    Admins receive empty lists so they can see all content.
    Regular users receive list of hidden content IDs for frontend filtering.
    
    Performance optimizations:
    - Uses DISTINCT to avoid duplicate IDs
    - Server-side caching (10 second TTL) to reduce DB queries
    - Sets Cache-Control header for CDN/browser caching
    """
    import time
    start_time = time.time()
    logger.info(f"🔍 [CP REPORTED IDS] API called at {start_time}")
    
    try:
        from services.cp_moderation import get_db
        import sqlite3
        from lemmy_integration import LemmyAPI
        import os
        
        # Check if user is admin (admins can see all CP content)
        jwt_token = request.cookies.get('jwt')
        is_admin = False
        
        if jwt_token:
            try:
                import jwt as pyjwt
                decoded = pyjwt.decode(jwt_token, options={"verify_signature": False})
                person_id = decoded.get('sub')
                
                # Quick check: admin is always person_id = 1
                if person_id == 1 or str(person_id) == '1':
                    is_admin = True
                    logger.info(f"Admin detected (person_id={person_id}) - returning empty content list")
                else:
                    # Check local DB if user has review permissions (moderator/reviewer) - fast path
                    try:
                        conn = get_db()
                        cursor = conn.cursor()
                        cursor.execute('SELECT can_review_cp FROM user_cp_permissions WHERE person_id = ?', (person_id,))
                        r = cursor.fetchone()
                        conn.close()
                        if r and r[0]:
                            logger.info(f"Moderator detected (person_id={person_id}) - returning empty content list")
                            is_admin = True
                    except Exception as db_err:
                        logger.error(f"Error checking local moderator permissions: {db_err}")
            except Exception as e:
                logger.error(f"Error decoding JWT: {e}")
        
        # Admins see everything, so return empty lists
        if is_admin:
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"✅ [CP REPORTED IDS] Admin detected - returning empty list ({elapsed:.1f}ms)")
            response = jsonify({"post_ids": [], "comment_ids": []})
            response.headers['Cache-Control'] = 'private, max-age=5'
            return response, 200
        
        logger.info(f"🔍 [CP REPORTED IDS] Regular user - querying DB for hidden content")
        db_start = time.time()
        
        conn = get_db()
        cursor = conn.cursor()
        
        # OPTIMIZED: Use DISTINCT to avoid duplicate IDs from multiple reports
        # Uses idx_cp_reports_hidden_type_id index for fast lookup
        cursor.execute('''
            SELECT DISTINCT content_type, content_id 
            FROM cp_reports 
            WHERE content_hidden = 1
        ''')
        
        db_elapsed = (time.time() - db_start) * 1000
        logger.info(f"⏱️ [CP REPORTED IDS] DB query took {db_elapsed:.1f}ms")
        
        # Use sets to automatically deduplicate and then convert to list
        post_ids_set = set()
        comment_ids_set = set()
        
        for row in cursor.fetchall():
            content_type = row[0]
            content_id = row[1]
            if content_type == 'post':
                post_ids_set.add(content_id)
            elif content_type == 'comment':
                comment_ids_set.add(content_id)
        
        conn.close()
        
        total_elapsed = (time.time() - start_time) * 1000
        logger.info(f"✅ [CP REPORTED IDS] Returning {len(post_ids_set)} posts, {len(comment_ids_set)} comments (total: {total_elapsed:.1f}ms)")
        
        response = jsonify({
            "post_ids": list(post_ids_set), 
            "comment_ids": list(comment_ids_set)
        })
        # Cache for 10 seconds - balance between freshness and performance
        response.headers['Cache-Control'] = 'public, max-age=10'
        
        return response, 200
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        logger.error(f"❌ [CP REPORTED IDS] Error after {elapsed:.1f}ms: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/report/<report_id>/check-existing', methods=['GET'])
@require_api_key
def api_check_existing(report_id):
    """Check if content has existing report"""
    try:
        content_type = request.args.get('content_type')
        content_id = request.args.get('content_id', type=int)
        creator_user_id = request.args.get('creator_user_id')
        
        if not all([content_type, content_id is not None, creator_user_id]):
            return jsonify({"error": "Missing required parameters"}), 400
        
        existing = check_existing_report(content_type, content_id, creator_user_id)
        return jsonify({"exists": existing is not None, "report": existing}), 200
    except Exception as e:
        logger.error(f"Error checking existing report: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# CP Review Endpoints
# ==========================================

@cp_bp.route('/report/<report_id>/review', methods=['POST'])
@require_api_key
def api_review_report(report_id):
    """Review a CP report (moderator or admin)"""
    try:
        data = request.json
        logger.info(f"📝 [CP REVIEW API] Received review request for report {report_id}")
        logger.info(f"📝 [CP REVIEW API] Request data: {data}")
        
        reviewer_person_id = data.get('reviewer_person_id')
        reviewer_username = data.get('reviewer_username')
        reviewer_role = data.get('reviewer_role')  # 'moderator' or 'admin'
        decision = data.get('decision')
        notes = data.get('notes', '')
        
        logger.info(f"📝 [CP REVIEW API] reviewer={reviewer_username}, role={reviewer_role}, decision={decision}")
        
        if not all([reviewer_person_id, reviewer_username, reviewer_role, decision]):
            return jsonify({"error": "Missing required fields"}), 400
        
        if reviewer_role not in ['moderator', 'admin']:
            return jsonify({"error": "Invalid reviewer_role"}), 400
        
        # TODO: Add authorization check - ensure user is actually moderator/admin
        
        report = review_cp_report(report_id, reviewer_person_id, reviewer_username,
                                 reviewer_role, decision, notes)
        
        logger.info(f"✅ [CP REVIEW API] Report {report_id} reviewed successfully: {decision}")
        return jsonify(report), 200
    
    except ValueError as e:
        logger.error(f"❌ [CP REVIEW API] ValueError: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"❌ [CP REVIEW API] Error reviewing report: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# Appeal Endpoints
# ==========================================

@cp_bp.route('/appeal', methods=['POST'])
def api_create_appeal():
    """Create an appeal (membership users only) - No auth required for banned users"""
    try:
        data = request.json
        username = data.get('username')
        appeal_type = data.get('appeal_type')  # 'ban' or 'report_ability_loss'
        appeal_reason = data.get('appeal_reason')
        related_report_id = data.get('related_report_id')
        
        if not all([username, appeal_type, appeal_reason]):
            return jsonify({"error": "Missing required fields: username, appeal_type, appeal_reason"}), 400
        
        if appeal_type not in ['ban', 'report_ability_loss']:
            return jsonify({"error": "Invalid appeal_type"}), 400
        
        # Verify user exists and is actually banned (prevent spam appeals)
        perms = get_user_permissions(username)
        if not perms:
            return jsonify({"error": "User not found"}), 404
        
        if not perms.get('is_banned'):
            return jsonify({"error": "You are not banned. Appeals are only available for banned users."}), 400
        
        # Get person_id from permissions (stored in DB)
        person_id = perms.get('person_id')
        if not person_id:
            return jsonify({"error": "Could not retrieve person_id for this user"}), 500
        
        # Use username as user_id
        user_id = username
        
        appeal = create_appeal(user_id, person_id, username, appeal_type,
                              appeal_reason, related_report_id)

        return jsonify(appeal), 201
    except Exception as e:
        logger.error(f"Error creating appeal: {e}\n{traceback.format_exc()}")
        # If create_appeal raised a PermissionError, return a clear client error with 'detail'
        if isinstance(e, PermissionError):
            return jsonify({"detail": str(e)}), 403
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/appeals/pending', methods=['GET'])
@require_api_key
def api_get_pending_appeals():
    """Get all pending appeals (admin only)"""
    try:
        from models import get_db_connection
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id, user_id, person_id, username, appeal_type, 
                appeal_reason, status, created_at, reviewed_by_username,
                reviewed_at, admin_decision, admin_notes
            FROM cp_appeals
            WHERE status = 'pending'
            ORDER BY created_at DESC
        """)
        
        appeals = []
        for row in cursor.fetchall():
            username = row[3]
            
            # Get reported posts for this user
            cursor.execute("""
                SELECT content_type, content_id, reason, created_at
                FROM cp_reports
                WHERE creator_username = ? AND content_hidden = 1
                ORDER BY created_at DESC
                LIMIT 5
            """, (username,))
            
            reported_content = []
            for report_row in cursor.fetchall():
                reported_content.append({
                    'content_type': report_row[0],
                    'content_id': report_row[1],
                    'reason': report_row[2],
                    'created_at': report_row[3]
                })
            
            appeals.append({
                'id': row[0],
                'user_id': row[1],
                'person_id': row[2],
                'username': username,
                'appeal_type': row[4],
                'appeal_reason': row[5],
                'status': row[6],
                'created_at': row[7],
                'reviewed_by_username': row[8],
                'reviewed_at': row[9],
                'admin_decision': row[10],
                'admin_notes': row[11],
                'reported_content': reported_content
            })
        
        conn.close()
        
        return jsonify({'appeals': appeals}), 200
    except Exception as e:
        logger.error(f"Error getting pending appeals: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/appeal/<appeal_id>', methods=['GET'])
@require_api_key
def api_get_appeal(appeal_id):
    """Get appeal by ID"""
    try:
        appeal = get_appeal(appeal_id)
        if not appeal:
            return jsonify({"error": "Appeal not found"}), 404
        return jsonify(appeal), 200
    except Exception as e:
        logger.error(f"Error getting appeal: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/appeals/<appeal_id>/review', methods=['POST'])
@require_api_key
def api_review_appeal(appeal_id):
    """Review an appeal (admin only)"""
    try:
        data = request.json
        reviewer_person_id = data.get('reviewer_person_id')
        reviewer_username = data.get('reviewer_username')
        decision = data.get('decision')  # 'approved' or 'rejected'
        admin_notes = data.get('admin_notes', '')
        
        if not all([reviewer_person_id, reviewer_username, decision]):
            return jsonify({"error": "Missing required fields"}), 400
        
        # Map frontend decision to backend decision
        if decision == 'approved':
            backend_decision = 'restore_privileges'
        elif decision == 'rejected':
            backend_decision = 'uphold_decision'
        else:
            return jsonify({"error": "Invalid decision. Must be 'approved' or 'rejected'"}), 400
        
        # TODO: Add admin authorization check
        
        appeal = review_appeal(appeal_id, reviewer_person_id, reviewer_username, backend_decision, admin_notes)
        
        return jsonify(appeal), 200
    
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error reviewing appeal: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# Admin Management Endpoints
# ==========================================

@cp_bp.route('/admin/user/<user_id>/ban', methods=['POST'])
@require_api_key
def api_admin_ban_user(user_id):
    """Admin: Manually ban a user"""
    try:
        data = request.json
        person_id = data.get('person_id')
        username = data.get('username')
        admin_person_id = data.get('admin_person_id')
        admin_username = data.get('admin_username')
        reason = data.get('reason', 'Manual admin action')
        
        if not all([person_id, username, admin_person_id, admin_username]):
            return jsonify({"error": "Missing required fields"}), 400
        
        # TODO: Add admin authorization check
        
        ban_user(user_id, person_id, username, admin_person_id, admin_username, reason)
        
        return jsonify({"success": True, "message": f"User {username} banned"}), 200
    except Exception as e:
        logger.error(f"Error banning user: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/admin/user/<user_id>/revoke-report', methods=['POST'])
@require_api_key
def api_admin_revoke_report(user_id):
    """Admin: Revoke user's CP reporting ability"""
    try:
        data = request.json
        person_id = data.get('person_id')
        username = data.get('username')
        admin_person_id = data.get('admin_person_id')
        admin_username = data.get('admin_username')
        
        if not all([person_id, username, admin_person_id, admin_username]):
            return jsonify({"error": "Missing required fields"}), 400
        
        # TODO: Add admin authorization check
        
        revoke_report_ability(user_id, person_id, username, admin_person_id, admin_username)
        
        return jsonify({"success": True, "message": f"Report ability revoked for {username}"}), 200
    except Exception as e:
        logger.error(f"Error revoking report ability: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/admin/user/<user_id>/restore', methods=['POST'])
@require_api_key
def api_admin_restore_privileges(user_id):
    """Admin: Restore user privileges"""
    try:
        data = request.json
        restore_ban = data.get('restore_ban', False)
        # Accept both 'restore_report' and 'restore_report_ability' for compatibility
        restore_report = data.get('restore_report', False) or data.get('restore_report_ability', False)
        admin_person_id = data.get('admin_person_id')
        admin_username = data.get('admin_username')
        
        if not (restore_ban or restore_report):
            return jsonify({"error": "Must specify what to restore"}), 400
        
        # TODO: Add admin authorization check
        
        restore_user_privileges(user_id, restore_ban, restore_report, 
                               admin_person_id, admin_username)
        
        return jsonify({"success": True, "message": "Privileges restored"}), 200
    except Exception as e:
        logger.error(f"Error restoring privileges: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# Notification Endpoints
# ==========================================

@cp_bp.route('/notifications/<int:person_id>', methods=['GET'])
@require_api_key
def api_get_notifications(person_id):
    """Get notifications for a user"""
    try:
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        limit = request.args.get('limit', 50, type=int)
        
        notifications = get_user_notifications(person_id, unread_only, limit)
        return jsonify({"notifications": notifications, "count": len(notifications)}), 200
    except Exception as e:
        logger.error(f"Error getting notifications: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@cp_bp.route('/notifications/<notification_id>/read', methods=['POST'])
@require_api_key
def api_mark_notification_read(notification_id):
    """Mark notification as read"""
    try:
        mark_notification_read(notification_id)
        return jsonify({"success": True}), 200
    except Exception as e:
        logger.error(f"Error marking notification read: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# Background Task Endpoints (for cron/scheduler)
# ==========================================

@cp_bp.route('/background/run-tasks', methods=['POST'])
@require_api_key
def api_run_background_tasks():
    """Run CP background tasks (auto-unban, auto-delete)"""
    try:
        result = run_cp_background_tasks()
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error running background tasks: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# Health Check
# ==========================================

@cp_bp.route('/health', methods=['GET'])
def api_cp_health():
    """CP system health check"""
    try:
        # Quick database check
        get_pending_reports(limit=1)
        return jsonify({"status": "healthy", "service": "cp-moderation"}), 200
    except Exception as e:
        logger.error(f"CP health check failed: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 500
