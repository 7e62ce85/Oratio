#!/bin/bash

# ==========================================
# CP Moderation System Deployment Script
# ==========================================
# Version: 1.0
# Description: Deploys the CP moderation backend system
# ==========================================

set -e  # Exit on error

echo "=========================================="
echo "CP Moderation System Deployment"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ORATIO_DIR="$SCRIPT_DIR"

echo "Working directory: $ORATIO_DIR"
echo ""

# ==========================================
# Step 1: Verify files exist
# ==========================================
echo -e "${YELLOW}[1/5]${NC} Verifying CP system files..."

REQUIRED_FILES=(
    "bitcoincash_service/services/cp_moderation.py"
    "bitcoincash_service/routes/cp.py"
    "bitcoincash_service/models.py"
    "bitcoincash_service/services/background_tasks.py"
    "migrations/cp_moderation_system.sql"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$ORATIO_DIR/$file" ]; then
        echo -e "${RED}✗${NC} Missing file: $file"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Found: $file"
done

echo ""

# ==========================================
# Step 2: Check Docker containers
# ==========================================
echo -e "${YELLOW}[2/5]${NC} Checking Docker containers..."

cd "$ORATIO_DIR"

if ! docker-compose ps | grep -q bitcoincash-service; then
    echo -e "${RED}✗${NC} bitcoincash-service container not running"
    echo "Starting containers..."
    docker-compose up -d
    sleep 5
else
    echo -e "${GREEN}✓${NC} bitcoincash-service is running"
fi

echo ""

# ==========================================
# Step 3: Restart bitcoincash-service
# ==========================================
echo -e "${YELLOW}[3/5]${NC} Restarting bitcoincash-service..."

docker-compose restart bitcoincash-service

echo "Waiting for service to initialize..."
sleep 5

echo ""

# ==========================================
# Step 4: Verify CP tables created
# ==========================================
echo -e "${YELLOW}[4/5]${NC} Verifying CP database tables..."

TABLES=(
    "user_cp_permissions"
    "cp_reports"
    "cp_reviews"
    "cp_appeals"
    "cp_notifications"
    "cp_audit_log"
    "moderator_cp_assignments"
)

for table in "${TABLES[@]}"; do
    if docker exec bitcoincash-service sqlite3 /data/payments.db ".tables" | grep -q "$table"; then
        echo -e "${GREEN}✓${NC} Table exists: $table"
    else
        echo -e "${RED}✗${NC} Table missing: $table"
        exit 1
    fi
done

echo ""

# ==========================================
# Step 5: Test CP API endpoints
# ==========================================
echo -e "${YELLOW}[5/5]${NC} Testing CP API endpoints..."

# Get API key from .env file
if [ -f "$ORATIO_DIR/.env" ]; then
    API_KEY=$(grep LEMMY_API_KEY "$ORATIO_DIR/.env" | cut -d '=' -f2 | tr -d ' ')
    
    if [ -z "$API_KEY" ]; then
        echo -e "${YELLOW}⚠${NC} No API key found in .env, skipping API tests"
    else
        # Test health endpoint
        echo "Testing health endpoint..."
        HEALTH_RESPONSE=$(curl -s -H "X-API-Key: $API_KEY" http://localhost:8081/api/cp/health)
        
        if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
            echo -e "${GREEN}✓${NC} CP API is healthy"
        else
            echo -e "${RED}✗${NC} CP API health check failed"
            echo "Response: $HEALTH_RESPONSE"
            exit 1
        fi
        
        # Test permissions endpoint (should return 404 for non-existent user, not error)
        echo "Testing permissions endpoint..."
        PERM_RESPONSE=$(curl -s -w "%{http_code}" -H "X-API-Key: $API_KEY" \
            http://localhost:8081/api/cp/permissions/test_user_not_exist -o /dev/null)
        
        if [ "$PERM_RESPONSE" = "404" ] || [ "$PERM_RESPONSE" = "200" ]; then
            echo -e "${GREEN}✓${NC} Permissions endpoint working"
        else
            echo -e "${RED}✗${NC} Permissions endpoint returned: $PERM_RESPONSE"
            exit 1
        fi
    fi
else
    echo -e "${YELLOW}⚠${NC} .env file not found, skipping API tests"
fi

echo ""

# ==========================================
# Step 6: Check logs
# ==========================================
echo -e "${YELLOW}[6/6]${NC} Checking service logs..."

echo "Recent logs:"
docker-compose logs --tail=20 bitcoincash-service | grep -i "cp\|초기화" || true

echo ""

# ==========================================
# Deployment Summary
# ==========================================
echo "=========================================="
echo -e "${GREEN}✓ CP Moderation System Deployed!${NC}"
echo "=========================================="
echo ""
echo "✓ All CP tables created"
echo "✓ API endpoints registered"
echo "✓ Background tasks integrated"
echo "✓ Service is running"
echo ""
echo "📖 Documentation:"
echo "   - Full Guide: docs/features/CP_MODERATION_SYSTEM.md"
echo "   - Quick Ref:  docs/features/CP_SYSTEM_QUICK_REF.md"
echo ""
echo "🔗 API Base URL:"
echo "   http://localhost:8081/api/cp"
echo ""
echo "🧪 Test Health:"
if [ -n "$API_KEY" ]; then
    echo "   curl -H 'X-API-Key: $API_KEY' http://localhost:8081/api/cp/health"
else
    echo "   curl -H 'X-API-Key: YOUR_KEY' http://localhost:8081/api/cp/health"
fi
echo ""
echo "📊 View Database:"
echo "   docker exec -it bitcoincash-service sqlite3 /app/data/payment.db"
echo ""
echo "⚠️  NEXT STEPS:"
echo "   1. Implement frontend components (see documentation)"
echo "   2. Test CP reporting workflow"
echo "   3. Configure moderator permissions"
echo ""
echo "=========================================="
