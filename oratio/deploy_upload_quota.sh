#!/bin/bash
# Upload Quota System Deployment Script
# Version: 1.0
# Created: 2025-11-04

set -e

echo "🚀 Deploying Upload Quota System..."
echo "======================================"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Navigate to project directory
cd /home/user/Oratio/oratio

echo -e "${BLUE}Step 1: Applying database migration...${NC}"
docker exec -it bitcoincash-service sqlite3 /app/data/payment.db < migrations/upload_quota_system.sql
echo -e "${GREEN}✅ Database migration applied${NC}"

echo ""
echo -e "${BLUE}Step 2: Restarting backend service...${NC}"
docker-compose restart bitcoincash-service
sleep 3
echo -e "${GREEN}✅ Backend service restarted${NC}"

echo ""
echo -e "${BLUE}Step 3: Rebuilding frontend (this may take 5-10 minutes)...${NC}"
docker-compose stop lemmy-ui
docker-compose rm -f lemmy-ui
docker rmi lemmy-ui-custom:latest 2>/dev/null || true
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui
echo -e "${GREEN}✅ Frontend rebuilt and started${NC}"

echo ""
echo -e "${BLUE}Step 4: Verifying deployment...${NC}"

# Test pricing API
echo -n "Testing pricing API... "
if curl -s http://localhost:8081/api/upload/pricing | grep -q "success"; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌${NC}"
    exit 1
fi

# Check services
echo "Checking services status:"
docker-compose ps | grep -E "bitcoincash|lemmy-ui"

echo ""
echo -e "${GREEN}======================================"
echo "✅ Upload Quota System Deployed!"
echo "======================================${NC}"
echo ""
echo "📝 Next steps:"
echo "  1. Visit http://localhost:1236/my-wallet to see upload quota"
echo "  2. Try uploading an image in a post"
echo "  3. Check logs: docker-compose logs -f bitcoincash-service"
echo ""
echo "📖 Documentation: docs/features/UPLOAD_QUOTA_SYSTEM.md"
echo ""
