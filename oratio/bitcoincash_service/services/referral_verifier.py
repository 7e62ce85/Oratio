"""
Referral Link Verifier Service (Phase B + Phase C)

- 제출된 URL을 크롤링해서 oratio.space 백링크 존재 여부를 확인
- 제출 시 1차 자동 검증 (auto-approve / pending)
- 주기적 재검증 (approved 링크가 여전히 유효한지)
- referral_verification_log 테이블에 기록
- Phase C: approve 시 1년 Gold 멤버십 자동 부여 / revoke 시 멤버십 비활성화
"""
import re
import time
import uuid
import traceback
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from config import logger
import models

# ==================== Config ====================

REFERRAL_TARGET_DOMAIN = "oratio.space"
VERIFY_HTTP_TIMEOUT = 12          # seconds
REVERIFY_INTERVAL_DAYS = 90       # 3개월마다 재검증
GRACE_PERIOD_DAYS = 14            # 재검증 실패 후 유예 기간
TOTAL_FAIL_LIMIT = 3              # 승인 후 1년간 누적 실패 N회 → 즉시 revoke (유예 무시)

# 승인 직후 지수 백오프 재검증 스케줄 (초 단위)
# 12h → 1d → 2d → 4d → 8d → 16d → 32d → 64d
EARLY_BACKOFF_SCHEDULE = [
    0.5 * 86400,   # 12시간
    1   * 86400,   # 1일
    2   * 86400,   # 2일
    4   * 86400,   # 4일
    8   * 86400,   # 8일
    16  * 86400,   # 16일
    32  * 86400,   # 32일
    64  * 86400,   # 64일
]


# ==================== Core Verification ====================

