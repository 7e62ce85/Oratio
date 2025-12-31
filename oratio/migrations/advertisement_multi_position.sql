-- Advertisement System Migration: Multi-Position Images
-- Version: 1.2
-- Created: 2025-12-10
-- Description: Change from single image_url to 4 position-specific image URLs
--              Remove position column (campaigns now target all positions)
--              Campaign is selected once per page load, shown in all positions

-- Add 4 position-specific image columns
ALTER TABLE ad_campaigns ADD COLUMN image_sidebar_url TEXT;
ALTER TABLE ad_campaigns ADD COLUMN image_post_top_url TEXT;
ALTER TABLE ad_campaigns ADD COLUMN image_post_bottom_url TEXT;
ALTER TABLE ad_campaigns ADD COLUMN image_feed_inline_url TEXT;

-- Migrate existing image_url to sidebar (most common)
UPDATE ad_campaigns SET image_sidebar_url = image_url WHERE image_url IS NOT NULL;

-- Note: image_url column kept for backward compatibility, will be ignored
-- Note: position column kept for backward compatibility, will be ignored

-- Create index for date-based queries (important for period-based probability)
CREATE INDEX IF NOT EXISTS idx_ad_campaigns_dates ON ad_campaigns(start_date, end_date);
