-- ==========================================
-- CP (Child Pornography) Moderation System
-- Database Schema Migration
-- ==========================================
-- Version: 1.0
-- Created: 2025-11-07
-- Description: Complete schema for CP reporting, moderation, and appeals system
-- ==========================================

-- 1. User CP Permissions Table
-- Tracks user permissions for reporting CP and moderator review rights
CREATE TABLE IF NOT EXISTS user_cp_permissions (
    user_id TEXT PRIMARY KEY,
    person_id INTEGER NOT NULL,  -- Lemmy person.id for cross-reference
    username TEXT NOT NULL,
    
    -- Permission flags
    can_report_cp BOOLEAN DEFAULT TRUE,  -- Can submit CP reports
    can_review_cp BOOLEAN DEFAULT FALSE,  -- Can review CP as moderator (subset of moderators)
    is_banned BOOLEAN DEFAULT FALSE,  -- Currently banned from posting
    
    -- Ban tracking
    ban_start INTEGER,  -- Unix timestamp when ban started
    ban_end INTEGER,    -- Unix timestamp when ban expires (3 months)
    ban_count INTEGER DEFAULT 0,  -- Number of times banned
    
    -- Metadata
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    last_violation INTEGER,  -- Last CP violation timestamp
    
    -- Index for quick lookups
    UNIQUE(person_id),
    INDEX idx_user_cp_can_report (can_report_cp),
    INDEX idx_user_cp_is_banned (is_banned),
    INDEX idx_user_cp_ban_end (ban_end)
);

-- 2. CP Reports Table
-- Main table for all CP reports
CREATE TABLE IF NOT EXISTS cp_reports (
    id TEXT PRIMARY KEY,  -- UUID
    
    -- Content identification
    content_type TEXT NOT NULL,  -- 'post' or 'comment'
    content_id INTEGER NOT NULL,  -- Lemmy post.id or comment.id
    community_id INTEGER NOT NULL,  -- Community where content was posted
    
    -- Reporter information
    reporter_user_id TEXT NOT NULL,
    reporter_person_id INTEGER NOT NULL,
    reporter_username TEXT NOT NULL,
    reporter_is_member BOOLEAN DEFAULT FALSE,  -- Is membership user
    
    -- Content creator information
    creator_user_id TEXT NOT NULL,
    creator_person_id INTEGER NOT NULL,
    creator_username TEXT NOT NULL,
    
    -- Report details
    reason TEXT,  -- Reporter's reason (optional)
    report_type TEXT DEFAULT 'cp',  -- Type of report
    
    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, moderator_review, admin_review, approved, rejected, auto_deleted
    
    -- Review tracking
    reviewed_by_person_id INTEGER,  -- Who reviewed this (moderator or admin)
    reviewed_by_username TEXT,
    reviewed_at INTEGER,
    review_decision TEXT,  -- 'cp_confirmed', 'not_cp', 'admin_approved', 'admin_rejected'
    review_notes TEXT,
    
    -- Content visibility
    content_hidden BOOLEAN DEFAULT TRUE,  -- Auto-hidden on report
    
    -- Escalation tracking
    escalation_level TEXT DEFAULT 'moderator',  -- 'moderator', 'admin'
    previous_report_id TEXT,  -- If re-reported after moderator approval
    
    -- Timestamps
    created_at INTEGER NOT NULL,
    auto_delete_at INTEGER,  -- 1 week from creation for unreviewed admin cases
    
    -- Constraints
    FOREIGN KEY (reporter_user_id) REFERENCES user_cp_permissions(user_id),
    FOREIGN KEY (creator_user_id) REFERENCES user_cp_permissions(user_id),
    
    -- Indexes
    INDEX idx_cp_reports_content (content_type, content_id),
    INDEX idx_cp_reports_status (status),
    INDEX idx_cp_reports_community (community_id),
    INDEX idx_cp_reports_creator (creator_user_id),
    INDEX idx_cp_reports_reporter (reporter_user_id),
    INDEX idx_cp_reports_escalation (escalation_level, status),
    INDEX idx_cp_reports_auto_delete (auto_delete_at)
);

-- 3. CP Reviews Table
-- Detailed review history for each report
CREATE TABLE IF NOT EXISTS cp_reviews (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    
    -- Reviewer info
    reviewer_person_id INTEGER NOT NULL,
    reviewer_username TEXT NOT NULL,
    reviewer_role TEXT NOT NULL,  -- 'moderator' or 'admin'
    
    -- Review decision
    decision TEXT NOT NULL,  -- 'cp_confirmed', 'not_cp', 'needs_admin_review'
    notes TEXT,
    
    -- Timestamps
    created_at INTEGER NOT NULL,
    
    FOREIGN KEY (report_id) REFERENCES cp_reports(id) ON DELETE CASCADE,
    INDEX idx_cp_reviews_report (report_id),
    INDEX idx_cp_reviews_reviewer (reviewer_person_id)
);

