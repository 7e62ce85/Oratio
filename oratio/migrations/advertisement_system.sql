-- Advertisement System Migration
-- Version: 1.0
-- Created: 2025-12-10
-- Description: Ad campaigns, credits, impressions, load points system

-- ============================================================
-- Table: ad_credits
-- 광고주별 USD 크레딧 잔액
-- ============================================================
CREATE TABLE IF NOT EXISTS ad_credits (
    username TEXT PRIMARY KEY,
    credit_balance_usd REAL DEFAULT 0.0,
    total_deposited_usd REAL DEFAULT 0.0,
    total_spent_usd REAL DEFAULT 0.0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ad_credits_balance ON ad_credits(credit_balance_usd);

-- ============================================================
-- Table: ad_campaigns
-- 광고 캠페인 (광고 단위)
-- ============================================================
CREATE TABLE IF NOT EXISTS ad_campaigns (
    id TEXT PRIMARY KEY,
    advertiser_username TEXT NOT NULL,
    -- 광고 콘텐츠
    title TEXT NOT NULL,
    image_url TEXT,
    link_url TEXT NOT NULL,
    alt_text TEXT,
    -- 예산 및 노출 설정
    monthly_budget_usd REAL NOT NULL DEFAULT 10.0,
    spent_this_month_usd REAL DEFAULT 0.0,
    -- 승인 상태: pending, approved, rejected
    approval_status TEXT DEFAULT 'pending',
    approved_by TEXT,
    approved_at INTEGER,
    rejection_reason TEXT,
    -- 타겟팅 설정
    target_communities TEXT,              -- JSON array of community names, null = all
    target_regex TEXT,                    -- 정규식 패턴 (null = 없음)
    is_nsfw BOOLEAN DEFAULT FALSE,
    show_on_all BOOLEAN DEFAULT TRUE,
    -- 로드 포인트 (타겟 미매치로 미노출 시 적립)
    load_points INTEGER DEFAULT 0,
    -- 기간
    start_date INTEGER,
    end_date INTEGER,
    -- 상태
    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,
    -- 통계
    total_impressions INTEGER DEFAULT 0,
    total_clicks INTEGER DEFAULT 0,
    -- 타임스탬프
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (advertiser_username) REFERENCES ad_credits(username)
);

CREATE INDEX IF NOT EXISTS idx_ad_campaigns_advertiser ON ad_campaigns(advertiser_username);
CREATE INDEX IF NOT EXISTS idx_ad_campaigns_status ON ad_campaigns(approval_status, is_active);
CREATE INDEX IF NOT EXISTS idx_ad_campaigns_load_points ON ad_campaigns(load_points);
CREATE INDEX IF NOT EXISTS idx_ad_campaigns_nsfw ON ad_campaigns(is_nsfw);

-- ============================================================
-- Table: ad_impressions
-- 광고 노출 기록
-- ============================================================
CREATE TABLE IF NOT EXISTS ad_impressions (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    advertiser_username TEXT NOT NULL,
    -- 노출 컨텍스트
    page_url TEXT,
    community_name TEXT,
    is_nsfw_page BOOLEAN DEFAULT FALSE,
    -- 광고 슬롯 위치 (sidebar, top, bottom 등)
    ad_slot TEXT,
    -- 사용자 정보 (익명화)
    viewer_ip_hash TEXT,
    viewer_user_id TEXT,
    -- 비용 (해당 노출에 대한 차감액)
    cost_usd REAL DEFAULT 0.0,
    -- 클릭 여부
    clicked BOOLEAN DEFAULT FALSE,
    clicked_at INTEGER,
    -- 타임스탬프
    created_at INTEGER NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES ad_campaigns(id),
    FOREIGN KEY (advertiser_username) REFERENCES ad_credits(username)
);

CREATE INDEX IF NOT EXISTS idx_ad_impressions_campaign ON ad_impressions(campaign_id);
CREATE INDEX IF NOT EXISTS idx_ad_impressions_advertiser ON ad_impressions(advertiser_username);
CREATE INDEX IF NOT EXISTS idx_ad_impressions_created ON ad_impressions(created_at);
CREATE INDEX IF NOT EXISTS idx_ad_impressions_community ON ad_impressions(community_name);

-- ============================================================
-- Table: ad_transactions
-- 광고 크레딧 입출금 기록
-- ============================================================
CREATE TABLE IF NOT EXISTS ad_transactions (
    id TEXT PRIMARY KEY,
    advertiser_username TEXT NOT NULL,
    -- 거래 유형: deposit, spend, refund, bonus
    transaction_type TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    -- 관련 캠페인/노출 ID
    related_campaign_id TEXT,
    related_impression_id TEXT,
    -- 설명
    description TEXT,
    -- 타임스탬프
    created_at INTEGER NOT NULL,
    FOREIGN KEY (advertiser_username) REFERENCES ad_credits(username),
    FOREIGN KEY (related_campaign_id) REFERENCES ad_campaigns(id)
);

CREATE INDEX IF NOT EXISTS idx_ad_transactions_advertiser ON ad_transactions(advertiser_username);
CREATE INDEX IF NOT EXISTS idx_ad_transactions_type ON ad_transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_ad_transactions_created ON ad_transactions(created_at);

-- ============================================================
-- Table: ad_config
-- 광고 시스템 설정
-- ============================================================
CREATE TABLE IF NOT EXISTS ad_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- 기준 예산 (이 금액 = 100% 노출 확률)
    baseline_budget_usd REAL DEFAULT 100.0,
    -- 최소 광고 예산
    minimum_budget_usd REAL DEFAULT 10.0,
    -- 노출당 비용 (CPM 기준으로 계산)
    cost_per_impression_usd REAL DEFAULT 0.001,
    -- 클릭당 추가 비용
    cost_per_click_usd REAL DEFAULT 0.01,
    -- 정규식 최대 길이
    max_regex_length INTEGER DEFAULT 500,
    -- 활성화 여부
    is_active BOOLEAN DEFAULT TRUE,
    -- 타임스탬프
    effective_from INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

-- Insert default config
INSERT INTO ad_config (
    baseline_budget_usd,
    minimum_budget_usd,
    cost_per_impression_usd,
    cost_per_click_usd,
    max_regex_length,
    is_active,
    effective_from,
    created_at
) VALUES (
    100.0,
    10.0,
    0.001,
    0.01,
    500,
    TRUE,
    strftime('%s', 'now'),
    strftime('%s', 'now')
);

-- ============================================================
-- Seed: gookjob 계정에 $10 USD 광고 크레딧 부여
-- ============================================================
INSERT OR IGNORE INTO ad_credits (
    username,
    credit_balance_usd,
    total_deposited_usd,
    total_spent_usd,
    created_at,
    updated_at
) VALUES (
    'gookjob',
    10.0,
    10.0,
    0.0,
    strftime('%s', 'now'),
    strftime('%s', 'now')
);

-- gookjob 보너스 지급 기록
INSERT OR IGNORE INTO ad_transactions (
    id,
    advertiser_username,
    transaction_type,
    amount_usd,
    description,
    created_at
) VALUES (
    'bonus_gookjob_initial_10usd',
    'gookjob',
    'bonus',
    10.0,
    'Initial free ad credits for gookjob',
    strftime('%s', 'now')
);