def fetch_page(url: str, timeout: int = VERIFY_HTTP_TIMEOUT) -> tuple:
    """
    URL을 가져와서 (http_status, html_body) 를 반환.
    실패 시 (None, None) 반환.
    """
    try:
        req = Request(url, headers={
            "User-Agent": "oratio-referral-verifier/1.0 (+https://oratio.space)",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            data = resp.read(512_000)  # 최대 500KB만 읽음
            try:
                html = data.decode("utf-8")
            except Exception:
                html = data.decode("latin-1", errors="ignore")
            return status, html
    except HTTPError as e:
        return e.code, None
    except (URLError, OSError) as e:
        logger.warning(f"[ReferralVerifier] Fetch failed for {url}: {e}")
        return None, None
    except Exception as e:
        logger.warning(f"[ReferralVerifier] Unexpected fetch error for {url}: {e}")
        return None, None


def check_backlink(html: str, target_domain: str = REFERRAL_TARGET_DOMAIN) -> bool:
    """
    HTML에서 target_domain으로의 dofollow 링크가 있는지 확인.
    nofollow/ugc/sponsored rel 속성이 포함된 링크는 제외.
    """
    if not html:
        return False

    # <a ... href="https://oratio.space..." ... > 패턴
    anchor_pattern = re.compile(
        r'<a\s[^>]*href=["\']https?://(?:www\.)?' + re.escape(target_domain) + r'[/"\'\s?#][^>]*>',
        re.IGNORECASE | re.DOTALL
    )

    for match in anchor_pattern.finditer(html):
        tag = match.group(0)
        # nofollow / ugc / sponsored 체크
        rel_match = re.search(r'rel=["\']([^"\']*)["\']', tag, re.IGNORECASE)
        if rel_match:
            rel_value = rel_match.group(1).lower()
            if any(bad in rel_value for bad in ("nofollow", "ugc", "sponsored")):
                continue  # 이 앵커는 SEO 효과 없으므로 건너뜀
        # dofollow 링크 발견
        return True

    return False


def verify_link(url: str) -> dict:
    """
    URL을 크롤링해서 백링크 존재 여부를 검증.
    Returns: {
        "http_status": int | None,
        "link_found": bool,
        "notes": str
    }
    """
    status, html = fetch_page(url)

    if status is None:
        return {"http_status": None, "link_found": False, "notes": "fetch_error: connection failed"}

    if status >= 400:
        return {"http_status": status, "link_found": False, "notes": f"http_error: status {status}"}

    found = check_backlink(html)
    notes = "backlink_found" if found else "backlink_not_found"
    return {"http_status": status, "link_found": found, "notes": notes}


def log_verification(link_id: str, result: dict, conn=None):
    """referral_verification_log 테이블에 검증 결과 기록"""
    should_close = False
    if conn is None:
        conn = models.get_db_connection()
        should_close = True

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO referral_verification_log (link_id, checked_at, http_status, link_found, notes)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            link_id,
            int(time.time()),
            result.get("http_status"),
            1 if result.get("link_found") else 0,
            (result.get("notes") or "")[:2000]
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"[ReferralVerifier] Failed to log verification for {link_id}: {e}")
    finally:
        if should_close:
            conn.close()


# ==================== Fail Count & Ban Helpers ====================

def _count_verification_failures(link_id: str, conn=None) -> int:
    """
    특정 링크의 승인 이후 1년간 재검증 실패(link_found=FALSE) 누적 횟수.
    referral_verification_log 테이블 기준.
    """
    should_close = False
    if conn is None:
        conn = models.get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM referral_verification_log
            WHERE link_id = ? AND link_found = 0
        ''', (link_id,))
        return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"[ReferralVerifier] Failed to count failures for {link_id}: {e}")
        return 0
    finally:
        if should_close:
            conn.close()


def _revoke_for_strike(link_id: str, submitted_by: str, fail_count: int, conn=None):
    """
    누적 실패 횟수 초과(3-strike)로 인한 즉시 revoke.
    유예 기간을 무시하고 즉시 badge + membership 취소.
    """
    should_close = False
    if conn is None:
        conn = models.get_db_connection()
        should_close = True
    try:
        cursor = conn.cursor()
        reason = f"3-strike auto-revoked: {fail_count} verification failures"

        cursor.execute('''
            UPDATE referral_awards SET revoked = TRUE, revoke_reason = ?
            WHERE link_id = ? AND username = ? AND revoked = FALSE
        ''', (reason, link_id, submitted_by))

        cursor.execute('''
            UPDATE referral_links SET status = 'rejected', reject_reason = ?
            WHERE id = ?
        ''', (reason, link_id))

        conn.commit()

        _revoke_referral_membership(link_id, submitted_by, conn)
        logger.warning(f"[ReferralVerifier] 3-STRIKE REVOKE: {link_id} by {submitted_by} "
                       f"({fail_count} failures)")
    except Exception as e:
        logger.error(f"[ReferralVerifier] Strike revoke error for {link_id}: {e}")
    finally:
        if should_close:
            conn.close()


# ==================== Submit-time Auto-Verify ====================

def auto_verify_on_submit(link_id: str, url: str, submitted_by: str) -> dict:
    """
    제출 직후 자동 1차 검증.
    - 백링크 발견 → status='approved', verified=TRUE, badge award 생성
    - 백링크 미발견 → status='pending' 유지, admin 수동 리뷰 대기

    Returns: {"auto_approved": bool, "result": dict}
    """
    logger.info(f"[ReferralVerifier] Auto-verifying {url} for {submitted_by}")
    result = verify_link(url)

    conn = models.get_db_connection()
    try:
        # 로그 기록
        log_verification(link_id, result, conn=conn)

        cursor = conn.cursor()

        if result["link_found"]:
            now = int(time.time())

            # auto-approve
            cursor.execute('''
                UPDATE referral_links
                SET status = 'approved', verified = TRUE, last_verified_at = ?
                WHERE id = ?
            ''', (now, link_id))

            # badge award가 없으면 생성 (submit 시 이미 만들어졌을 수 있음)
            cursor.execute(
                'SELECT id, revoked FROM referral_awards WHERE link_id = ? AND username = ?',
                (link_id, submitted_by)
            )
            existing = cursor.fetchone()
            if existing:
                # revoked 상태면 복구
                if existing[1]:
                    cursor.execute(
                        'UPDATE referral_awards SET revoked = FALSE, revoke_reason = NULL WHERE id = ?',
                        (existing[0],)
                    )
            else:
                award_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO referral_awards (id, username, link_id, award_type, awarded_at, revoked)
                    VALUES (?, ?, ?, 'badge', ?, FALSE)
                ''', (award_id, submitted_by, link_id, now))

            conn.commit()
            logger.info(f"[ReferralVerifier] Auto-approved link {link_id} — backlink found")

            # ── Phase C: 1년 Gold 멤버십 자동 부여 ──
            _grant_referral_membership(link_id, submitted_by, conn)

            return {"auto_approved": True, "result": result}

        else:
            # pending 유지 — admin이 수동 리뷰
            conn.commit()
            logger.info(f"[ReferralVerifier] Link {link_id} stays pending — backlink not found")
            return {"auto_approved": False, "result": result}

    except Exception as e:
        logger.error(f"[ReferralVerifier] Auto-verify error for {link_id}: {e}")
        logger.error(traceback.format_exc())
        return {"auto_approved": False, "result": result}
    finally:
        conn.close()


