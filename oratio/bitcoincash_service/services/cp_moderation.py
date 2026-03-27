"""
CP (Child Pornography) Moderation Service
=====================================
Handles all business logic for CP reporting, moderation, appeals, and permissions.
"""

import sqlite3
import time
import uuid
import json
import logging
from typing import Optional, Dict, List, Tuple
from config import DB_PATH, logger


# ==========================================
# Constants
# ==========================================

BAN_DURATION_SECONDS = 90 * 24 * 60 * 60  # 3 months in seconds
AUTO_DELETE_DURATION_SECONDS = 7 * 24 * 60 * 60  # 1 week in seconds

REPORT_STATUS_PENDING = 'pending'
REPORT_STATUS_MODERATOR_CONFIRMED = 'moderator_confirmed'  # Mod confirmed CP → awaiting appeal (NOT shown in admin pending reports)
REPORT_STATUS_MODERATOR_REVIEW = 'moderator_review'
REPORT_STATUS_ADMIN_REVIEW = 'admin_review'
REPORT_STATUS_APPROVED = 'approved'
REPORT_STATUS_REJECTED = 'rejected'
REPORT_STATUS_AUTO_DELETED = 'auto_deleted'

REVIEW_DECISION_CP_CONFIRMED = 'cp_confirmed'
REVIEW_DECISION_NOT_CP = 'not_cp'
REVIEW_DECISION_ADMIN_APPROVED = 'admin_approved'
REVIEW_DECISION_ADMIN_REJECTED = 'admin_rejected'

ESCALATION_MODERATOR = 'moderator'
ESCALATION_ADMIN = 'admin'

APPEAL_TYPE_BAN = 'ban'
APPEAL_TYPE_REPORT_ABILITY = 'report_ability_loss'

NOTIFICATION_REPORT_SUBMITTED = 'report_submitted'
NOTIFICATION_REVIEW_NEEDED = 'review_needed'
NOTIFICATION_BAN_NOTICE = 'ban_notice'
NOTIFICATION_PERMISSION_REVOKED = 'permission_revoked'
NOTIFICATION_APPEAL_REVIEWED = 'appeal_reviewed'


# ==========================================
# Database Helpers
# ==========================================

def get_db():
    """Get database connection with proper settings"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def execute_query(query: str, params: tuple = (), commit: bool = False):
    """Execute a database query with error handling"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(query, params)
        if commit:
            conn.commit()
        result = cursor.fetchall()
        conn.close()
        return result
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise


def log_audit(action_type: str, actor_person_id: Optional[int], actor_username: Optional[str],
              target_user_id: Optional[str] = None, target_person_id: Optional[int] = None,
              target_username: Optional[str] = None, related_report_id: Optional[str] = None,
              related_appeal_id: Optional[str] = None, action_details: Optional[Dict] = None):
    """Log an audit entry"""
    audit_id = str(uuid.uuid4())
    now = int(time.time())
    details_json = json.dumps(action_details) if action_details else None
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO cp_audit_log 
        (id, action_type, actor_person_id, actor_username, target_user_id, target_person_id,
         target_username, related_report_id, related_appeal_id, action_details, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (audit_id, action_type, actor_person_id, actor_username, target_user_id, target_person_id,
          target_username, related_report_id, related_appeal_id, details_json, now))
    conn.commit()
    conn.close()


# ==========================================
# User Permissions Management
# ==========================================

def ensure_user_permissions(user_id: str, person_id: int, username: str) -> Dict:
    """Ensure user has permissions entry, create if not exists"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if exists
    cursor.execute('SELECT * FROM user_cp_permissions WHERE user_id = ?', (user_id,))
    existing = cursor.fetchone()
    
    if existing:
        conn.close()
        return dict(existing)
    
    # Create new entry
    now = int(time.time())
    cursor.execute('''
        INSERT INTO user_cp_permissions 
        (user_id, person_id, username, can_report_cp, can_review_cp, is_banned, 
         ban_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, person_id, username, True, False, False, 0, now, now))
    conn.commit()
    
    cursor.execute('SELECT * FROM user_cp_permissions WHERE user_id = ?', (user_id,))
    result = dict(cursor.fetchone())
    conn.close()
    
    log_audit('user_permissions_created', person_id, username, user_id, person_id, username)
    return result


def get_user_permissions(user_id: str) -> Optional[Dict]:
    """Get user CP permissions by user_id"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM user_cp_permissions WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


