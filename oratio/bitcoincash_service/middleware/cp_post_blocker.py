"""
CP Post Blocker Middleware
===========================
Blocks direct access to CP-reported posts via nginx reverse proxy check.
This module provides an endpoint that nginx can call to verify if a post should be blocked.
"""

from flask import Blueprint, request, jsonify
import sqlite3
import logging
import os
import re

logger = logging.getLogger(__name__)

cp_blocker_bp = Blueprint('cp_blocker', __name__)

DB_PATH = os.environ.get('PAYMENT_DB_PATH', '/data/payments.db')


def get_lemmy_db_password():
    """Read PostgreSQL password from lemmy.hjson config file.
    
    The .env POSTGRES_PASSWORD may be out of sync with lemmy.hjson,
    so we read directly from the config file that Lemmy actually uses.
    """
    hjson_paths = [
        '/config/config.hjson',  # Docker mount path
        '/home/user/Oratio/oratio/lemmy.hjson',  # Direct path
    ]
    
    for path in hjson_paths:
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    content = f.read()
                    # Parse password from hjson (simple regex for this format)
                    match = re.search(r'password:\s*"([^"]+)"', content)
                    if match:
                        password = match.group(1)
                        logger.info(f"📋 [CP POST BLOCKER] Loaded DB password from {path}")
                        return password
        except Exception as e:
            logger.error(f"Error reading {path}: {e}")
    
    # Fallback to environment variable
    return os.environ.get('POSTGRES_PASSWORD', '')


# PostgreSQL connection for Lemmy DB (to check community moderators)
LEMMY_DB_HOST = os.environ.get('POSTGRES_HOST', 'postgres')
LEMMY_DB_USER = os.environ.get('POSTGRES_USER', 'lemmy')
LEMMY_DB_PASS = get_lemmy_db_password()
LEMMY_DB_NAME = os.environ.get('POSTGRES_DB', 'lemmy')

# In-memory cache for blocked post IDs (refreshed every 5 seconds)
_blocked_cache = {'post_ids': set(), 'timestamp': 0}
# Cache for moderator-accessible posts (pending review at moderator level)
_mod_accessible_cache = {'post_ids': set(), 'timestamp': 0}
# Cache for Lemmy community moderators (person_ids)
_lemmy_mods_cache = {'person_ids': set(), 'timestamp': 0}
_CACHE_TTL = 5  # seconds


def get_lemmy_db_connection():
    """Get PostgreSQL connection to Lemmy database"""
    import psycopg2
    return psycopg2.connect(
        host=LEMMY_DB_HOST,
        user=LEMMY_DB_USER,
        password=LEMMY_DB_PASS,
        dbname=LEMMY_DB_NAME
    )


def is_lemmy_community_moderator(person_id: int) -> bool:
    """Check if person_id is a moderator of ANY community in Lemmy.
    
    Uses cache with 5-second TTL. Checks Lemmy's community_moderator table.
    
    Moderator access logic:
    1. If user is in Lemmy's community_moderator table → allowed (default)
    2. Admin can explicitly revoke by setting cp_review_revoked=1 in our DB
    
    Note: can_review_cp=0 is the default value for all users, so we DON'T use
    it to block. Instead we check cp_review_revoked flag (if it exists).
    """
    import time
    now = time.time()
    
    # First check Lemmy's community_moderator table
    # Refresh cache if stale
    if now - _lemmy_mods_cache['timestamp'] >= _CACHE_TTL:
        try:
            pg_conn = get_lemmy_db_connection()
            pg_cursor = pg_conn.cursor()
            # Get all unique person_ids who are moderators of any community
            pg_cursor.execute('SELECT DISTINCT person_id FROM community_moderator')
            mod_ids = set(row[0] for row in pg_cursor.fetchall())
            pg_conn.close()
            
            _lemmy_mods_cache['person_ids'] = mod_ids
            _lemmy_mods_cache['timestamp'] = now
            logger.info(f"📋 [CP POST BLOCKER] Refreshed Lemmy mods cache: {len(mod_ids)} moderators")
        except Exception as e:
            logger.error(f"Error fetching Lemmy moderators: {e}")
    
    # Check if user is a Lemmy community moderator
    is_mod = person_id in _lemmy_mods_cache['person_ids']
    
    if not is_mod:
        return False
    
    # User is a Lemmy mod - now check if admin explicitly revoked their CP review permission
    # We use can_review_cp=0 ONLY if the user record exists AND was explicitly set by admin
    # For now, we'll trust Lemmy's community_moderator as the source of truth
    # Admin revocation can be implemented later with a separate cp_review_revoked column
    
    logger.info(f"✅ [CP POST BLOCKER] person_id={person_id} is a Lemmy community moderator")
    return True

