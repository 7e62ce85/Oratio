# Annual Membership & Gold Badge System

> **Version**: v4.0 | **Updated**: 2025-10-24 | **Status**: ✅ Production

## 🎯 Quick Overview

**Gold Badge System** (💰): Annual membership-based premium feature system for Oratio platform.

| Feature | Details |
|---------|---------|
| **Cost** | $5 USD in BCH (real-time exchange rate) |
| **Duration** | 365 days from purchase |
| **Payment** | From user credit → admin wallet |
| **Benefits** | Gold badge display, premium community access |

---

## 🏗️ System Architecture

### Database Schema

```sql
-- User memberships
CREATE TABLE user_memberships (
    user_id TEXT PRIMARY KEY,
    membership_type TEXT DEFAULT 'annual',
    purchased_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    amount_paid REAL NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

-- Transaction history
CREATE TABLE membership_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    from_address TEXT,
    to_address TEXT NOT NULL,
    amount REAL NOT NULL,
    tx_hash TEXT,
    status TEXT DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    confirmed_at INTEGER
);
```

### API Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/membership/price` | GET | ❌ | Get current price (BCH/USD) |
| `/api/membership/status/<user>` | GET | ✅ | Check membership status |
| `/api/membership/purchase` | POST | ✅ | Purchase membership |
| `/api/membership/transactions/<user>` | GET | ✅ | Get transaction history |

### Price Service

**Multiple API Fallback**:
```
Coinbase API → Blockchain.com API → CoinGecko API → Default $480
```

**Configuration** (`price_service.py`):
```python
MEMBERSHIP_USD_PRICE = 5.00  # Change price here
```

---

## 💻 Frontend Implementation

### Gold Badge Logic

**Cache System**:
- **Storage**: Memory Map + localStorage
- **Duration**: 5 minutes
- **Values**: `1.0` = active, `0.0` = inactive
- **Event**: `'bch-credit-cache-updated'`

**Key Functions** (`bch-payment.ts`):
```typescript
// Async: Fetch from API
checkUserHasGoldBadge(person: Person): Promise<boolean>

// Sync: Check cache, trigger async if needed
checkUserHasGoldBadgeSync(person: Person): boolean

// Rate limiting queue (100ms delay between requests)
processQueue()
```

### Badge Display Locations

✅ Post author names  
✅ Comment author names  
✅ Profile pages  
✅ Navbar user dropdown  
✅ Vote modals  

### Components Modified

1. **`navbar.tsx`** - Fetches membership status on login
2. **`wallet.tsx`** - Membership management page
3. **`post-listing.tsx`** - Badge after author name
4. **`comment-node.tsx`** - Badge after author name
5. **`person-listing.tsx`** - Name/avatar only (no internal badge)
6. **`bch-payment.ts`** - Core logic with queue & cache

---

## 🚀 Quick Deployment

### 1. Backend (2 min)

```bash
cd /home/user/Oratio/oratio
docker-compose restart bitcoincash-service
```

### 2. Frontend (5-10 min)

```bash
docker-compose stop lemmy-ui
docker-compose rm -f lemmy-ui
docker rmi lemmy-ui-custom:latest
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui
```

### 3. Verify

```bash
# Test price API
curl http://localhost:8081/api/membership/price

# Check services
docker-compose ps

# View logs
docker-compose logs -f bitcoincash-service
```

---

## 🧪 Testing

### Purchase Flow Test

1. Login → User menu → "My Wallet"
2. Verify credit balance > membership price
3. Click "Purchase Annual Membership"
4. Confirm purchase dialog
5. ✅ Success message
6. ✅ Gold badge (💰) appears
7. ✅ Membership status shows "Active"

### Badge Display Test

Visit these locations and verify badge shows:
- Feed post authors
- Comment authors  
- Profile header
- User dropdown menu

### Cache Persistence Test

1. Purchase membership → Badge appears
2. **Refresh page (F5)**
3. ✅ Badge still visible (no flicker)
4. Check DevTools → Application → Local Storage → `bch_membership_cache`

---

## 🔧 Configuration

### Change Price

**File**: `/oratio/bitcoincash_service/services/price_service.py`

```python
MEMBERSHIP_USD_PRICE = 5.00  # Edit this value
```

```bash
docker-compose restart bitcoincash-service
```

### Set Admin Wallet

**File**: `.env`

```bash
LEMMY_ADMIN_USER=admin  # Receives membership payments
PAYOUT_WALLET=bitcoincash:qr...  # Optional BCH address
```

### Premium Communities

**File**: `/lemmy-ui-custom/src/shared/utils/bch-payment.ts`

