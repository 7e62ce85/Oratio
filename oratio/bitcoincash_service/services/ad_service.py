"""
Advertisement Service
광고 선택, 노출, 크레딧 관리 핵심 로직
"""

import sqlite3
import time
import uuid
import random
import re
import json
from typing import Optional, Dict, List, Any
from config import DB_PATH, logger

# Post ID → Community 캐시 (성능 최적화)
# TTL 1시간, 최대 1000개 항목
_post_community_cache: Dict[int, Dict] = {}
_post_community_cache_time: Dict[int, float] = {}
_POST_CACHE_TTL = 3600  # 1시간
_POST_CACHE_MAX = 1000

# Post ID → Content 캐시 (정규식 매칭용)
# TTL 1시간, 최대 1000개 항목
_post_content_cache: Dict[int, str] = {}
_post_content_cache_time: Dict[int, float] = {}


def _parse_post_id_from_url(page_url: str) -> Optional[int]:
    """
    URL에서 post ID 추출
    예: https://oratio.space/post/146 → 146
        /post/55 → 55
    """
    if not page_url:
        return None
    match = re.search(r'/post/(\d+)', page_url)
    if match:
        return int(match.group(1))
    return None


def _get_community_by_post_id(post_id: int) -> Optional[Dict[str, str]]:
    """
    Post ID로 community 정보 조회 (캐시 사용)
    Returns: {"name": "banmal", "title": "반말"} 또는 None
    """
    global _post_community_cache, _post_community_cache_time
    
    now = time.time()
    
    # 캐시 히트 체크
    if post_id in _post_community_cache:
        cache_time = _post_community_cache_time.get(post_id, 0)
        if now - cache_time < _POST_CACHE_TTL:
            return _post_community_cache[post_id]
    
    # 캐시 미스 - Lemmy API 호출
    try:
        from lemmy_integration import LemmyAPI
        import os
        
        # Lemmy API 인스턴스 생성
        lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
        lemmy_api = LemmyAPI(lemmy_api_url)
        
        community_info = lemmy_api.get_community_by_post_id(post_id)
        
        if community_info:
            # 캐시 저장
            if len(_post_community_cache) >= _POST_CACHE_MAX:
                # 가장 오래된 항목 삭제
                oldest_key = min(_post_community_cache_time, key=_post_community_cache_time.get)
                del _post_community_cache[oldest_key]
                del _post_community_cache_time[oldest_key]
            
            _post_community_cache[post_id] = community_info
            _post_community_cache_time[post_id] = now
            logger.info(f"[AdService] Post {post_id} → community '{community_info.get('name')}' (cached)")
            return community_info
    except Exception as e:
        logger.warning(f"[AdService] Failed to get community for post {post_id}: {e}")
    
    return None


def _get_post_content_by_id(post_id: int) -> Optional[str]:
    """
    Post ID로 게시글 콘텐츠 조회 (정규식 매칭용, 캐시 사용)
    Returns: "제목 본문 URL" 형태의 문자열 또는 None
    """
    global _post_content_cache, _post_content_cache_time
    
    now = time.time()
    
    # 캐시 히트 체크
    if post_id in _post_content_cache:
        cache_time = _post_content_cache_time.get(post_id, 0)
        if now - cache_time < _POST_CACHE_TTL:
            return _post_content_cache[post_id]
    
    # 캐시 미스 - Lemmy API 호출
    try:
        from lemmy_integration import LemmyAPI
        import os
        
        # Lemmy API 인스턴스 생성
        lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
        lemmy_api = LemmyAPI(lemmy_api_url)
        
        post_data = lemmy_api.get_post(post_id)
        
        if post_data and "post_view" in post_data:
            post = post_data["post_view"].get("post", {})
            # 제목 + 본문 + URL 결합 (정규식 매칭 대상)
            title = post.get("name", "")
            body = post.get("body", "") or ""
            url = post.get("url", "") or ""
            
            content = f"{title} {body} {url}".strip()
            
            if content:
                # 캐시 저장
                if len(_post_content_cache) >= _POST_CACHE_MAX:
                    # 가장 오래된 항목 삭제
                    oldest_key = min(_post_content_cache_time, key=_post_content_cache_time.get)
                    del _post_content_cache[oldest_key]
                    del _post_content_cache_time[oldest_key]
                
                _post_content_cache[post_id] = content
                _post_content_cache_time[post_id] = now
                logger.info(f"[AdService] Post {post_id} content cached (len={len(content)})")
                return content
    except Exception as e:
        logger.warning(f"[AdService] Failed to get content for post {post_id}: {e}")
    
    return None


