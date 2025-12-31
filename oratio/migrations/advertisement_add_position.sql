-- Advertisement System Migration: Add Position Field
-- Version: 1.1
-- Created: 2025-12-11
-- Description: Add position field to ad_campaigns for ad placement targeting

-- Add position column to ad_campaigns
-- Values: sidebar_right, post_top, post_bottom, feed_inline
ALTER TABLE ad_campaigns ADD COLUMN position TEXT DEFAULT 'sidebar_right';

-- Index for position-based queries
CREATE INDEX IF NOT EXISTS idx_ad_campaigns_position ON ad_campaigns(position);