def get_user_permissions_by_username(username: str) -> Optional[Dict]:
    """Get user CP permissions by username (for public/non-authenticated access)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM user_cp_permissions WHERE username = ?', (username,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


def can_user_report_cp(user_id: str) -> Tuple[bool, Optional[str]]:
    """Check if user can report CP content"""
    perms = get_user_permissions(user_id)
    if not perms:
        return False, "User permissions not found"
    
    now = int(time.time())
    
    if perms['is_banned']:
        ban_end = perms.get('ban_end')
        if ban_end:
            days_left = (ban_end - now) / (24 * 60 * 60)
            ban_end_date = time.strftime('%Y-%m-%d', time.localtime(ban_end))
            return False, f"You are currently banned until {ban_end_date} ({int(days_left)} days remaining)"
        return False, "You are currently banned"
    
    if not perms['can_report_cp']:
        report_ability_end = perms.get('report_ability_revoked_at')
        if report_ability_end:
            days_left = (report_ability_end - now) / (24 * 60 * 60)
            restore_date = time.strftime('%Y-%m-%d', time.localtime(report_ability_end))
            return False, f"Your CP reporting ability has been revoked until {restore_date} ({int(days_left)} days remaining). You can appeal at /cp/appeal"
        return False, "Your CP reporting ability has been revoked"
    
    return True, None


def ban_user(user_id: str, person_id: int, username: str, banned_by_person_id: int, 
             banned_by_username: str, reason: str = "CP violation") -> bool:
    """Ban user for 3 months"""
    now = int(time.time())
    ban_end = now + BAN_DURATION_SECONDS
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Update permissions in CP system
    cursor.execute('''
        UPDATE user_cp_permissions 
        SET is_banned = ?, ban_start = ?, ban_end = ?, ban_count = ban_count + 1,
            last_violation = ?, updated_at = ?
        WHERE user_id = ?
    ''', (True, now, ban_end, now, now, user_id))
    conn.commit()
    conn.close()
    
    # BAN USER IN LEMMY (Admin ban)
    logger.info(f"🚫 [CP BAN] Banning user in Lemmy: person_id={person_id}, username={username}")
    try:
        from lemmy_integration import LemmyAPI
        import os
        
        lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
        lemmy_admin_username = os.environ.get('LEMMY_ADMIN_USER', 'admin')
        lemmy_admin_password = os.environ.get('LEMMY_ADMIN_PASS', '')
        
        if lemmy_admin_password:
            lemmy_api = LemmyAPI(lemmy_api_url)
            lemmy_api.set_admin_credentials(lemmy_admin_username, lemmy_admin_password)
            
            if lemmy_api.login_as_admin():
                # Ban user in Lemmy for 3 months
                success = lemmy_api.ban_person(
                    person_id=person_id,
                    ban=True,
                    reason=f"CP violation - {reason}",
                    expires=ban_end,  # Unix timestamp for 3 months from now
                    remove_data=False  # Don't delete user's data
                )
                
                if success:
                    logger.info(f"✅ [CP BAN] User {username} banned in Lemmy until {time.strftime('%Y-%m-%d', time.localtime(ban_end))}")
                else:
                    logger.error(f"❌ [CP BAN] Failed to ban user {username} in Lemmy")
            else:
                logger.error(f"❌ [CP BAN] Failed to login as admin to ban user")
        else:
            logger.warning(f"⚠️  [CP BAN] No admin password - cannot ban user in Lemmy")
    except Exception as e:
        logger.error(f"❌ [CP BAN] Error banning user in Lemmy: {e}")
        import traceback
        logger.error(f"❌ [CP BAN] Traceback: {traceback.format_exc()}")
    
    # Create notification
    create_notification(
        person_id, username, NOTIFICATION_BAN_NOTICE,
        "You Have Been Banned",
        f"Your account has been banned for 3 months due to {reason}. Ban expires on {time.strftime('%Y-%m-%d', time.localtime(ban_end))}."
    )
    
    # Log audit
    log_audit('user_banned', banned_by_person_id, banned_by_username, user_id, person_id, username,
              action_details={'reason': reason, 'duration_days': 90, 'ban_end': ban_end})
    
    logger.info(f"💀 [CP BAN] User {username} (ID: {user_id}) banned for 3 months by {banned_by_username}")
    return True


def revoke_report_ability(user_id: str, person_id: int, username: str, 
                          revoked_by_person_id: int, revoked_by_username: str) -> bool:
    """Revoke user's ability to report CP for 3 months"""
    now = int(time.time())
    report_ability_end = now + BAN_DURATION_SECONDS  # 3 months, same as ban duration
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Add report_ability_revoked_at column if it doesn't exist (migration)
    try:
        cursor.execute('ALTER TABLE user_cp_permissions ADD COLUMN report_ability_revoked_at INTEGER')
        conn.commit()
        logger.info("✅ Added report_ability_revoked_at column to user_cp_permissions")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    cursor.execute('''
        UPDATE user_cp_permissions 
        SET can_report_cp = ?, report_ability_revoked_at = ?, updated_at = ?
        WHERE user_id = ?
    ''', (False, report_ability_end, now, user_id))
    conn.commit()
    conn.close()
    
    # Create notification
    expire_date = time.strftime('%Y-%m-%d', time.localtime(report_ability_end))
    create_notification(
        person_id, username, NOTIFICATION_PERMISSION_REVOKED,
        "CP Reporting Ability Revoked",
        f"Your ability to report child pornography has been revoked for 3 months due to false reporting. "
        f"Report ability will be restored on {expire_date}."
    )
    
    # Log audit
    log_audit('report_ability_revoked', revoked_by_person_id, revoked_by_username, 
              user_id, person_id, username, 
              action_details={'duration_days': 90, 'report_ability_end': report_ability_end})
    
    logger.info(f"⛔ [CP REPORT BAN] User {username} (ID: {user_id}) report ability revoked for 3 months until {expire_date}")
    return True


def _unban_user_in_lemmy(person_id: int, username: str, reason: str = "Ban lifted") -> bool:
    """Helper: Unban a user in Lemmy PostgreSQL via API. Returns True on success."""
    logger.info(f"✅ [CP UNBAN] Unbanning user in Lemmy: person_id={person_id}, username={username}")
    try:
        from lemmy_integration import LemmyAPI
        import os

        lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
        lemmy_admin_username = os.environ.get('LEMMY_ADMIN_USER', 'admin')
        lemmy_admin_password = os.environ.get('LEMMY_ADMIN_PASS', '')

        if not lemmy_admin_password:
            logger.warning(f"⚠️  [CP UNBAN] No admin password - cannot unban user in Lemmy")
            return False

        lemmy_api = LemmyAPI(lemmy_api_url)
        lemmy_api.set_admin_credentials(lemmy_admin_username, lemmy_admin_password)

        if not lemmy_api.login_as_admin():
            logger.error(f"❌ [CP UNBAN] Failed to login as admin to unban user")
            return False

        success = lemmy_api.ban_person(
            person_id=person_id,
            ban=False,  # Unban
            reason=reason,
            remove_data=False
        )

        if success:
            logger.info(f"✅ [CP UNBAN] User {username} unbanned in Lemmy successfully")
        else:
            logger.error(f"❌ [CP UNBAN] Failed to unban user {username} in Lemmy")
        return success

    except Exception as e:
        logger.error(f"❌ [CP UNBAN] Error unbanning user in Lemmy: {e}")
        import traceback
        logger.error(f"❌ [CP UNBAN] Traceback: {traceback.format_exc()}")
        return False


def restore_user_privileges(user_id: str, restore_ban: bool = False, 
                           restore_report: bool = False,
                           restored_by_person_id: int = None,
                           restored_by_username: str = None) -> dict:
    """Restore user privileges (admin action).
    Returns dict: {'success': bool, 'lemmy_unban': bool|None, 'warning': str|None}
    """
    now = int(time.time())
    updates = []
    params = []
    
    if restore_ban:
        updates.append("is_banned = ?, ban_start = NULL, ban_end = NULL")
        params.extend([False])
    
    if restore_report:
        updates.append("can_report_cp = ?, report_ability_revoked_at = NULL")
        params.extend([True])
    
    if not updates:
        return {'success': False, 'lemmy_unban': None, 'warning': 'Nothing to restore'}
    
    updates.append("updated_at = ?")
    params.append(now)
    params.append(user_id)
    
    query = f"UPDATE user_cp_permissions SET {', '.join(updates)} WHERE user_id = ?"
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get user info before updating
    cursor.execute('SELECT person_id, username FROM user_cp_permissions WHERE user_id = ?', (user_id,))
    user_info = cursor.fetchone()
    
    cursor.execute(query, tuple(params))
    conn.commit()
    conn.close()
    
    # UNBAN USER IN LEMMY if restoring ban
    lemmy_unban_result = None
    warning = None
    if restore_ban and user_info:
        person_id = user_info['person_id']
        username = user_info['username']
        lemmy_unban_result = _unban_user_in_lemmy(
            person_id, username, reason="Admin CP panel - privileges restored"
        )
        if not lemmy_unban_result:
            warning = (f"SQLite unban 성공, but Lemmy PostgreSQL unban 실패! "
                       f"Admin Settings > Banned Users에서 수동으로 '{username}' 추방취소 필요")
    
    # Log audit
    log_audit('privileges_restored', restored_by_person_id, restored_by_username,
              user_id, action_details={
                  'restore_ban': restore_ban, 
                  'restore_report': restore_report,
                  'lemmy_unban': lemmy_unban_result
              })
    
    return {'success': True, 'lemmy_unban': lemmy_unban_result, 'warning': warning}