class AdService:
    """광고 시스템 핵심 서비스"""
    
    def __init__(self):
        # 페이지 로드당 load_points 중복 증가 방지용 캐시
        # key: campaign_id, value: last_increment_timestamp
        self._load_point_cache: Dict[str, float] = {}
        self._cache_ttl = 5  # 5초 내 같은 광고는 load_points 증가 안 함
    
    # ============================================================
    # Database Helpers
    # ============================================================
    
    def get_db_connection(self):
        """데이터베이스 연결 생성"""
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_config(self) -> Dict[str, Any]:
        """광고 시스템 설정 조회"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM ad_config 
            WHERE is_active = TRUE 
            ORDER BY effective_from DESC 
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        # 기본값 (TEST MODE: minimum_budget_usd 1.0으로 낮춤)
        return {
            "baseline_budget_usd": 100.0,
            "minimum_budget_usd": 1.0,
            "cost_per_impression_usd": 0.001,
            "cost_per_click_usd": 0.01,
            "max_regex_length": 500
        }
    
    # ============================================================
    # Ad Credits Management
    # ============================================================
    
    def get_ad_credits(self, username: str) -> float:
        """광고 크레딧 잔액 조회"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT credit_balance_usd FROM ad_credits WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        conn.close()
        return row["credit_balance_usd"] if row else 0.0
    
    def add_ad_credits(self, username: str, amount_usd: float, description: str = "deposit") -> Dict:
        """광고 크레딧 추가"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        
        try:
            # Upsert ad_credits
            cursor.execute("""
                INSERT INTO ad_credits (username, credit_balance_usd, total_deposited_usd, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    credit_balance_usd = credit_balance_usd + ?,
                    total_deposited_usd = total_deposited_usd + ?,
                    updated_at = ?
            """, (username, amount_usd, amount_usd, now, now, amount_usd, amount_usd, now))
            
            # 거래 기록
            tx_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO ad_transactions (id, advertiser_username, transaction_type, amount_usd, description, created_at)
                VALUES (?, ?, 'deposit', ?, ?, ?)
            """, (tx_id, username, amount_usd, description, now))
            
            conn.commit()
            new_balance = self.get_ad_credits(username)
            conn.close()
            
            logger.info(f"광고 크레딧 추가: {username} +${amount_usd:.2f} (잔액: ${new_balance:.2f})")
            return {"success": True, "new_balance_usd": new_balance}
        
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"광고 크레딧 추가 실패: {e}")
            return {"success": False, "error": str(e)}
    
    def deduct_ad_credits(self, username: str, amount_usd: float, campaign_id: str = None, impression_id: str = None) -> bool:
        """광고 크레딧 차감 (원자적)"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        
        try:
            # 원자적 차감 (잔액 부족 시 실패)
            cursor.execute("""
                UPDATE ad_credits
                SET credit_balance_usd = credit_balance_usd - ?,
                    total_spent_usd = total_spent_usd + ?,
                    updated_at = ?
                WHERE username = ? AND credit_balance_usd >= ?
            """, (amount_usd, amount_usd, now, username, amount_usd))
            
            if cursor.rowcount == 0:
                conn.close()
                return False
            
            # 거래 기록
            tx_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO ad_transactions (id, advertiser_username, transaction_type, amount_usd, 
                    related_campaign_id, related_impression_id, description, created_at)
                VALUES (?, ?, 'spend', ?, ?, ?, 'Ad impression', ?)
            """, (tx_id, username, amount_usd, campaign_id, impression_id, now))
            
            conn.commit()
            conn.close()
            return True
        
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"광고 크레딧 차감 실패: {e}")
            return False
    
    # ============================================================
    # Campaign Management
    # ============================================================
    
    def create_campaign(self, data: Dict) -> Dict:
        """
        새 광고 캠페인 생성
        
        Required:
            - advertiser_username: str
            - title: str
            - link_url: str
            - monthly_budget_usd: float (최소 $10)
        
        Optional (4개 위치별 이미지):
            - image_sidebar_url: str (300×250 or 300×600)
            - image_post_top_url: str (728×90)
            - image_post_bottom_url: str (728×90)
            - image_feed_inline_url: str (300×250)
            - alt_text: str
            - target_communities: list[str] or None (null = all)
            - target_regex: str or None
            - is_nsfw: bool
            - show_on_all: bool
            - start_date: int (unix timestamp, default: now)
            - end_date: int (unix timestamp, default: now + 30 days)
        """
        config = self.get_config()
        
        # 필수 필드 검증
        required = ["advertiser_username", "title", "link_url", "monthly_budget_usd"]
        for field in required:
            if field not in data:
                return {"success": False, "error": f"Missing required field: {field}"}
        
        username = data["advertiser_username"]
        monthly_budget = float(data["monthly_budget_usd"])
        
        # 최소 예산 검증
        if monthly_budget < config["minimum_budget_usd"]:
            return {
                "success": False, 
                "error": f"Minimum budget is ${config['minimum_budget_usd']:.2f}"
            }
        
        # 크레딧 잔액 확인
        balance = self.get_ad_credits(username)
        if balance < monthly_budget:
            return {
                "success": False,
                "error": "Insufficient ad credits",
                "required_usd": monthly_budget,
                "available_usd": balance
            }
        
        # 정규식 검증 (길이 제한)
        target_regex = data.get("target_regex")
        if target_regex:
            if len(target_regex) > config["max_regex_length"]:
                return {"success": False, "error": f"Regex exceeds max length ({config['max_regex_length']})"}
            try:
                re.compile(target_regex)
            except re.error as e:
                return {"success": False, "error": f"Invalid regex: {e}"}
        
        # 타겟 커뮤니티 JSON 변환
        target_communities = data.get("target_communities")
        if isinstance(target_communities, list):
            target_communities = json.dumps(target_communities)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        campaign_id = str(uuid.uuid4())
        
        # 기간 설정: 기본값 1개월 (30일)
        start_date = data.get("start_date") or now
        end_date = data.get("end_date") or (now + 30 * 24 * 60 * 60)  # 30일 후
        
        try:
            cursor.execute("""
                INSERT INTO ad_campaigns (
                    id, advertiser_username, title, link_url, alt_text,
                    image_sidebar_url, image_post_top_url, image_post_bottom_url, image_feed_inline_url,
                    monthly_budget_usd, approval_status,
                    target_communities, target_regex, is_nsfw, show_on_all,
                    start_date, end_date, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, TRUE, ?, ?)
            """, (
                campaign_id,
                username,
                data["title"],
                data["link_url"],
                data.get("alt_text"),
                data.get("image_sidebar_url"),
                data.get("image_post_top_url"),
                data.get("image_post_bottom_url"),
                data.get("image_feed_inline_url"),
                monthly_budget,
                target_communities,
                target_regex,
                data.get("is_nsfw", False),
                data.get("show_on_all", True),
                start_date,
                end_date,
                now, now
            ))
            
            # 즉시 크레딧 차감 (캠페인 생성 시점에 Cost 차감)
            cursor.execute("""
                UPDATE ad_credits
                SET credit_balance_usd = credit_balance_usd - ?,
                    updated_at = ?
                WHERE username = ?
            """, (monthly_budget, now, username))
            
            # 거래 기록: campaign_cost
            tx_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO ad_transactions (id, advertiser_username, transaction_type, amount_usd, description, created_at)
                VALUES (?, ?, 'campaign_cost', ?, ?, ?)
            """, (tx_id, username, -monthly_budget, f"Campaign created: {data['title']}", now))
            
            conn.commit()
            
            new_balance = self.get_ad_credits(username)
            conn.close()
            
            logger.info(f"광고 캠페인 생성: {campaign_id} by {username} (${monthly_budget:.2f} 차감, 잔액: ${new_balance:.2f})")
            return {
                "success": True,
                "campaign_id": campaign_id,
                "approval_status": "pending",
                "start_date": start_date,
                "end_date": end_date,
                "cost_deducted_usd": monthly_budget,
                "new_balance_usd": new_balance,
                "message": "Campaign created. Cost deducted. Awaiting admin approval."
            }
        
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"캠페인 생성 실패: {e}")
            return {"success": False, "error": str(e)}
    
    def approve_campaign(self, campaign_id: str, admin_username: str) -> Dict:
        """관리자가 광고 캠페인 승인"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        
        try:
            cursor.execute("""
                UPDATE ad_campaigns
                SET approval_status = 'approved',
                    approved_by = ?,
                    approved_at = ?,
                    updated_at = ?
                WHERE id = ? AND approval_status = 'pending'
            """, (admin_username, now, now, campaign_id))
            
            if cursor.rowcount == 0:
                conn.close()
                return {"success": False, "error": "Campaign not found or already processed"}
            
            conn.commit()
            conn.close()
            logger.info(f"캠페인 승인: {campaign_id} by {admin_username}")
            return {"success": True, "campaign_id": campaign_id, "approval_status": "approved"}
        
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"캠페인 승인 실패: {e}")
            return {"success": False, "error": str(e)}
    
    def reject_campaign(self, campaign_id: str, admin_username: str, reason: str) -> Dict:
        """관리자가 광고 캠페인 거부 - 크레딧 환불 포함"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        
        try:
            # 먼저 캠페인 정보 조회 (환불 금액 확인용)
            cursor.execute("""
                SELECT advertiser_username, monthly_budget_usd, title
                FROM ad_campaigns 
                WHERE id = ? AND approval_status = 'pending'
            """, (campaign_id,))
            campaign = cursor.fetchone()
            
            if not campaign:
                conn.close()
                return {"success": False, "error": "Campaign not found or already processed"}
            
            username = campaign['advertiser_username']
            refund_amount = campaign['monthly_budget_usd']
            title = campaign['title']
            
            # 캠페인 상태 업데이트
            cursor.execute("""
                UPDATE ad_campaigns
                SET approval_status = 'rejected',
                    approved_by = ?,
                    approved_at = ?,
                    rejection_reason = ?,
                    is_active = FALSE,
                    updated_at = ?
                WHERE id = ?
            """, (admin_username, now, reason, now, campaign_id))
            
            # 크레딧 환불
            cursor.execute("""
                UPDATE ad_credits
                SET credit_balance_usd = credit_balance_usd + ?,
                    updated_at = ?
                WHERE username = ?
            """, (refund_amount, now, username))
            
            # 거래 기록: refund
            tx_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO ad_transactions (id, advertiser_username, transaction_type, amount_usd, description, created_at)
                VALUES (?, ?, 'refund', ?, ?, ?)
            """, (tx_id, username, refund_amount, f"Campaign rejected: {title}", now))
            
            conn.commit()
            conn.close()
            
            logger.info(f"캠페인 거부 + 환불: {campaign_id} by {admin_username} - ${refund_amount:.2f} refunded to {username}")
            return {
                "success": True, 
                "campaign_id": campaign_id, 
                "approval_status": "rejected",
                "refunded_usd": refund_amount,
                "refunded_to": username
            }
        
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"캠페인 거부 실패: {e}")
            return {"success": False, "error": str(e)}
    
    def get_campaign(self, campaign_id: str) -> Optional[Dict]:
        """캠페인 정보 조회"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ad_campaigns WHERE id = ?", (campaign_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_campaigns_by_advertiser(self, username: str) -> List[Dict]:
        """광고주의 캠페인 목록 조회"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM ad_campaigns 
            WHERE advertiser_username = ? AND is_deleted = FALSE
            ORDER BY created_at DESC
        """, (username,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_pending_campaigns(self) -> List[Dict]:
        """승인 대기 중인 캠페인 목록 (관리자용)"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM ad_campaigns 
            WHERE approval_status = 'pending' AND is_deleted = FALSE
            ORDER BY created_at ASC
        """)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_all_active_campaigns(self) -> List[Dict]:
        """관리자용: 현재 활성화되어 있고 승인된 모든 캠페인 조회"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        cursor.execute("""
            SELECT * FROM ad_campaigns c
            WHERE c.approval_status = 'approved'
              AND c.is_active = TRUE
              AND c.is_deleted = FALSE
              AND (c.start_date IS NULL OR c.start_date <= ?)
              AND (c.end_date IS NULL OR c.end_date >= ?)
            ORDER BY c.updated_at DESC
        """, (now, now))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    # ============================================================
    # Ad Selection Algorithm
    # ============================================================
    
    def select_ad_to_display(
        self,
        community: Optional[str] = None,
        community_display_name: Optional[str] = None,
        is_nsfw: bool = False,
        page_url: str = '',
        page_content: str = '',
        session_id: Optional[str] = None
    ) -> Optional[Dict]:
        """
        광고 선택 알고리즘 (페이지 로드당 한 번 호출)
        
        1. 로드 포인트가 있는 광고 우선 처리
        2. 로드 포인트 없으면 확률 기반 선택 (전체 예산 합계 대비 비율)
        3. 타겟 미매치 시 해당 광고에 로드 포인트 부여 (세션당 1회)
        4. 선택된 캠페인의 4개 위치 이미지 모두 반환
        
        Args:
            community: 현재 페이지의 커뮤니티 이름 (None = 홈/전체)
            community_display_name: 커뮤니티 표시 이름 (title)
            is_nsfw: 현재 페이지가 NSFW인지 여부
            page_url: 현재 페이지 URL
            page_content: 페이지 콘텐츠 (정규식 매칭용, 선택적)
            session_id: 페이지 로드 세션 ID (같은 세션에서 load_points 중복 증가 방지)
        
        Returns:
            선택된 광고 정보 (4개 위치 이미지 포함) 또는 None
        """
        # ========================================
        # Post URL → Community 자동 매핑 (fallback)
        # ========================================
        # community 정보가 없고 page_url에 /post/{id}가 있으면
        # Lemmy API로 해당 게시글의 community 조회
        if not community and page_url:
            post_id = _parse_post_id_from_url(page_url)
            if post_id:
                community_info = _get_community_by_post_id(post_id)
                if community_info:
                    community = community_info.get("name")
                    if not community_display_name:
                        community_display_name = community_info.get("title")
                    logger.info(f"[AdService] Resolved community from post URL: post_id={post_id} → community={community}")
        
        config = self.get_config()
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        
        # 활성화된 승인 광고 조회 (기간 내 캠페인만)
        cursor.execute("""
            SELECT c.*
            FROM ad_campaigns c
            WHERE c.approval_status = 'approved'
              AND c.is_active = TRUE
              AND c.is_deleted = FALSE
              AND (c.start_date IS NULL OR c.start_date <= ?)
              AND (c.end_date IS NULL OR c.end_date >= ?)
            ORDER BY c.load_points DESC, c.monthly_budget_usd DESC
        """, (now, now))
        
        candidates = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        if not candidates:
            return None
        
        # 전체 예산 합계 계산
        total_budget = sum(ad["monthly_budget_usd"] for ad in candidates)
        
        if total_budget <= 0:
            return None
        
        # ========================================
        # 1단계: 모든 광고의 타겟팅 매치 여부 확인
        # ========================================
        eligible_ads = []  # 타겟 매치된 모든 광고
        
        for ad in candidates:
            targeting_match = self._check_targeting(ad, community, community_display_name, is_nsfw, page_url, page_content)
            
            if targeting_match:
                eligible_ads.append(ad)
            else:
                # 타겟 미매치 + 타겟팅 설정이 있는 광고만 load_points +1
                # (show_on_all=False 또는 target_regex가 있는 경우)
                # session_id로 세션당 1회만 증가
                has_targeting = not ad.get("show_on_all", True) or ad.get("target_regex")
                if has_targeting:
                    self._increment_load_points(ad["id"], session_id)
        
        if not eligible_ads:
            return None
        
        # ========================================
        # 2단계: load_points > 0인 광고 우선 풀 생성
        # ========================================
        load_point_ads = [ad for ad in eligible_ads if ad["load_points"] > 0]
        normal_ads = [ad for ad in eligible_ads if ad["load_points"] <= 0]
        
        logger.info(f"[AdService] Eligible ads: {len(eligible_ads)}, load_point_ads: {len(load_point_ads)}, normal_ads: {len(normal_ads)}")
        
        selected_ad = None
        
        # ========================================
        # 3단계: 우선 풀에서 확률 기반 선택
        # ========================================
        if load_point_ads:
            # 우선 풀 내에서 예산 비율에 따른 확률 선택
            lp_total = sum(ad["monthly_budget_usd"] for ad in load_point_ads)
            if lp_total > 0:
                rand_value = random.random() * lp_total
                cumulative = 0.0
                
                for ad in load_point_ads:
                    cumulative += ad["monthly_budget_usd"]
                    if rand_value <= cumulative:
                        selected_ad = ad
                        # 로드 포인트 감소 (세션당 1회만)
                        self._decrement_load_points(ad["id"], session_id)
                        logger.info(f"[AdService] Selected from load_point pool: {ad.get('title')} (budget=${ad['monthly_budget_usd']}, load_points={ad['load_points']})")
                        break
        
        # ========================================
        # 4단계: 우선 풀에서 선택 안 됐으면 일반 풀에서 확률 선택
        # ========================================
        if not selected_ad and normal_ads:
            normal_total = sum(ad["monthly_budget_usd"] for ad in normal_ads)
            if normal_total > 0:
                rand_value = random.random() * normal_total
                cumulative = 0.0
                
                for ad in normal_ads:
                    cumulative += ad["monthly_budget_usd"]
                    if rand_value <= cumulative:
                        selected_ad = ad
                        logger.info(f"[AdService] Selected from normal pool: {ad.get('title')} (budget=${ad['monthly_budget_usd']})")
                        break
        
        # Fallback: 아직 선택 안 됐으면 eligible_ads 중 첫 번째
        if not selected_ad and eligible_ads:
            selected_ad = eligible_ads[0]
            logger.info(f"[AdService] Fallback selection: {selected_ad.get('title')}")
        
        if selected_ad:
            return self._record_impression_and_return(selected_ad, community, is_nsfw, page_url, config)
        
        return None
    
    def _check_targeting(
        self,
        ad: Dict,
        community: Optional[str],
        community_display_name: Optional[str],
        is_nsfw: bool,
        page_url: str,
        page_content: str
    ) -> bool:
        """타겟팅 조건 확인"""
        ad_title = ad.get("title", ad.get("id", "unknown"))
        
        # NSFW 체크: NSFW 광고는 NSFW 페이지에서만
        if ad["is_nsfw"] and not is_nsfw:
            logger.debug(f"[Targeting] {ad_title}: NSFW mismatch")
            return False
        
        # 비NSFW 광고도 NSFW 페이지에는 표시하지 않음 (선택적 정책)
        # if not ad["is_nsfw"] and is_nsfw:
        #     return False
        
        # 커뮤니티 타겟팅 (name 또는 display_name 중 하나만 매치해도 OK)
        if not ad["show_on_all"] and ad["target_communities"]:
            try:
                target_comms = json.loads(ad["target_communities"])
                # 대소문자 무시 비교
                target_comms_lower = [c.lower() for c in target_comms]
                community_lower = community.lower() if community else None
                display_name_lower = community_display_name.lower() if community_display_name else None
                
                logger.info(f"[Targeting] {ad_title}: target_comms={target_comms}, community={community}, display_name={community_display_name}")
                
                # 둘 중 하나라도 매치하면 OK
                name_match = community_lower and community_lower in target_comms_lower
                display_match = display_name_lower and display_name_lower in target_comms_lower
                
                if community_lower or display_name_lower:
                    if not name_match and not display_match:
                        logger.info(f"[Targeting] {ad_title}: neither '{community}' nor '{community_display_name}' in {target_comms} -> REJECT")
                        return False
                else:
                    # 홈페이지에서는 특정 커뮤니티 타겟 광고 미표시
                    logger.info(f"[Targeting] {ad_title}: no community but has target -> REJECT")
                    return False
                    
                logger.info(f"[Targeting] {ad_title}: community MATCH (name={name_match}, display={display_match}) -> ACCEPT")
            except json.JSONDecodeError:
                pass
        
        # 정규식 타겟팅
        if ad["target_regex"]:
            try:
                pattern = re.compile(ad["target_regex"], re.IGNORECASE)
                
                # page_content가 있으면 사용, 없으면 URL에서 post ID 추출하여 게시글 콘텐츠 조회
                text_to_match = page_content
                if not text_to_match and page_url:
                    # URL에서 post ID 추출 후 게시글 콘텐츠 조회
                    post_id = _parse_post_id_from_url(page_url)
                    if post_id:
                        text_to_match = _get_post_content_by_id(post_id)
                        logger.info(f"[Targeting] {ad_title}: fetched post content for regex matching (post_id={post_id}, content_len={len(text_to_match or '')})")
                
                # 콘텐츠도 없으면 URL에서 매칭 시도
                if not text_to_match:
                    text_to_match = page_url
                
                if not pattern.search(text_to_match):
                    logger.info(f"[Targeting] {ad_title}: regex '{ad['target_regex']}' NOT matched in content (len={len(text_to_match)}) -> REJECT")
                    return False
                else:
                    logger.info(f"[Targeting] {ad_title}: regex '{ad['target_regex']}' MATCHED in content -> ACCEPT")
            except re.error:
                # 잘못된 정규식은 무시
                pass
        
        return True
    
    def _increment_load_points(self, campaign_id: str, session_id: Optional[str] = None):
        """로드 포인트 증가 (세션당 1회만)"""
        # session_id가 있으면 세션 기반 중복 방지
        if session_id:
            cache_key = f"{session_id}:{campaign_id}"
            if cache_key in self._load_point_cache:
                return  # 같은 세션에서 이미 증가함
            self._load_point_cache[cache_key] = time.time()
            
            # 캐시 정리 (1000개 초과 시, 60초 이상 된 항목 삭제)
            if len(self._load_point_cache) > 1000:
                cutoff = time.time() - 60
                self._load_point_cache = {
                    k: v for k, v in self._load_point_cache.items() if v > cutoff
                }
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ad_campaigns
            SET load_points = load_points + 1,
                updated_at = ?
            WHERE id = ?
        """, (int(time.time()), campaign_id))
        conn.commit()
        conn.close()
    
    def _decrement_load_points(self, campaign_id: str, session_id: Optional[str] = None):
        """로드 포인트 감소 (세션당 1회만)"""
        # session_id가 있으면 세션 기반 중복 방지
        if session_id:
            cache_key = f"dec:{session_id}:{campaign_id}"
            if cache_key in self._load_point_cache:
                return  # 같은 세션에서 이미 감소함
            self._load_point_cache[cache_key] = time.time()
            
            # 캐시 정리 (1000개 초과 시, 60초 이상 된 항목 삭제)
            if len(self._load_point_cache) > 1000:
                cutoff = time.time() - 60
                self._load_point_cache = {
                    k: v for k, v in self._load_point_cache.items() if v > cutoff
                }
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ad_campaigns
            SET load_points = CASE WHEN load_points > 0 THEN load_points - 1 ELSE 0 END,
                updated_at = ?
            WHERE id = ?
        """, (int(time.time()), campaign_id))
        conn.commit()
        conn.close()
    
    def _record_impression_and_return(
        self,
        ad: Dict,
        community: Optional[str],
        is_nsfw: bool,
        page_url: str,
        config: Dict
    ) -> Dict:
        """노출 기록 및 광고 정보 반환 (과금 없음 - 월 예산 기반, 4개 위치 이미지 포함)"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        impression_id = str(uuid.uuid4())
        
        try:
            # 노출 기록 (비용 없음)
            cursor.execute("""
                INSERT INTO ad_impressions (
                    id, campaign_id, advertiser_username,
                    page_url, community_name, is_nsfw_page,
                    cost_usd, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                impression_id, ad["id"], ad["advertiser_username"],
                page_url, community, is_nsfw, now
            ))
            
            # 캠페인 통계 업데이트 (노출 수만, 비용 차감 없음)
            cursor.execute("""
                UPDATE ad_campaigns
                SET total_impressions = total_impressions + 1,
                    updated_at = ?
                WHERE id = ?
            """, (now, ad["id"]))
            
            conn.commit()
            conn.close()
            
            # 크레딧 차감 없음 (월 예산 기반)
            
            # 광고 정보 반환 (4개 위치 이미지 모두 포함)
            return {
                "campaign_id": ad["id"],
                "impression_id": impression_id,
                "title": ad["title"],
                "link_url": ad["link_url"],
                "alt_text": ad["alt_text"],
                "advertiser": ad["advertiser_username"],
                "is_nsfw": ad["is_nsfw"],
                # 4개 위치별 이미지 URL
                "images": {
                    "sidebar": ad.get("image_sidebar_url"),
                    "post_top": ad.get("image_post_top_url"),
                    "post_bottom": ad.get("image_post_bottom_url"),
                    "feed_inline": ad.get("image_feed_inline_url"),
                },
                # Backward compatibility
                "image_url": ad.get("image_sidebar_url") or ad.get("image_url"),
            }
        
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"노출 기록 실패: {e}")
            return None
    
    # ============================================================
    # Click Tracking
    # ============================================================
    
    def record_click(self, impression_id: str) -> bool:
        """광고 클릭 기록 (과금 없음 - 통계용)"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        
        try:
            # 노출 정보 조회
            cursor.execute("""
                SELECT campaign_id, advertiser_username, clicked
                FROM ad_impressions WHERE id = ?
            """, (impression_id,))
            row = cursor.fetchone()
            
            if not row or row["clicked"]:
                conn.close()
                return False
            
            # 클릭 기록
            cursor.execute("""
                UPDATE ad_impressions
                SET clicked = TRUE, clicked_at = ?
                WHERE id = ?
            """, (now, impression_id))
            
            # 캠페인 클릭 수 업데이트
            cursor.execute("""
                UPDATE ad_campaigns
                SET total_clicks = total_clicks + 1,
                    updated_at = ?
                WHERE id = ?
            """, (now, row["campaign_id"]))
            
            conn.commit()
            conn.close()
            
            # 클릭 비용 차감 없음 (월 예산 기반)
            
            return True
        
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"클릭 기록 실패: {e}")
            return False

    # ============================================================
    # Impression helpers
    # ============================================================

    def update_impression_slot(self, impression_id: str, ad_slot: str, viewer_user_id: Optional[str] = None, viewer_ip_hash: Optional[str] = None) -> bool:
        """Update impression record with the ad_slot and optional viewer info."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())

        try:
            # Update the ad_slot and optional viewer fields
            cursor.execute("""
                UPDATE ad_impressions
                SET ad_slot = ?, viewer_user_id = COALESCE(?, viewer_user_id), viewer_ip_hash = COALESCE(?, viewer_ip_hash)
                WHERE id = ?
            """, (ad_slot, viewer_user_id, viewer_ip_hash, impression_id))

            if cursor.rowcount == 0:
                conn.close()
                return False

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"update_impression_slot failed: {e}")
            return False

    def get_impression_stats_by_slot(self, days: int = 90) -> Dict[str, int]:
        """Return counts of impressions grouped by ad_slot for the past `days` days.

        Returns a dict mapping ad_slot -> count. Unknown/NULL ad_slot will be returned under 'unknown'.
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        since = now - days * 24 * 60 * 60

        try:
            cursor.execute("""
                SELECT COALESCE(ad_slot, 'unknown') as slot, COUNT(*) as cnt
                FROM ad_impressions
                WHERE created_at >= ?
                GROUP BY slot
            """, (since,))

            rows = cursor.fetchall()
            conn.close()

            result: Dict[str, int] = {}
            for r in rows:
                result[r['slot']] = r['cnt']

            return result
        except Exception as e:
            conn.close()
            logger.error(f"get_impression_stats_by_slot failed: {e}")
            return {}
    
    # ============================================================
    # Total Budget API (for probability preview)
    # ============================================================
    
    def get_total_active_budget(self) -> dict:
        """현재 활성 광고들의 총 예산 조회 (확률 미리보기용)"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        now = int(time.time())
        
        try:
            cursor.execute("""
                SELECT COALESCE(SUM(monthly_budget_usd), 0) as total_budget,
                       COUNT(*) as active_count
                FROM ad_campaigns
                WHERE approval_status = 'approved'
                  AND is_active = TRUE
                  AND is_deleted = FALSE
                  AND (start_date IS NULL OR start_date <= ?)
                  AND (end_date IS NULL OR end_date >= ?)
            """, (now, now))
            row = cursor.fetchone()
            conn.close()
            
            return {
                "success": True,
                "total_budget_usd": row["total_budget"] if row else 0,
                "active_campaign_count": row["active_count"] if row else 0
            }
        except Exception as e:
            conn.close()
            logger.error(f"총 예산 조회 실패: {e}")
            return {
                "success": False,
                "total_budget_usd": 0,
                "active_campaign_count": 0,
                "error": str(e)
            }


# 싱글톤 인스턴스
ad_service = AdService()
