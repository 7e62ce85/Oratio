-- Script to fix vote aggregates after vote multiplier implementation
-- This recalculates all post scores, upvotes, and downvotes based on actual votes

-- Create a temporary function to recalculate post aggregates
CREATE OR REPLACE FUNCTION recalculate_post_aggregates()
RETURNS void AS $$
DECLARE
    post_record RECORD;
    total_score INTEGER;
    total_upvotes INTEGER;
    total_downvotes INTEGER;
    vote_record RECORD;
    is_member BOOLEAN;
    vote_multiplier INTEGER;
BEGIN
    -- Loop through all posts
    FOR post_record IN SELECT DISTINCT post_id FROM post_like LOOP
        total_score := 0;
        total_upvotes := 0;
        total_downvotes := 0;
        
        -- Loop through all votes for this post
        FOR vote_record IN 
            SELECT pl.score, p.name as person_name
            FROM post_like pl
            JOIN person p ON pl.person_id = p.id
            WHERE pl.post_id = post_record.post_id
        LOOP
            -- Check if voter is a member
            is_member := check_user_membership(vote_record.person_name);
            
            -- Apply multiplier
            IF is_member THEN
                vote_multiplier := 5;
            ELSE
                vote_multiplier := 1;
            END IF;
            
            -- Add to totals
            total_score := total_score + (vote_record.score * vote_multiplier);
            
            IF vote_record.score = 1 THEN
                total_upvotes := total_upvotes + vote_multiplier;
            ELSE
                total_downvotes := total_downvotes + vote_multiplier;
            END IF;
        END LOOP;
        
        -- Update post_aggregates
        UPDATE post_aggregates
        SET 
            score = total_score,
            upvotes = total_upvotes,
            downvotes = total_downvotes
        WHERE post_id = post_record.post_id;
        
        RAISE NOTICE 'Updated post_id %: score=%, upvotes=%, downvotes=%', 
            post_record.post_id, total_score, total_upvotes, total_downvotes;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Run the recalculation
SELECT recalculate_post_aggregates();

-- Drop the temporary function
DROP FUNCTION recalculate_post_aggregates();

-- Verify results
SELECT post_id, score, upvotes, downvotes 
FROM post_aggregates 
WHERE post_id IN (SELECT DISTINCT post_id FROM post_like)
ORDER BY post_id DESC 
LIMIT 20;