def _restore_reported_content(user_id: str, admin_username: str):
    """Restore (un-remove) all CP-reported content for a user when their appeal is approved.
    
    Only restores content that was removed (not purged). Purged content cannot be recovered.
    Also updates CP report records to mark content as unhidden.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Find all reports where content was hidden and pending admin review (not yet purged)
    cursor.execute('''
        SELECT id, content_type, content_id
        FROM cp_reports
        WHERE creator_user_id = ? AND content_hidden = 1
        ORDER BY created_at DESC
    ''', (user_id,))
    
    reports = cursor.fetchall()
    
    if not reports:
        conn.close()
        logger.info(f"📝 [APPEAL RESTORE] No hidden content found for user {user_id}")
        return
    
    try:
        from lemmy_integration import LemmyAPI
        import os
        
        lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
        lemmy_admin_username = os.environ.get('LEMMY_ADMIN_USER', 'admin')
        lemmy_admin_password = os.environ.get('LEMMY_ADMIN_PASS', '')
        
        lemmy_api = None
        if lemmy_admin_password:
            lemmy_api = LemmyAPI(lemmy_api_url)
            lemmy_api.set_admin_credentials(lemmy_admin_username, lemmy_admin_password)
            if not lemmy_api.login_as_admin():
                logger.error(f"❌ [APPEAL RESTORE] Failed to login as admin")
                lemmy_api = None
        
        for report in reports:
            report_id = report['id']
            content_type = report['content_type']
            content_id = report['content_id']
            
            # Try to un-remove in Lemmy (will fail silently for purged content)
            restored_in_lemmy = False
            if lemmy_api:
                try:
                    restore_reason = f"Appeal approved by admin {admin_username}"
                    if content_type == 'post':
                        restored_in_lemmy = lemmy_api.remove_post(content_id, removed=False, reason=restore_reason)
                    elif content_type == 'comment':
                        restored_in_lemmy = lemmy_api.remove_comment(content_id, removed=False, reason=restore_reason)
                    
                    if restored_in_lemmy:
                        logger.info(f"✅ [APPEAL RESTORE] {content_type} #{content_id} restored in Lemmy")
                    else:
                        logger.warning(f"⚠️  [APPEAL RESTORE] Could not restore {content_type} #{content_id} (may have been purged)")
                except Exception as e:
                    logger.error(f"❌ [APPEAL RESTORE] Error restoring {content_type} #{content_id}: {e}")
            
            # Update CP report: mark content as unhidden, change status to approved
            cursor.execute('''
                UPDATE cp_reports
                SET content_hidden = 0, status = ?, auto_delete_at = NULL
                WHERE id = ?
            ''', (REPORT_STATUS_APPROVED, report_id))
            
            logger.info(f"📝 [APPEAL RESTORE] CP report {report_id} marked as approved/unhidden")
        
        conn.commit()
    except Exception as e:
        logger.error(f"❌ [APPEAL RESTORE] Error in content restoration: {e}")
    finally:
        conn.close()


def _purge_reported_content(user_id: str, admin_username: str):
    """Permanently purge all CP-reported content for a user when appeal is rejected.
    
    This is the final action: content is permanently removed from Lemmy.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Find all reports where content is still hidden (removed but not yet purged)
    cursor.execute('''
        SELECT id, content_type, content_id
        FROM cp_reports
        WHERE creator_user_id = ? AND content_hidden = 1
        ORDER BY created_at DESC
    ''', (user_id,))
    
    reports = cursor.fetchall()
    
    if not reports:
        conn.close()
        logger.info(f"📝 [APPEAL REJECT PURGE] No hidden content found for user {user_id}")
        return
    
    try:
        from lemmy_integration import LemmyAPI
        import os
        
        lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
        lemmy_admin_username = os.environ.get('LEMMY_ADMIN_USER', 'admin')
        lemmy_admin_password = os.environ.get('LEMMY_ADMIN_PASS', '')
        
        lemmy_api = None
        if lemmy_admin_password:
            lemmy_api = LemmyAPI(lemmy_api_url)
            lemmy_api.set_admin_credentials(lemmy_admin_username, lemmy_admin_password)
            if not lemmy_api.login_as_admin():
                logger.error(f"❌ [APPEAL REJECT PURGE] Failed to login as admin")
                lemmy_api = None
        
        for report in reports:
            report_id = report['id']
            content_type = report['content_type']
            content_id = report['content_id']
            
            purged = False
            if lemmy_api:
                try:
                    purge_reason = f"Appeal rejected - CP confirmed by admin {admin_username}"
                    if content_type == 'post':
                        purged = lemmy_api.purge_post(content_id, reason=purge_reason)
                    elif content_type == 'comment':
                        purged = lemmy_api.purge_comment(content_id, reason=purge_reason)
                    
                    if purged:
                        logger.info(f"✅ [APPEAL REJECT PURGE] {content_type} #{content_id} PURGED from Lemmy")
                    else:
                        logger.warning(f"⚠️  [APPEAL REJECT PURGE] Could not purge {content_type} #{content_id}")
                except Exception as e:
                    logger.error(f"❌ [APPEAL REJECT PURGE] Error purging {content_type} #{content_id}: {e}")
            
            # Update CP report: mark as auto_deleted
            cursor.execute('''
                UPDATE cp_reports
                SET status = ?, auto_delete_at = NULL
                WHERE id = ?
            ''', (REPORT_STATUS_AUTO_DELETED, report_id))
        
        conn.commit()
    except Exception as e:
        logger.error(f"❌ [APPEAL REJECT PURGE] Error in content purge: {e}")
    finally:
        conn.close()


# ==========================================
# CP Report Management
# ==========================================