# ==================== Early Backoff Re-verification ====================

def reverify_early_backoff():
    """
    승인 직후 90일 이내의 링크를 지수 백오프 간격으로 재검증.

    스케줄: 승인 후 12h → 1d → 2d → 4d → 8d → 16d → 32d → 64d
    - 각 간격 시점이 도래했는데 해당 시점 이후 검증 기록이 없으면 재검증 실행.
    - 64일 이후부터는 기존 90일 정기 재검증(reverify_approved_links)에 합류.
    - 실패 시 기존 유예 로직(14일)과 동일하게 처리.

    background_tasks.py에서 12시간마다 호출 (DB 기반 스케줄 — 컨테이너 재시작에 영향 없음).
    """
    now = int(time.time())
    max_backoff = EARLY_BACKOFF_SCHEDULE[-1]  # 64일
    grace_cutoff = now - (GRACE_PERIOD_DAYS * 86400)

    conn = models.get_db_connection()
    try:
        cursor = conn.cursor()

        # 대상: approved 상태 & 승인 시점이 64일 이내인 링크
        cursor.execute('''
            SELECT id, url, submitted_by, last_verified_at, verified, submitted_at
            FROM referral_links
            WHERE status = 'approved'
              AND last_verified_at IS NOT NULL
              AND last_verified_at > ?
        ''', (int(now - max_backoff - 86400),))
        # last_verified_at > (now - 65일) → 아직 초기 백오프 구간에 있을 수 있는 링크

        rows = cursor.fetchall()
        if not rows:
            return 0

        checked = 0

        for link_id, url, submitted_by, last_verified_at, currently_verified, submitted_at in rows:
            # 이 링크의 approved 시점 찾기 (last_verified_at의 최초 기록 = 승인 시점)
            # 좀 더 정확하게: referral_awards의 awarded_at 사용
            cursor.execute('''
                SELECT awarded_at FROM referral_awards
                WHERE link_id = ? AND award_type IN ('badge', 'membership')
                ORDER BY awarded_at ASC LIMIT 1
            ''', (link_id,))
            award_row = cursor.fetchone()
            if not award_row:
                continue
            approved_at = award_row[0]

            elapsed = now - approved_at
            if elapsed > max_backoff:
                # 64일 초과 → 정기 재검증 대상, 여기서는 스킵
                continue

            # 현재 경과 시간에 맞는 백오프 간격 찾기
            # 다음 검증 시점 계산: 경과 시간보다 작거나 같은 마지막 스케줄 항목
            next_check_after = 0
            for interval in EARLY_BACKOFF_SCHEDULE:
                if elapsed >= interval:
                    next_check_after = approved_at + interval
                else:
                    break

            if next_check_after == 0:
                continue

            # 이미 해당 시점 이후에 검증했으면 스킵
            if last_verified_at and last_verified_at >= next_check_after:
                continue

            # 검증 로그에서 해당 시점 이후 기록이 있는지도 확인 (안전장치)
            cursor.execute('''
                SELECT COUNT(*) FROM referral_verification_log
                WHERE link_id = ? AND checked_at >= ?
            ''', (link_id, next_check_after))
            if cursor.fetchone()[0] > 0:
                continue

            # ── 재검증 실행 ──
            logger.info(f"[ReferralVerifier] Early backoff re-verify: {link_id} (elapsed={elapsed/86400:.1f}d)")
            result = verify_link(url)
            log_verification(link_id, result, conn=conn)

            if result["link_found"]:
                cursor.execute('''
                    UPDATE referral_links SET verified = TRUE, last_verified_at = ?
                    WHERE id = ?
                ''', (now, link_id))
                conn.commit()
            else:
                # ── 3-strike 체크: 누적 실패 횟수가 한도 이상이면 즉시 revoke ──
                fail_count = _count_verification_failures(link_id, conn)
                if fail_count >= TOTAL_FAIL_LIMIT:
                    _revoke_for_strike(link_id, submitted_by, fail_count, conn)
                elif currently_verified:
                    # 첫 실패 → verified=FALSE (유예 시작)
                    cursor.execute('''
                        UPDATE referral_links SET verified = FALSE, last_verified_at = ?
                        WHERE id = ?
                    ''', (now, link_id))
                    conn.commit()
                    logger.warning(f"[ReferralVerifier] Early backoff: {link_id} failed (strike {fail_count}/{TOTAL_FAIL_LIMIT}) — grace period started")
                else:
                    # 이미 실패 상태 — 유예 초과 여부 확인
                    if last_verified_at and last_verified_at < grace_cutoff:
                        # 유예 초과 → revoke
                        cursor.execute('''
                            UPDATE referral_awards SET revoked = TRUE, revoke_reason = ?
                            WHERE link_id = ? AND username = ? AND revoked = FALSE
                        ''', ("Early re-verification failed: backlink removed", link_id, submitted_by))

                        cursor.execute('''
                            UPDATE referral_links SET status = 'rejected', reject_reason = ?
                            WHERE id = ?
                        ''', ("Backlink removed — early backoff revoked after grace period", link_id))

                        conn.commit()

                        _revoke_referral_membership(link_id, submitted_by, conn)
                        logger.warning(f"[ReferralVerifier] Early backoff: {link_id} revoked — grace expired")
                    else:
                        # 아직 유예 기간 내
                        cursor.execute('''
                            UPDATE referral_links SET last_verified_at = ?
                            WHERE id = ?
                        ''', (now, link_id))
                        conn.commit()

            checked += 1

        if checked:
            logger.info(f"[ReferralVerifier] Early backoff re-verification: {checked} links checked")
        return checked

    except Exception as e:
        logger.error(f"[ReferralVerifier] Early backoff error: {e}")
        logger.error(traceback.format_exc())
        return 0
    finally:
        conn.close()