# In-memory cache for blocked post IDs (refreshed every 5 seconds)
_blocked_cache = {'post_ids': set(), 'timestamp': 0}
# Cache for moderator-accessible posts (pending review at moderator level)
_mod_accessible_cache = {'post_ids': set(), 'timestamp': 0}
_CACHE_TTL = 5  # seconds

def get_blocked_post_ids():
    """Get list of post IDs that should be blocked (content_hidden=1)
    
    Uses in-memory cache with 5-second TTL to minimize DB queries.
    Critical for nginx auth_request performance.
    """
    import time
    now = time.time()
    
    # Return cached result if fresh
    if now - _blocked_cache['timestamp'] < _CACHE_TTL:
        return _blocked_cache['post_ids']
    
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cursor = conn.cursor()
        # OPTIMIZED: Use DISTINCT to avoid duplicates from multiple reports
        cursor.execute('''
            SELECT DISTINCT content_id FROM cp_reports 
            WHERE content_type = 'post' AND content_hidden = 1
        ''')
        post_ids = set(row[0] for row in cursor.fetchall())
        conn.close()
        
        # Update cache
        _blocked_cache['post_ids'] = post_ids
        _blocked_cache['timestamp'] = now
        
        return post_ids
    except Exception as e:
        logger.error(f"Error fetching blocked post IDs: {e}")
        # Return stale cache if available, otherwise empty set
        return _blocked_cache['post_ids'] if _blocked_cache['post_ids'] else set()