def create_cp_report(content_type: str, content_id: int, community_id: int,
                     reporter_user_id: str, reporter_person_id: int, reporter_username: str,
                     reporter_is_member: bool, creator_user_id: str, creator_person_id: int,
                     creator_username: str, reason: Optional[str] = None) -> Dict:
    """Create a new CP report - content is immediately hidden"""
    
    # Ensure both users have permissions entries (create if not exists)
    ensure_user_permissions(reporter_user_id, reporter_person_id, reporter_username)
    ensure_user_permissions(creator_user_id, creator_person_id, creator_username)
    
    # Check if reporter can report (after ensuring permissions exist)
    can_report, error_msg = can_user_report_cp(reporter_user_id)
    if not can_report:
        raise PermissionError(error_msg)
    
    # Check for existing reports
    existing = check_existing_report(content_type, content_id, creator_user_id)
    
    report_id = str(uuid.uuid4())
    now = int(time.time())
    escalation_level = ESCALATION_MODERATOR
    previous_report_id = None
    
    # If content was previously approved by moderator and reporter is member, escalate to admin
    if existing and existing['status'] == REPORT_STATUS_APPROVED and existing['review_decision'] == REVIEW_DECISION_NOT_CP:
        if reporter_is_member:
            escalation_level = ESCALATION_ADMIN
            previous_report_id = existing['id']
        else:
            raise PermissionError("Free users cannot re-report content approved by moderators")
    
    # If content was approved by admin, no one can re-report
    if existing and existing['review_decision'] == REVIEW_DECISION_ADMIN_APPROVED:
        raise PermissionError("Content approved by admin cannot be reported again")
    
    # If moderator already confirmed CP (creator banned, awaiting appeal), no one can re-report
    if existing and existing['status'] == REPORT_STATUS_MODERATOR_CONFIRMED:
        raise PermissionError("Content has already been confirmed as CP by a moderator. Creator has been banned.")
    
    # Set auto-delete time for admin-level reports
    auto_delete_at = None
    if escalation_level == ESCALATION_ADMIN:
        auto_delete_at = now + AUTO_DELETE_DURATION_SECONDS
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO cp_reports
        (id, content_type, content_id, community_id, reporter_user_id, reporter_person_id,
         reporter_username, reporter_is_member, creator_user_id, creator_person_id,
         creator_username, reason, status, content_hidden, escalation_level,
         previous_report_id, created_at, auto_delete_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (report_id, content_type, content_id, community_id, reporter_user_id, reporter_person_id,
          reporter_username, reporter_is_member, creator_user_id, creator_person_id,
          creator_username, reason, REPORT_STATUS_PENDING, True, escalation_level,
          previous_report_id, now, auto_delete_at))
    conn.commit()
    conn.close()
    
    # Log audit
    log_audit('report_created', reporter_person_id, reporter_username, creator_user_id,
              creator_person_id, creator_username, report_id,
              action_details={'content_type': content_type, 'content_id': content_id,
                            'escalation_level': escalation_level})
    
    # NOTE: Content is NOT removed in Lemmy immediately
    # Instead, it will be filtered out on the frontend based on CP report status
    # Moderators will still be able to see the content for review
    # When moderator confirms as CP, THEN we remove it in Lemmy
    logger.info(f"✅ [CP MODERATION] CP report created for {content_type} {content_id}")
    logger.info(f"📌 [CP MODERATION] Content will be hidden via frontend filtering")
    logger.info(f"👁️  [CP MODERATION] Moderators can still view for review")
    
    # Notify moderators or admin
    if escalation_level == ESCALATION_MODERATOR:
        notify_community_moderators(community_id, report_id, content_type, content_id)
    else:
        notify_admins(report_id, content_type, content_id, "Re-report by membership user")
    
    logger.info(f"CP report created: {report_id} for {content_type} {content_id} by {reporter_username}")
    
    return get_cp_report(report_id)


def check_existing_report(content_type: str, content_id: int, creator_user_id: str) -> Optional[Dict]:
    """Check if content has been reported before"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM cp_reports 
        WHERE content_type = ? AND content_id = ? AND creator_user_id = ?
        ORDER BY created_at DESC LIMIT 1
    ''', (content_type, content_id, creator_user_id))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


def get_cp_report(report_id: str) -> Optional[Dict]:
    """Get CP report by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM cp_reports WHERE id = ?', (report_id,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


def get_pending_reports(community_id: Optional[int] = None, 
                       escalation_level: str = ESCALATION_MODERATOR,
                       limit: int = 50, offset: int = 0) -> List[Dict]:
    """Get pending CP reports for moderation"""
    query = '''
        SELECT * FROM cp_reports 
        WHERE status = ? AND escalation_level = ?
    '''
    params = [REPORT_STATUS_PENDING, escalation_level]
    
    if community_id:
        query += ' AND community_id = ?'
        params.append(community_id)
    
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, tuple(params))
    results = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in results]


# ==========================================
# CP Review (Moderator/Admin)
# ==========================================

