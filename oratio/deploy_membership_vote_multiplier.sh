#!/bin/bash

# Deployment script for Membership Vote Multiplier (5x votes for membership users)
# This script deploys the vote multiplier system for Oratio

set -e  # Exit on any error

echo "=========================================="
echo "Membership Vote Multiplier Deployment"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running from correct directory
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}Error: Please run this script from the /home/user/Oratio/oratio directory${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Checking prerequisites...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo "Please run: bash refresh_passwords.sh first"
    exit 1
fi

# Check if POSTGRES_PASSWORD is set in .env
if ! grep -q "POSTGRES_PASSWORD=" .env; then
    echo -e "${RED}Error: POSTGRES_PASSWORD not found in .env!${NC}"
    echo "Please run: bash refresh_passwords.sh first"
    exit 1
fi

echo -e "${GREEN}✓ Prerequisites checked${NC}"
echo ""

echo -e "${YELLOW}Step 2: Applying SQL migration (creating triggers and tables)...${NC}"

# Get postgres password from .env
POSTGRES_PASSWORD=$(grep "POSTGRES_PASSWORD=" .env | cut -d'=' -f2)

# Wait for postgres to be ready
echo "Waiting for PostgreSQL to be ready..."
max_attempts=30
attempt=0
until docker exec postgres pg_isready -U lemmy > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ $attempt -eq $max_attempts ]; then
        echo -e "${RED}Error: PostgreSQL is not responding${NC}"
        exit 1
    fi
    echo "Attempt $attempt/$max_attempts..."
    sleep 2
done

echo -e "${GREEN}✓ PostgreSQL is ready${NC}"

# Apply the SQL migration
echo "Applying migration..."
docker exec -i postgres psql -U lemmy -d lemmy < migrations/membership_vote_multiplier.sql

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ SQL migration applied successfully${NC}"
else
    echo -e "${RED}Error: Failed to apply SQL migration${NC}"
    exit 1
fi
echo ""

echo -e "${YELLOW}Step 3: Restarting bitcoincash-service to enable membership sync...${NC}"
docker compose restart bitcoincash-service

# Wait for service to be ready
sleep 5

if docker ps | grep -q "bitcoincash-service"; then
    echo -e "${GREEN}✓ bitcoincash-service restarted${NC}"
else
    echo -e "${RED}Error: bitcoincash-service failed to start${NC}"
    exit 1
fi
echo ""

echo -e "${YELLOW}Step 4: Verifying installation...${NC}"

# Check if triggers exist
TRIGGER_CHECK=$(docker exec -i postgres psql -U lemmy -d lemmy -t -c "SELECT COUNT(*) FROM pg_trigger WHERE tgname = 'membership_post_vote_multiplier';")

if [ "$TRIGGER_CHECK" -gt 0 ]; then
    echo -e "${GREEN}✓ Vote multiplier trigger installed${NC}"
else
    echo -e "${RED}✗ Vote multiplier trigger not found${NC}"
fi

# Check if table exists
TABLE_CHECK=$(docker exec -i postgres psql -U lemmy -d lemmy -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'user_memberships';")

if [ "$TABLE_CHECK" -gt 0 ]; then
    echo -e "${GREEN}✓ user_memberships table created${NC}"
else
    echo -e "${RED}✗ user_memberships table not found${NC}"
fi

# Check bitcoincash-service logs for sync service
echo ""
echo "Checking membership sync service logs..."
docker compose logs --tail=20 bitcoincash-service | grep -i "membership sync" && echo -e "${GREEN}✓ Membership sync service is running${NC}" || echo -e "${YELLOW}⚠ Check logs manually if needed${NC}"

echo ""
echo "=========================================="
echo -e "${GREEN}Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo "📊 System Status:"
echo "  - Vote Multiplier: ACTIVE (5x for membership users)"
echo "  - Membership Sync: Running every 60 seconds"
echo "  - Database Triggers: Installed"
echo ""
echo "📝 What happens now:"
echo "  1. When a membership user votes on a post, their vote counts as 5x"
echo "  2. Membership status syncs from SQLite → PostgreSQL every 60 seconds"
echo "  3. Database triggers automatically apply the multiplier"
echo ""
echo "🧪 Testing:"
echo "  1. Purchase a membership for a test user"
echo "  2. Have that user vote on a post"
echo "  3. Check post_aggregates to see vote count increased by 5"
echo ""
echo "📖 View logs:"
echo "  docker compose logs -f bitcoincash-service | grep -i membership"
echo ""
echo "🔍 Verify membership sync:"
echo "  docker exec -i postgres psql -U lemmy -d lemmy -c 'SELECT * FROM user_memberships;'"
echo ""
echo "⚠️  Note: You may need to refresh passwords first if this is a new deployment:"
echo "  bash refresh_passwords.sh"
echo "  Then restart all services:"
echo "  docker compose down && docker compose up -d"
echo ""
