"""
Advertisement API Routes
광고 시스템 REST API 엔드포인트
"""

from flask import Blueprint, jsonify, request
from flask_cors import CORS
from functools import wraps
from datetime import datetime

from config import logger, LEMMY_API_KEY
from services.ad_service import ad_service
from services.price_service import calculate_bch_amount
import models
import qrcode
from io import BytesIO
import base64
from services.electron_cash import electron_cash
from services.payment import process_payment

# Blueprint 생성
ads_bp = Blueprint('ads', __name__)
CORS(ads_bp)


# ============================================================
# Authentication Decorators
# ============================================================

def require_api_key(f):
    """API 키 인증 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != LEMMY_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function


def require_admin(f):
    """관리자 권한 확인 데코레이터 (JWT 기반)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # TODO: JWT에서 관리자 권한 확인 구현
        # 현재는 X-Admin-Username 헤더로 임시 처리
        admin_username = request.headers.get('X-Admin-Username')
        if not admin_username:
            return jsonify({"error": "Admin authorization required"}), 403
        kwargs['admin_username'] = admin_username
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# Public Endpoints (광고 표시용)
# ============================================================

@ads_bp.route('/api/ads/display', methods=['GET'])
def get_ad_to_display():
    """
    광고 표시 API (페이지 로드당 한 번 호출)
    
    Query Parameters:
        - community: 현재 커뮤니티 이름 (선택)
        - community_display_name: 현재 커뮤니티 표시 이름 (선택)
        - is_nsfw: NSFW 페이지 여부 (default: false)
        - page_url: 현재 페이지 URL (선택)
        - session_id: 페이지 로드 세션 ID (같은 세션에서 load_points 중복 증가 방지)
    
    Returns:
        - 선택된 광고 정보 (4개 위치별 이미지 포함) 또는 null
        - 응답에는 images.sidebar, images.post_top, images.post_bottom, images.feed_inline 포함
    """
    community = request.args.get('community')
    community_display_name = request.args.get('community_display_name')
    is_nsfw = request.args.get('is_nsfw', 'false').lower() == 'true'
    page_url = request.args.get('page_url', '')
    session_id = request.args.get('session_id')
    
    ad = ad_service.select_ad_to_display(
        community=community,
        community_display_name=community_display_name,
        is_nsfw=is_nsfw,
        page_url=page_url,
        session_id=session_id
    )
    
    if ad:
        return jsonify({"success": True, "ad": ad})
    else:
        return jsonify({"success": True, "ad": None})


@ads_bp.route('/api/ads/click', methods=['POST'])
def record_ad_click():
    """
    광고 클릭 기록 API
    
    Request Body:
        - impression_id: 노출 ID
    
    Returns:
        - success: bool
    """
    data = request.get_json() or {}
    impression_id = data.get('impression_id')
    
    if not impression_id:
        return jsonify({"success": False, "error": "Missing impression_id"}), 400
    
    result = ad_service.record_click(impression_id)
    return jsonify({"success": result})


@ads_bp.route('/api/ads/confirm', methods=['POST'])
def confirm_ad_impression():
    """
    Confirm impression with slot information. This allows the frontend to notify which slot was actually displayed.

    Request Body:
        - impression_id: str
        - ad_slot: str (e.g., sidebar, post_top, post_bottom, feed_inline)
    """
    data = request.get_json() or {}
    impression_id = data.get('impression_id')
    ad_slot = data.get('ad_slot')

    if not impression_id or not ad_slot:
        return jsonify({"success": False, "error": "Missing impression_id or ad_slot"}), 400

    # Optional: viewer info could be provided for analytics (not required)
    viewer_user = request.headers.get('X-Viewer-User')

    result = ad_service.update_impression_slot(impression_id, ad_slot, viewer_user_id=viewer_user)
    return jsonify({"success": result})


@ads_bp.route('/api/ads/stats/sections', methods=['GET'])
def get_ads_stats_sections():
    """
    Return impression counts grouped by ad_slot for the past N days (default 90 days).

    Query params:
      - days: int (optional)
    """
    days = int(request.args.get('days') or 90)
    stats = ad_service.get_impression_stats_by_slot(days)
    return jsonify({"success": True, "days": days, "by_slot": stats})


# ============================================================
# Advertiser Endpoints (광고주용)
# ============================================================

@ads_bp.route('/api/ads/credits/<username>', methods=['GET'])
@require_api_key
def get_ad_credits(username):
    """광고 크레딧 잔액 조회"""
    balance = ad_service.get_ad_credits(username)
    return jsonify({
        "success": True,
        "username": username,
        "credit_balance_usd": balance
    })


