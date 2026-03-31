#!/bin/bash
# ─────────────────────────────────────────────────────────
# Setup script for the Content Importer bot account.
#
# Run ONCE after Lemmy is up and the admin account exists.
# This creates the OratioRepostBot user account in Lemmy.
# ─────────────────────────────────────────────────────────
set -euo pipefail

source .env 2>/dev/null || true

# Lemmy는 Docker 내부에서만 8536을 열어서 호스트에서 직접 접근 불가.
# nginx 프록시(https://DOMAIN)를 통해 접근해야 함.
LEMMY_URL="https://${DOMAIN:-oratio.space}"
ADMIN_USER="${LEMMY_ADMIN_USER:-admin}"
ADMIN_PASS="${LEMMY_ADMIN_PASS}"
BOT_USER="${LEMMY_BOT_USERNAME:-OratioRepostBot}"
BOT_PASS="${LEMMY_BOT_PASSWORD}"

if [ -z "$ADMIN_PASS" ] || [ -z "$BOT_PASS" ]; then
    echo "❌ LEMMY_ADMIN_PASS and LEMMY_BOT_PASSWORD must be set in .env"
    exit 1
fi

echo "🔐 Logging in as admin ($ADMIN_USER)..."
JWT=$(curl -s -X POST "$LEMMY_URL/api/v3/user/login" \
    -H "Content-Type: application/json" \
    -d "{\"username_or_email\": \"$ADMIN_USER\", \"password\": \"$ADMIN_PASS\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('jwt',''))")

if [ -z "$JWT" ]; then
    echo "❌ Admin login failed"
    exit 1
fi
echo "✅ Admin login OK"

# ── 봇 계정이 이미 있는지 확인 ──
EXISTING=$(curl -s "$LEMMY_URL/api/v3/user?username=$BOT_USER" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('person_view',{}).get('person',{}).get('name',''))" 2>/dev/null || echo "")

if [ "$EXISTING" = "$BOT_USER" ]; then
    echo "ℹ️  Bot account already exists: $BOT_USER (skip registration)"
else
    # ── captcha 일시 비활성화 → 봇 등록 → captcha 복원 ──
    echo "🔓 Temporarily disabling captcha for bot registration..."
    CAPTCHA_WAS=$(curl -s "$LEMMY_URL/api/v3/site" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['site_view']['local_site']['captcha_enabled'])" 2>/dev/null || echo "True")

    curl -s -X PUT "$LEMMY_URL/api/v3/site" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $JWT" \
        -d '{"captcha_enabled": false}' >/dev/null

    echo "👤 Registering bot account: $BOT_USER..."
    RESULT=$(curl -s -X POST "$LEMMY_URL/api/v3/user/register" \
        -H "Content-Type: application/json" \
        -d "{
            \"username\": \"$BOT_USER\",
            \"password\": \"$BOT_PASS\",
            \"password_verify\": \"$BOT_PASS\",
            \"show_nsfw\": false
        }")

    if echo "$RESULT" | grep -q "jwt"; then
        echo "✅ Bot account created: $BOT_USER"
    elif echo "$RESULT" | grep -qi "already"; then
        echo "ℹ️  Bot account already exists: $BOT_USER"
    else
        echo "⚠️  Registration response: $(echo $RESULT | head -c 200)"
    fi

    # ── captcha 원래 상태로 복원 ──
    if [ "$CAPTCHA_WAS" = "True" ]; then
        echo "🔒 Re-enabling captcha..."
        curl -s -X PUT "$LEMMY_URL/api/v3/site" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $JWT" \
            -d '{"captcha_enabled": true}' >/dev/null
        echo "✅ Captcha restored"
    fi
fi

# Create default communities
echo ""
echo "📁 Creating default communities..."
for COMMUNITY in trending news technology science reddit bbc arstechnica sciencedaily reuters youtube fourchan mgtowtv bitchute; do
    RESULT=$(curl -s -X POST "$LEMMY_URL/api/v3/community" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $JWT" \
        -d "{\"name\": \"$COMMUNITY\", \"title\": \"$(echo $COMMUNITY | sed 's/.*/\u&/')\"}")
    
    if echo "$RESULT" | grep -q "community_view"; then
        echo "  ✅ Created: $COMMUNITY"
    elif echo "$RESULT" | grep -qi "already"; then
        echo "  ℹ️  Already exists: $COMMUNITY"
    else
        echo "  ⚠️  $COMMUNITY: $(echo $RESULT | head -c 100)"
    fi
done

echo ""
echo "🎉 Setup complete!"
echo "   Bot account: $BOT_USER"
echo "   Make sure LEMMY_BOT_PASSWORD is set in .env"
echo "   Then: docker compose build content-importer && docker compose up -d content-importer"
