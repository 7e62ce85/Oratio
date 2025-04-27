#!/bin/bash
# Test script for Bitcoin Cash payment service
# This script performs comprehensive testing of the Bitcoin Cash payment system

# Set colors for better readability
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BOLD}${BLUE}===== BITCOIN CASH PAYMENT SERVICE TEST =====${NC}"
echo -e "${CYAN}Started at:${NC} $(date)"
echo -e "${CYAN}Checking container status...${NC}"

# Check if the container is running
CONTAINER_ID=$(docker ps -q -f name=bitcoincash)
if [ -z "$CONTAINER_ID" ]; then
  echo -e "${RED}❌ Bitcoin Cash service container is not running!${NC}"
  echo -e "   Please ensure the service is up with: ${YELLOW}docker-compose up -d${NC}"
  exit 1
fi

echo -e "${GREEN}✅ Bitcoin Cash service container is running (ID: $CONTAINER_ID)${NC}"
echo -e "${CYAN}Running payment system tests...${NC}"
echo

# Run the test script inside the Docker container
docker exec -t $CONTAINER_ID python3 /app/test_payment.py

# Check if the test was successful
TEST_RESULT=$?
if [ $TEST_RESULT -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✅ Basic functionality tests completed successfully${NC}"
else
  echo -e "${RED}${BOLD}❌ Basic functionality tests failed (Exit code: $TEST_RESULT)${NC}"
fi

# Display current wallet balance
echo -e "\n${BOLD}${BLUE}===== WALLET STATUS =====${NC}"
BALANCE=$(docker exec -t $CONTAINER_ID python3 -c "from services.electron_cash import electron_cash; balance = electron_cash.call_method('getbalance'); print(balance);")
echo -e "${CYAN}Current ElectronCash wallet balance:${NC} ${YELLOW}$BALANCE BCH${NC}"

# Check transaction history
echo -e "\n${BOLD}${BLUE}===== RECENT TRANSACTIONS =====${NC}"
docker exec -t $CONTAINER_ID python3 -c "
from services.electron_cash import electron_cash
import json
history = electron_cash.call_method('history')
if history and len(history) > 0:
    print(f'Found {len(history)} transactions in wallet history')
    recent = history[0]
    print(f'Most recent transaction:')
    print(f'  - TxID: {recent.get(\"txid\", \"N/A\")}')
    print(f'  - Amount: {recent.get(\"value\", \"N/A\")} BCH')
    print(f'  - Date: {recent.get(\"date\", \"N/A\")}')
    print(f'  - Confirmations: {recent.get(\"confirmations\", \"N/A\")}')
else:
    print('No transactions found in wallet history')
"

# Display payout wallet address
echo -e "\n${BOLD}${BLUE}===== CONFIGURATION =====${NC}"
PAYOUT_WALLET=$(docker exec -t $CONTAINER_ID python3 -c "import os; from dotenv import load_dotenv; load_dotenv('/app/.env'); print(os.environ.get('PAYOUT_WALLET', 'Not configured'));")
MIN_CONFIRMATIONS=$(docker exec -t $CONTAINER_ID python3 -c "import os; from dotenv import load_dotenv; load_dotenv('/app/.env'); print(os.environ.get('MIN_CONFIRMATIONS', '1'));")

echo -e "${CYAN}Payout wallet address:${NC} ${PAYOUT_WALLET}"
echo -e "${CYAN}Minimum confirmations:${NC} ${MIN_CONFIRMATIONS}"

# Test the transaction confirmation tracking
echo -e "\n${BOLD}${BLUE}===== CONFIRMATION TRACKING TEST =====${NC}"
if [ -n "$BALANCE" ] && [ "$BALANCE" != "0" ]; then
  docker exec -t $CONTAINER_ID python3 -c "
from direct_payment import direct_payment_handler
import time

# Test real transaction confirmation tracking with a known tx hash
# Using a sample known transaction from Bitcoin Cash blockchain
sample_tx = '42b7f45e5f3ab1e5667dfd6ca2d5ee20c139b04420d52104f2a0c946d88506b4'
print(f'Testing confirmation tracking for transaction: {sample_tx}')
print('Requesting confirmation count...')
start_time = time.time()
confirmations = direct_payment_handler.get_transaction_confirmations(sample_tx)
end_time = time.time()
print(f'Transaction has {confirmations} confirmations')
print(f'Request completed in {end_time - start_time:.2f} seconds')
  "
else
  echo -e "${YELLOW}Skipping confirmation tracking test - wallet balance is zero${NC}"
fi

echo -e "\n${BOLD}${BLUE}===== TEST SUMMARY =====${NC}"
echo -e "${CYAN}Completed at:${NC} $(date)"
echo -e "${CYAN}Service status:${NC} ${GREEN}Running${NC}"
echo -e "${CYAN}Tests result:${NC} $([ $TEST_RESULT -eq 0 ] && echo "${GREEN}Passed${NC}" || echo "${RED}Failed${NC}")"
echo -e "${CYAN}Wallet balance:${NC} ${YELLOW}$BALANCE BCH${NC}"

echo -e "\n${BOLD}${BLUE}===== END OF TESTS =====${NC}"