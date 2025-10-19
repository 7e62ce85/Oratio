# BCH Balance Display Fix for Local Testing

**Date:** October 2, 2025  
**Issue:** BCH balance not displaying in navbar after login during local testing  
**Status:** ✅ RESOLVED

## Problem Description

The BCH balance was not appearing in the navbar next to the account name after login, even though:
- BCH payment service was running on localhost:8081
- API endpoint was accessible with proper authentication
- Environment variables were correctly configured

## Root Cause Analysis

1. **Initial Investigation:** User reported that navbar.tsx was configured to use localhost URLs but balance wasn't showing
2. **API Testing:** Confirmed BCH service was working:
   ```bash
   curl -H "X-API-Key: $LEMMY_API_KEY" http://localhost:8081/api/user_credit/1
   # Response: {"credit_balance": 0, "user_id": "1"}
   ```
3. **Browser Console Analysis:** Revealed the actual issue was **Content Security Policy (CSP)** blocking API calls:
   ```
   Content-Security-Policy: The page's settings blocked the loading of a resource (connect-src) 
   at http://localhost:8081/api/user_credit/2 because it violates the following directive: 
   "connect-src 'self' https://payments.oratio.space"
   ```

## Solution Implemented

### 1. Code Changes (Minimal)

**File:** `/home/user/Oratio/lemmy-ui-custom/src/shared/components/app/navbar.tsx`

```typescript
// LOCAL TEST - temporarily hardcoded for testing
const BCH_PAYMENT_URL = "http://localhost:8081/";  // process.env.LEMMY_BCH_PAYMENT_URL || "http://localhost:8081/";
const BCH_API_URL = "http://localhost:8081/api/user_credit";  // process.env.LEMMY_BCH_API_URL || "http://localhost:8081/api/user_credit";
```

**Impact:** Only 2 lines changed from original environment variable approach to hardcoded localhost URLs for testing.

### 2. CSP Configuration Fix

**File:** `/home/user/Oratio/oratio/nginx_production.conf`

**Before:**
```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' payments.oratio.space;" always;
```

**After:**
```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' payments.oratio.space http://localhost:8081;" always;
```

**Change:** Added `http://localhost:8081` to the `connect-src` directive to allow API calls to the local BCH service.

## Steps to Apply Fix

1. **Update navbar.tsx** with hardcoded localhost URLs (2 lines)
2. **Update CSP in nginx_production.conf** to allow localhost:8081 connections
3. **Rebuild lemmy-ui:**
   ```bash
   docker-compose down
   docker rmi lemmy-ui-custom:latest
   docker system prune -f --filter="label=com.docker.compose.project=oratio"
   docker-compose build --no-cache lemmy-ui
   docker-compose up -d
   ```
4. **Reload nginx configuration:**
   ```bash
   docker-compose exec proxy nginx -s reload
   ```

## Verification

After applying the fix:
- Browser console shows successful API calls with `[BCH Debug]` messages
- No more CSP violation errors
- BCH balance displays correctly in navbar dropdown: "보유 크레딧: 0 BCH"

## Reverting for Production

### 1. Revert navbar.tsx
```typescript
const BCH_PAYMENT_URL = process.env.LEMMY_BCH_PAYMENT_URL || "http://localhost:8081/";
const BCH_API_URL = process.env.LEMMY_BCH_API_URL || "http://localhost:8081/api/user_credit";
```

### 2. Revert CSP in nginx_production.conf
```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' payments.oratio.space;" always;
```

### 3. Rebuild and reload
```bash
docker-compose build --no-cache lemmy-ui
docker-compose up -d
docker-compose exec proxy nginx -s reload
```

## Key Learnings

1. **Always check browser console** for CSP violations when API calls fail silently
2. **Minimal code changes** are preferred for temporary testing configurations
3. **CSP configuration** in nginx takes precedence over application-level CSP settings
4. **Environment variables vs hardcoding:** For local testing, hardcoding can be simpler than complex environment variable management

## Related Files

- `/home/user/Oratio/lemmy-ui-custom/src/shared/components/app/navbar.tsx` - Main implementation
- `/home/user/Oratio/oratio/nginx_production.conf` - CSP configuration
- `/home/user/Oratio/oratio/docker-compose.yml` - Service configuration
- `/home/user/Oratio/oratio/.env` - Environment variables

## Environment

- **Lemmy Version:** 0.19.8
- **UI:** Custom lemmy-ui with BCH integration
- **BCH Service:** Running on localhost:8081
- **Nginx:** Proxy with CSP headers
- **Testing Mode:** Local development environment

---

**Note:** This fix is specifically for local testing. Ensure proper reversion before production deployment.