def review_cp_report(report_id: str, reviewer_person_id: int, reviewer_username: str,
                    reviewer_role: str, decision: str, notes: Optional[str] = None) -> Dict:
    """Review a CP report (moderator or admin)"""
    
    report = get_cp_report(report_id)
    if not report:
        raise ValueError("Report not found")
    
    if report['status'] != REPORT_STATUS_PENDING:
        raise ValueError("Report already reviewed")
    
    # Validate decision
    if reviewer_role == 'moderator' and decision not in [REVIEW_DECISION_CP_CONFIRMED, REVIEW_DECISION_NOT_CP]:
        raise ValueError("Invalid moderator decision")
    
    if reviewer_role == 'admin' and decision not in [REVIEW_DECISION_ADMIN_APPROVED, REVIEW_DECISION_ADMIN_REJECTED]:
        raise ValueError("Invalid admin decision")
    
    now = int(time.time())
    review_id = str(uuid.uuid4())
    
    # Create review record
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO cp_reviews
        (id, report_id, reviewer_person_id, reviewer_username, reviewer_role, decision, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (review_id, report_id, reviewer_person_id, reviewer_username, reviewer_role, decision, notes, now))
    
    # Update report
    # Moderator cp_confirmed: escalate to admin with 7-day window (remove, not purge)
    # Admin rejected: final purge
    new_status = REPORT_STATUS_REJECTED
    content_hidden = 1  # Default: keep hidden

    if decision == REVIEW_DECISION_CP_CONFIRMED:
        # Moderator confirmed CP → mark as moderator_confirmed (NOT pending)
        # This will NOT appear in admin pending reports.
        # Creator gets banned, can appeal via appeal system.
        # If admin does not review via appeal within 7 days, content auto-purged.
        new_status = REPORT_STATUS_MODERATOR_CONFIRMED
        content_hidden = 1
    elif decision == REVIEW_DECISION_ADMIN_REJECTED:
        # Admin final decision: this IS CP → permanent purge now
        new_status = REPORT_STATUS_AUTO_DELETED
        content_hidden = 1
    elif decision == REVIEW_DECISION_NOT_CP or decision == REVIEW_DECISION_ADMIN_APPROVED:
        new_status = REPORT_STATUS_APPROVED  # Not CP, unhide it
        content_hidden = 0  # Mark as not hidden anymore

    # For moderator cp_confirmed: set escalation to admin + 7-day auto_delete timer
    auto_delete_at_value = None
    new_escalation = None
    if decision == REVIEW_DECISION_CP_CONFIRMED:
        auto_delete_at_value = now + AUTO_DELETE_DURATION_SECONDS  # 7 days from now
        new_escalation = ESCALATION_ADMIN
    
    cursor.execute('''
        UPDATE cp_reports
        SET status = ?, reviewed_by_person_id = ?, reviewed_by_username = ?,
            reviewed_at = ?, review_decision = ?, review_notes = ?, content_hidden = ?
        WHERE id = ?
    ''', (new_status, reviewer_person_id, reviewer_username, now, decision, notes, content_hidden, report_id))

    # If moderator confirmed CP, set escalation to admin + 7-day auto_delete timer
    # Status stays as moderator_confirmed (NOT pending) so it does NOT appear in admin pending reports
    if decision == REVIEW_DECISION_CP_CONFIRMED:
        cursor.execute('''
            UPDATE cp_reports
            SET escalation_level = ?, auto_delete_at = ?, status = ?
            WHERE id = ?
        ''', (ESCALATION_ADMIN, auto_delete_at_value, REPORT_STATUS_MODERATOR_CONFIRMED, report_id))
    
    conn.commit()
    conn.close()
    
    # Handle consequences based on decision
    if decision == REVIEW_DECISION_CP_CONFIRMED:
        # Moderator confirmed CP → ban creator + REMOVE (not purge) content
        # Content stays in Lemmy DB but hidden — admin can still review
        ban_user(report['creator_user_id'], report['creator_person_id'], 
                report['creator_username'], reviewer_person_id, reviewer_username)
        
        logger.info(f"🚫 [CP REVIEW] Moderator CP confirmed - REMOVING (not purging) content from Lemmy")
        logger.info(f"� [CP REVIEW] Content escalated to admin. Admin has 7 days to review.")
        try:
            from lemmy_integration import LemmyAPI
            import os
            
            lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
            lemmy_admin_username = os.environ.get('LEMMY_ADMIN_USER', 'admin')
            lemmy_admin_password = os.environ.get('LEMMY_ADMIN_PASS', '')
            
            if lemmy_admin_password:
                lemmy_api = LemmyAPI(lemmy_api_url)
                lemmy_api.set_admin_credentials(lemmy_admin_username, lemmy_admin_password)
                
                if lemmy_api.login_as_admin():
                    cp_reason = f"CP reported - pending admin review (confirmed by moderator {reviewer_username})"
                    success = False
                    
                    # Use REMOVE (not purge!) so admin can still see and appeal can restore
                    if report['content_type'] == 'post':
                        success = lemmy_api.remove_post(report['content_id'], removed=True, reason=cp_reason)
                    elif report['content_type'] == 'comment':
                        success = lemmy_api.remove_comment(report['content_id'], removed=True, reason=cp_reason)
                    
                    if success:
                        logger.info(f"✅ [CP REVIEW] Content REMOVED in Lemmy (admin can still view for review)")
                    else:
                        logger.error(f"❌ [CP REVIEW] Failed to remove content from Lemmy")
                else:
                    logger.error(f"❌ [CP REVIEW] Failed to login as admin")
            else:
                logger.warning(f"⚠️  [CP REVIEW] No admin password - cannot remove from Lemmy")
        except Exception as e:
            logger.error(f"❌ [CP REVIEW] Error removing content: {e}")

    elif decision == REVIEW_DECISION_ADMIN_REJECTED:
        # Admin final decision: this IS CP → permanent PURGE now
        ban_user(report['creator_user_id'], report['creator_person_id'], 
                report['creator_username'], reviewer_person_id, reviewer_username)
        
        # 2-1: If this is a re-report (previous_report_id exists), the original reporter
        # had their report ability revoked by mod's "not_cp" decision. Since admin now
        # confirms it IS CP, the original reporter was RIGHT → restore their report ability.
        if report.get('previous_report_id'):
            prev_report = get_cp_report(report['previous_report_id'])
            if prev_report and prev_report.get('review_decision') == REVIEW_DECISION_NOT_CP:
                original_reporter_user_id = prev_report['reporter_user_id']
                original_reporter_perms = get_user_permissions(original_reporter_user_id)
                if original_reporter_perms and not original_reporter_perms.get('can_report_cp', True):
                    restore_user_privileges(
                        original_reporter_user_id,
                        restore_ban=False,
                        restore_report=True,
                        restored_by_person_id=reviewer_person_id,
                        restored_by_username=reviewer_username
                    )
                    logger.info(f"✅ [CP REVIEW] Original reporter {prev_report['reporter_username']} "
                                f"report ability RESTORED (admin confirmed CP, mod was wrong)")
                    # Notify the original reporter
                    if original_reporter_perms.get('person_id'):
                        create_notification(
                            original_reporter_perms['person_id'],
                            prev_report['reporter_username'],
                            'report_ability_restored',
                            "Report Ability Restored",
                            "Your CP reporting ability has been restored. "
                            "An admin confirmed the content you reported was indeed CP. Thank you for your report."
                        )
        
        logger.info(f"🚫 [CP REVIEW] Admin confirmed CP - PURGING content permanently from Lemmy")
        try:
            from lemmy_integration import LemmyAPI
            import os
            
            lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
            lemmy_admin_username = os.environ.get('LEMMY_ADMIN_USER', 'admin')
            lemmy_admin_password = os.environ.get('LEMMY_ADMIN_PASS', '')
            
            if lemmy_admin_password:
                lemmy_api = LemmyAPI(lemmy_api_url)
                lemmy_api.set_admin_credentials(lemmy_admin_username, lemmy_admin_password)
                
                if lemmy_api.login_as_admin():
                    cp_reason = f"Child pornography confirmed by admin {reviewer_username}"
                    success = False
                    
                    # PURGE for permanent deletion
                    if report['content_type'] == 'post':
                        success = lemmy_api.purge_post(report['content_id'], reason=cp_reason)
                    elif report['content_type'] == 'comment':
                        success = lemmy_api.purge_comment(report['content_id'], reason=cp_reason)
                    
                    if success:
                        logger.info(f"✅ [CP REVIEW] Content PERMANENTLY PURGED from Lemmy")
                        try:
                            conn2 = get_db()
                            cur2 = conn2.cursor()
                            cur2.execute('''
                                UPDATE cp_reports
                                SET status = ?, content_hidden = 1, auto_delete_at = NULL
                                WHERE id = ?
                            ''', (REPORT_STATUS_AUTO_DELETED, report_id))
                            conn2.commit()
                            conn2.close()
                        except Exception as e:
                            logger.error(f"❌ [CP REVIEW] Failed to update cp_reports after purge: {e}")
                    else:
                        logger.error(f"❌ [CP REVIEW] Failed to purge content from Lemmy")
                else:
                    logger.error(f"❌ [CP REVIEW] Failed to login as admin")
            else:
                logger.warning(f"⚠️  [CP REVIEW] No admin password - cannot purge from Lemmy")
        except Exception as e:
            logger.error(f"❌ [CP REVIEW] Error purging content: {e}")
    
    elif decision == REVIEW_DECISION_NOT_CP or decision == REVIEW_DECISION_ADMIN_APPROVED:
        # Content is not CP - unhide it in Lemmy for all users who hid it
        logger.info(f"✅ [CP REVIEW] Not CP - unhiding content in Lemmy DB directly")
        
        try:
            import psycopg2
            import os
            
            # Connect to Lemmy's PostgreSQL database
            lemmy_db_host = os.environ.get('POSTGRES_HOST', 'postgres')
            lemmy_db_name = os.environ.get('POSTGRES_DB', 'lemmy')
            lemmy_db_user = os.environ.get('POSTGRES_USER', 'lemmy')
            lemmy_db_password = os.environ.get('POSTGRES_PASSWORD', '')
            
            pg_conn = psycopg2.connect(
                host=lemmy_db_host,
                database=lemmy_db_name,
                user=lemmy_db_user,
                password=lemmy_db_password
            )
            pg_cursor = pg_conn.cursor()
            
            if report['content_type'] == 'post':
                # Remove all post_hide entries for this post
                pg_cursor.execute('DELETE FROM post_hide WHERE post_id = %s', (report['content_id'],))
                deleted_count = pg_cursor.rowcount
                pg_conn.commit()
                logger.info(f"✅ [CP REVIEW] Unhid post {report['content_id']} for {deleted_count} users")
            elif report['content_type'] == 'comment':
                # No comment_hide table in Lemmy, comments use different mechanism
                logger.info(f"📝 [CP REVIEW] Comment unhide not needed (no comment_hide table)")
            
            pg_conn.close()
        except Exception as e:
            logger.error(f"❌ [CP REVIEW] Error unhiding content in Lemmy DB: {e}")
        
        if decision == REVIEW_DECISION_NOT_CP:
            # Revoke reporter's reporting ability (false report)
            revoke_report_ability(report['reporter_user_id'], report['reporter_person_id'],
                                 report['reporter_username'], reviewer_person_id, reviewer_username)
    
    # Log audit
    log_audit('report_reviewed', reviewer_person_id, reviewer_username,
              report['creator_user_id'], report['creator_person_id'], report['creator_username'],
              report_id, action_details={'decision': decision, 'reviewer_role': reviewer_role})
    
    logger.info(f"CP report {report_id} reviewed by {reviewer_username} ({reviewer_role}): {decision}")
    
    return get_cp_report(report_id)


