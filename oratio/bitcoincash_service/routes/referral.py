"""
Link Referral System API Routes
Phase A (MVP): Submit links, get status, admin approve/reject
Phase B: Auto-verify on submit + periodic re-verification
"""
from flask import Blueprint, jsonify, request
from flask_cors import CORS
from functools import wraps
import threading
import time
import uuid
import re
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs
from config import logger, LEMMY_API_KEY
import models
from services.referral_verifier import (
    auto_verify_on_submit, _grant_referral_membership, _revoke_referral_membership,
    _count_verification_failures, _revoke_for_strike,
    verify_link, log_verification,
    TOTAL_FAIL_LIMIT, EARLY_BACKOFF_SCHEDULE, GRACE_PERIOD_DAYS
)

# Blueprint
referral_bp = Blueprint('referral', __name__)
CORS(referral_bp)

# ==================== Config ====================

REFERRAL_ENABLED = True
REFERRAL_DOMAIN_LIMIT = 1           # 도메인당 최대 보상 횟수
REFERRAL_USER_LIMIT = 1             # 사용자당 최대 보상 횟수
REFERRAL_TARGET_DOMAIN = "oratio.space"

BLACKLISTED_DOMAINS = [
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "is.gd", "ow.ly",
    "oratio.space",  # 자체 도메인
]

BLACKLISTED_DOMAIN_PATTERNS = [
    r".*\.blogspot\.com$",
    r".*\.wordpress\.com$",
    r".*\.tumblr\.com$",
]

# ==================== Auth ====================

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != LEMMY_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function


