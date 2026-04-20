# Annual Membership & Gold Badge System

> **Version**: v5.2 | **Updated**: 2026-04-15 | **Status**: ✅ Production (Comment Vote Multiplier)

## 🎯 Quick Overview

**Gold Badge System** (💰): Annual membership-based premium feature system for Oratio platform.

| Feature | Details |
|---------|---------|| **5x Vote Multiplier** (membership users' votes count 5 times more on posts and comments) || **Cost** | $5 USD in BCH (real-time exchange rate) |
| **Duration** | 365 days from purchase |
| **Payment** | From user credit → admin wallet |
| **Benefits** | Gold badge display, premium community access, **5x vote power (posts + comments)** |

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

-- User custom settings (Oratio-specific, not in Lemmy API)
CREATE TABLE user_settings (
    user_id TEXT PRIMARY KEY,
    membership_default_filter BOOLEAN DEFAULT FALSE,
    updated_at INTEGER NOT NULL DEFAULT 0
);
```

### API Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/membership/price` | GET | ❌ | Get current price (BCH/USD) |
| `/api/membership/status/<user>` | GET | ✅ | Check membership status |
| `/api/membership/purchase` | POST | ✅ | Purchase membership |
| `/api/membership/transactions/<user>` | GET | ✅ | Get transaction history |
| `/api/membership/settings/<user>` | GET | ❌ | Get user's custom settings |
| `/api/membership/settings` | POST | ❌ | Save user's custom settings |

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
- **5x Vote Multiplier** (membership users' votes count 5 times more on posts)
- **Automatic Membership Sync** (SQLite → PostgreSQL every 60 seconds)
- **Database-Level Implementation** (transparent to frontend, no UI changes needed)
- **Membership Posts Filter** (DB-level filtering, all sort types, full pagination)
- **Settings Default Filter** (Settings 페이지에서 default members-only 설정, SQLite DB 영구 저장)
- **Auto Expiry Filter Clear** (멤버십 만료 시 default filter 자동 해제)

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

**2026-04-15** (v5.2) - Comment Vote Multiplier
- ✅ **NEW**: Comment vote에도 5x multiplier 적용 (기존 post만 → post + comment 모두)
- 🔧 `apply_comment_vote_multiplier()` PostgreSQL 함수 추가
- ✅ `membership_comment_vote_multiplier` trigger를 `comment_like` 테이블에 설치
- ✅ INSERT, UPDATE, DELETE 모든 vote 동작 지원 (toggle off 포함)
- 🔧 deploy 스크립트 컨테이너명 `postgres` → `oratio-postgres-1` 수정
- 📝 문서 업데이트: Benefits 섹션, Verification 커맨드 등

**2026-04-10** (v5.1) - Settings Default Filter + DB Storage
- ✅ Settings 페이지(`/settings`)에 "Members only default" 체크박스 추가 (Sort type 바로 아래)
- 🔧 localStorage → SQLite DB(`user_settings` 테이블) 영구 저장으로 전환
- ✅ 멤버십 만료 시 `check_and_expire_memberships()`에서 자동으로 filter 설정 해제
- ✅ `GET/POST /api/membership/settings` 엔드포인트 추가
- ✅ POST 시 서버에서 멤버십 활성 여부 검증 (비멤버 활성화 차단)
- 🔧 Home 로고 클릭 시 이미 `/`면 full page reload로 state 완전 리셋
- ⚡ Home 초기 로드 최적화: membership check + settings API 병렬 호출, 이중 fetchData 제거
- ✅ 30개 언어 `membership_default_filter` 번역 키 추가

**2026-04-10** (v5.0) - Membership Posts Filter
- ✅ **NEW FEATURE**: Home feed에서 멤버십 유저 게시글만 필터링하는 체크박스
- 🔧 PostgreSQL 직접 쿼리로 DB 레벨 필터링 (프론트엔드 한계 극복)
- ✅ 모든 정렬 옵션 지원 (Active, Hot, New, Old, TopAll 등 19개)
- ✅ 페이지네이션 완벽 지원 (20개씩 페이지 꽉 채움)
- ✅ 비멤버십 유저는 체크박스 disabled 처리
- ✅ `GET /api/membership/posts` + `GET /api/membership/active-users` 엔드포인트 추가
- ✅ 30개 언어 번역 키 추가
- 📝 이전 프론트엔드-only 시도 실패 기록 통합 (MEMBERSHIP_FILTER_ATTEMPT.md 삭제)

**2025-11-02** (v4.2) - Vote Toggle Bug Fix
- 🐛 **CRITICAL FIX**: Fixed mobile browser vote toggle issue
- 🔧 Trigger now properly tracks upvote/downvote removal separately
- ✅ Fixed cumulative upvote/downvote accumulation bug
- 📝 When toggling vote off, now correctly removes the multiplied votes
- 🔄 Ran migration to recalculate all existing post aggregates
- **Before**: Toggle upvote→off would only remove -1 instead of -5
- **After**: Toggle upvote→off correctly removes -5

**2025-10-24** (v4.1) - Badge Flicker Fix
- 🐛 **CRITICAL FIX**: Removed duplicate membership API calls from Navbar
- 🔧 Fixed badge flickering on login/refresh by removing redundant `fetchUserCredit()` membership check
- 🚀 Now using centralized `bch-payment.ts` cache system exclusively
- ⚡ Eliminated 4x duplicate API calls (was calling membership API from both navbar.tsx and bch-payment.ts)
- 📝 See detailed analysis: [Badge Flicker Debug Report](../troubleshooting/badge-flicker-vscode-disk-mismatch-2025-10-24.md)

**2025-10-24** (v4.0)
- ✅ Full annual membership system
- ✅ Changed from credit-based (0.0001 BCH) to membership ($5/year)
- ✅ Multiple price API fallbacks
- ✅ localStorage persistence
- ✅ Rate limiting queue
- ✅ Fixed duplicate badges
- ✅ Comprehensive documentation

**Previous Versions**
- v3.x: Credit-based gold badge system
- v2.x: Premium community access
- v1.x: Basic BCH payment integration

---

## � Membership Posts Filter

### Overview

Home feed에서 멤버십 유저의 게시글만 필터링하는 체크박스. 기존 정렬(Active, Hot, New 등) 옆에 💰 체크박스 → 체크하면 해당 정렬을 유지하면서 멤버십 유저 글만 20개씩 페이지를 꽉 채워서 표시.

### Why Backend Implementation?

프론트엔드만으로는 불가능했음 (Lemmy API가 `creator_id` 1명만 지원):
- 클라이언트 필터링: 20개 중 멤버 글 1~2개만 남아 페이지 비어보임
- 다중 API 호출: 속도 심각하게 느려짐
- **해결**: PostgreSQL 직접 쿼리로 DB 레벨 필터링 → 빠르고 정확히 20개씩 반환

### Architecture

```
[체크박스 체크] → home.tsx fetchMembershipPosts()
    → fetch('/api/membership/posts?sort=New&page=1&limit=20')
    → Nginx → bitcoincash-service (Flask)
    → membership_posts.py → PostgreSQL 직접 쿼리
    → Lemmy API 형식으로 응답 반환
    → 기존 PostListings 컴포넌트에 그대로 렌더링
```

### Access Control

- **멤버십 유저**: 체크박스 활성화, 클릭 가능
- **비멤버십 유저**: 체크박스 보이지만 disabled (grayed out), 호버 시 tooltip 표시
- **비로그인 유저**: 체크박스 보이지만 disabled

### Key Files

| File | Role |
|------|------|
| `bitcoincash_service/services/membership_posts.py` | PostgreSQL 직접 쿼리, 모든 정렬 지원, Lemmy API 형식 응답 |
| `bitcoincash_service/routes/membership.py` | posts, active-users, settings 엔드포인트 |
| `bitcoincash_service/models.py` | `user_settings` 테이블 + CRUD + 만료 시 자동 해제 |
| `lemmy-ui-custom/src/shared/components/home/home.tsx` | 체크박스 UI, 멤버십 필터 로직, DB에서 default 설정 로드 |
| `lemmy-ui-custom/src/shared/components/person/settings.tsx` | Settings 페이지 "Members only" 체크박스, DB 저장 |
| `lemmy-ui-custom/src/shared/components/app/navbar.tsx` | 홈 로고 클릭 시 full reload (state 리셋) |
| `lemmy-ui-custom/custom-translations.json` | `membership_posts_only` + `membership_default_filter` (30개 언어) |

### API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/membership/posts` | ❌ | Membership posts (sort, page, limit, type_) |
| GET | `/api/membership/active-users` | ❌ | Active membership user list |
| GET | `/api/membership/settings/<user>` | ❌ | User's custom settings |
| POST | `/api/membership/settings` | ❌ | Save user's custom settings (서버에서 멤버십 검증) |

### Supported Sort Types

Active, Hot, Scaled, Controversial, New, Old, MostComments, NewComments, TopHour, TopSixHour, TopTwelveHour, TopDay, TopWeek, TopMonth, TopThreeMonths, TopSixMonths, TopNineMonths, TopYear, TopAll

### Verification

```bash
# Test membership posts API
curl -s 'http://localhost:8081/api/membership/posts?sort=New&limit=5&page=1' | python3 -m json.tool

# Test active users
curl -s 'http://localhost:8081/api/membership/active-users' | python3 -m json.tool

# Nginx routing test
curl -s 'https://oratio.space/api/membership/posts?sort=Active&limit=3'
```

---

## �🗳️ Vote Multiplier System

### Overview

Membership users' votes on posts and comments automatically count as **5x normal votes**. This is implemented at the database level using PostgreSQL triggers, making it transparent and automatic.

### How It Works

1. **User votes on a post or comment** → Lemmy backend records vote in `post_like` / `comment_like` table
2. **PostgreSQL trigger fires** → Checks if user has active membership
3. **If membership active** → Automatically multiplies vote impact by 5x in `post_aggregates` / `comment_aggregates`
4. **Result** → Post/comment score reflects the 5x multiplier immediately

### Technical Implementation

**Database Triggers**:
- `membership_post_vote_multiplier` — Fires on INSERT, UPDATE, DELETE of `post_like` table
- `membership_comment_vote_multiplier` — Fires on INSERT, UPDATE, DELETE of `comment_like` table
- Both check `user_memberships` table for active status
- Apply 5x multiplier to vote score
- Update `post_aggregates` / `comment_aggregates` accordingly

**Membership Sync Service**:
- Runs every 60 seconds in bitcoincash-service
- Syncs active memberships from SQLite → PostgreSQL
- Ensures vote multiplier has current membership data

**Key Files**:
- `/oratio/migrations/membership_vote_multiplier.sql` - Database triggers (posts + comments)
- `/oratio/bitcoincash_service/services/membership_sync.py` - Sync service
- `/oratio/deploy_membership_vote_multiplier.sh` - Deployment script

### Deployment

```bash
# 1. First time: Refresh passwords (includes PostgreSQL password)
cd /home/user/Oratio/oratio
bash refresh_passwords.sh

# 2. Restart services with new passwords
docker compose down
docker compose up -d

# 3. Deploy vote multiplier
bash deploy_membership_vote_multiplier.sh
```

### Verification

```bash
# Check if triggers are installed
docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
  "SELECT tgname, tgrelid::regclass FROM pg_trigger WHERE tgname LIKE 'membership_%';"

# View synced memberships
docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
  "SELECT user_id, is_active, expires_at FROM user_memberships;"

# Check sync service logs
docker compose logs -f bitcoincash-service | grep -i "membership sync"

# Test post vote multiplier
# 1. Have a membership user vote on a post
# 2. Check the vote counts:
docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
  "SELECT id, score, upvotes FROM post_aggregates WHERE post_id = YOUR_POST_ID;"

# Test comment vote multiplier
# 1. Have a membership user vote on a comment
# 2. Check the vote counts:
docker exec -i oratio-postgres-1 psql -U lemmy -d lemmy -c \
  "SELECT comment_id, score, upvotes FROM comment_aggregates WHERE comment_id = YOUR_COMMENT_ID;"
```

### Benefits

- **Reward loyal members** - Membership users have more influence
- **Transparent** - Works automatically, no frontend changes
- **Fair** - Applies to both posts and comments
- **Efficient** - Database-level implementation (no API overhead)

---

_Document Version: 1.6 | System Version: v5.2 | Status: Production Ready_