@ads_bp.route('/api/ads/credits/add', methods=['POST'])
@require_api_key
def add_ad_credits():
    """
    광고 크레딧 추가 (BCH 결제 완료 후 호출)
    
    Request Body:
        - username: 광고주 사용자명
        - amount_usd: 추가할 USD 금액
        - description: 설명 (선택)
    """
    data = request.get_json() or {}
    
    username = data.get('username')
    amount_usd = data.get('amount_usd')
    
    if not username or not amount_usd:
        return jsonify({"success": False, "error": "Missing username or amount_usd"}), 400
    
    try:
        amount_usd = float(amount_usd)
        if amount_usd <= 0:
            return jsonify({"success": False, "error": "Amount must be positive"}), 400
    except ValueError:
        return jsonify({"success": False, "error": "Invalid amount"}), 400
    
    result = ad_service.add_ad_credits(
        username=username,
        amount_usd=amount_usd,
        description=data.get('description', 'deposit')
    )
    
    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 400


@ads_bp.route('/api/ads/campaigns', methods=['POST'])
@require_api_key
def create_campaign():
    """
    새 광고 캠페인 생성
    
    Request Body:
        - advertiser_username: 광고주 사용자명
        - title: 광고 제목
        - link_url: 클릭 시 이동 URL
        - monthly_budget_usd: 월 예산 (최소 $10)
        - image_url: 이미지 URL (선택)
        - alt_text: 대체 텍스트 (선택)
        - target_communities: 타겟 커뮤니티 배열 (선택, null=전체)
        - target_regex: 타겟 정규식 (선택)
        - is_nsfw: NSFW 광고 여부 (default: false)
        - show_on_all: 전체 표시 여부 (default: true)
        - start_date: 시작일 Unix timestamp (선택)
        - end_date: 종료일 Unix timestamp (선택)
    """
    data = request.get_json() or {}
    result = ad_service.create_campaign(data)
    
    if result["success"]:
        return jsonify(result), 201
    else:
        return jsonify(result), 400


@ads_bp.route('/api/ads/campaigns/user/<username>', methods=['GET'])
@require_api_key
def get_user_campaigns(username):
    """광고주의 캠페인 목록 조회"""
    campaigns = ad_service.get_campaigns_by_advertiser(username)
    return jsonify({
        "success": True,
        "username": username,
        "campaigns": campaigns
    })


@ads_bp.route('/api/ads/campaigns/<campaign_id>', methods=['GET'])
@require_api_key
def get_campaign(campaign_id):
    """캠페인 상세 정보 조회"""
    campaign = ad_service.get_campaign(campaign_id)
    if campaign:
        return jsonify({"success": True, "campaign": campaign})
    else:
        return jsonify({"success": False, "error": "Campaign not found"}), 404


# ============================================================
# Admin Endpoints (관리자용)
# ============================================================

@ads_bp.route('/api/ads/admin/pending', methods=['GET'])
@require_api_key
@require_admin
def get_pending_campaigns(admin_username):
    """승인 대기 중인 캠페인 목록 (관리자용)"""
    campaigns = ad_service.get_pending_campaigns()
    return jsonify({
        "success": True,
        "pending_count": len(campaigns),
        "campaigns": campaigns
    })


@ads_bp.route('/api/ads/admin/active', methods=['GET'])
@require_api_key
@require_admin
def get_admin_active_campaigns(admin_username):
    """관리자용: 승인되어 현재 활성화된 캠페인 목록 조회"""
    campaigns = ad_service.get_all_active_campaigns()
    return jsonify({
        "success": True,
        "campaigns": campaigns,
        "count": len(campaigns)
    })


@ads_bp.route('/api/ads/admin/approve/<campaign_id>', methods=['POST'])
@require_api_key
@require_admin
def approve_campaign(campaign_id, admin_username):
    """캠페인 승인 (관리자용)"""
    result = ad_service.approve_campaign(campaign_id, admin_username)
    
    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 400


@ads_bp.route('/api/ads/admin/reject/<campaign_id>', methods=['POST'])
@require_api_key
@require_admin
def reject_campaign(campaign_id, admin_username):
    """
    캠페인 거부 (관리자용)
    
    Request Body:
        - reason: 거부 사유
    """
    data = request.get_json() or {}
    reason = data.get('reason', 'Policy violation')
    
    result = ad_service.reject_campaign(campaign_id, admin_username, reason)
    
    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 400


# ============================================================
# Total Budget (for probability preview)
# ============================================================

@ads_bp.route('/api/ads/total-budget', methods=['GET'])
def get_total_budget():
    """
    활성 광고의 총 예산 조회 (확률 미리보기용)
    
    프론트엔드에서 광고주가 예산 입력 시 예상 노출 확률 계산에 사용:
    예상 확률 = 내 예산 / (현재 총 예산 + 내 예산) × 100%
    """
    result = ad_service.get_total_active_budget()
    return jsonify(result)


