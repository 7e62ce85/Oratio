-- Upload Quota System Migration
-- Version: 1.0
-- Created: 2025-11-04
-- Description: Implements tiered upload quota system with credit charging

-- Table: user_upload_quotas
-- Tracks annual upload quotas for users
CREATE TABLE IF NOT EXISTS user_upload_quotas (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    -- Annual quota in bytes (20GB for members = 21474836480 bytes)
    annual_quota_bytes BIGINT DEFAULT 0,
    -- Current usage in bytes
    used_bytes BIGINT DEFAULT 0,
    -- Quota period start (Unix timestamp)
    quota_start_date INTEGER NOT NULL,
    -- Quota period end (Unix timestamp)
    quota_end_date INTEGER NOT NULL,
    -- Membership type ('free', 'annual')
    membership_type TEXT DEFAULT 'free',
    -- Created timestamp
    created_at INTEGER NOT NULL,
    -- Last updated timestamp
    updated_at INTEGER NOT NULL,
    -- Is quota active
    is_active BOOLEAN DEFAULT TRUE
);

-- Table: upload_transactions
-- Records every file upload with size and pricing
CREATE TABLE IF NOT EXISTS upload_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    -- File information
    filename TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    file_type TEXT,
    -- Upload URL
    upload_url TEXT,
    -- Pricing information
    was_within_quota BOOLEAN DEFAULT TRUE,
    overage_bytes BIGINT DEFAULT 0,
    credit_charged REAL DEFAULT 0.0,
    -- USD per 4GB rate at time of upload
    usd_per_4gb REAL DEFAULT 1.0,
    -- Transaction status
    status TEXT DEFAULT 'completed',
    -- Post/comment association
    post_id INTEGER,
    comment_id INTEGER,
    -- Timestamps
    created_at INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES user_upload_quotas(user_id)
);

-- Table: upload_pricing_config
-- Centralized pricing configuration
CREATE TABLE IF NOT EXISTS upload_pricing_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Free user limits
    free_user_limit_bytes BIGINT DEFAULT 256000, -- 250KB
    -- Member limits
    member_annual_quota_bytes BIGINT DEFAULT 21474836480, -- 20GB
    -- Overage pricing
    overage_usd_per_4gb REAL DEFAULT 1.0,
    overage_min_charge_usd REAL DEFAULT 0.01, -- Minimum charge
    -- File type recommendations
    recommended_formats TEXT DEFAULT 'jpg,jpeg',
    -- Effective date
    effective_from INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at INTEGER NOT NULL
);

-- Insert default pricing config
INSERT INTO upload_pricing_config (
    free_user_limit_bytes,
    member_annual_quota_bytes,
    overage_usd_per_4gb,
    overage_min_charge_usd,
    recommended_formats,
    effective_from,
    is_active,
    created_at
) VALUES (
    256000, -- 250KB for free users
    21474836480, -- 20GB for members
    1.0, -- $1 per 4GB
    0.01, -- Minimum $0.01
    'jpg,jpeg',
    strftime('%s', 'now'),
    TRUE,
    strftime('%s', 'now')
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_upload_quotas_user_id ON user_upload_quotas(user_id);
CREATE INDEX IF NOT EXISTS idx_upload_quotas_username ON user_upload_quotas(username);
CREATE INDEX IF NOT EXISTS idx_upload_quotas_active ON user_upload_quotas(is_active);

CREATE INDEX IF NOT EXISTS idx_upload_transactions_user_id ON upload_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_upload_transactions_created_at ON upload_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_upload_transactions_status ON upload_transactions(status);

-- Trigger: Update upload quota usage
CREATE TRIGGER IF NOT EXISTS update_quota_usage_after_upload
AFTER INSERT ON upload_transactions
WHEN NEW.status = 'completed'
BEGIN
    UPDATE user_upload_quotas
    SET used_bytes = used_bytes + NEW.file_size_bytes,
        updated_at = strftime('%s', 'now')
    WHERE user_id = NEW.user_id;
END;

-- Trigger: Sync quota when membership changes
CREATE TRIGGER IF NOT EXISTS sync_quota_on_membership_change
AFTER INSERT ON user_memberships
WHEN NEW.is_active = TRUE
BEGIN
    INSERT OR REPLACE INTO user_upload_quotas (
        user_id,
        username,
        annual_quota_bytes,
        used_bytes,
        quota_start_date,
        quota_end_date,
        membership_type,
        created_at,
        updated_at,
        is_active
    ) VALUES (
        NEW.user_id,
        NEW.user_id, -- Will be updated by sync service
        21474836480, -- 20GB
        COALESCE((SELECT used_bytes FROM user_upload_quotas WHERE user_id = NEW.user_id), 0),
        NEW.purchased_at,
        NEW.expires_at,
        'annual',
        strftime('%s', 'now'),
        strftime('%s', 'now'),
        TRUE
    );
END;

-- View: User quota summary
CREATE VIEW IF NOT EXISTS user_quota_summary AS
SELECT 
    uq.user_id,
    uq.username,
    uq.membership_type,
    uq.annual_quota_bytes,
    uq.used_bytes,
    (uq.annual_quota_bytes - uq.used_bytes) AS remaining_bytes,
    ROUND((uq.used_bytes * 100.0 / uq.annual_quota_bytes), 2) AS usage_percentage,
    uq.quota_start_date,
    uq.quota_end_date,
    datetime(uq.quota_end_date, 'unixepoch') AS quota_ends_at,
    COUNT(ut.id) AS total_uploads,
    SUM(ut.file_size_bytes) AS total_uploaded_bytes,
    SUM(ut.credit_charged) AS total_credits_charged
FROM user_upload_quotas uq
LEFT JOIN upload_transactions ut ON uq.user_id = ut.user_id
GROUP BY uq.user_id;

-- View: Recent uploads
CREATE VIEW IF NOT EXISTS recent_uploads AS
SELECT 
    ut.id,
    ut.user_id,
    ut.username,
    ut.filename,
    ut.file_size_bytes,
    ROUND(ut.file_size_bytes / 1024.0 / 1024.0, 2) AS file_size_mb,
    ut.file_type,
    ut.was_within_quota,
    ut.credit_charged,
    datetime(ut.created_at, 'unixepoch') AS uploaded_at
FROM upload_transactions ut
ORDER BY ut.created_at DESC
LIMIT 100;

-- Comments
COMMENT ON TABLE user_upload_quotas IS 'Tracks annual upload quotas for each user';
COMMENT ON TABLE upload_transactions IS 'Records all file upload transactions with pricing';
COMMENT ON TABLE upload_pricing_config IS 'Centralized upload pricing configuration';
