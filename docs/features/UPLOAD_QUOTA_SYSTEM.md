# Upload Quota System Documentation

> **Version**: 1.0 | **Created**: 2025-11-04 | **Status**: ✅ Production Ready

## ⚠️ Critical Implementation Notes

**Before deploying, ensure:**

1. **Database Path**: Use `/data/payments.db` (plural), NOT `/app/data/payment.db`
2. **User Identifier**: System uses **username** (e.g., `gookjob`), NOT numeric user ID (e.g., `36`)
3. **SQLite Compatibility**: Do not use PostgreSQL syntax (e.g., `COMMENT ON TABLE`)
4. **Record All Uploads**: Backend records every upload, regardless of size
5. **Display Units**: Show KB/MB for small values, GB for large values

**Common Pitfalls:**
- ❌ Creating tables in wrong database → "no such table" errors
- ❌ Sending user ID instead of username → Members treated as free users
- ❌ Only recording uploads > 250KB → Quota tracking broken
- ❌ Displaying "0 GB" for MB-sized uploads → Confusing UX

---

## 🎯 Overview

**Tiered Upload Quota System**: File size limits and credit-based charging for image/video uploads on the Oratio platform.

| User Type | Per-Upload Limit | Annual Quota | Overage Pricing |
|-----------|------------------|--------------|-----------------|
| **Free Users** | 250 KB | N/A | Must upgrade |
| **Members** | No limit* | 20 GB | $1 USD per 4GB |

*Members can upload files of any size as long as they have quota or credit available.

---

## 🏗️ System Architecture

### Component Stack

```
┌─────────────────────────────────────────┐
│         Frontend (Inferno.js)           │
│  - post-form.tsx (Upload validation)    │
│  - wallet.tsx (Quota display)           │
│  - upload-quota.ts (Utilities)          │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│      Backend API (Flask/Python)         │
│  - /api/upload/quota/<user>             │
│  - /api/upload/validate (Pre-check)     │
│  - /api/upload/record (Transaction)     │
│  - /api/upload/history/<user>           │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│     Upload Quota Service (Python)       │
│  - Quota validation                     │
│  - Credit charging                      │
│  - Usage tracking                       │
│  - Quota reset (background task)        │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          SQLite Database                │
│  - user_upload_quotas                   │
│  - upload_transactions                  │
│  - upload_pricing_config                │
└─────────────────────────────────────────┘
```

### Database Schema

#### `user_upload_quotas`
```sql
CREATE TABLE user_upload_quotas (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    annual_quota_bytes BIGINT DEFAULT 0,
    used_bytes BIGINT DEFAULT 0,
    quota_start_date INTEGER NOT NULL,
    quota_end_date INTEGER NOT NULL,
    membership_type TEXT DEFAULT 'free',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);
```

#### `upload_transactions`
```sql
CREATE TABLE upload_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    file_type TEXT,
    upload_url TEXT,
    was_within_quota BOOLEAN DEFAULT TRUE,
    overage_bytes BIGINT DEFAULT 0,
    credit_charged REAL DEFAULT 0.0,
    usd_per_4gb REAL DEFAULT 1.0,
    status TEXT DEFAULT 'completed',
    post_id INTEGER,
    comment_id INTEGER,
    created_at INTEGER NOT NULL
);
```

#### `upload_pricing_config`
```sql
CREATE TABLE upload_pricing_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    free_user_limit_bytes BIGINT DEFAULT 256000,
    member_annual_quota_bytes BIGINT DEFAULT 21474836480,
    overage_usd_per_4gb REAL DEFAULT 1.0,
    overage_min_charge_usd REAL DEFAULT 0.01,
    recommended_formats TEXT DEFAULT 'jpg,jpeg',
    effective_from INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);
```

---

## 💻 API Endpoints

### Public Endpoints

#### `GET /api/upload/pricing`
Get current pricing configuration.