# ==================== Periodic Re-verification ====================

def reverify_approved_links():
    """
    승인된 링크를 주기적으로 재검증.
    - last_verified_at이 REVERIFY_INTERVAL_DAYS보다 오래된 링크 대상
    - 백링크 사라지면 verified=FALSE 표시, 14일 유예
    - 유예 후에도 미복구 시 badge revoke

    background_tasks.py 의 run_background_tasks() 루프에서 호출됨 (DB 기반 스케줄).
    """
    cutoff = int(time.time()) - (REVERIFY_INTERVAL_DAYS * 86400)
    grace_cutoff = int(time.time()) - (GRACE_PERIOD_DAYS * 86400)

    conn = models.get_db_connection()
    try:
        cursor = conn.cursor()

        # 재검증 대상: approved 상태이고 마지막 검증이 cutoff 이전
        cursor.execute('''
            SELECT id, url, submitted_by, last_verified_at, verified
            FROM referral_links
            WHERE status = 'approved'
              AND (last_verified_at IS NULL OR last_verified_at < ?)
        ''', (cutoff,))

        rows = cursor.fetchall()
        if not rows:
            return 0

        logger.info(f"[ReferralVerifier] Re-verifying {len(rows)} approved links")
        checked = 0

        for link_id, url, submitted_by, last_verified_at, currently_verified in rows:
            result = verify_link(url)
            log_verification(link_id, result, conn=conn)
            now = int(time.time())

            if result["link_found"]:
                # 아직 살아있음 → verified 갱신
                cursor.execute('''
                    UPDATE referral_links SET verified = TRUE, last_verified_at = ?
                    WHERE id = ?
                ''', (now, link_id))
                conn.commit()
            else:
                # ── 3-strike 체크: 누적 실패 횟수가 한도 이상이면 즉시 revoke ──
                fail_count = _count_verification_failures(link_id, conn)
                if fail_count >= TOTAL_FAIL_LIMIT:
                    _revoke_for_strike(link_id, submitted_by, fail_count, conn)
                elif currently_verified:
                    # 처음 실패 → verified=FALSE 표시 (유예 기간 시작)
                    cursor.execute('''
                        UPDATE referral_links SET verified = FALSE, last_verified_at = ?
                        WHERE id = ?
                    ''', (now, link_id))
                    conn.commit()
                    logger.warning(f"[ReferralVerifier] Link {link_id} failed re-verify (strike {fail_count}/{TOTAL_FAIL_LIMIT}) — grace period started")
                else:
                    # 이미 verified=FALSE인데, 유예 기간 초과?
                    if last_verified_at and last_verified_at < grace_cutoff:
                        # 유예 초과 → badge revoke
                        cursor.execute('''
                            UPDATE referral_awards SET revoked = TRUE, revoke_reason = ?
                            WHERE link_id = ? AND username = ? AND revoked = FALSE
                        ''', ("Re-verification failed: backlink removed", link_id, submitted_by))

                        cursor.execute('''
                            UPDATE referral_links SET status = 'rejected', reject_reason = ?
                            WHERE id = ?
                        ''', ("Backlink removed — auto-revoked after grace period", link_id))

                        conn.commit()

                        # ── Phase C: 멤버십 비활성화 ──
                        _revoke_referral_membership(link_id, submitted_by, conn)

                        logger.warning(f"[ReferralVerifier] Link {link_id} revoked — grace period expired")
                    else:
                        # 아직 유예 기간 내
                        cursor.execute('''
                            UPDATE referral_links SET last_verified_at = ?
                            WHERE id = ?
                        ''', (now, link_id))
                        conn.commit()

            checked += 1

        logger.info(f"[ReferralVerifier] Re-verification complete: {checked} links checked")
        return checked

    except Exception as e:
        logger.error(f"[ReferralVerifier] Re-verification error: {e}")
        logger.error(traceback.format_exc())
        return 0
    finally:
        conn.close()