```typescript
const PREMIUM_COMMUNITIES = ['test', 'premium', 'vip'];
```

Rebuild frontend after changes.

---

## 🐛 Common Issues

### Issue: Badge Not Showing

**Quick Fix**:
```javascript
// In browser console
localStorage.clear();
location.reload();
```

**Diagnosis**:
```bash
# Check API
curl -H "X-API-Key: KEY" \
  http://localhost:8081/api/membership/status/USERNAME

# Check logs
docker-compose logs bitcoincash-service | grep -i error
```

### Issue: Purchase Failed

**Check**:
```bash
# User has enough credit?
curl -H "X-API-Key: KEY" \
  http://localhost:8081/api/user_credit/USERNAME

# Price API working?
curl http://localhost:8081/api/membership/price
```

### Issue: 429 Too Many Requests

✅ **Already Fixed**: Request queue system with 100ms delay

If still occurs, increase delay in `bch-payment.ts`:
```typescript
const QUEUE_DELAY = 200; // Increase from 100ms
```

---

## 📊 Monitoring

### Database Queries

```bash
docker exec -it bitcoincash-service sqlite3 /app/data/payment.db

-- Membership stats
SELECT 
  COUNT(*) as total,
  SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active
FROM user_memberships;

-- Recent purchases
SELECT user_id, amount_paid, 
       datetime(purchased_at, 'unixepoch') as date
FROM user_memberships 
ORDER BY purchased_at DESC LIMIT 10;

-- Expiring soon (30 days)
SELECT user_id, 
       datetime(expires_at, 'unixepoch') as expires,
       (expires_at - strftime('%s','now')) / 86400 as days_left
FROM user_memberships 
WHERE is_active = 1 AND expires_at < strftime('%s','now') + 2592000
ORDER BY expires_at;

.exit
```

### Health Check

```bash
# Quick check
docker-compose ps | grep -E "bitcoincash|lemmy-ui"
curl http://localhost:8081/health
curl http://localhost:8081/api/membership/price

# Detailed logs
docker-compose logs -f bitcoincash-service | grep -i "membership\|error"
```

---

## 📈 Key Features

### ✅ Implemented

- **Multiple Price API Fallbacks** (no single point of failure)
- **localStorage Caching** (survives page refresh)
- **Rate Limiting Queue** (prevents 429 errors)
- **Anti-Flicker Cache** (keeps old value during refresh)
- **Auto Admin Transfer** (payment goes to admin wallet)
- **Auto Expiry Check** (background task every 15s)
- **Comprehensive Logging** (all operations tracked)

---

## 🔄 Background Tasks

**Membership Expiry Check** (runs every 15 seconds):
```python
# Auto-deactivates expired memberships
cursor.execute("""
    UPDATE user_memberships 
    SET is_active = FALSE 
    WHERE expires_at < ? AND is_active = TRUE
""", (now,))
```

---

## 🎨 Premium Communities

### Setup

1. **Define communities** in `bch-payment.ts`:
```typescript
const PREMIUM_COMMUNITIES = ['test', 'vip'];
```

2. **UI Indicators**:
- 🔒 Lock icon next to community name
- Warning message for non-members
- Login/purchase links

3. **Access Control**:
- Community page: Blocked with message
- Direct post links: Also blocked
- Feed: Posts visible but clicking blocked

---

## 📖 Quick Reference Commands

```bash
# Restart backend
docker-compose restart bitcoincash-service

# Rebuild frontend  
docker-compose stop lemmy-ui && docker-compose rm -f lemmy-ui && \
docker rmi lemmy-ui-custom:latest && \
docker-compose build --no-cache lemmy-ui && \
docker-compose up -d lemmy-ui

# Check health
docker-compose ps
curl http://localhost:8081/health

# View logs
docker-compose logs -f bitcoincash-service

# Access database
docker exec -it bitcoincash-service sqlite3 /app/data/payment.db
```

---

## 📅 Changelog

**2025-10-24** (v4.0)
- ✅ Full annual membership system
- ✅ Changed from credit-based (0.0001 BCH) to membership ($5/year)
- ✅ Multiple price API fallbacks
- ✅ localStorage persistence
- ✅ Rate limiting queue
- ✅ Fixed badge flickering
- ✅ Fixed duplicate badges
- ✅ Comprehensive documentation

**Previous Versions**
- v3.x: Credit-based gold badge system
- v2.x: Premium community access
- v1.x: Basic BCH payment integration

---

_Document Version: 1.0 | System Version: v4.0 | Status: Production Ready_