def require_admin_key(f):
    """Admin-only endpoint (same API key but could be extended)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != LEMMY_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function


# ==================== URL Helpers ====================

def normalize_url(url: str) -> str:
    """URL 정규화: 소문자, www 제거, fragment 제거, trailing slash 제거"""
    try:
        parsed = urlparse(url.strip())

        # scheme 기본값
        scheme = (parsed.scheme or "https").lower()
        netloc = (parsed.netloc or "").lower()

        # www. 제거
        if netloc.startswith("www."):
            netloc = netloc[4:]

        # path trailing slash 제거
        path = parsed.path.rstrip("/") or ""

        # 쿼리 파라미터 정렬
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        sorted_query = urlencode(sorted(query_params.items()), doseq=True) if query_params else ""

        # fragment 제거
        normalized = urlunparse((scheme, netloc, path, "", sorted_query, ""))
        return normalized
    except Exception:
        return url.strip().lower()


def extract_domain(url: str) -> str:
    """URL에서 도메인 추출 (www. 제거)"""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = (parsed.netloc or parsed.path.split("/")[0]).lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def is_blacklisted(domain: str) -> bool:
    """도메인이 블랙리스트에 있는지 확인"""
    if domain in BLACKLISTED_DOMAINS:
        return True
    for pattern in BLACKLISTED_DOMAIN_PATTERNS:
        if re.match(pattern, domain):
            return True
    return False


def validate_url(url: str) -> tuple:
    """URL 유효성 검사. Returns (is_valid, error_message)"""
    if not url or not url.strip():
        return False, "URL is required"

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"

    if parsed.scheme not in ("http", "https"):
        return False, "URL must start with http:// or https://"

    domain = extract_domain(url)
    if not domain:
        return False, "Could not extract domain from URL"

    if is_blacklisted(domain):
        return False, f"Domain '{domain}' is not allowed"

    return True, ""


# ==================== API Endpoints ====================

@referral_bp.route('/api/referral/submit', methods=['POST'])
@require_api_key
def submit_referral():
    """
    사용자가 외부 링크 제출
    Body: { "username": "...", "url": "https://example.com/page-with-oratio-link" }
    """
    if not REFERRAL_ENABLED:
        return jsonify({"error": "Referral system is currently disabled"}), 503

    try:
        data = request.get_json()
        if not data or 'username' not in data or 'url' not in data:
            return jsonify({"error": "Missing username or url"}), 400

        username = data['username'].strip()
        raw_url = data['url'].strip()

        # URL 유효성 검사
        is_valid, error_msg = validate_url(raw_url)
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        normalized = normalize_url(raw_url)
        domain = extract_domain(raw_url)

        # ── 활성 멤버십 보유자 차단 ──
        # 이미 유료(또는 기존 referral) 멤버십이 활성 상태인 사용자는 제출 불가
        # 멤버십 만료 후에는 다시 제출 가능
        membership_status = models.get_membership_status(username)
        if membership_status.get('is_active', False):
            return jsonify({
                "error": "You already have an active membership. "
                         "The Link Referral Program is for users without a membership. "
                         "You may submit after your current membership expires."
            }), 409

        conn = models.get_db_connection()
        cursor = conn.cursor()

        # 사용자 제출 횟수 제한 확인
        # rejected 제외 (재제출 허용)
        # approved이지만 멤버십이 만료된 링크도 제외 (1년 후 재제출 허용)
        now_ts = int(time.time())
        cursor.execute('''
            SELECT COUNT(*) FROM referral_links rl
            WHERE rl.submitted_by = ? AND rl.status != 'rejected'
              AND NOT (
                rl.status = 'approved'
                AND EXISTS (
                  SELECT 1 FROM referral_awards ra
                  WHERE ra.link_id = rl.id AND ra.username = rl.submitted_by
                    AND ra.award_type = 'membership'
                    AND ra.expires_at IS NOT NULL AND ra.expires_at < ?
                )
              )
        ''', (username, now_ts))
        user_count = cursor.fetchone()[0]
        if user_count >= REFERRAL_USER_LIMIT:
            conn.close()
            return jsonify({"error": "You have already submitted a referral link"}), 409

        # 도메인 제한 확인 (rejected + 멤버십 만료 제외)
        cursor.execute('''
            SELECT COUNT(*) FROM referral_links rl
            WHERE rl.domain = ? AND rl.status != 'rejected'
              AND NOT (
                rl.status = 'approved'
                AND EXISTS (
                  SELECT 1 FROM referral_awards ra
                  WHERE ra.link_id = rl.id AND ra.username = rl.submitted_by
                    AND ra.award_type = 'membership'
                    AND ra.expires_at IS NOT NULL AND ra.expires_at < ?
                )
              )
        ''', (domain, now_ts))
        domain_count = cursor.fetchone()[0]
        if domain_count >= REFERRAL_DOMAIN_LIMIT:
            conn.close()
            return jsonify({"error": f"A referral link from domain '{domain}' has already been submitted"}), 409

        # URL 중복 확인 (rejected + 멤버십 만료 제외)
        cursor.execute('''
            SELECT rl.id FROM referral_links rl
            WHERE rl.normalized_url = ? AND rl.status != 'rejected'
              AND NOT (
                rl.status = 'approved'
                AND EXISTS (
                  SELECT 1 FROM referral_awards ra
                  WHERE ra.link_id = rl.id AND ra.username = rl.submitted_by
                    AND ra.award_type = 'membership'
                    AND ra.expires_at IS NOT NULL AND ra.expires_at < ?
                )
              )
        ''', (normalized, now_ts))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return jsonify({"error": "This URL has already been submitted"}), 409

        # 저장
        link_id = str(uuid.uuid4())
        now = int(time.time())

        cursor.execute('''
            INSERT INTO referral_links (id, url, normalized_url, domain, submitted_by, status, submitted_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
        ''', (link_id, raw_url, normalized, domain, username, now))

        # 뱃지 보상 즉시 생성 (pending 상태)
        award_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO referral_awards (id, username, link_id, award_type, awarded_at, revoked)
            VALUES (?, ?, ?, 'badge', ?, FALSE)
        ''', (award_id, username, link_id, now))

        conn.commit()
        conn.close()

        logger.info(f"[Referral] New submission by {username}: {domain} (link_id={link_id})")

        # ── Phase B: 백그라운드 자동 검증 ──
        # API 응답을 지연시키지 않기 위해 별도 스레드에서 실행
        def _bg_verify():
            try:
                vr = auto_verify_on_submit(link_id, raw_url, username)
                if vr["auto_approved"]:
                    logger.info(f"[Referral] Auto-approved {link_id} in background")
                else:
                    logger.info(f"[Referral] {link_id} stays pending — admin review needed")
            except Exception as ex:
                logger.error(f"[Referral] Background verify error: {ex}")

        threading.Thread(target=_bg_verify, daemon=True).start()

        return jsonify({
            "success": True,
            "message": "Link submitted successfully. Referral badge granted! Auto-verification in progress.",
            "link_id": link_id,
            "status": "pending"
        })

    except Exception as e:
        logger.error(f"[Referral] Submit error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@referral_bp.route('/api/referral/status/<username>', methods=['GET'])
@require_api_key
def get_referral_status(username):
    """사용자의 레퍼럴 상태 조회"""
    try:
        conn = models.get_db_connection()
        cursor = conn.cursor()

        # 제출한 링크 조회 (link 기준, 중복 없이)
        cursor.execute('''
            SELECT id, url, domain, status, verified, submitted_at, reject_reason
            FROM referral_links
            WHERE submitted_by = ?
            ORDER BY submitted_at DESC
        ''', (username,))

        link_rows = cursor.fetchall()

        if not link_rows:
            conn.close()
            return jsonify({
                "has_referral": False,
                "has_badge": False,
                "has_membership": False,
                "is_banned": False,
                "links": []
            })

        # badge 유무 확인 (별도 쿼리 — JOIN 중복 방지)
        cursor.execute('''
            SELECT COUNT(*) FROM referral_awards
            WHERE username = ? AND award_type = 'badge' AND revoked = FALSE
        ''', (username,))
        has_badge = cursor.fetchone()[0] > 0

        # membership 유무 확인
        cursor.execute('''
            SELECT COUNT(*) FROM referral_awards
            WHERE username = ? AND award_type = 'membership' AND revoked = FALSE
        ''', (username,))
        has_membership = cursor.fetchone()[0] > 0

        links = []
        now_ts = int(time.time())
        for row in link_rows:
            link_id, url, domain, status, verified, submitted_at, reject_reason = row
            link_data = {
                "link_id": link_id,
                "url": url,
                "domain": domain,
                "status": status,
                "verified": bool(verified),
                "submitted_at": submitted_at,
                "reject_reason": reject_reason,
            }

            # rejected (3-strike/auto-revoked) 링크에도 상세 정보 추가
            if status == 'rejected' and reject_reason and ('3-strike' in reject_reason or 'auto-revoked' in reject_reason or 'Backlink removed' in reject_reason):
                fail_count = _count_verification_failures(link_id, conn)
                link_data["fail_count"] = fail_count
                link_data["fail_limit"] = TOTAL_FAIL_LIMIT
                link_data["grace_period_days"] = GRACE_PERIOD_DAYS

                # 마지막 검증 로그 가져오기
                cursor.execute('''
                    SELECT datetime(checked_at, 'unixepoch'), http_status, link_found, notes
                    FROM referral_verification_log
                    WHERE link_id = ?
                    ORDER BY checked_at DESC LIMIT 5
                ''', (link_id,))
                recent_logs = cursor.fetchall()
                link_data["recent_checks"] = [
                    {"checked_at": r[0], "http_status": r[1], "link_found": bool(r[2]), "notes": r[3]}
                    for r in recent_logs
                ]

            # approved 상태인 링크에 재검증 상세 정보 추가
            if status == 'approved':
                fail_count = _count_verification_failures(link_id, conn)
                link_data["fail_count"] = fail_count
                link_data["fail_limit"] = TOTAL_FAIL_LIMIT
                link_data["grace_period_days"] = GRACE_PERIOD_DAYS

                # 실제 다음 background task 실행 시점 계산
                # background_task_state에서 last_run_at + 12h = 다음 실행 시점
                cursor.execute('''
                    SELECT last_run_at FROM background_task_state
                    WHERE task_name = 'referral_reverify'
                ''')
                task_row = cursor.fetchone()
                next_task_run = (task_row[0] + 12 * 3600) if task_row else now_ts

                # 백오프 스케줄에서 다음 체크 가능 시점 계산
                cursor.execute('''
                    SELECT awarded_at FROM referral_awards
                    WHERE link_id = ? AND award_type IN ('badge', 'membership')
                    ORDER BY awarded_at ASC LIMIT 1
                ''', (link_id,))
                award_row = cursor.fetchone()
                if award_row:
                    approved_at = award_row[0]
                    elapsed = now_ts - approved_at

                    # 다음 백오프 체크 가능 시점
                    next_backoff_at = None
                    for interval in EARLY_BACKOFF_SCHEDULE:
                        check_time = approved_at + int(interval)
                        if check_time > now_ts:
                            next_backoff_at = check_time
                            break

                    if next_backoff_at:
                        # 실제 재검증 = max(다음 백오프 시점, 다음 task 실행 시점)
                        actual_next = max(next_backoff_at, next_task_run)
                        link_data["next_check_at"] = actual_next
                        link_data["next_check_in_hours"] = round(max(0, (actual_next - now_ts)) / 3600, 1)
                    elif next_task_run > now_ts:
                        # 64일 이후이지만 아직 체크 예정이면 task 실행 시점 사용
                        link_data["next_check_at"] = next_task_run
                        link_data["next_check_in_hours"] = round((next_task_run - now_ts) / 3600, 1)
                    else:
                        # 90일 정기 재검증 대상
                        link_data["next_check_at"] = None
                        link_data["next_check_in_hours"] = None

            links.append(link_data)

        conn.close()

        return jsonify({
            "has_referral": True,
            "has_badge": has_badge,
            "has_membership": has_membership,
            "is_banned": False,
            "links": links
        })

    except Exception as e:
        logger.error(f"[Referral] Status error for {username}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@referral_bp.route('/api/referral/check/<username>', methods=['GET'])
@require_api_key
def check_referral_badge(username):
    """
    간단한 뱃지 유무 체크 (프론트엔드 캐시용)
    Returns: { "has_badge": true/false }
    """
    try:
        conn = models.get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT COUNT(*) FROM referral_awards
            WHERE username = ? AND award_type = 'badge' AND revoked = FALSE
        ''', (username,))

        count = cursor.fetchone()[0]
        conn.close()

        return jsonify({"has_badge": count > 0})

    except Exception as e:
        logger.error(f"[Referral] Check error for {username}: {str(e)}")
        return jsonify({"has_badge": False})


# ==================== Admin Endpoints ====================

@referral_bp.route('/api/referral/list', methods=['GET'])
@require_admin_key
def list_referrals():
    """관리자: 전체 제출 목록 조회 (필터: status)"""
    try:
        status_filter = request.args.get('status', None)
        limit = min(int(request.args.get('limit', 50)), 200)
        offset = int(request.args.get('offset', 0))

        conn = models.get_db_connection()
        cursor = conn.cursor()

        if status_filter:
            cursor.execute('''
                SELECT rl.id, rl.url, rl.domain, rl.submitted_by, rl.status,
                       rl.verified, rl.submitted_at, rl.reject_reason
                FROM referral_links rl
                WHERE rl.status = ?
                ORDER BY rl.submitted_at DESC
                LIMIT ? OFFSET ?
            ''', (status_filter, limit, offset))
        else:
            cursor.execute('''
                SELECT rl.id, rl.url, rl.domain, rl.submitted_by, rl.status,
                       rl.verified, rl.submitted_at, rl.reject_reason
                FROM referral_links rl
                ORDER BY rl.submitted_at DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))

        rows = cursor.fetchall()

        # 총 개수
        if status_filter:
            cursor.execute('SELECT COUNT(*) FROM referral_links WHERE status = ?', (status_filter,))
        else:
            cursor.execute('SELECT COUNT(*) FROM referral_links')
        total = cursor.fetchone()[0]

        conn.close()

        links = []
        for row in rows:
            link_id, url, domain, submitted_by, status, verified, submitted_at, reject_reason = row
            links.append({
                "link_id": link_id,
                "url": url,
                "domain": domain,
                "submitted_by": submitted_by,
                "status": status,
                "verified": bool(verified),
                "submitted_at": submitted_at,
                "reject_reason": reject_reason
            })

        return jsonify({
            "links": links,
            "total": total,
            "limit": limit,
            "offset": offset
        })

    except Exception as e:
        logger.error(f"[Referral] List error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@referral_bp.route('/api/referral/approve/<link_id>', methods=['POST'])
@require_admin_key
def approve_referral(link_id):
    """관리자: 레퍼럴 링크 승인"""
    try:
        conn = models.get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT id, submitted_by, status FROM referral_links WHERE id = ?', (link_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "Link not found"}), 404

        _, submitted_by, current_status = row

        if current_status == 'approved':
            conn.close()
            return jsonify({"message": "Already approved"}), 200

        now = int(time.time())

        # 상태 변경
        cursor.execute('''
            UPDATE referral_links SET status = 'approved', verified = TRUE, last_verified_at = ?
            WHERE id = ?
        ''', (now, link_id))

        # 기존 badge award가 없으면 생성
        cursor.execute(
            'SELECT id FROM referral_awards WHERE link_id = ? AND username = ?',
            (link_id, submitted_by)
        )
        if not cursor.fetchone():
            award_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO referral_awards (id, username, link_id, award_type, awarded_at, revoked)
                VALUES (?, ?, ?, 'badge', ?, FALSE)
            ''', (award_id, submitted_by, link_id, now))

        conn.commit()
        conn.close()

        # ── Phase C: 1년 Gold 멤버십 자동 부여 ──
        _grant_referral_membership(link_id, submitted_by)

        logger.info(f"[Referral] Approved link {link_id} by {submitted_by}")
        return jsonify({"success": True, "message": "Referral approved — Gold membership granted"})

    except Exception as e:
        logger.error(f"[Referral] Approve error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@referral_bp.route('/api/referral/reject/<link_id>', methods=['POST'])
@require_admin_key
def reject_referral(link_id):
    """관리자: 레퍼럴 링크 거부"""
    try:
        data = request.get_json() or {}
        reason = data.get('reason', '')

        conn = models.get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT id, submitted_by FROM referral_links WHERE id = ?', (link_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "Link not found"}), 404

        _, submitted_by = row
        now = int(time.time())

        # 상태 변경
        cursor.execute('''
            UPDATE referral_links SET status = 'rejected', reject_reason = ?
            WHERE id = ?
        ''', (reason, link_id))

        # 뱃지 취소
        cursor.execute('''
            UPDATE referral_awards SET revoked = TRUE, revoke_reason = ?
            WHERE link_id = ? AND username = ?
        ''', (reason or 'Referral rejected', link_id, submitted_by))

        conn.commit()
        conn.close()

        # ── Phase C: 멤버십도 비활성화 ──
        _revoke_referral_membership(link_id, submitted_by)

        logger.info(f"[Referral] Rejected link {link_id} (reason: {reason})")
        return jsonify({"success": True, "message": "Referral rejected — membership revoked"})

    except Exception as e:
        logger.error(f"[Referral] Reject error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


# ==================== Phase B: Verification Endpoints ====================

@referral_bp.route('/api/referral/verify/<link_id>', methods=['POST'])
@require_admin_key
def manual_verify_referral(link_id):
    """관리자: 특정 링크 수동 재검증 트리거 (3-strike 포함)"""
    try:
        conn = models.get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT id, url, submitted_by, status, verified FROM referral_links WHERE id = ?', (link_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "Link not found"}), 404

        _, url, submitted_by, status, currently_verified = row

        # pending 상태 링크는 기존 auto_verify_on_submit 사용
        if status != 'approved':
            conn.close()
            result = auto_verify_on_submit(link_id, url, submitted_by)
            return jsonify({
                "success": True,
                "auto_approved": result["auto_approved"],
                "verification": result["result"],
                "message": "Auto-approved" if result["auto_approved"] else "Backlink not found — still pending"
            })

        # ── approved 링크: 3-strike 포함 재검증 ──
        result = verify_link(url)
        log_verification(link_id, result, conn=conn)
        now = int(time.time())

        if result["link_found"]:
            cursor.execute('''
                UPDATE referral_links SET verified = TRUE, last_verified_at = ?
                WHERE id = ?
            ''', (now, link_id))
            conn.commit()
            conn.close()
            return jsonify({
                "success": True,
                "verified": True,
                "verification": result,
                "message": "Backlink found — link verified successfully"
            })
        else:
            # 실패 → 3-strike 체크
            fail_count = _count_verification_failures(link_id, conn)
            if fail_count >= TOTAL_FAIL_LIMIT:
                _revoke_for_strike(link_id, submitted_by, fail_count, conn)
                conn.close()
                return jsonify({
                    "success": True,
                    "verified": False,
                    "verification": result,
                    "revoked": True,
                    "message": f"3-strike auto-revoked: {fail_count} total failures — badge and membership revoked"
                })
            elif currently_verified:
                # 첫 실패 → verified=FALSE (유예 시작)
                cursor.execute('''
                    UPDATE referral_links SET verified = FALSE, last_verified_at = ?
                    WHERE id = ?
                ''', (now, link_id))
                conn.commit()
                conn.close()
                return jsonify({
                    "success": True,
                    "verified": False,
                    "verification": result,
                    "message": f"Backlink not found — grace period started (strike {fail_count}/{TOTAL_FAIL_LIMIT})"
                })
            else:
                # 이미 유예 상태
                cursor.execute('''
                    UPDATE referral_links SET last_verified_at = ?
                    WHERE id = ?
                ''', (now, link_id))
                conn.commit()
                conn.close()
                return jsonify({
                    "success": True,
                    "verified": False,
                    "verification": result,
                    "message": f"Backlink still not found — grace period continues (strike {fail_count}/{TOTAL_FAIL_LIMIT})"
                })

    except Exception as e:
        logger.error(f"[Referral] Manual verify error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


# ==================== Link Replace (User) ====================

@referral_bp.route('/api/referral/replace/<link_id>', methods=['POST'])
@require_api_key
def replace_referral_link(link_id):
    """
    유저: 유예 상태(approved + verified=FALSE)인 링크의 URL을 교체하고 즉시 재검증.
    - 백링크가 발견되면 verified=TRUE로 복구 → 멤버십 유지
    - 백링크가 없으면 verified=FALSE 유지 → 유예 기간 계속
    Body: { "username": "...", "url": "https://new-site.com/page-with-link" }
    """
    if not REFERRAL_ENABLED:
        return jsonify({"error": "Referral system is currently disabled"}), 503

    try:
        data = request.get_json()
        if not data or 'username' not in data or 'url' not in data:
            return jsonify({"error": "Missing username or url"}), 400

        username = data['username'].strip()
        new_url = data['url'].strip()

        # URL 유효성 검사
        is_valid, error_msg = validate_url(new_url)
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        new_normalized = normalize_url(new_url)
        new_domain = extract_domain(new_url)

        # 기존 링크 조회 + 권한 확인
        conn = models.get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT id, url, submitted_by, status, verified FROM referral_links WHERE id = ?',
            (link_id,)
        )
        row = cursor.fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "Link not found"}), 404

        _, old_url, submitted_by, status, verified = row

        # 본인 링크만 교체 가능
        if submitted_by != username:
            conn.close()
            return jsonify({"error": "You can only replace your own link"}), 403

        # approved + verified=FALSE (유예 상태)에서만 교체 가능
        if status != 'approved' or verified:
            conn.close()
            return jsonify({
                "error": "Link replacement is only available when re-verification has failed "
                         "(approved but backlink not found)."
            }), 409

        # URL이 동일하면 그냥 재검증만 실행
        old_normalized = normalize_url(old_url)
        url_changed = (new_normalized != old_normalized)

        if url_changed:
            # 새 URL 중복 확인 (다른 사용자가 이미 사용 중인지)
            cursor.execute('''
                SELECT id FROM referral_links
                WHERE normalized_url = ? AND id != ? AND status != 'rejected'
            ''', (new_normalized, link_id))
            if cursor.fetchone():
                conn.close()
                return jsonify({"error": "This URL has already been submitted by another user"}), 409

            # URL 업데이트
            cursor.execute('''
                UPDATE referral_links SET url = ?, normalized_url = ?, domain = ?
                WHERE id = ?
            ''', (new_url, new_normalized, new_domain, link_id))
            conn.commit()

            logger.info(f"[Referral] Link {link_id} URL replaced by {username}: {new_domain}")

        conn.close()

        # 즉시 재검증 실행
        result = verify_link(new_url)

        now = int(time.time())
        conn2 = models.get_db_connection()
        log_verification(link_id, result, conn=conn2)

        if result["link_found"]:
            # 백링크 발견 → verified=TRUE 복구 (멤버십 유지!)
            cursor2 = conn2.cursor()
            cursor2.execute('''
                UPDATE referral_links SET verified = TRUE, last_verified_at = ?
                WHERE id = ?
            ''', (now, link_id))
            conn2.commit()
            conn2.close()

            logger.info(f"[Referral] Link {link_id} re-verified successfully — membership preserved")
            return jsonify({
                "success": True,
                "verified": True,
                "message": "Backlink verified! Your referral badge and membership are preserved."
            })
        else:
            # 백링크 없음 → 3-strike 체크
            fail_count = _count_verification_failures(link_id, conn2)
            if fail_count >= TOTAL_FAIL_LIMIT:
                _revoke_for_strike(link_id, username, fail_count, conn2)
                conn2.close()
                logger.warning(f"[Referral] Link {link_id} replacement 3-strike revoked ({fail_count} failures)")
                return jsonify({
                    "success": True,
                    "verified": False,
                    "revoked": True,
                    "message": f"Backlink not found. Your referral has been revoked due to {fail_count} total verification failures (3-strike rule)."
                })

            # 아직 3-strike 아님 → verified=FALSE 유지, last_verified_at 갱신
            cursor2 = conn2.cursor()
            cursor2.execute('''
                UPDATE referral_links SET last_verified_at = ?
                WHERE id = ?
            ''', (now, link_id))
            conn2.commit()
            conn2.close()

            logger.warning(f"[Referral] Link {link_id} replacement re-verify failed — strike {fail_count}/{TOTAL_FAIL_LIMIT}")
            return jsonify({
                "success": True,
                "verified": False,
                "message": f"Backlink not found on the new URL (strike {fail_count}/{TOTAL_FAIL_LIMIT}). "
                           "The grace period continues — please ensure a visible dofollow link to oratio.space is present."
            })

    except Exception as e:
        logger.error(f"[Referral] Replace error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

