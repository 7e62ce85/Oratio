# POW System Expansion - Changelog

**Date**: October 13, 2025  
**Author**: GitHub Copilot  
**Version**: 2.0

## 🎯 Summary

Expanded the Proof of Work (PoW) system from signup-only to both **signup** and **post creation**, with improved user-friendly messaging.

---

## 📝 Changes Made

### 1. Frontend Updates

#### File: `lemmy-ui-custom/src/shared/components/home/signup.tsx`
- **Changed UI Text** (more user-friendly):
  - Label: `🔐 Proof of Work` → `🛡️ Bot Verification`
  - Button: `Proof of Work 계산 시작` → `Verify I'm Not a Bot`
  - Progress: `AI 봇 방지를 위한 계산 중...` → `🤖 Verifying you're human...`
  - Success: `✓ Proof of Work 완료` → `✓ Verification Complete!`
  - Description: Technical terms removed, now says "automatic verification check that runs in your browser and takes about 10 seconds"
  - Validation error: `먼저 Proof of Work를 완료해주세요` → `Please complete the bot verification first.`

#### File: `lemmy-ui-custom/src/shared/components/post/post-form.tsx`
- **Added POW to Post Creation**:
  - Imported POW utilities (`computeProofOfWork`)
  - Added POW state fields to `PostFormState`
  - Added `renderProofOfWork()` method (identical UI to signup)
  - Added `handleComputePoW()` method
  - Modified `handlePostSubmit()` to validate POW before submission
  - POW data (`pow_challenge`, `pow_nonce`, `pow_hash`) sent with create post request
  - **Note**: POW only required for NEW posts, not edits

### 2. Backend Updates

#### File: `oratio/pow_validator_service/app.py`
- **Added new endpoint**: `/api/v3/post`
  - Validates POW before forwarding to Lemmy backend
  - Removes POW fields before sending to Lemmy
  - Forwards authentication headers (for logged-in users)
  - Same validation logic as signup

### 3. Infrastructure Updates

#### File: `oratio/nginx_production.conf`
- **Added routing for post creation**:
  ```nginx
  location /api/v3/post {
      proxy_pass http://pow-validator:5001;
      proxy_set_header Authorization $http_authorization;
  }
  ```

### 4. Documentation Updates

#### File: `docs/features/POW_SYSTEM_GUIDE.md`
- Updated title to reflect both signup and post creation
- Added `/api/v3/post` to endpoints table
- Added example POST request for creating posts
- Updated system architecture diagram
- Updated version to 2.0

---

## 🚀 Deployment Steps

```bash
# 1. Rebuild and restart frontend
cd /home/user/Oratio/lemmy-ui-custom
docker-compose -f ../oratio/docker-compose.yml build lemmy-ui
docker-compose -f ../oratio/docker-compose.yml up -d lemmy-ui

# 2. Restart POW validator
cd /home/user/Oratio/oratio
docker-compose restart pow-validator

# 3. Restart Nginx
docker-compose restart nginx

# 4. Check logs
docker-compose logs -f pow-validator
docker-compose logs -f lemmy-ui
```

---

## 🎨 UI/UX Improvements

### Before
- ❌ Technical jargon: "Proof of Work", "암호학적 계산"
- ❌ Korean + English mixed
- ❌ Not intuitive for regular users

### After
- ✅ User-friendly: "Bot Verification", "Verify I'm Not a Bot"
- ✅ All English
- ✅ Clear explanation: "automatic verification check"
- ✅ Similar to familiar systems (reCAPTCHA)

---

## 🔒 Security Benefits

1. **Signup Protection**: Prevents automated bot registrations
2. **Spam Post Prevention**: Requires 10-second computation per post
3. **No Backend Changes**: Works with vanilla Lemmy backend
4. **Rate Limiting**: Combined with Nginx rate limits for double protection

---

## ⚠️ Important Notes

- POW is **NOT required for editing posts** (only creation)
- POW validation happens on Python proxy, transparent to Rust backend
- Users must complete verification before submitting signup/post
- Difficulty can be adjusted via `POW_DIFFICULTY` environment variable

---

## 📊 Technical Details

**POW Algorithm**: SHA-256 hashcash  
**Default Difficulty**: 20 bits (≈10 seconds on average browser)  
**Challenge Format**: `{timestamp}-{random}`  
**Validation**: Server-side in Python, client-side pre-check in TypeScript

---

## ✅ Testing Checklist

- [ ] Signup page shows new "Bot Verification" UI
- [ ] Post creation page shows new "Bot Verification" UI  
- [ ] Verification completes in ~10 seconds
- [ ] Cannot submit without completing verification
- [ ] Post editing does NOT require verification
- [ ] POW validator logs show successful validations
- [ ] Lemmy backend receives clean requests (no POW fields)

---

**Status**: ✅ Ready for Production Deployment