# ==========================================
# Appeals System
# ==========================================

def create_appeal(user_id: str, person_id: int, username: str, appeal_type: str,
                 appeal_reason: str, related_report_id: Optional[str] = None) -> Dict:
    """Create an appeal (membership users only)"""
    
    # TODO: Add membership check here
    # For now, allow all users to appeal
    
    appeal_id = str(uuid.uuid4())
    now = int(time.time())
    seven_days_ago = now - (7 * 24 * 60 * 60)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current ban_start to scope appeal blocks to the CURRENT ban period only.
    # If user was unbanned and re-banned, previous appeal rejections should not block new appeals.
    current_ban_start = None
    cursor.execute('SELECT ban_start FROM user_cp_permissions WHERE user_id = ?', (user_id,))
    ban_row = cursor.fetchone()
    if ban_row:
        current_ban_start = ban_row[0] or 0
    
    # Block 1: If admin already made a final decision (admin_rejected) on the user's content
    # DURING THE CURRENT BAN PERIOD, the case is permanently closed — no appeal allowed.
    # Once ban expires/is lifted and user gets re-banned, this block resets.
    if appeal_type == APPEAL_TYPE_BAN and current_ban_start:
        cursor.execute('''
            SELECT COUNT(*) FROM cp_reports
            WHERE creator_user_id = ? AND review_decision = ? AND reviewed_at >= ?
        ''', (user_id, REVIEW_DECISION_ADMIN_REJECTED, current_ban_start))
        admin_final_count = cursor.fetchone()[0]
        if admin_final_count > 0:
            conn.close()
            raise PermissionError("Your case has been permanently decided by an admin. No further appeals are allowed.")
    
    # Block 2: If a previous appeal was already rejected by admin DURING THE CURRENT BAN PERIOD,
    # no more appeals allowed. Resets when ban expires/is lifted.
    if current_ban_start:
        cursor.execute('''
            SELECT COUNT(*) FROM cp_appeals
            WHERE user_id = ? AND appeal_type = ? AND status = 'rejected' AND created_at >= ?
        ''', (user_id, appeal_type, current_ban_start))
    else:
        cursor.execute('''
            SELECT COUNT(*) FROM cp_appeals
            WHERE user_id = ? AND appeal_type = ? AND status = 'rejected'
        ''', (user_id, appeal_type))
    rejected_appeal_count = cursor.fetchone()[0]
    if rejected_appeal_count > 0:
        conn.close()
        raise PermissionError("Your previous appeal was rejected by an admin. No further appeals are allowed.")
    
    # Block 3: Check if user already has a pending appeal (prevent spam)
    cursor.execute('''
        SELECT COUNT(*) FROM cp_appeals
        WHERE user_id = ? AND appeal_type = ? AND created_at > ? AND status = 'pending'
    ''', (user_id, appeal_type, seven_days_ago))
    existing_count = cursor.fetchone()[0]
    
    if existing_count > 0:
        conn.close()
        raise PermissionError("You already have a pending appeal. Please wait for admin review before submitting another.")
    
    # For ban appeals, check if it's within 7 days of the moderator cp_confirmed decision
    # The 7-day window starts when moderator confirms CP (which is when content gets removed
    # and escalated to admin). After 7 days, content is auto-purged and appeal is no longer possible.
    if appeal_type == APPEAL_TYPE_BAN:
        cursor.execute('''
            SELECT r.reviewed_at, r.auto_delete_at, rv.decision
            FROM cp_reports r
            JOIN cp_reviews rv ON r.id = rv.report_id
            WHERE r.creator_user_id = ? 
            AND rv.decision = 'cp_confirmed'
            ORDER BY rv.created_at DESC
            LIMIT 1
        ''', (user_id,))
        recent_review = cursor.fetchone()
        
        if recent_review:
            reviewed_at = recent_review[0]
            auto_delete_at = recent_review[1]
            if reviewed_at:
                days_since_review = (now - reviewed_at) / (24 * 60 * 60)
                if days_since_review > 7:
                    conn.close()
                    raise PermissionError("Appeal window has expired. You can only appeal within 7 days of the decision.")
    
    cursor.execute('''
        INSERT INTO cp_appeals
        (id, user_id, person_id, username, appeal_type, related_report_id, 
         appeal_reason, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (appeal_id, user_id, person_id, username, appeal_type, related_report_id,
          appeal_reason, 'pending', now))
    conn.commit()
    conn.close()
    
    # Notify admins
    notify_admins(None, 'appeal', appeal_id, f"New appeal from {username}")
    
    # Log audit
    log_audit('appeal_created', person_id, username, user_id, person_id, username,
              related_appeal_id=appeal_id, action_details={'appeal_type': appeal_type})
    
    logger.info(f"Appeal created: {appeal_id} by {username}")
    
    return get_appeal(appeal_id)


def get_appeal(appeal_id: str) -> Optional[Dict]:
    """Get appeal by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM cp_appeals WHERE id = ?', (appeal_id,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


def review_appeal(appeal_id: str, admin_person_id: int, admin_username: str,
                 decision: str, admin_notes: Optional[str] = None) -> Dict:
    """Review an appeal (admin only)"""
    
    appeal = get_appeal(appeal_id)
    if not appeal:
        raise ValueError("Appeal not found")
    
    if appeal['status'] != 'pending':
        raise ValueError("Appeal already reviewed")
    
    now = int(time.time())
    new_status = 'approved' if decision == 'restore_privileges' else 'rejected'
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE cp_appeals
        SET status = ?, reviewed_by_person_id = ?, reviewed_by_username = ?,
            reviewed_at = ?, admin_decision = ?, admin_notes = ?
        WHERE id = ?
    ''', (new_status, admin_person_id, admin_username, now, decision, admin_notes, appeal_id))
    conn.commit()
    conn.close()
    
    # Apply decision
    if decision == 'restore_privileges':
        restore_ban = appeal['appeal_type'] == APPEAL_TYPE_BAN
        restore_report = appeal['appeal_type'] == APPEAL_TYPE_REPORT_ABILITY
        restore_user_privileges(appeal['user_id'], restore_ban, restore_report,
                               admin_person_id, admin_username)
        
        # If ban appeal approved, also restore (un-remove) the reported content in Lemmy
        if restore_ban:
            _restore_reported_content(appeal['user_id'], admin_username)
            
            # 2-2: Ban appeal approved = CP was NOT real = original reporter filed false report
            # Find the original report and revoke the reporter's ability
            try:
                conn_appeal = get_db()
                cursor_appeal = conn_appeal.cursor()
                # Find the CP report where this user was the creator and mod confirmed CP
                cursor_appeal.execute('''
                    SELECT r.reporter_user_id, r.reporter_person_id, r.reporter_username
                    FROM cp_reports r
                    JOIN cp_reviews rv ON r.id = rv.report_id
                    WHERE r.creator_user_id = ? AND rv.decision = ?
                    ORDER BY rv.created_at DESC
                    LIMIT 1
                ''', (appeal['user_id'], REVIEW_DECISION_CP_CONFIRMED))
                original_report_info = cursor_appeal.fetchone()
                conn_appeal.close()
                
                if original_report_info:
                    orig_reporter_user_id = original_report_info['reporter_user_id']
                    orig_reporter_person_id = original_report_info['reporter_person_id']
                    orig_reporter_username = original_report_info['reporter_username']
                    
                    # Revoke the original reporter's report ability (false report confirmed by admin)
                    revoke_report_ability(
                        orig_reporter_user_id,
                        orig_reporter_person_id,
                        orig_reporter_username,
                        admin_person_id,
                        admin_username
                    )
                    logger.info(f"⛔ [APPEAL] Original reporter {orig_reporter_username} "
                                f"report ability REVOKED (admin approved appeal = CP was false report)")
            except Exception as e:
                logger.error(f"❌ [APPEAL] Error revoking original reporter's ability: {e}")
    
    elif decision == 'uphold_decision':
        # Appeal rejected: admin upholds the CP decision → purge content now
        if appeal['appeal_type'] == APPEAL_TYPE_BAN:
            _purge_reported_content(appeal['user_id'], admin_username)
    
    # Notify user
    create_notification(
        appeal['person_id'], appeal['username'], NOTIFICATION_APPEAL_REVIEWED,
        "Appeal Decision",
        f"Your appeal has been {new_status}. " + (admin_notes or "")
    )
    
    # Log audit
    log_audit('appeal_reviewed', admin_person_id, admin_username,
              appeal['user_id'], appeal['person_id'], appeal['username'],
              related_appeal_id=appeal_id, action_details={'decision': decision})
    
    logger.info(f"Appeal {appeal_id} reviewed by {admin_username}: {decision}")
    
    return get_appeal(appeal_id)