-- 4. CP Appeals Table
-- Appeals from membership users
CREATE TABLE IF NOT EXISTS cp_appeals (
    id TEXT PRIMARY KEY,
    
    -- Appeal details
    user_id TEXT NOT NULL,
    person_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    
    -- What is being appealed
    appeal_type TEXT NOT NULL,  -- 'ban', 'report_ability_loss'
    related_report_id TEXT,  -- Original report that caused the issue
    
    -- Appeal content
    appeal_reason TEXT NOT NULL,
    
    -- Status
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'approved', 'rejected'
    
    -- Admin review
    reviewed_by_person_id INTEGER,
    reviewed_by_username TEXT,
    reviewed_at INTEGER,
    admin_decision TEXT,  -- 'restore_privileges', 'uphold_decision'
    admin_notes TEXT,
    
    -- Timestamps
    created_at INTEGER NOT NULL,
    
    -- Constraints
    FOREIGN KEY (user_id) REFERENCES user_cp_permissions(user_id),
    FOREIGN KEY (related_report_id) REFERENCES cp_reports(id),
    
    INDEX idx_cp_appeals_user (user_id),
    INDEX idx_cp_appeals_status (status),
    INDEX idx_cp_appeals_created (created_at)
);

-- 5. CP Notifications Table
-- Notifications for moderators and users
CREATE TABLE IF NOT EXISTS cp_notifications (
    id TEXT PRIMARY KEY,
    
    -- Recipient
    recipient_person_id INTEGER NOT NULL,
    recipient_username TEXT NOT NULL,
    
    -- Notification details
    notification_type TEXT NOT NULL,  -- 'report_submitted', 'review_needed', 'ban_notice', 'permission_revoked', 'appeal_reviewed'
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    
    -- Related entities
    related_report_id TEXT,
    related_appeal_id TEXT,
    
    -- Status
    is_read BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at INTEGER NOT NULL,
    read_at INTEGER,
    
    INDEX idx_cp_notifications_recipient (recipient_person_id),
    INDEX idx_cp_notifications_unread (recipient_person_id, is_read),
    INDEX idx_cp_notifications_created (created_at)
);

-- 6. CP Audit Log Table
-- Complete audit trail of all CP system actions
CREATE TABLE IF NOT EXISTS cp_audit_log (
    id TEXT PRIMARY KEY,
    
    -- Action details
    action_type TEXT NOT NULL,  -- 'report_created', 'review_completed', 'user_banned', 'permission_revoked', 'appeal_submitted', 'admin_override', etc.
    actor_person_id INTEGER,  -- Who performed the action
    actor_username TEXT,
    
    -- Target
    target_user_id TEXT,
    target_person_id INTEGER,
    target_username TEXT,
    
    -- Related entities
    related_report_id TEXT,
    related_appeal_id TEXT,
    
    -- Details
    action_details TEXT,  -- JSON string with additional details
    
    -- Timestamp
    created_at INTEGER NOT NULL,
    
    INDEX idx_cp_audit_action (action_type),
    INDEX idx_cp_audit_actor (actor_person_id),
    INDEX idx_cp_audit_target (target_person_id),
    INDEX idx_cp_audit_created (created_at)
);

-- 7. Moderator CP Assignments Table
-- Track which moderators can review CP in which communities
CREATE TABLE IF NOT EXISTS moderator_cp_assignments (
    id TEXT PRIMARY KEY,
    
    -- Moderator info
    person_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    
    -- Community assignment
    community_id INTEGER NOT NULL,
    
    -- CP review permission (admin can toggle this per moderator)
    can_review_cp BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    
    -- Constraints
    UNIQUE(person_id, community_id),
    INDEX idx_mod_cp_community (community_id),
    INDEX idx_mod_cp_person (person_id),
    INDEX idx_mod_cp_can_review (can_review_cp)
);

-- ==========================================
-- SQLITE-SPECIFIC FUNCTIONS (for bitcoincash_service)
-- ==========================================

-- Insert default permissions for existing users
-- This should be run manually or via migration script
-- INSERT INTO user_cp_permissions (user_id, person_id, username, can_report_cp, can_review_cp, is_banned, created_at, updated_at)
-- SELECT user_id, person_id, username, TRUE, FALSE, FALSE, strftime('%s', 'now'), strftime('%s', 'now')
-- FROM (SELECT DISTINCT user_id FROM user_credits);

-- ==========================================
-- POSTGRESQL-SPECIFIC TRIGGERS (for Lemmy backend)
-- ==========================================
-- These will be created separately in a PostgreSQL migration file

-- Trigger to auto-hide content when reported
-- Trigger to notify moderators when CP report is created
-- Trigger to auto-delete old unreviewed admin cases after 1 week
-- Trigger to auto-unban users after 3 months

-- ==========================================
-- END OF MIGRATION
-- ==========================================

-- Verification queries
-- SELECT COUNT(*) FROM user_cp_permissions;
-- SELECT COUNT(*) FROM cp_reports;
-- SELECT COUNT(*) FROM cp_reviews;
-- SELECT COUNT(*) FROM cp_appeals;
-- SELECT COUNT(*) FROM cp_notifications;
