import threading
import time
import traceback
from config import (
    logger, ZERO_CONF_ENABLED, ZERO_CONF_DOUBLE_SPEND_CHECK, FORWARD_PAYMENTS
)
import models
from services.electron_cash import electron_cash
from services.payment import process_payment
from zero_conf_validator import get_validator
from services.membership_sync import setup_membership_sync
from services.cp_moderation import run_cp_background_tasks  # CP system
from services.referral_verifier import reverify_approved_links, reverify_early_backoff  # Referral Phase B

# Initialize membership sync service
membership_sync_service = None

# ==================== DB-based Task Scheduler ====================
# 컨테이너 재시작에도 유지되는 DB 기반 스케줄러

REFERRAL_REVERIFY_INTERVAL = 12 * 3600  # 12시간 (초)
REFERRAL_REVERIFY_TASK_NAME = "referral_reverify"


def _get_last_task_run(task_name: str) -> int:
    """DB에서 특정 작업의 마지막 실행 시각(unix timestamp) 조회. 없으면 0 반환."""
    try:
        conn = models.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT last_run_at FROM background_task_state WHERE task_name = ?",
            (task_name,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"[TaskScheduler] Failed to read last run for {task_name}: {e}")
        return 0


def _set_last_task_run(task_name: str, timestamp: int = None):
    """DB에 특정 작업의 마지막 실행 시각 기록."""
    if timestamp is None:
        timestamp = int(time.time())
    try:
        conn = models.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO background_task_state (task_name, last_run_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(task_name) DO UPDATE SET last_run_at = ?, updated_at = ?
        ''', (task_name, timestamp, timestamp, timestamp, timestamp))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[TaskScheduler] Failed to update last run for {task_name}: {e}")


def _is_task_due(task_name: str, interval_seconds: int) -> bool:
    """작업의 마지막 실행으로부터 interval_seconds 이상 경과했는지 확인."""
    last_run = _get_last_task_run(task_name)
    now = int(time.time())
    return (now - last_run) >= interval_seconds

def cleanup_expired_invoices():
    """만료된 인보이스 처리"""
    count = models.expire_pending_invoices()
    return count

def update_paid_invoices():
    """지불 확인된 인보이스의 상태 업데이트"""
    # 지불 확인된 인보이스 목록 조회
    paid_invoices = models.get_paid_invoices()
    
    for invoice_id, tx_hash in paid_invoices:
        # 모의 트랜잭션은 건너뛰기
        if tx_hash and not tx_hash.startswith("mock_tx_"):
            # 결제 처리 로직 실행
            process_payment(invoice_id)

def monitor_zero_conf_transactions():
    """
    Zero-Conf 트랜잭션 모니터링
    첫 번째 컨펌까지 이중지불 체크
    """
    if not ZERO_CONF_ENABLED or not ZERO_CONF_DOUBLE_SPEND_CHECK:
        return
    
    try:
        # completed 상태이지만 confirmations < 1인 인보이스 조회
        conn = models.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, tx_hash, payment_address, amount, created_at, confirmations
            FROM invoices
            WHERE status = 'completed' 
            AND confirmations < 1
            AND tx_hash IS NOT NULL
            AND tx_hash NOT LIKE 'mock_%'
            ORDER BY paid_at DESC
            LIMIT 100
        """)
        zero_conf_invoices = cursor.fetchall()
        conn.close()
        
        if not zero_conf_invoices:
            return
        
        logger.info(f"🔍 Zero-Conf 모니터링: {len(zero_conf_invoices)}개 트랜잭션 체크 중...")
        
        validator = get_validator(electron_cash)
        
        for invoice in zero_conf_invoices:
            invoice_id = invoice['id']
            tx_hash = invoice['tx_hash']
            
            try:
                # 트랜잭션 상태 재확인
                tx_details = electron_cash.call_method("gettransaction", [tx_hash])
                
                if not tx_details:
                    logger.warning(f"⚠️ 트랜잭션을 찾을 수 없음: {tx_hash} (인보이스: {invoice_id})")
                    # 트랜잭션이 사라졌으면 의심스러움 - 일단 로그만
                    continue
                
                confirmations = tx_details.get('confirmations', 0)
                
                # 확인 수 업데이트
                if confirmations != invoice['confirmations']:
                    models.update_invoice_confirmations(invoice_id, confirmations)
                    logger.info(f"✅ 확인 수 업데이트: {invoice_id} -> {confirmations} confirmations")
                
                # 여전히 0-conf이면 이중지불 재체크
                if confirmations == 0:
                    is_valid, msg, _ = validator.validate_transaction(
                        tx_hash,
                        invoice['amount'],
                        invoice['payment_address'],
                        invoice['created_at']
                    )
                    
                    if not is_valid:
                        logger.error(f"❌ Zero-Conf 이중지불 감지! 인보이스: {invoice_id}, 사유: {msg}")
                        # 이중지불 감지 시 처리 (크레딧 회수, 알림 등)
                        # TODO: 크레딧 회수 로직 추가
                        models.update_invoice_status(invoice_id, "double_spend_detected")
                        
            except Exception as e:
                logger.error(f"Zero-Conf 모니터링 오류 (인보이스 {invoice_id}): {str(e)}")
                
    except Exception as e:
        logger.error(f"Zero-Conf 모니터링 전체 오류: {str(e)}")
        logger.error(traceback.format_exc())

def check_pending_invoices():
    """대기 중인 인보이스 상태 확인"""
    # 대기 중인 인보이스 목록 조회
    pending_invoices = models.get_pending_invoices()
    
    for invoice_id in pending_invoices:
        process_payment(invoice_id)

def run_background_tasks():
    """백그라운드 작업 처리"""
    while True:
        try:
            # 만료된 인보이스 처리
            cleanup_expired_invoices()
            
            # 대기 중인 인보이스 상태 확인
            check_pending_invoices()
            
            # 지불 확인된 인보이스 업데이트
            update_paid_invoices()
            
            # Zero-Conf 트랜잭션 모니터링 (이중지불 체크)
            monitor_zero_conf_transactions()
            
            # 멤버십 만료 체크 (새로 추가)
            check_expired_memberships()
            
            # 업로드 쿼터 리셋 체크 (새로 추가)
            reset_expired_upload_quotas()
            
            # CP 시스템 백그라운드 작업 (auto-unban, auto-delete)
            run_cp_background_tasks()

            # ── Referral Phase B: 주기적 재검증 (DB 기반 12시간 간격) ──
            # 컨테이너 재시작에도 영향받지 않음: DB에 마지막 실행 시각 저장
            if _is_task_due(REFERRAL_REVERIFY_TASK_NAME, REFERRAL_REVERIFY_INTERVAL):
                logger.info("[Referral] 12h interval reached — starting re-verification cycle")
                _set_last_task_run(REFERRAL_REVERIFY_TASK_NAME)

                try:
                    # 승인 직후 지수 백오프 재검증 (12h~64d 구간)
                    early_checked = reverify_early_backoff()
                    if early_checked:
                        logger.info(f"[Referral] Early backoff re-verification done: {early_checked} links")
                except Exception as eb_err:
                    logger.error(f"[Referral] Early backoff re-verification error: {eb_err}")

                try:
                    # 정기 90일 재검증
                    checked = reverify_approved_links()
                    if checked:
                        logger.info(f"[Referral] Periodic re-verification done: {checked} links")
                except Exception as rv_err:
                    logger.error(f"[Referral] Re-verification error: {rv_err}")
            
            # 주기적으로 자금 전송 시도 (설정에 따라)
            if FORWARD_PAYMENTS:
                electron_cash.forward_to_payout_wallet()
                
        except Exception as e:
            logger.error(f"백그라운드 작업 오류: {str(e)}")
        
        # 15초마다 실행 (Zero-Conf를 위해 더 자주 체크)
        time.sleep(15)

def check_expired_memberships():
    """만료된 멤버십 확인 및 비활성화"""
    try:
        expired_count = models.check_and_expire_memberships()
        if expired_count > 0:
            logger.info(f"만료된 멤버십 {expired_count}개 비활성화됨")
    except Exception as e:
        logger.error(f"멤버십 만료 체크 중 오류: {str(e)}")

def reset_expired_upload_quotas():
    """만료된 업로드 쿼터 리셋"""
    try:
        from .upload_quota_service import UploadQuotaService
        from config import DB_PATH
        
        quota_service = UploadQuotaService(DB_PATH)
        
        # Get all active memberships
        conn = models.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id FROM user_memberships 
            WHERE is_active = TRUE
        """)
        active_users = cursor.fetchall()
        conn.close()
        
        reset_count = 0
        for user in active_users:
            user_id = user[0]
            if quota_service.reset_quota_if_expired(user_id):
                reset_count += 1
        
        if reset_count > 0:
            logger.info(f"✅ 업로드 쿼터 {reset_count}개 리셋됨")
    except Exception as e:
        logger.error(f"❌ 업로드 쿼터 리셋 중 오류: {str(e)}")

def start_background_tasks():
    """백그라운드 작업 시작"""
    global membership_sync_service
    
    # Initialize membership sync service
    try:
        membership_sync_service = setup_membership_sync()
        # Start periodic sync every 60 seconds
        membership_sync_service.start_periodic_sync(interval_seconds=60)
        logger.info("멤버십 동기화 서비스 시작됨 (PostgreSQL ↔ SQLite)")
    except Exception as e:
        logger.error(f"멤버십 동기화 서비스 시작 실패: {str(e)}")
        logger.error(traceback.format_exc())
    
    # 백그라운드 스레드 시작
    background_thread = threading.Thread(target=run_background_tasks)
    background_thread.daemon = True
    background_thread.start()
    
    logger.info("백그라운드 작업 시작됨")
    return background_thread