# ==========================================
# Notifications
# ==========================================

def create_notification(recipient_person_id: int, recipient_username: str,
                       notification_type: str, title: str, message: str,
                       related_report_id: Optional[str] = None,
                       related_appeal_id: Optional[str] = None):
    """Create a notification"""
    notification_id = str(uuid.uuid4())
    now = int(time.time())
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO cp_notifications
        (id, recipient_person_id, recipient_username, notification_type, title, message,
         related_report_id, related_appeal_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (notification_id, recipient_person_id, recipient_username, notification_type,
          title, message, related_report_id, related_appeal_id, now))
    conn.commit()
    conn.close()


def get_user_notifications(person_id: int, unread_only: bool = False, limit: int = 50) -> List[Dict]:
    """Get notifications for a user"""
    query = 'SELECT * FROM cp_notifications WHERE recipient_person_id = ?'
    params = [person_id]
    
    if unread_only:
        query += ' AND is_read = ?'
        params.append(False)
    
    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, tuple(params))
    results = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in results]


def mark_notification_read(notification_id: str):
    """Mark notification as read"""
    now = int(time.time())
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE cp_notifications SET is_read = ?, read_at = ? WHERE id = ?',
                  (True, now, notification_id))
    conn.commit()
    conn.close()


def notify_community_moderators(community_id: int, report_id: str, content_type: str, content_id: int):
    """Notify all moderators of a community about a CP report"""
    # TODO: Implement moderator lookup from Lemmy database
    # For now, this is a placeholder
    logger.info(f"Would notify moderators of community {community_id} about report {report_id}")