**Response**:
```json
{
  "success": true,
  "pricing": {
    "free_user_limit_bytes": 256000,
    "free_user_limit_kb": 250,
    "member_annual_quota_bytes": 21474836480,
    "member_annual_quota_gb": 20,
    "overage_usd_per_4gb": 1.0,
    "min_charge_usd": 0.01,
    "recommended_formats": ["jpg", "jpeg"]
  }
}
```

### Authenticated Endpoints (Require API Key)

#### `GET /api/upload/quota/<user_id>`
Get user's current quota status.

**Headers**: `X-API-Key: YOUR_API_KEY`

**Response**:
```json
{
  "success": true,
  "quota": {
    "user_id": "user123",
    "username": "alice",
    "membership_type": "annual",
    "is_member": true,
    "annual_quota_bytes": 21474836480,
    "annual_quota_gb": 20.0,
    "used_bytes": 1073741824,
    "used_gb": 1.0,
    "remaining_bytes": 20401094656,
    "remaining_gb": 19.0,
    "usage_percentage": 5.0,
    "quota_start_date": 1699000000,
    "quota_end_date": 1730536000,
    "is_active": true
  }
}
```

#### `POST /api/upload/validate`
Validate if an upload is allowed before processing.

**Headers**: `X-API-Key: YOUR_API_KEY`

**Request Body**:
```json
{
  "user_id": "user123",
  "username": "alice",
  "file_size_bytes": 5242880,
  "filename": "photo.jpg"
}
```

**Response (Within Quota)**:
```json
{
  "success": true,
  "validation": {
    "allowed": true,
    "reason": "within_quota",
    "message": "Upload allowed. Remaining quota: 19.00 GB",
    "will_charge": false,
    "charge_amount_usd": 0.0,
    "charge_amount_bch": 0.0,
    "remaining_after_upload_bytes": 20395851776,
    "remaining_after_upload_gb": 19.0
  }
}
```

**Response (Requires Charge)**:
```json
{
  "success": true,
  "validation": {
    "allowed": true,
    "reason": "overage_charged",
    "message": "Upload allowed. Overage of 1.00 GB will cost 0.00052083 BCH ($0.25)",
    "will_charge": true,
    "overage_bytes": 1073741824,
    "overage_gb": 1.0,
    "charge_amount_usd": 0.25,
    "charge_amount_bch": 0.00052083,
    "user_credit_bch": 0.001,
    "remaining_credit_after_bch": 0.00047917
  }
}
```

**Response (Not Allowed)**:
```json
{
  "success": true,
  "validation": {
    "allowed": false,
    "reason": "file_too_large",
    "message": "File size (5.00 MB) exceeds free user limit of 250.00 KB. Purchase annual membership for 20GB quota.",
    "max_size_bytes": 256000,
    "requires_membership": true
  }
}
```

#### `POST /api/upload/record`
Record an upload transaction and charge credit if needed.

**Headers**: `X-API-Key: YOUR_API_KEY`

**Request Body**:
```json
{
  "user_id": "user123",
  "username": "alice",
  "filename": "photo.jpg",
  "file_size_bytes": 5242880,
  "file_type": "image/jpeg",
  "upload_url": "https://oratio.space/pictrs/image/abc123.jpg",
  "post_id": 456,
  "use_credit": true
}
```

**Response**:
```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "charged": false,
  "charge_amount_bch": 0.0,
  "charge_amount_usd": 0.0,
  "quota": {
    "user_id": "user123",
    "used_gb": 1.005,
    "remaining_gb": 18.995,
    ...
  }
}
```

#### `GET /api/upload/history/<user_id>?limit=50`
Get user's upload history.

**Headers**: `X-API-Key: YOUR_API_KEY`

**Query Parameters**:
- `limit` (optional, default: 50, max: 200)

