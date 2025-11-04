-- Membership Vote Multiplier - 5x votes for membership users
-- This script creates PostgreSQL triggers to automatically multiply votes from membership users

-- Function to check if a user has an active membership
CREATE OR REPLACE FUNCTION check_user_membership(user_id_param TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    has_membership BOOLEAN;
BEGIN
    -- Check if user has an active membership in the bitcoincash service database
    -- We'll use a foreign data wrapper or direct connection
    -- For now, we'll check a synced table
    SELECT EXISTS(
        SELECT 1 FROM user_memberships 
        WHERE user_id = user_id_param 
        AND is_active = TRUE 
        AND expires_at > EXTRACT(EPOCH FROM NOW())
    ) INTO has_membership;
    
    RETURN COALESCE(has_membership, FALSE);
END;
$$ LANGUAGE plpgsql;

-- Function to handle post vote multiplier
-- This trigger runs AFTER Lemmy's default triggers, so Lemmy has already
-- applied the base vote (+1 or -1). We only need to add the EXTRA votes.
CREATE OR REPLACE FUNCTION apply_post_vote_multiplier()
RETURNS TRIGGER AS $$
DECLARE
    person_name TEXT;
    is_member BOOLEAN;
    extra_votes INTEGER := 0;
    score_diff INTEGER;
    upvote_diff INTEGER := 0;
    downvote_diff INTEGER := 0;
BEGIN
    -- Get the person's name/id from NEW if available, otherwise from OLD
    IF TG_OP = 'DELETE' THEN
        SELECT name INTO person_name FROM person WHERE id = OLD.person_id;
    ELSE
        SELECT name INTO person_name FROM person WHERE id = NEW.person_id;
    END IF;
    
    -- Check if user is a membership holder
    is_member := check_user_membership(person_name);
    
    -- Calculate extra votes to add (beyond the base vote Lemmy already applied)
    -- Membership users get 5x total (so +4 extra), normal users get 1x (so +0 extra)
    IF is_member THEN
        extra_votes := 4;  -- 5x - 1x = 4x extra
    ELSE
        extra_votes := 0;  -- 1x - 1x = 0x extra (normal users stay at default 1x)
    END IF;
    
    -- Calculate the score difference and upvote/downvote changes based on operation
    IF TG_OP = 'INSERT' THEN
        -- New vote: add extra votes based on vote direction
        score_diff := NEW.score * extra_votes;
        IF NEW.score = 1 THEN
            upvote_diff := extra_votes;  -- Adding upvote
            downvote_diff := 0;
        ELSE
            upvote_diff := 0;
            downvote_diff := extra_votes;  -- Adding downvote
        END IF;
        
    ELSIF TG_OP = 'UPDATE' THEN
        -- Vote changed (e.g., from up to down or vice versa)
        -- This is a vote flip: remove old extra votes and add new extra votes
        score_diff := (NEW.score * extra_votes) - (OLD.score * extra_votes);
        
        -- When flipping from upvote to downvote or vice versa
        IF OLD.score = 1 AND NEW.score = -1 THEN
            -- Was upvote, now downvote
            upvote_diff := -extra_votes;  -- Remove extra upvotes
            downvote_diff := extra_votes;  -- Add extra downvotes
        ELSIF OLD.score = -1 AND NEW.score = 1 THEN
            -- Was downvote, now upvote
            upvote_diff := extra_votes;  -- Add extra upvotes
            downvote_diff := -extra_votes;  -- Remove extra downvotes
        END IF;
        
    ELSIF TG_OP = 'DELETE' THEN
        -- Vote removed (user clicked same button to toggle off)
        score_diff := -(OLD.score * extra_votes);
        IF OLD.score = 1 THEN
            upvote_diff := -extra_votes;  -- Removing upvote
            downvote_diff := 0;
        ELSE
            upvote_diff := 0;
            downvote_diff := -extra_votes;  -- Removing downvote
        END IF;
    END IF;
    
    -- Update post_aggregates with the extra votes
    IF score_diff != 0 OR upvote_diff != 0 OR downvote_diff != 0 THEN
        UPDATE post_aggregates
        SET 
            score = score + score_diff,
            upvotes = upvotes + upvote_diff,
            downvotes = downvotes + downvote_diff
        WHERE post_id = COALESCE(NEW.post_id, OLD.post_id);
    END IF;
    
    -- Return appropriate value based on operation
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for post likes (after standard Lemmy processing)
DROP TRIGGER IF EXISTS membership_post_vote_multiplier ON post_like;
CREATE TRIGGER membership_post_vote_multiplier
    AFTER INSERT OR UPDATE OR DELETE ON post_like
    FOR EACH ROW
    EXECUTE FUNCTION apply_post_vote_multiplier();

-- Create table to sync membership status from bitcoincash service
CREATE TABLE IF NOT EXISTS user_memberships (
    user_id TEXT PRIMARY KEY,
    membership_type TEXT DEFAULT 'annual',
    purchased_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    amount_paid REAL NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    synced_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_memberships_active 
    ON user_memberships(user_id, is_active, expires_at);

-- Create a function to sync membership data from bitcoincash service
CREATE OR REPLACE FUNCTION sync_membership_status()
RETURNS TABLE(synced_count INTEGER) AS $$
DECLARE
    sync_count INTEGER := 0;
BEGIN
    -- This function should be called periodically to sync membership status
    -- from the bitcoincash service database
    -- Implementation depends on how we connect the two databases
    
    -- For now, we'll just return 0
    -- In production, this would use dblink or a similar mechanism
    RETURN QUERY SELECT 0;
END;
$$ LANGUAGE plpgsql;

-- Comments and documentation
COMMENT ON FUNCTION check_user_membership IS 'Checks if a user has an active annual membership';
COMMENT ON FUNCTION apply_post_vote_multiplier IS 'Applies 5x vote multiplier for membership users on posts';
COMMENT ON TRIGGER membership_post_vote_multiplier ON post_like IS 'Trigger to apply vote multiplier for membership users';
COMMENT ON TABLE user_memberships IS 'Synced membership status from bitcoincash service for vote multiplier';