def notify_admins(report_id: Optional[str], content_type: str, content_id: int, message: str):
    """Notify admins about escalated CP reports or appeals"""
    # TODO: Implement admin lookup from Lemmy database
    # For now, this is a placeholder
    logger.info(f"Would notify admins about {content_type} {content_id}: {message}")


# ==========================================
# Background Tasks
# ==========================================

def check_expired_bans():
    """Check and auto-unban users whose ban period has expired"""
    now = int(time.time())
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Find expired bans
    cursor.execute('''
        SELECT user_id, person_id, username FROM user_cp_permissions
        WHERE is_banned = ? AND ban_end <= ?
    ''', (True, now))
    
    expired_users = cursor.fetchall()
    
    for user in expired_users:
        cursor.execute('''
            UPDATE user_cp_permissions
            SET is_banned = ?, ban_start = NULL, ban_end = NULL, updated_at = ?
            WHERE user_id = ?
        ''', (False, now, user['user_id']))
        
        # Also unban in Lemmy PostgreSQL
        _unban_user_in_lemmy(
            user['person_id'], user['username'], 
            reason="Auto-unban: ban period expired"
        )
        
        # Notify user
        create_notification(
            user['person_id'], user['username'], 'ban_expired',
            "Ban Lifted", "Your 3-month ban has expired. You can now post again."
        )
        
        # Log audit
        log_audit('ban_expired', None, 'system', user['user_id'], user['person_id'], user['username'])
        
        logger.info(f"Auto-unbanned user {user['username']} (ID: {user['user_id']}) in SQLite + Lemmy")
    
    conn.commit()
    conn.close()
    
    return len(expired_users)


def check_auto_delete_reports():
    """Auto-delete unreviewed admin-level CP cases after 1 week.
    
    After moderator confirms CP, report is escalated to admin with a 7-day window.
    If admin does not review within 7 days, this task permanently purges the content.
    """
    now = int(time.time())
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Find reports to auto-delete (admin-escalated, still pending or moderator_confirmed, past 7-day deadline)
    cursor.execute('''
        SELECT id, content_type, content_id, creator_username 
        FROM cp_reports
        WHERE escalation_level = ? AND status IN (?, ?) AND auto_delete_at IS NOT NULL AND auto_delete_at <= ?
    ''', (ESCALATION_ADMIN, REPORT_STATUS_PENDING, REPORT_STATUS_MODERATOR_CONFIRMED, now))
    
    reports_to_delete = cursor.fetchall()
    
    for report in reports_to_delete:
        cursor.execute('''
            UPDATE cp_reports
            SET status = ?, reviewed_at = ?, auto_delete_at = NULL
            WHERE id = ?
        ''', (REPORT_STATUS_AUTO_DELETED, now, report['id']))
        
        # Actually PURGE the content from Lemmy now
        try:
            from lemmy_integration import LemmyAPI
            import os
            
            lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
            lemmy_admin_username = os.environ.get('LEMMY_ADMIN_USER', 'admin')
            lemmy_admin_password = os.environ.get('LEMMY_ADMIN_PASS', '')
            
            if lemmy_admin_password:
                lemmy_api = LemmyAPI(lemmy_api_url)
                lemmy_api.set_admin_credentials(lemmy_admin_username, lemmy_admin_password)
                
                if lemmy_api.login_as_admin():
                    purge_reason = f"Auto-purge: admin did not review within 7 days"
                    success = False
                    
                    if report['content_type'] == 'post':
                        success = lemmy_api.purge_post(report['content_id'], reason=purge_reason)
                    elif report['content_type'] == 'comment':
                        success = lemmy_api.purge_comment(report['content_id'], reason=purge_reason)
                    
                    if success:
                        logger.info(f"✅ [AUTO-DELETE] Content {report['content_type']} #{report['content_id']} PURGED from Lemmy (7-day deadline passed)")
                    else:
                        logger.error(f"❌ [AUTO-DELETE] Failed to purge {report['content_type']} #{report['content_id']} from Lemmy")
                else:
                    logger.error(f"❌ [AUTO-DELETE] Failed to login as admin for auto-purge")
            else:
                logger.warning(f"⚠️  [AUTO-DELETE] No admin password - cannot purge from Lemmy")
        except Exception as e:
            logger.error(f"❌ [AUTO-DELETE] Error purging content: {e}")
        
        # Log audit
        log_audit('report_auto_deleted', None, 'system', None, None, None, report['id'],
                 action_details={'content_type': report['content_type'], 
                               'content_id': report['content_id']})
        
        logger.info(f"Auto-deleted unreviewed CP report {report['id']}")
    
    conn.commit()
    conn.close()
    
    return len(reports_to_delete)


def check_expired_report_ability_bans():
    """Check and auto-restore report ability for users whose restriction period has expired"""
    now = int(time.time())
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Add column if it doesn't exist (migration)
    try:
        cursor.execute('ALTER TABLE user_cp_permissions ADD COLUMN report_ability_revoked_at INTEGER')
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Find expired report ability bans
    cursor.execute('''
        SELECT user_id, person_id, username FROM user_cp_permissions
        WHERE can_report_cp = ? AND report_ability_revoked_at IS NOT NULL AND report_ability_revoked_at <= ?
    ''', (False, now))
    
    expired_users = cursor.fetchall()
    
    for user in expired_users:
        cursor.execute('''
            UPDATE user_cp_permissions
            SET can_report_cp = ?, report_ability_revoked_at = NULL, updated_at = ?
            WHERE user_id = ?
        ''', (True, now, user['user_id']))
        
        # Notify user
        create_notification(
            user['person_id'], user['username'], 'report_ability_restored',
            "Report Ability Restored", "Your ability to report CP content has been restored after 3 months."
        )
        
        # Log audit
        log_audit('report_ability_restored', None, 'system', user['user_id'], user['person_id'], user['username'])
        
        logger.info(f"✅ [AUTO RESTORE] User {user['username']} (ID: {user['user_id']}) report ability restored after 3 months")
    
    conn.commit()
    conn.close()
    
    return len(expired_users)


def run_cp_background_tasks():
    """Run all CP background tasks"""
    try:
        unbanned = check_expired_bans()
        deleted = check_auto_delete_reports()
        restored = check_expired_report_ability_bans()
        logger.info(f"CP background tasks complete: {unbanned} users unbanned, {deleted} reports auto-deleted, {restored} report abilities restored")
        return {'unbanned': unbanned, 'deleted': deleted, 'restored': restored}
    except Exception as e:
        logger.error(f"Error in CP background tasks: {e}")
        return {'error': str(e)}
