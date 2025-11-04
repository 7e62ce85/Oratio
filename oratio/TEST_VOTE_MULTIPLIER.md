# Vote Multiplier Test Guide

## ✅ System Status

**Current Status**: Vote multiplier system is FULLY OPERATIONAL (FIXED 2025-11-02)

- ✅ SQL triggers installed and FIXED for mobile browser compatibility
- ✅ Membership sync service running  
- ✅ Membership data synced (user: gookjob)
- ✅ All containers running
- ✅ Vote toggle bug FIXED (upvotes/downvotes now properly tracked)

## 🧪 How to Test the 5x Vote Multiplier

The vote multiplier only affects **NEW votes** going forward. Existing votes from before the trigger was installed are NOT retroactively multiplied.

### Method 1: Vote on a New Post (Recommended)

1. **Create a new post** (as any user)
2. **Log in as membership user** (gookjob)
3. **Upvote the new post**
4. **Check the post score** - it should show +5 instead of +1

### Method 2: Re-vote on Existing Post

1. **Log in as membership user** (gookjob)
2. **Remove your upvote** from an existing post (click the upvote button to undo)
3. **Wait 2 seconds**
4. **Upvote again**
5. **Check the aggregate** - the vote should now count as 5x

### Method 3: Database Verification (Technical)

```bash
# Before vote: Check current post aggregates
docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
  "SELECT post_id, score, upvotes FROM post_aggregates WHERE post_id = YOUR_POST_ID;"

# Have membership user vote on the post via UI

# After vote: Check updated aggregates
docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
  "SELECT post_id, score, upvotes FROM post_aggregates WHERE post_id = YOUR_POST_ID;"

# The difference should be +5 for membership user votes
```

## 📊 Current System State

### Membership User
```
User: gookjob
Status: Active (✓)
Expires: 2026-10-28 (365 days from now)
```

### Existing Votes (Before Trigger)
These votes still count as 1x because they were cast before the trigger:
- Post 42: voted 2025-10-28 (score currently: 3)
- Post 41: voted 2025-10-27
- Post 36: voted 2025-10-18

## 🔍 Verification Commands

### Check trigger is enabled:
```bash
docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
  "SELECT tgname, tgenabled FROM pg_trigger WHERE tgname = 'membership_post_vote_multiplier';"
```
Expected: Should show trigger with tgenabled = 'O' (enabled)

### Check membership sync:
```bash
docker-compose logs --tail=10 bitcoincash-service | grep -i "membership sync"
```
Expected: Should show "Successfully synced 1 memberships"

### Check synced memberships:
```bash
docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
  "SELECT user_id, is_active, expires_at FROM user_memberships;"
```
Expected: Should show gookjob with is_active = t

## 💡 Important Notes

1. **Only affects posts, not comments** - As requested, the multiplier only applies to post votes
2. **Only affects NEW votes** - Votes cast before trigger installation count as 1x
3. **Automatic sync** - Membership status syncs every 60 seconds
4. **Real-time** - New votes are multiplied immediately via database trigger

## 🔧 Recent Fixes (2025-11-02)

### Mobile Browser Vote Toggle Bug - FIXED ✅

**Problem**: On mobile browsers, when membership users toggled their vote (clicking the same button twice), the vote counts were incorrect:
- Click upvote: +5 ✅
- Click upvote again (toggle off): -1 ❌ (should be -5)
- Result: Upvotes and downvotes accumulated incorrectly (e.g., post 54 showed upvotes=33, downvotes=28 instead of upvotes=5, downvotes=0)

**Root Cause**: The trigger function was not properly tracking upvote/downvote removals separately. It only looked at score_diff and incorrectly added to both upvotes AND downvotes cumulatively.

**Solution**: 
1. Updated `apply_post_vote_multiplier()` function to track `upvote_diff` and `downvote_diff` separately
2. Now correctly handles all operations:
   - INSERT: Adds to upvotes OR downvotes (not both)
   - DELETE: Removes from upvotes OR downvotes (whichever was toggled off)
   - UPDATE: Properly handles vote flips (up→down or down→up)
3. Ran migration script to recalculate all existing post aggregates

**Files Updated**:
- `/oratio/migrations/membership_vote_multiplier.sql` - Fixed trigger logic
- `/oratio/migrations/fix_vote_aggregates.sql` - One-time fix for existing data

**Verification**: Post 54 now correctly shows score=5, upvotes=5, downvotes=0 (was score=5, upvotes=33, downvotes=28)

## 🐛 Troubleshooting

If votes still count as 1x:

1. **Verify trigger is installed**:
   ```bash
   docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
     "SELECT COUNT(*) FROM pg_trigger WHERE tgname = 'membership_post_vote_multiplier';"
   ```
   Should return: 1

2. **Verify membership is synced**:
   ```bash
   docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
     "SELECT * FROM user_memberships WHERE user_id = 'gookjob';"
   ```
   Should show: is_active = t

3. **Check trigger function**:
   ```bash
   docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
     "SELECT proname FROM pg_proc WHERE proname = 'apply_post_vote_multiplier';"
   ```
   Should return: apply_post_vote_multiplier

4. **View recent logs**:
   ```bash
   docker-compose logs --tail=50 bitcoincash-service | grep -i membership
   ```

## ✨ Expected Behavior (CORRECTED)

### Voting Behavior:

**Non-member vote on post**: 
- Click upvote: +1 score
- Click upvote again (toggle off): -1 score (back to 0)
- Click downvote: -1 score  
- Click downvote again (toggle off): +1 score (back to 0)

**Member vote on post** (gookjob):
- Click upvote: +5 score
- Click upvote again (toggle off): -5 score (back to 0)
- Click downvote: -5 score
- Click downvote again (toggle off): +5 score (back to 0)

### How it Works:

Lemmy's default system applies the base vote (+1 or -1), then our trigger adds EXTRA votes:
- **Normal users**: 0 extra votes (1x total)
- **Membership users**: +4 extra votes (5x total)

This ensures vote toggling works correctly - when you toggle off, all multiplied votes are removed properly.

**This creates a significant advantage for membership users' votes!**
