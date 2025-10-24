#!/bin/bash
# Annual Membership System - Quick Test Script

echo "=========================================="
echo "Annual Membership System - API Tests"
echo "=========================================="
echo ""

# Get API key from .env
API_KEY=$(grep LEMMY_API_KEY /home/user/Oratio/oratio/.env | cut -d'=' -f2)

echo "1. Testing Membership Price API..."
PRICE_RESPONSE=$(curl -s http://localhost:8081/api/membership/price)
echo "$PRICE_RESPONSE" | python3 -m json.tool
echo ""

if echo "$PRICE_RESPONSE" | grep -q "bch_amount"; then
    echo "✅ Price API working"
else
    echo "❌ Price API failed"
    exit 1
fi

echo ""
echo "2. Testing Health Check..."
HEALTH_RESPONSE=$(curl -s http://localhost:8081/health)
echo "$HEALTH_RESPONSE" | python3 -m json.tool
echo ""

if echo "$HEALTH_RESPONSE" | grep -q '"status": "ok"'; then
    echo "✅ Health check passed"
else
    echo "❌ Health check failed"
    exit 1
fi

echo ""
echo "3. Testing Membership Status API..."
STATUS_RESPONSE=$(curl -s -H "X-API-Key: $API_KEY" http://localhost:8081/api/membership/status/testuser)
echo "$STATUS_RESPONSE" | python3 -m json.tool
echo ""

if echo "$STATUS_RESPONSE" | grep -q "is_active"; then
    echo "✅ Membership status API working"
else
    echo "❌ Membership status API failed"
    exit 1
fi

echo ""
echo "4. Testing User Credit API..."
CREDIT_RESPONSE=$(curl -s -H "X-API-Key: $API_KEY" http://localhost:8081/api/user_credit/testuser)
echo "$CREDIT_RESPONSE" | python3 -m json.tool
echo ""

if echo "$CREDIT_RESPONSE" | grep -q "credit_balance"; then
    echo "✅ User credit API working"
else
    echo "❌ User credit API failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ All API tests passed!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Visit https://your-domain.com/wallet"
echo "2. Login and check the wallet page"
echo "3. Try purchasing an annual membership"
echo ""
echo "Current BCH price:"
echo "$PRICE_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"  1 BCH = \${data['price']['price_per_bch']:.2f} USD\"); print(f\"  Membership = {data['price']['bch_amount']:.8f} BCH (~\${data['price']['usd_amount']} USD)\")"
echo ""
