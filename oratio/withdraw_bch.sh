#!/bin/bash
# ==============================================
# BCH Withdrawal Script - Admin Only
# Transfer BCH from ElectronCash wallet to specified address
# ==============================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}        BCH WITHDRAWAL - ADMIN ONLY${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""

# Check if running as expected user
if [ "$USER" != "user" ] && [ "$USER" != "root" ]; then
    echo -e "${RED}❌ Unauthorized user: $USER${NC}"
    exit 1
fi

# Check container
if ! docker ps | grep -q bitcoincash-service; then
    echo -e "${RED}❌ BCH service is not running!${NC}"
    exit 1
fi

# Get current balance
echo -e "${GREEN}💰 Current Wallet Balance:${NC}"
docker exec bitcoincash-service python3 -c "
import logging
logging.disable(logging.CRITICAL)
from services.electron_cash import ElectronCashClient
client = ElectronCashClient()
info = client.call_method('getbalance')
if info:
    confirmed = float(info.get('confirmed', '0'))
    unconfirmed = float(info.get('unconfirmed', '0'))
    print(f'   Confirmed:   {confirmed:.8f} BCH')
    print(f'   Unconfirmed: {unconfirmed:.8f} BCH')
    print(f'   Available:   {confirmed:.8f} BCH (only confirmed can be sent)')
" 2>/dev/null
echo ""

# Default payout wallet
DEFAULT_PAYOUT=$(grep PAYOUT_WALLET /home/user/Oratio/oratio/.env | cut -d'=' -f2)

# Get destination address
echo -e "${YELLOW}📤 Enter destination address${NC}"
echo -e "   (Press Enter to use default PAYOUT_WALLET)"
echo -e "   Default: ${DEFAULT_PAYOUT}"
read -p "   Address: " DEST_ADDRESS

if [ -z "$DEST_ADDRESS" ]; then
    DEST_ADDRESS="$DEFAULT_PAYOUT"
fi

# Validate address format
if [[ ! "$DEST_ADDRESS" =~ ^bitcoincash: ]] && [[ ! "$DEST_ADDRESS" =~ ^q ]]; then
    echo -e "${RED}❌ Invalid BCH address format${NC}"
    exit 1
fi

echo ""

# Get amount
echo -e "${YELLOW}💵 Enter amount to send (in BCH)${NC}"
echo -e "   Example: 0.01"
read -p "   Amount: " AMOUNT

# Validate amount
if ! [[ "$AMOUNT" =~ ^[0-9]+\.?[0-9]*$ ]]; then
    echo -e "${RED}❌ Invalid amount format${NC}"
    exit 1
fi

if (( $(echo "$AMOUNT <= 0" | bc -l) )); then
    echo -e "${RED}❌ Amount must be greater than 0${NC}"
    exit 1
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}⚠️  TRANSACTION SUMMARY${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "   To:     ${DEST_ADDRESS}"
echo -e "   Amount: ${AMOUNT} BCH"
echo -e "   Fee:    ~0.00001 BCH (auto)"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""

# Double confirmation
echo -e "${RED}⚠️  WARNING: This action is IRREVERSIBLE!${NC}"
read -p "   Type 'SEND' to confirm: " CONFIRM

if [ "$CONFIRM" != "SEND" ]; then
    echo -e "${YELLOW}❌ Transaction cancelled${NC}"
    exit 0
fi

echo ""
echo -e "${CYAN}🔄 Processing transaction...${NC}"

# Execute transaction
RESULT=$(docker exec bitcoincash-service python3 -c "
import logging
logging.disable(logging.CRITICAL)
from services.electron_cash import ElectronCashClient
import json

client = ElectronCashClient()
dest = '$DEST_ADDRESS'
amount = float('$AMOUNT')

# Add bitcoincash: prefix if not present
if not dest.startswith('bitcoincash:'):
    dest = 'bitcoincash:' + dest

try:
    # Create and broadcast transaction
    result = client.call_method('payto', [dest, amount])
    if result:
        # Sign and broadcast
        signed = client.call_method('signtransaction', [result])
        if signed:
            txid = client.call_method('broadcast', [signed])
            if txid:
                print(json.dumps({'success': True, 'txid': txid}))
            else:
                print(json.dumps({'success': False, 'error': 'Broadcast failed'}))
        else:
            print(json.dumps({'success': False, 'error': 'Signing failed'}))
    else:
        print(json.dumps({'success': False, 'error': 'Transaction creation failed'}))
except Exception as e:
    print(json.dumps({'success': False, 'error': str(e)}))
" 2>/dev/null)

# Parse result
if echo "$RESULT" | grep -q '"success": true'; then
    TXID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['txid'])")
    echo ""
    echo -e "${GREEN}✅ Transaction sent successfully!${NC}"
    echo -e "   TXID: ${TXID}"
    echo ""
    echo -e "   View on explorer:"
    echo -e "   https://blockchair.com/bitcoin-cash/transaction/${TXID}"
    
    # Log the transaction
    LOG_FILE="/home/user/Oratio/oratio/logs/withdrawals.log"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$(date '+%Y-%m-%d %H:%M:%S') | TXID: ${TXID} | Amount: ${AMOUNT} BCH | To: ${DEST_ADDRESS}" >> "$LOG_FILE"
    echo ""
    echo -e "${CYAN}📝 Transaction logged to: ${LOG_FILE}${NC}"
else
    ERROR=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', 'Unknown error'))" 2>/dev/null || echo "$RESULT")
    echo ""
    echo -e "${RED}❌ Transaction failed!${NC}"
    echo -e "   Error: ${ERROR}"
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