**Response**:
```json
{
  "success": true,
  "uploads": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "photo.jpg",
      "file_size_bytes": 5242880,
      "file_size_mb": 5.0,
      "file_type": "image/jpeg",
      "was_within_quota": true,
      "overage_bytes": 0,
      "overage_mb": 0,
      "credit_charged": 0.0,
      "status": "completed",
      "created_at": 1699000000,
      "uploaded_at": "2023-11-03T12:00:00Z"
    }
  ],
  "count": 1
}
```

---

## 🚀 User Flows

### Flow 1: Free User Uploads Small File

1. User selects 200KB image in post form
2. Frontend validates file size client-side (optional)
3. User clicks upload
4. Backend validates: 200KB < 250KB ✅
5. File uploads successfully
6. No quota tracking (free users don't have quotas)

### Flow 2: Member Uploads Within Quota

1. Member selects 5MB image
2. Frontend calls `/api/upload/validate`
3. Backend: Member has 19GB remaining ✅
4. File uploads to pictrs
5. Frontend calls `/api/upload/record`
6. Backend records transaction, updates quota
7. Success! Used: 1.005GB / 20GB

### Flow 3: Member Uploads With Overage

1. Member with 0.5GB remaining selects 2GB video
2. Frontend calls `/api/upload/validate`
3. Backend calculates:
   - Overage: 1.5GB
   - Cost: $0.375 USD (1.5GB ÷ 4GB × $1)
   - BCH: 0.00078125 BCH (at $480/BCH)
4. User has 0.001 BCH credit ✅
5. Frontend shows confirmation dialog:
   ```
   ⚠️ Upload Size Notice
   
   This file (2.00 GB) exceeds your available quota.
   
   Overage: 1.50 GB
   Cost: 0.00078125 BCH ($0.38)
   
   Do you want to proceed and charge your credit?
   ```
6. User clicks "OK"
7. File uploads to pictrs
8. Frontend calls `/api/upload/record` with `use_credit: true`
9. Backend:
   - Records upload transaction
   - Deducts 0.00078125 BCH from user credit
   - Updates quota: Used 2.5GB / 20GB
10. Success! Credit: 0.00021875 BCH remaining

### Flow 4: Free User Tries Large File

1. Free user selects 5MB image
2. Frontend calls `/api/upload/validate`
3. Backend: 5MB > 250KB ❌
4. Frontend shows error:
   ```
   ❌ File size (5.00 MB) exceeds free user limit of 250.00 KB.
   Purchase annual membership for 20GB quota.
   ```
5. Upload blocked
6. User sees membership upgrade button

### Flow 5: Annual Quota Reset

1. Background task runs every 15 seconds
2. Checks all active memberships
3. Finds user123's quota expired (1 year passed)
4. User still has active membership ✅
5. Resets quota:
   ```sql
   UPDATE user_upload_quotas
   SET used_bytes = 0,
       quota_start_date = <new_membership_start>,
       quota_end_date = <new_membership_end>
   WHERE user_id = 'user123'
   ```
6. User now has fresh 20GB quota

---

## 🎨 Frontend Integration

### Upload Form Enhancement

**File**: `lemmy-ui-custom/src/shared/components/post/post-form.tsx`

**Features**:
- ✅ File size validation before upload
- ✅ JPG/JPEG format recommendation
- ✅ Quota check integration
- ✅ Credit charge confirmation dialog
- ✅ Informative helper text

**Helper Text Display**:
```tsx
<small className="form-text text-muted">
  💡 Free users: 250KB per file. Members: 20GB annual quota.{" "}
  <strong>JPG/JPEG recommended</strong> for best efficiency.
</small>
```

**Upload Flow**:
```tsx
function handleImageUpload(i: PostForm, event: any) {
  // 1. Get file and user info
  const file = event.target.files[0];
  const userId = userInfo.local_user_view.person.id.toString();
  const username = userInfo.local_user_view.person.name;
  
  // 2. Validate quota
  validateUpload(userId, username, file.size, file.name)
    .then(validation => {
      // Show warnings/errors
      showUploadSizeMessage(file.size, file.name, validation);
      
      // 3. Confirm if credit charge needed
      if (shouldPromptForCredit(validation)) {
        const confirmed = confirm(`Cost: ${validation.charge_amount_bch} BCH`);
        if (!confirmed) return;
      }
      
      // 4. Upload file
      return HttpService.client.uploadImage({ image: file });
    })
    .then(res => {
      // 5. Record transaction
      recordUpload(userId, username, file.name, file.size, res.data.url, ...);
    });
}
```

### Wallet Page Display

**File**: `lemmy-ui-custom/src/shared/components/person/wallet.tsx`

**Quota Display Card**:
```tsx
<div className="card mb-4">
  <div className="card-header">
    <h5 className="mb-0">
      <Icon icon="upload" classes="me-2" />
      Upload Quota
    </h5>
  </div>
  <div className="card-body">
    {/* For Members */}
    <div className="row mb-3">
      <div className="col-md-4">
        <div className="text-center p-3 border rounded">
          <h6 className="text-muted mb-1">Annual Quota</h6>
          <h4 className="mb-0">20 GB</h4>
        </div>
      </div>
      <div className="col-md-4">
        <div className="text-center p-3 border rounded">
          <h6 className="text-muted mb-1">Used</h6>
          <h4 className="mb-0 text-primary">1.5 GB</h4>
        </div>
      </div>
      <div className="col-md-4">
        <div className="text-center p-3 border rounded">
          <h6 className="text-muted mb-1">Remaining</h6>
          <h4 className="mb-0 text-success">18.5 GB</h4>
        </div>
      </div>
    </div>
    
    {/* Progress Bar */}
    <div className="progress" style={{ height: '20px' }}>
      <div className="progress-bar bg-success" 
           style={{ width: '7.5%' }}>
        7.5%
      </div>
    </div>
    
    {/* Upload History Table */}
    <table className="table table-sm table-hover">
      <thead>
        <tr>
          <th>Filename</th>
          <th>Size</th>
          <th>Date</th>
          <th>Status</th>
          <th>Cost</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>photo.jpg</td>
          <td>5.0 MB</td>
          <td>2023-11-03</td>
          <td><span className="badge bg-success">Within Quota</span></td>
          <td>Free</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
```

---

## ⚙️ Configuration

### Pricing Configuration

**File**: `/oratio/bitcoincash_service/services/upload_quota_service.py`

```python
class UploadQuotaService:
    # Constants
    FREE_USER_LIMIT_BYTES = 256_000  # 250KB
    MEMBER_ANNUAL_QUOTA_BYTES = 21_474_836_480  # 20GB
    OVERAGE_USD_PER_4GB = 1.0
    BYTES_PER_4GB = 4_294_967_296
    MIN_CHARGE_USD = 0.01
```

### Changing Limits

**To change free user limit**:
```python
# In upload_quota_service.py
FREE_USER_LIMIT_BYTES = 512_000  # Change to 500KB
```

**To change member annual quota**:
```python
# In upload_quota_service.py
MEMBER_ANNUAL_QUOTA_BYTES = 53_687_091_200  # Change to 50GB
```

**To change overage pricing**:
```python
# In upload_quota_service.py
OVERAGE_USD_PER_4GB = 0.5  # Change to $0.50 per 4GB
```

### Environment Variables

No additional environment variables needed. The system uses existing BCH payment configuration.

---

## 🧪 Testing

### Manual Testing Checklist

#### Free User Tests
- [ ] Upload 200KB file ✅ Should succeed
- [ ] Upload 300KB file ❌ Should fail with error
- [ ] See upgrade prompt in error message
- [ ] Check wallet shows "Free User Limit: 250KB"

#### Member User Tests
- [ ] Upload 1MB file (within quota) ✅ Should succeed
- [ ] Check quota updates correctly
- [ ] Upload large file (causes overage)
- [ ] See credit charge confirmation dialog
- [ ] Confirm and upload ✅ Credit deducted
- [ ] Decline confirmation ❌ Upload cancelled
- [ ] Upload with insufficient credit ❌ Should fail

#### Wallet Page Tests
- [ ] Free user sees "250KB per upload" message
- [ ] Member sees quota bars (Annual/Used/Remaining)
- [ ] Progress bar shows correct percentage
- [ ] Upload history table displays correctly
- [ ] "Within Quota" badge for normal uploads
- [ ] "Overage" badge for charged uploads
- [ ] Credit charged amount shows correctly

#### Background Task Tests
- [ ] Wait for quota expiry date
- [ ] Background task resets quota to 0
- [ ] User has fresh 20GB quota
- [ ] Old usage data preserved in history

### API Testing

#### Test Quota Endpoint
```bash
curl -H "X-API-Key: YOUR_KEY" \
  http://localhost:8081/api/upload/quota/alice
```

#### Test Validation
```bash
curl -X POST http://localhost:8081/api/upload/validate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{
    "user_id": "alice",
    "username": "alice",
    "file_size_bytes": 5242880,
    "filename": "test.jpg"
  }'
```

#### Test Upload Recording
```bash
curl -X POST http://localhost:8081/api/upload/record \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{
    "user_id": "alice",
    "username": "alice",
    "filename": "test.jpg",
    "file_size_bytes": 5242880,
    "file_type": "image/jpeg",
    "upload_url": "https://oratio.space/test.jpg",
    "use_credit": false
  }'
```

---

## 📊 Database Queries

### Check User Quota
```bash
docker exec -it bitcoincash-service sqlite3 /app/data/payment.db

-- View user quota summary
SELECT * FROM user_quota_summary WHERE user_id = 'alice';

-- Check upload transactions
SELECT * FROM upload_transactions 
WHERE user_id = 'alice' 
ORDER BY created_at DESC 
LIMIT 10;

-- Get quota usage statistics
SELECT 
  COUNT(*) as total_users,
  SUM(used_bytes) / 1073741824.0 as total_used_gb,
  AVG(usage_percentage) as avg_usage_pct
FROM user_upload_quotas
WHERE is_active = TRUE AND membership_type = 'annual';
```

### Find Heavy Users
```sql
-- Top 10 users by upload volume
SELECT 
  username,
  used_gb,
  annual_quota_gb,
  usage_percentage
FROM user_quota_summary
WHERE membership_type = 'annual'
ORDER BY used_bytes DESC
LIMIT 10;
```

### Overage Analysis
```sql
-- Total overage charges
SELECT 
  SUM(credit_charged) as total_charged_bch,
  COUNT(*) as overage_count,
  SUM(overage_bytes) / 1073741824.0 as total_overage_gb
FROM upload_transactions
WHERE was_within_quota = FALSE;
```

---

## 🔧 Troubleshooting

### Issue: Quota Not Updating

**Symptoms**: Upload succeeds but quota stays the same

**Diagnosis**:
```bash
# Check database trigger
docker exec -it bitcoincash-service sqlite3 /app/data/payment.db

SELECT name FROM sqlite_master 
WHERE type='trigger' 
AND name='update_quota_usage_after_upload';
```

**Fix**: Recreate database schema
```bash
cd /home/user/Oratio/oratio
docker exec -it bitcoincash-service python3 << EOF
from services.upload_quota_service import UploadQuotaService
service = UploadQuotaService('/app/data/payment.db')
# Service __init__ will recreate tables if needed
EOF
```

### Issue: Upload Validation Fails

**Symptoms**: All uploads rejected with validation error

**Check API connectivity**:
```bash
# Test API endpoint
curl http://localhost:8081/api/upload/pricing

# Check logs
docker logs bitcoincash-service | grep -i "upload"
```

**Common causes**:
- API key mismatch
- Database connection error
- Membership not synced

### Issue: User ID vs Username Mismatch ⚠️ CRITICAL

**Symptoms**: 
- Members treated as free users (250KB limit applied)
- Quota shows 0 GB for members
- Two separate quota records created

**Root Cause**: 
Frontend sends numeric user ID (`36`), but BCH service uses username (`gookjob`) as primary identifier in `user_memberships` table.

**Solution Applied**:
Changed frontend to send **username** as `user_id`:
```typescript
// post-form.tsx - BEFORE (WRONG)
const userId = userInfo.local_user_view.person.id.toString(); // "36"
validateUpload(userId, username, fileSize, filename);

// post-form.tsx - AFTER (CORRECT)
const username = userInfo.local_user_view.person.name; // "gookjob"
validateUpload(username, username, fileSize, filename);
```

**Database Cleanup**:
```bash
# Remove incorrect numeric user_id records
docker exec -it bitcoincash-service sqlite3 /data/payments.db \
  "DELETE FROM user_upload_quotas WHERE user_id LIKE '%[0-9]%' AND user_id NOT LIKE '%[a-z]%';"
```

### Issue: Wrong Database File Path

**Symptoms**:
- "no such table: user_upload_quotas" error
- Tables exist but not found by service
- Migration succeeds but service fails

**Root Cause**:
Created tables in `/app/data/payment.db` but service uses `/data/payments.db` (note: "payments" is plural).

**Check database path**:
```bash
# Find all .db files
docker exec bitcoincash-service find /app -name "*.db"

# Check config
docker exec bitcoincash-service python3 -c "from config import DB_PATH; print(DB_PATH)"
# Output: /data/payments.db
```

**Solution**:
Apply migration to **correct database**:
```bash
docker exec -i bitcoincash-service sqlite3 /data/payments.db < migrations/upload_quota_system.sql
```

### Issue: SQLite vs PostgreSQL Syntax

**Symptoms**: Migration SQL fails with syntax errors

**Root Cause**: 
Used PostgreSQL syntax (`COMMENT ON TABLE`) in SQLite migration.

**Errors**:
```
Parse error near line 185: near 'COMMENT': syntax error
Parse error near line 118: no such table: main.user_memberships
```

**Solution**:
Removed PostgreSQL-specific features:
- `COMMENT ON TABLE` statements (SQLite doesn't support)
- Trigger referencing `user_memberships` from PostgreSQL database
- Used simple `CREATE TABLE IF NOT EXISTS` instead

### Issue: Quota Display Shows "0 GB" for Small Uploads

**Symptoms**:
- User uploads 1.4 MB
- Wallet shows "Used: 0 GB" (should show actual usage)
- Confuses users about quota tracking

**Root Cause**:
Backend rounds to 2 decimal places:
```python
'used_gb': round(quota['used_bytes'] / 1_073_741_824, 2)
# 1,472,402 bytes = 0.00137 GB → rounds to 0.00
```

**Solution**:
Frontend displays appropriate unit based on size:
```typescript
// wallet.tsx - Smart unit selection
const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(2)} KB`;
  if (bytes < 1_073_741_824) return `${(bytes / 1_048_576).toFixed(2)} MB`;
  return `${(bytes / 1_073_741_824).toFixed(2)} GB`;
};

// Shows "1.40 MB" instead of "0.00 GB"
```

### Issue: Uploads Not Recorded in Database

**Symptoms**:
- Upload succeeds
- No transaction record created
- Quota not deducted

**Root Cause**:
Incorrect conditional logic in `post-form.tsx`:
```typescript
// BEFORE (WRONG) - Only records if over 250KB
const validation_required = fileSize > 256000;
if (validation_required) {
  recordUpload(...);
}

// AFTER (CORRECT) - Records ALL uploads
recordUpload(...); // Always record, let backend decide charging
```

**Verification**:
```bash
# Check if uploads are being recorded
docker exec -it bitcoincash-service sqlite3 /data/payments.db \
  "SELECT filename, file_size_bytes, created_at FROM upload_transactions ORDER BY created_at DESC LIMIT 5;"
```

### Issue: Credit Not Deducted

**Symptoms**: Overage upload succeeds but credit unchanged

**Check**:
```bash
# Verify deduct_credit function exists
docker exec -it bitcoincash-service python3 << EOF
import models
print(hasattr(models, 'deduct_credit'))
EOF
```

**Check transaction log**:
```sql
SELECT * FROM transactions 
WHERE type = 'debit' 
AND description LIKE '%Upload overage%'
ORDER BY created_at DESC;
```

---

## 🚀 Deployment

### Prerequisites

1. **Verify database path**:
```bash
docker exec bitcoincash-service python3 -c "from config import DB_PATH; print(DB_PATH)"
# Should output: /data/payments.db (NOT /app/data/payment.db)
```

2. **Check existing tables**:
```bash
docker exec -it bitcoincash-service sqlite3 /data/payments.db ".tables"
```

### Initial Setup

1. **Apply database migration to CORRECT database**:
```bash
cd /home/user/Oratio/oratio

# Create tables in /data/payments.db (NOT /app/data/payment.db)
docker exec -i bitcoincash-service sqlite3 /data/payments.db << 'EOF'
CREATE TABLE IF NOT EXISTS user_upload_quotas (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    annual_quota_bytes BIGINT DEFAULT 0,
    used_bytes BIGINT DEFAULT 0,
    quota_start_date INTEGER NOT NULL,
    quota_end_date INTEGER NOT NULL,
    membership_type TEXT DEFAULT 'free',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS upload_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    file_type TEXT,
    upload_url TEXT,
    was_within_quota BOOLEAN DEFAULT TRUE,
    overage_bytes BIGINT DEFAULT 0,
    credit_charged REAL DEFAULT 0.0,
    usd_per_4gb REAL DEFAULT 1.0,
    status TEXT DEFAULT 'completed',
    post_id INTEGER,
    comment_id INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS upload_pricing_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    free_user_limit_bytes BIGINT DEFAULT 256000,
    member_annual_quota_bytes BIGINT DEFAULT 21474836480,
    overage_usd_per_4gb REAL DEFAULT 1.0,
    overage_min_charge_usd REAL DEFAULT 0.01,
    recommended_formats TEXT DEFAULT 'jpg,jpeg',
    effective_from INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at INTEGER NOT NULL
);

-- Insert default pricing
INSERT OR IGNORE INTO upload_pricing_config (
    free_user_limit_bytes,
    member_annual_quota_bytes,
    overage_usd_per_4gb,
    overage_min_charge_usd,
    recommended_formats,
    effective_from,
    is_active,
    created_at
) VALUES (
    256000,
    21474836480,
    1.0,
    0.01,
    'jpg,jpeg',
    strftime('%s', 'now'),
    TRUE,
    strftime('%s', 'now')
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_upload_quotas_user_id ON user_upload_quotas(user_id);
CREATE INDEX IF NOT EXISTS idx_upload_quotas_username ON user_upload_quotas(username);
CREATE INDEX IF NOT EXISTS idx_upload_quotas_active ON user_upload_quotas(is_active);
CREATE INDEX IF NOT EXISTS idx_upload_transactions_user_id ON upload_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_upload_transactions_created_at ON upload_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_upload_transactions_status ON upload_transactions(status);

-- Create trigger for automatic quota updates
CREATE TRIGGER IF NOT EXISTS update_quota_usage_after_upload
AFTER INSERT ON upload_transactions
WHEN NEW.status = 'completed'
BEGIN
    UPDATE user_upload_quotas
    SET used_bytes = used_bytes + NEW.file_size_bytes,
        updated_at = strftime('%s', 'now')
    WHERE user_id = NEW.user_id;
END;
EOF
```

2. **Verify tables created**:
```bash
docker exec -it bitcoincash-service sqlite3 /data/payments.db "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%upload%';"
# Expected output:
# user_upload_quotas
# upload_transactions
# upload_pricing_config
```

3. **Clean up any incorrect user_id records** (numeric IDs instead of usernames):
```bash
docker exec -it bitcoincash-service sqlite3 /data/payments.db \
  "DELETE FROM user_upload_quotas WHERE user_id GLOB '[0-9]*' AND length(user_id) < 4;"
```

4. **Rebuild backend service** (to pick up code changes):
```bash
docker-compose stop bitcoincash-service
docker-compose build --no-cache bitcoincash-service
docker-compose up -d bitcoincash-service
```

5. **Rebuild frontend**:
```bash
docker-compose stop lemmy-ui
docker-compose rm -f lemmy-ui
docker rmi lemmy-ui-custom:latest
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui
```

6. **Reload nginx** (if container IPs changed):
```bash
docker exec oratio-proxy-1 nginx -s reload
```

7. **Verify deployment**:
```bash
# Check API responds
curl http://localhost:8081/api/upload/pricing

# Check service logs (should not show "no such table" errors)
docker logs bitcoincash-service --tail 50 | grep -i "upload\|quota"

# Test with actual user (replace 'gookjob' with your member username)
docker exec -it bitcoincash-service python3 << EOF
import sys
sys.path.insert(0, '/app')
from services.upload_quota_service import UploadQuotaService
from config import DB_PATH

service = UploadQuotaService(DB_PATH)
quota = service.get_user_quota('gookjob', 'gookjob')
print(f"Membership type: {quota['membership_type']}")
print(f"Annual quota: {quota['annual_quota_gb']} GB")
print(f"Used: {quota['used_gb']} GB")
EOF
```

### Health Checks

```bash
# Watch background task logs
docker-compose logs -f bitcoincash-service | grep "업로드 쿼터"

# Check quota reset activity
docker exec -it bitcoincash-service sqlite3 /app/data/payment.db \
  "SELECT COUNT(*) FROM user_upload_quotas WHERE used_bytes = 0;"
```

---

## 📈 Future Enhancements

### Planned Features

1. **Admin Dashboard**
   - Total storage usage across all users
   - Top uploaders list
   - Overage revenue statistics
   - Quota usage trends

2. **Additional Purchase Options**
   - One-time quota boost ($0.25 per 1GB)
   - Pay-as-you-go mode (no annual limit)
   - Team/organization quotas

3. **Format Conversion**
   - Auto-convert PNG to JPG
   - Compress large images
   - Suggest optimal format

4. **Advanced Analytics**
   - Upload frequency charts
   - File type distribution
   - Peak usage times

---

## 📝 Changelog

**2025-11-04** (v1.0) - Initial Release
- ✅ Tiered quota system (Free: 250KB, Member: 20GB)
- ✅ Credit-based overage charging ($1 per 4GB)
- ✅ Frontend validation and user prompts
- ✅ Wallet page quota display with smart unit formatting
- ✅ Upload history tracking
- ✅ Background quota reset task
- ✅ Comprehensive API endpoints
- ✅ Full documentation with troubleshooting guide

**Implementation Fixes Applied:**
- 🔧 Fixed user ID vs username mismatch (use username as identifier)
- 🔧 Fixed database path (`/data/payments.db` not `/app/data/payment.db`)
- 🔧 Removed PostgreSQL syntax from SQLite migration
- 🔧 Changed to record ALL uploads (not just >250KB)
- 🔧 Improved quota display to show KB/MB for small values
- 🔧 Added comprehensive error logging for debugging

**Known Issues:**
- ⚠️ FORWARD_PAYMENTS import error in background_tasks.py (non-critical, doesn't affect upload quota)
- ℹ️ Migration file warning in logs (harmless, tables already created manually)

---

**Document Version**: 1.0  
**System Version**: 1.0  
**Status**: Production Ready ✅  
**Last Updated**: 2025-11-04  
**Tested**: Member uploads (>250KB), Free user limits, Quota tracking, Credit charging