# ==================== Phase C: Membership Helpers ====================

REFERRAL_MEMBERSHIP_AMOUNT = 0.0  # 무료 부여 (referral 보상)

def _grant_referral_membership(link_id: str, username: str, conn=None):
    """
    Referral 승인 시 1년 Gold 멤버십을 자동 부여.
    - models.create_membership() 호출
    - referral_awards에 'membership' award 기록
    """
    try:
        # 멤버십 생성 (amount_paid=0, 무료 보상)
        success = models.create_membership(
            user_id=username,
            amount_paid=REFERRAL_MEMBERSHIP_AMOUNT,
            tx_hash=f"referral:{link_id}"
        )

        if not success:
            logger.error(f"[ReferralVerifier] Failed to create membership for {username}")
            return False

        # referral_awards에 membership award 기록
        should_close = False
        if conn is None:
            conn = models.get_db_connection()
            should_close = True

        try:
            now = int(time.time())
            expires_at = now + (365 * 24 * 60 * 60)  # 1년
            cursor = conn.cursor()

            # 이미 membership award가 있는지 확인
            cursor.execute(
                "SELECT id FROM referral_awards WHERE link_id = ? AND username = ? AND award_type = 'membership'",
                (link_id, username)
            )
            if not cursor.fetchone():
                award_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO referral_awards (id, username, link_id, award_type, awarded_at, expires_at, revoked)
                    VALUES (?, ?, ?, 'membership', ?, ?, FALSE)
                ''', (award_id, username, link_id, now, expires_at))
                conn.commit()

            logger.info(f"[ReferralVerifier] 🥇 Gold membership granted to {username} via referral {link_id}")
            return True
        finally:
            if should_close:
                conn.close()

    except Exception as e:
        logger.error(f"[ReferralVerifier] Membership grant error for {username}: {e}")
        logger.error(traceback.format_exc())
        return False


def _revoke_referral_membership(link_id: str, username: str, conn=None):
    """
    재검증 실패(유예 초과) 시 멤버십 비활성화.
    - models.deactivate_membership() 호출
    - referral_awards의 membership award를 revoked 처리
    """
    try:
        # 멤버십 비활성화
        models.deactivate_membership(username)

        # referral_awards 업데이트
        should_close = False
        if conn is None:
            conn = models.get_db_connection()
            should_close = True

        try:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE referral_awards
                SET revoked = TRUE, revoke_reason = ?
                WHERE link_id = ? AND username = ? AND award_type = 'membership' AND revoked = FALSE
            ''', ("Backlink removed — membership revoked", link_id, username))
            conn.commit()

            logger.info(f"[ReferralVerifier] 🥇 Gold membership revoked for {username} (referral {link_id})")
            return True
        finally:
            if should_close:
                conn.close()

    except Exception as e:
        logger.error(f"[ReferralVerifier] Membership revoke error for {username}: {e}")
        logger.error(traceback.format_exc())
        return False