# ============================================================
# Health Check
# ============================================================

@ads_bp.route('/api/ads/health', methods=['GET'])
def ads_health_check():
    """광고 시스템 상태 확인"""
    return jsonify({
        "status": "ok",
        "service": "advertisement-system",
        "timestamp": datetime.now().isoformat()
    })


# ============================================================
# Ad Credits BCH Payment Flow
# ============================================================

@ads_bp.route('/api/ads/credits/price', methods=['GET'])
def get_ad_credits_price():
    """
    Get current BCH price for a USD amount of ad credits.

    Query params:
      - amount_usd: float (required)
    """
    amount_usd = request.args.get('amount_usd', type=float)
    if not amount_usd or amount_usd <= 0:
        return jsonify({"success": False, "error": "amount_usd is required and must be positive"}), 400

    price_data = calculate_bch_amount(amount_usd)
    if not price_data:
        return jsonify({"success": False, "error": "Failed to get BCH price"}), 500

    return jsonify({"success": True, "price": price_data})


@ads_bp.route('/api/ads/credits/invoice', methods=['POST'])
@require_api_key
def create_ad_credits_invoice():
    """
    Create an invoice for purchasing ad credits.

    Request Body:
      - username: str
      - amount_usd: float (must be >= 10)
    """
    data = request.get_json() or {}
    username = data.get('username')
    amount_usd = data.get('amount_usd')

    if not username or not amount_usd:
        return jsonify({"success": False, "error": "Missing username or amount_usd"}), 400

    try:
        amount_usd = float(amount_usd)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid amount_usd"}), 400

    if amount_usd < 10:
        return jsonify({"success": False, "error": "Minimum ad credit purchase is $10 USD"}), 400

    price_data = calculate_bch_amount(amount_usd)
    if not price_data:
        return jsonify({"success": False, "error": "Failed to get BCH price"}), 500

    bch_amount = price_data["bch_amount"]

    # Generate payment address and create invoice
    try:
        payment_address = electron_cash.get_new_address()
    except Exception as e:
        logger.error(f"Failed to generate payment address: {e}")
        return jsonify({"success": False, "error": "Failed to generate payment address"}), 500

    # Create invoice in DB (user_id stored as username for ad_credits system)
    invoice_data = models.create_invoice(payment_address, bch_amount, username)
    invoice_id = invoice_data.get("invoice_id")

    # QR code generation
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr_uri = f"bitcoincash:{payment_address}?amount={bch_amount}"
    qr.add_data(qr_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf)
    qr_base64 = base64.b64encode(buf.getvalue()).decode()

    return jsonify({
        "success": True,
        "invoice_id": invoice_id,
        "payment_address": payment_address,
        "bch_amount": bch_amount,
        "usd_amount": amount_usd,
        "price_per_bch": price_data["price_per_bch"],
        "qr_code": qr_base64,
        "qr_uri": qr_uri
    })


@ads_bp.route('/api/ads/credits/check/<invoice_id>', methods=['GET'])
@require_api_key
def check_ad_credits_payment(invoice_id):
    """
    Check payment status for an ad credits invoice.
    On completed payment, automatically add credits to user's ad_credits.

    Returns:
      - success: bool
      - status: pending | completed
      - credits_added: bool (if completed and credits were added)
    """
    invoice = process_payment(invoice_id)
    if not invoice:
        return jsonify({"success": False, "error": "Invoice not found"}), 404

    status = invoice.get("status", "pending")
    credits_added = False

    if status == "completed":
        # Fetch the original invoice to get amount and username
        inv_record = models.get_invoice(invoice_id)
        if inv_record:
            username = inv_record.get("user_id")
            bch_amount = float(inv_record.get("amount", 0))
            # Calculate USD from BCH at time of creation (approx.)
            price_data = calculate_bch_amount(1)  # get current price per BCH
            if price_data and price_data.get("price_per_bch"):
                usd_amount = bch_amount * price_data["price_per_bch"]
            else:
                usd_amount = bch_amount * 480  # fallback

            # Add credits (idempotent via description check could be added)
            result = ad_service.add_ad_credits(username, usd_amount, description=f"BCH purchase {invoice_id}")
            if result.get("success"):
                credits_added = True
                logger.info(f"Ad credits added for {username}: ${usd_amount:.2f} via invoice {invoice_id}")

    return jsonify({
        "success": True,
        "status": status,
        "invoice_id": invoice_id,
        "credits_added": credits_added
    })