def get_mod_accessible_post_ids():
    """Get list of post IDs that moderators can still access.
    
    Moderators can ONLY access posts that are:
    - content_hidden = 1 (reported)
    - escalation_level = 'moderator' (pending moderator review)
    - status = 'pending'
    
    Once a moderator confirms CP (escalation_level becomes 'admin'), 
    moderators can NO LONGER access the post. Only admin can.
    """
    import time
    now = time.time()
    
    # Return cached result if fresh
    if now - _mod_accessible_cache['timestamp'] < _CACHE_TTL:
        return _mod_accessible_cache['post_ids']
    
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT content_id FROM cp_reports 
            WHERE content_type = 'post' 
              AND content_hidden = 1 
              AND escalation_level = 'moderator'
              AND status = 'pending'
        ''')
        post_ids = set(row[0] for row in cursor.fetchall())
        conn.close()
        
        # Update cache
        _mod_accessible_cache['post_ids'] = post_ids
        _mod_accessible_cache['timestamp'] = now
        
        logger.info(f"📋 [CP POST BLOCKER] Mod-accessible posts (pending at moderator level): {post_ids}")
        return post_ids
    except Exception as e:
        logger.error(f"Error fetching mod-accessible post IDs: {e}")
        return _mod_accessible_cache['post_ids'] if _mod_accessible_cache['post_ids'] else set()

@cp_blocker_bp.route('/api/cp/check-post-access/<int:post_id>', methods=['GET'])
def check_post_access(post_id):
    """
    Check if a post should be blocked.
    Returns: 
      200 {"allowed": true} if accessible
      403 {"allowed": false, "reason": "..."} if blocked
    
    Admin users can always access CP-reported posts.
    """
    logger.info(f"🔍 [CP POST BLOCKER] Checking access to post {post_id}")
    logger.info(f"🍪 [CP POST BLOCKER] Cookies: {request.cookies}")
    
    # Check if user is admin (via JWT from cookie)
    # Admin is always person_id = 1 in Lemmy
    jwt_token = request.cookies.get('jwt')
    logger.info(f"🔑 [CP POST BLOCKER] JWT token present: {bool(jwt_token)}")
    
    if jwt_token:
        try:
            import jwt as pyjwt
            decoded = pyjwt.decode(jwt_token, options={"verify_signature": False})
            person_id = decoded.get('sub')
            
            # JWT 'sub' can be either int or str, normalize to int
            if isinstance(person_id, str):
                person_id = int(person_id) if person_id.isdigit() else None
            
            # Admin user (quick check)
            logger.info(f"👤 [CP POST BLOCKER] Decoded person_id: {person_id} (type: {type(person_id).__name__})")
            if person_id == 1:
                logger.info(f"✅ [CP POST BLOCKER] Admin access to post {post_id} - ALLOWED")
                return jsonify({"allowed": True, "admin": True}), 200

            # Check if user is a Lemmy community moderator (any community)
            # Also respects admin's manual revocation of CP review permission
            if is_lemmy_community_moderator(person_id):
                # Moderator found - but check if this post is still at moderator level
                mod_accessible_posts = get_mod_accessible_post_ids()
                blocked_posts = get_blocked_post_ids()
                
                if post_id in mod_accessible_posts:
                    # Post is pending at moderator level - allow access
                    logger.info(f"✅ [CP POST BLOCKER] Moderator (person_id={person_id}) access to post {post_id} (pending review) - ALLOWED")
                    return jsonify({"allowed": True, "moderator": True}), 200
                elif post_id in blocked_posts:
                    # Post is hidden but NOT at moderator level (escalated to admin or already reviewed)
                    # Moderator cannot access anymore
                    logger.info(f"❌ [CP POST BLOCKER] Moderator DENIED access to post {post_id} (escalated to admin or reviewed)")
                    return jsonify({
                        "allowed": False,
                        "reason": "Content under admin review - moderator access revoked"
                    }), 403
                else:
                    # Post is not blocked at all - allow normal access
                    logger.info(f"✅ [CP POST BLOCKER] Moderator access to post {post_id} (not blocked) - ALLOWED")
                    return jsonify({"allowed": True, "moderator": True}), 200
        except Exception as e:
            logger.error(f"Error decoding JWT: {e}")
    
    blocked_posts = get_blocked_post_ids()
    logger.info(f"🚫 [CP POST BLOCKER] Blocked posts: {blocked_posts}")
    
    if post_id in blocked_posts:
        logger.info(f"❌ [CP POST BLOCKER] Post {post_id} is blocked - denying access")
        return jsonify({
            "allowed": False,
            "reason": "Content unavailable (removed or under review)"
        }), 403
    
    logger.info(f"✅ [CP POST BLOCKER] Post {post_id} not blocked - allowing access")
    return jsonify({"allowed": True}), 200


@cp_blocker_bp.route('/api/cp/check-post-uri', methods=['GET'])
@cp_blocker_bp.route('/api/cp/check-post-uri', methods=['GET'])
def check_post_uri():
    """
    Check if a post should be blocked by parsing X-Original-URI header.
    Used by nginx auth_request.
    """
    import re
    
    original_uri = request.headers.get('X-Original-URI', '')
    logger.info(f"🔍 [CP POST BLOCKER] Checking URI: {original_uri}")
    
    # Extract post_id from URI like /post/136
    match = re.match(r'^/post/(\d+)', original_uri)
    if not match:
        logger.warning(f"⚠️ [CP POST BLOCKER] Could not extract post_id from URI: {original_uri}")
        return '', 200  # Allow if we can't parse (fail open for non-post URIs)
    
    post_id = int(match.group(1))
    logger.info(f"🔍 [CP POST BLOCKER] Extracted post_id: {post_id}")
    
    # Check if user is admin (via JWT from cookie)
    jwt_token = request.cookies.get('jwt')
    logger.info(f"🔑 [CP POST BLOCKER] JWT token present: {bool(jwt_token)}")
    
    if jwt_token:
        try:
            import jwt as pyjwt
            decoded = pyjwt.decode(jwt_token, options={"verify_signature": False})
            person_id = decoded.get('sub')
            
            # JWT 'sub' can be either int or str, normalize to int
            if isinstance(person_id, str):
                person_id = int(person_id) if person_id.isdigit() else None
            
            # Admin user (quick check)
            logger.info(f"👤 [CP POST BLOCKER] Decoded person_id: {person_id} (type: {type(person_id).__name__})")
            if person_id == 1:
                logger.info(f"✅ [CP POST BLOCKER] Admin access to post {post_id} - ALLOWED")
                return '', 200

            # Check if user is a Lemmy community moderator (any community)
            # Also respects admin's manual revocation of CP review permission
            if is_lemmy_community_moderator(person_id):
                # Moderator found - check if post is still at moderator level
                mod_accessible_posts = get_mod_accessible_post_ids()
                blocked_posts = get_blocked_post_ids()
                
                if post_id in mod_accessible_posts:
                    logger.info(f"✅ [CP POST BLOCKER] Moderator (person_id={person_id}) access to post {post_id} (pending review) - ALLOWED")
                    return '', 200
                elif post_id in blocked_posts:
                    # Escalated to admin or already reviewed - deny mod access
                    logger.info(f"❌ [CP POST BLOCKER] Moderator DENIED access to post {post_id} (escalated/reviewed)")
                    return '', 403
                else:
                    # Not blocked - normal access
                    logger.info(f"✅ [CP POST BLOCKER] Moderator access to post {post_id} (not blocked) - ALLOWED")
                    return '', 200
        except Exception as e:
            logger.error(f"Error decoding JWT: {e}")
    
    blocked_posts = get_blocked_post_ids()
    logger.info(f"🚫 [CP POST BLOCKER] Blocked posts: {blocked_posts}")
    
    if post_id in blocked_posts:
        logger.info(f"❌ [CP POST BLOCKER] Post {post_id} is blocked - denying access")
        return '', 403
    
    logger.info(f"✅ [CP POST BLOCKER] Post {post_id} not blocked - allowing access")
    return '', 200

