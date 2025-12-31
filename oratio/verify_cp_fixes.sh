#!/bin/bash
# CP Moderation System - Fix Verification Script
# Date: 2025-11-25

echo "======================================"
echo "CP Moderation System - Fix Verification"
echo "======================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running from oratio directory
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}Error: Must run from /home/user/Oratio/oratio directory${NC}"
    exit 1
fi

echo "1️⃣  Checking Report Ability Revoked Status..."
echo "----------------------------------------"
docker exec bitcoincash-service sqlite3 /data/payments.db << 'EOF'
.mode column
.headers on
SELECT 
    username,
    can_report_cp,
    CASE 
        WHEN report_ability_revoked_at IS NULL THEN 'Never revoked'
        ELSE datetime(report_ability_revoked_at, 'unixepoch')
    END as revoked_until
FROM user_cp_permissions 
WHERE username IN ('cpcp2', 'test_user')
ORDER BY username;
EOF
echo ""

echo "2️⃣  Checking Ban Status..."
echo "----------------------------------------"
docker exec bitcoincash-service sqlite3 /data/payments.db << 'EOF'
.mode column
.headers on
SELECT 
    username,
    is_banned,
    ban_count,
    CASE 
        WHEN ban_end IS NULL THEN 'N/A'
        ELSE datetime(ban_end, 'unixepoch')
    END as ban_expires,
    CASE 
        WHEN ban_end IS NULL THEN 0
        ELSE CAST((ban_end - strftime('%s', 'now')) / 86400.0 AS INTEGER)
    END as days_remaining
FROM user_cp_permissions 
WHERE username IN ('cpcp', 'cpcpcp')
ORDER BY username;
EOF
echo ""

echo "3️⃣  Checking CP Hidden Posts..."
echo "----------------------------------------"
docker exec bitcoincash-service sqlite3 /data/payments.db << 'EOF'
.mode column
.headers on
SELECT 
    content_type,
    content_id,
    creator_username,
    status,
    content_hidden,
    datetime(created_at, 'unixepoch') as reported_at
FROM cp_reports
WHERE content_hidden = 1
ORDER BY created_at DESC
LIMIT 5;
EOF
echo ""

echo "4️⃣  Checking Moderator Permissions..."
echo "----------------------------------------"
docker exec bitcoincash-service sqlite3 /data/payments.db << 'EOF'
.mode column
.headers on
SELECT 
    username,
    has_cp_review_permission,
    can_report_cp
FROM user_cp_permissions 
WHERE has_cp_review_permission = 1;
EOF
echo ""

echo "5️⃣  Checking Services Status..."
echo "----------------------------------------"
docker-compose ps | grep -E "(lemmy-ui|proxy|bitcoincash-service)" | awk '{print $1, $NF}'
echo ""

echo "6️⃣  Checking Nginx Configuration..."
echo "----------------------------------------"
if docker-compose exec proxy nginx -t 2>&1 | grep -q "successful"; then
    echo -e "${GREEN}✅ Nginx configuration is valid${NC}"
else
    echo -e "${RED}❌ Nginx configuration has errors${NC}"
fi
echo ""

echo "======================================"
echo "Manual Testing Required:"
echo "======================================"
echo ""
echo "📋 Test 1: Report Ability Revoked Toast"
echo "   1. Login as 'cpcp2' user"
echo "   2. Click 'Report CP' on any post/comment"
echo "   3. Expected: Toast shows 'Revoked until YYYY-MM-DD (X days remaining). Appeal at /cp/appeal'"
echo ""

echo "📋 Test 2: Admin/Mod CP Post Access"
echo "   1. Identify CP hidden post ID from above list"
echo "   2. Try accessing as regular user (should be 403)"
echo "   3. Login as admin and access same post (should work)"
echo "   4. Login as moderator and access same post (should work)"
echo ""

echo "📋 Test 3: Ban Login Toast"
echo "   1. Go to https://oratio.space/login"
echo "   2. Try to login as 'cpcp' user"
echo "   3. Expected: Toast shows 'You are banned from this site until YYYY-MM-DD (X days remaining)'"
echo ""

echo "======================================"
echo "Quick Access URLs:"
echo "======================================"
echo "Login: https://oratio.space/login"
echo "Admin Panel: https://oratio.space/cp/admin-panel"
echo "Moderator Review: https://oratio.space/cp/moderator-review"
echo "Appeal Form: https://oratio.space/cp/appeal"
echo ""

echo "======================================"
echo "Verification Complete!"
echo "======================================"