@ads_bp.route('/api/ads/credits/purchase', methods=['POST'])
@require_api_key
def purchase_ad_credits():
    """
    사용자의 BCH 크레딧으로 광고 크레딧 구매
    BCH credit → Ad credit 전환
    
    Request body:
        username: 사용자 이름
        usd_amount: 구매할 USD 금액
        
    Returns:
        success: 성공 여부
        credits_balance: 구매 후 광고 크레딧 잔액
        bch_deducted: 차감된 BCH 금액
    """
    try:
        data = request.get_json() or {}
        username = data.get('username')
        usd_amount = float(data.get('usd_amount', 0))
        
        if not username:
            return jsonify({"error": "Username required"}), 400
        if usd_amount <= 0:
            return jsonify({"error": "Invalid amount"}), 400
        if usd_amount > 1000:
            return jsonify({"error": "Maximum purchase amount is $1000"}), 400
        
        # BCH 가격 계산
        price_data = calculate_bch_amount(usd_amount)
        if not price_data or not price_data.get("bch_amount"):
            return jsonify({"error": "Failed to calculate BCH price"}), 500
        
        bch_amount = float(price_data["bch_amount"])
        
        # 사용자의 BCH 크레딧 잔액 확인 - models.get_user_credit_by_username returns float directly
        user_credit = models.get_user_credit_by_username(username)
        if not user_credit or user_credit == 0:
            return jsonify({
                "error": "No BCH credit found",
                "bch_required": bch_amount,
                "bch_balance": 0
            }), 400
        
        current_balance = float(user_credit)
        
        if current_balance < bch_amount:
            return jsonify({
                "error": "Insufficient BCH credit",
                "bch_required": bch_amount,
                "bch_balance": current_balance
            }), 400
        
        # BCH 크레딧 차감 (트랜잭션 처리)
        conn = models.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # BCH 크레딧 차감 - column name is credit_balance, user_id is username
            cursor.execute("""
                UPDATE user_credits 
                SET credit_balance = credit_balance - ?
                WHERE user_id = ? AND credit_balance >= ?
            """, (bch_amount, username, bch_amount))
            
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({"error": "Failed to deduct BCH credit (insufficient balance)"}), 400
            
            conn.commit()
            logger.info(f"BCH credit deducted: {username} - {bch_amount} BCH for ${usd_amount}")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error deducting BCH credit: {e}")
            return jsonify({"error": "Transaction failed"}), 500
        finally:
            conn.close()
        
        # 광고 크레딧 추가
        result = ad_service.add_ad_credits(
            username, 
            usd_amount, 
            description=f"Purchased with {bch_amount:.8f} BCH"
        )
        
        if not result.get("success"):
            # 광고 크레딧 추가 실패 시 BCH 환불
            try:
                conn = models.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE user_credits 
                    SET credit_balance = credit_balance + ?
                    WHERE user_id = ?
                """, (bch_amount, username))
                conn.commit()
                conn.close()
                logger.warning(f"BCH credit refunded due to ad credit failure: {username} - {bch_amount} BCH")
            except Exception as refund_error:
                logger.error(f"Failed to refund BCH: {refund_error}")
            
            return jsonify({"error": "Failed to add ad credits"}), 500
        
        return jsonify({
            "success": True,
            "credits_balance": result.get("credits_balance", 0),
            "bch_deducted": bch_amount,
            "usd_added": usd_amount,
            "message": f"Successfully purchased ${usd_amount:.2f} ad credits"
        })
        
    except Exception as e:
        logger.error(f"Error in purchase_ad_credits: {e}")
        return jsonify({"error": str(e)}), 500


@ads_bp.route('/api/ads/credits/balance/<username>', methods=['GET'])
@require_api_key
def get_user_balances(username):
    """
    사용자의 BCH 크레딧과 광고 크레딧 잔액 조회
    
    Returns:
        bch_balance: BCH 크레딧 잔액
        ad_credits: 광고 크레딧 잔액 (USD)
    """
    try:
        # BCH 크레딧 조회 - models.get_user_credit_by_username returns float directly
        user_credit = models.get_user_credit_by_username(username)
        bch_balance = float(user_credit) if user_credit else 0
        
        # 광고 크레딧 조회 - ad_service.get_ad_credits returns float directly
        ad_credits_data = ad_service.get_ad_credits(username)
        ad_balance = float(ad_credits_data) if ad_credits_data else 0
        
        # 현재 BCH 가격 조회
        price_data = calculate_bch_amount(1)
        bch_to_usd = price_data.get("price_per_bch", 480) if price_data else 480
        bch_balance_usd = bch_balance * bch_to_usd
        
        return jsonify({
            "success": True,
            "bch_balance": bch_balance,
            "bch_balance_usd": bch_balance_usd,
            "ad_credits": ad_balance,
            "bch_price_usd": bch_to_usd
        })
        
    except Exception as e:
        logger.error(f"Error getting user balances: {e}")
        return jsonify({"error": str(e)}), 500
