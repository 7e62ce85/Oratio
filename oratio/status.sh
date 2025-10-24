#!/bin/bash

# Quick Status Dashboard for Oratio System
# Shows system health at a glance

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

clear
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${BLUE}       ORATIO SYSTEM STATUS DASHBOARD${NC}"
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# System Memory
echo -e "${BOLD}1. SYSTEM MEMORY${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TOTAL_MEM=$(free -h | awk '/^Mem:/ {print $2}')
USED_MEM=$(free -h | awk '/^Mem:/ {print $3}')
FREE_MEM=$(free -h | awk '/^Mem:/ {print $4}')
AVAIL_MEM=$(free -h | awk '/^Mem:/ {print $7}')

echo -e "Total:     ${BOLD}$TOTAL_MEM${NC}"
echo -e "Used:      $USED_MEM"
echo -e "Free:      $FREE_MEM"
echo -e "Available: ${GREEN}$AVAIL_MEM${NC}"
echo ""

# Electron Cash Container
echo -e "${BOLD}2. ELECTRON CASH CONTAINER${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if docker ps --format "{{.Names}}" | grep -q "^electron-cash$"; then
    EC_MEM=$(docker stats --no-stream --format "{{.MemUsage}}" electron-cash | awk '{print $1}')
    EC_LIMIT=$(docker stats --no-stream --format "{{.MemUsage}}" electron-cash | awk '{print $3}')
    EC_PERCENT=$(docker stats --no-stream --format "{{.MemPerc}}" electron-cash)
    EC_PROCESSES=$(docker top electron-cash 2>/dev/null | grep -c python || echo "0")
    
    # Parse memory to check threshold
    EC_MEM_MB=$(echo $EC_MEM | sed 's/MiB//' | sed 's/GiB/*1024/' | bc 2>/dev/null | cut -d'.' -f1)
    
    echo -e "Status:    ${GREEN}✅ Running${NC}"
    echo -e "Memory:    $EC_MEM / $EC_LIMIT ($EC_PERCENT)"
    echo -e "Processes: $EC_PROCESSES python processes"
    
    # Health indicators
    if [ "$EC_MEM_MB" -gt 500 ]; then
        echo -e "Health:    ${YELLOW}⚠️  High memory usage${NC}"
    elif [ "$EC_PROCESSES" -gt 10 ]; then
        echo -e "Health:    ${YELLOW}⚠️  Too many processes${NC}"
    else
        echo -e "Health:    ${GREEN}✅ Healthy${NC}"
    fi
else
    echo -e "Status:    ${RED}❌ Not Running${NC}"
fi
echo ""

# BCH Payment Service
echo -e "${BOLD}2.5 BCH PAYMENT SERVICE (ZERO-CONF)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if docker ps --format "{{.Names}}" | grep -q "bitcoincash-service"; then
    BC_MEM=$(docker stats --no-stream --format "{{.MemUsage}}" bitcoincash-service | awk '{print $1}')
    BC_LIMIT=$(docker stats --no-stream --format "{{.MemUsage}}" bitcoincash-service | awk '{print $3}')
    BC_PERCENT=$(docker stats --no-stream --format "{{.MemPerc}}" bitcoincash-service)
    
    # Check HTTP health
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/health 2>/dev/null)
    
    echo -e "Status:    ${GREEN}✅ Running${NC}"
    echo -e "Memory:    $BC_MEM / $BC_LIMIT ($BC_PERCENT)"
    
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "Health:    ${GREEN}✅ Healthy (HTTP 200)${NC}"
        
        # Get Zero-Conf status
        ZERO_CONF=$(docker exec bitcoincash-service python3 -c "from config import ZERO_CONF_ENABLED, MIN_CONFIRMATIONS; print(f'Zero-Conf: {ZERO_CONF_ENABLED}, Min: {MIN_CONFIRMATIONS}')" 2>/dev/null || echo "N/A")
        echo -e "Config:    $ZERO_CONF"
    else
        echo -e "Health:    ${YELLOW}⚠️  Unhealthy (HTTP $HTTP_CODE)${NC}"
    fi
else
    echo -e "Status:    ${RED}❌ Not Running${NC}"
fi
echo ""

# All Containers
echo -e "${BOLD}3. ALL CONTAINERS${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Size}}" | head -11
echo ""

# Recent Health Checks
echo -e "${BOLD}4. RECENT HEALTH CHECKS${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -f /home/user/Oratio/oratio/logs/health_check.log ]; then
    echo "Last 5 entries:"
    tail -5 /home/user/Oratio/oratio/logs/health_check.log
else
    echo "No health check logs yet"
fi
echo ""

# Automated Monitoring Status
echo -e "${BOLD}5. AUTOMATED MONITORING${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if crontab -l 2>/dev/null | grep -q "health_check_and_restart.sh"; then
    echo -e "Status:    ${GREEN}✅ Active${NC}"
    echo "Schedule:  Every hour (automatic)"
    echo "Next run:  Top of next hour"
    
    # Show cron jobs
    echo ""
    echo "Active cron jobs:"
    crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" | grep "Oratio\|health"
else
    echo -e "Status:    ${RED}❌ Not configured${NC}"
    echo "To enable: crontab /home/user/Oratio/oratio/electron_cash_crontab"
fi
echo ""

# Quick Actions
echo -e "${BOLD}6. QUICK ACTIONS${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Manual health check: /home/user/Oratio/oratio/health_check_and_restart.sh"
echo "View live logs:      docker logs -f electron-cash"
echo "Restart container:   cd /home/user/Oratio/oratio && docker-compose restart electron-cash"
echo "View cron logs:      tail -f /home/user/Oratio/oratio/logs/cron.log"
echo ""

echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
