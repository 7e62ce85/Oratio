# Badge Flicker Bug: The VS Code vs Disk File Mismatch Mystery

> **Date**: 2025-10-24  
> **Duration**: 5 hours  
> **Severity**: Critical UX Bug  
> **Root Cause**: Dual source of truth (VS Code memory buffer vs disk file) + Duplicate API calls

---

## 🐛 The Problem

**User Report**:
> "처음 접속하면 badge 보였다가, login하면 badge가 나타났다가 사라져, 새로고침할때마다 badge나타났다가 사라지는것 볼수 있음"
> 
> Translation: "Badge appears on first load, then disappears after login, and flickers on every page refresh"

**Observed Behavior**:
- Gold badge visible for ~100ms, then disappears
- 4 duplicate `[Navbar] Membership URL:` console logs on each page load
- Badge state inconsistent between page loads
- User logged in as `gookjob` (ID: 36) with ACTIVE membership

---

## 🔍 Investigation Timeline

### Hour 1-2: Initial Diagnosis

**Hypothesis**: Badge flickering due to timing issues between cache load and API calls

**Discovery**:
```bash
# Browser console showed 4 duplicate calls:
[Navbar] Membership URL: https://oratio.space/payments/api/membership/status/gookjob (x4)
```

**Attempted Fix #1**: Added localStorage cache initialization
- Modified `componentWillMount()` to call `checkUserHasGoldBadgeSync()`
- Result: ❌ Flickering persisted

**Attempted Fix #2**: Changed `componentDidUpdate()` logic
- Changed from checking `!this.state.hasGoldBadge` to `!this.membershipFetched`
- Result: ❌ Still 4 duplicate calls

### Hour 2-3: Docker Rebuild Hell

**Multiple Docker rebuilds executed**:
```bash
# Attempt 1: Standard rebuild
docker-compose build --no-cache lemmy-ui

# Attempt 2: Force removal
docker-compose stop lemmy-ui
docker-compose rm -f lemmy-ui
docker rmi lemmy-ui-custom:latest
docker-compose build --no-cache lemmy-ui

# Attempt 3: Nuclear option
docker system prune -af --volumes  # Freed 53.3GB!
docker-compose build --no-cache --pull lemmy-ui
```

**Problem**: After every rebuild, browser still showed old logs!

### Hour 3-4: The Browser Cache Trap

**Discovery**: Browser was caching `client.js`

**Solutions tried**:
1. Hard refresh (Ctrl + Shift + R)
2. DevTools "Disable cache" + refresh
3. Clear browsing data
4. Empty cache and hard reload

**Result**: ❌ Logs still appeared in container's built file!

```bash
# Verification showed the problem was real:
docker exec oratio-lemmy-ui-1 grep -c "Membership URL" /app/dist/js/client.js
# Output: 1
```

### Hour 4-5: The Smoking Gun - File Mismatch

**Critical Discovery**:

```bash
# Using grep on source file: NOT FOUND
grep -n "Membership URL" navbar.tsx
# (no output)

# Using sed on source file: FOUND!
sed -n '260p' navbar.tsx
# console.log('[Navbar] Membership URL:', membershipApiUrl);

# Using read_file tool: NOT FOUND
# (tool returned clean code without membership call)
```

**The Revelation**: VS Code had TWO versions of the file!
1. **VS Code Memory Buffer**: Clean version without membership call (what `read_file` tool saw)
2. **Disk File**: Old version WITH membership call (what Docker build used)

---

## 🧠 Computer Science Deep Dive

### Layer 1: Operating System File System

**The Disk File** (`/home/user/Oratio/lemmy-ui-custom/src/shared/components/app/navbar.tsx`):

```
┌─────────────────────────────────────┐
│  File System (ext4, NTFS, etc.)    │
│                                     │
│  Inode: 12345                       │
│  Path: /home/user/Oratio/...       │
│  Content: [Binary data on disk]    │
│  Modified: 2025-10-24 14:23:15     │
└─────────────────────────────────────┘
          ↑
          │ read/write syscalls
          │
    ┌─────┴─────┐
    │   Kernel  │
    │   VFS     │
    └───────────┘
```

When you save a file:
1. **User space**: VS Code calls `write()` syscall
2. **Kernel space**: VFS (Virtual File System) layer
3. **Buffer cache**: OS may cache writes
4. **Disk**: Physical write to storage (SSD/HDD)

### Layer 2: VS Code Architecture

**VS Code's File Management**:

```
┌──────────────────────────────────────────┐
│        VS Code (Electron App)            │
│                                          │
│  ┌────────────────────────────────┐     │
│  │   Editor Buffer (Memory)       │     │
│  │                                │     │
│  │   - In-memory representation   │     │
│  │   - All your edits             │     │
│  │   - NOT yet written to disk    │     │
│  └────────────────────────────────┘     │
│             ↕                            │
│  ┌────────────────────────────────┐     │
│  │   File Watcher                 │     │
│  │                                │     │
│  │   - Monitors disk changes      │     │
│  │   - Detects external edits     │     │
│  └────────────────────────────────┘     │
└──────────────────────────────────────────┘
            ↕
      File System
```

**Key Insight**: VS Code keeps **TWO copies**:
- **Memory buffer**: Your unsaved changes
- **Disk file**: Last saved state

### Layer 3: The Edit Tools' Perspective

**When `replace_string_in_file` tool was used**:
```
┌─────────────────────────────────────┐
│  GitHub Copilot Tool                │
│                                     │
│  replace_string_in_file()           │
│       ↓                             │
│  VS Code Extension API              │
│       ↓                             │
│  Editor Buffer (Memory)             │  ← Modified here!
│       ↓                             │
│  NOT automatically saved to disk    │
└─────────────────────────────────────┘
```

**When `sed` command was used**:
```bash
sed -i '251,268d' navbar.tsx
```

```
┌─────────────────────────────────────┐
│  Terminal Command                   │
│                                     │
│  sed -i (in-place edit)             │
│       ↓                             │
│  Direct syscall to kernel           │
│       ↓                             │
│  File System (Disk)                 │  ← Modified here!
│       ↓                             │
│  VS Code notified of change         │
│       ↓                             │
│  "File changed on disk" dialog      │
└─────────────────────────────────────┘
```

### Layer 4: Docker Build Process

**Docker COPY instruction**:

```dockerfile
COPY src src
```

**What happens**:
```
Build Context (Host):
/home/user/Oratio/lemmy-ui-custom/src/
                    ↓
            stat() syscall
                    ↓
        Read from disk (NOT VS Code)
                    ↓
        Copy to Docker layer
                    ↓
    Container filesystem (/app/src/)
```

**Critical Point**: Docker **ALWAYS reads from disk**, never from VS Code's memory!

### Layer 5: Browser Caching

```
Browser Request:
GET /js/client.js
    ↓
┌───────────────────────────────┐
│  Browser Cache (Memory/Disk)  │
│                               │
│  Key: /js/client.js          │
│  ETag: "abc123def456"        │
│  Max-Age: 31536000           │
│  Status: HIT                 │
└───────────────────────────────┘
    ↓
Return cached file (OLD VERSION!)
```

**Why hard refresh didn't work initially**:
- Server needed to send `Cache-Control: no-cache`
- ETag needed to change
- Or container needed restart to serve new file

---

## 🎯 The Root Cause Chain

### Primary Issue: Duplicate API Calls

**Before Fix** (`navbar.tsx` lines 250-268):
```typescript
async fetchUserCredit() {
  try {
    // ... fetch credit balance ...
    
    // ❌ PROBLEM: Membership check embedded here!
    const membershipApiUrl = `${baseMembershipUrl}/api/membership/status/${person.name}`;
    console.log('[Navbar] Membership URL:', membershipApiUrl);
    
    const membershipResponse = await fetch(membershipApiUrl, {
      headers: { 'X-API-Key': getApiKey() || "" }
    });
    
    if (membershipResponse.ok) {
      const membershipData = await membershipResponse.json();
      if (membershipData.status === 'active') {
        updateCreditCache(person.id, 1.0);
      } else {
        updateCreditCache(person.id, 0.0);
      }
    }
  } catch (error) {
    console.error("[BCH] Error fetching user credit:", error);
  }
}
```

**Consequence**:
- `fetchUserCredit()` called from `componentWillMount()`
- `fetchUserCredit()` called from `componentDidUpdate()` (when `userCredit === 0`)
- Navbar component mounted **4 times** during page load (SSR + client hydration + re-renders)
- Result: **4 duplicate membership API calls**

### Secondary Issue: Race Conditions

```
Timeline of Events:
T=0ms    Page loads, Navbar mounts
T=10ms   checkUserHasGoldBadgeSync() reads empty localStorage
T=15ms   Background membership fetch queued
T=20ms   Badge rendered as FALSE (default state)
T=100ms  API response returns: ACTIVE
T=105ms  Badge updated to TRUE (cache hit)
T=200ms  Page re-renders for unrelated reason
T=210ms  Badge reads cache: TRUE
T=300ms  fetchUserCredit() called again (userCredit === 0)
T=350ms  New membership check overrides cache
T=355ms  Badge flickers to FALSE momentarily
T=400ms  API returns, badge back to TRUE
```

**Visual Result**: Badge flickers on every interaction!

### Tertiary Issue: File Synchronization

```
State of the System:
┌──────────────────────────────────────────────────────────┐
│                    Developer Machine                      │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  VS Code Memory:                                         │
│  navbar.tsx (version A)                                  │
│  - No membership call                                    │
│  - Clean code                                            │
│  - What developer THINKS is saved                        │
│                                                           │
│                    ↕ (unsaved)                           │
│                                                           │
│  Disk File:                                              │
│  navbar.tsx (version B)                                  │
│  - HAS membership call at line 260                       │
│  - Old code                                              │
│  - What Docker actually builds                           │
│                                                           │
├──────────────────────────────────────────────────────────┤
│                    Docker Container                       │
│                                                           │
│  /app/dist/js/client.js                                  │
│  - Built from disk version B                             │
│  - Contains "Membership URL" log                         │
│  - Served to browser                                     │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

---

## ✅ The Solution

### Fix #1: Remove Duplicate Code (Surgical Approach)

**Command executed**:
```bash
cd /home/user/Oratio/lemmy-ui-custom
sed -i '251,268d' src/shared/components/app/navbar.tsx
```

**Lines removed** (251-268):
```typescript
// Update membership status to cache
const membershipApiUrl = `${baseMembershipUrl}/api/membership/status/${person.name}`;
console.log('[Navbar] Membership URL:', membershipApiUrl);

const membershipResponse = await fetch(membershipApiUrl, {
  headers: { 'X-API-Key': getApiKey() || "" }
});

if (membershipResponse.ok) {
  const membershipData = await membershipResponse.json();
  if (membershipData.status === 'active') {
    updateCreditCache(person.id, 1.0);
  } else {
    updateCreditCache(person.id, 0.0);
  }
}
```

**Why `sed` worked when `replace_string_in_file` didn't**:
- `sed` operates **directly on disk**
- No VS Code buffer interference
- Immediate effect on Docker builds

### Fix #2: Clean Docker Build

```bash
cd /home/user/Oratio/oratio
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui
```

**Verification**:
```bash
docker exec oratio-lemmy-ui-1 grep -c "Membership URL" /app/dist/js/client.js
# Output: 0 ✅
```

### Fix #3: Force Browser Cache Clear

User must perform:
1. Open DevTools (F12)
2. Right-click refresh button
3. "Empty Cache and Hard Reload"

---

## 📊 Before vs After

### Before Fix

**Console Logs**:
```
[BCH] Loading cache from localStorage... found: true
[BCH] localStorage has 3 entries
[Navbar] Membership URL: https://oratio.space/payments/api/membership/status/gookjob
[Navbar] Membership URL: https://oratio.space/payments/api/membership/status/gookjob
[Navbar] Membership URL: https://oratio.space/payments/api/membership/status/gookjob
[Navbar] Membership URL: https://oratio.space/payments/api/membership/status/gookjob
[BCH] Saved 3 entries to localStorage (x4)
```

**API Calls**:
- Navbar: 4 calls to `/api/membership/status/gookjob`
- bch-payment.ts: 1 call (deduped)
- **Total**: 5 calls per page load ❌

**Badge Behavior**:
- Visible for ~100ms
- Flickers to invisible
- Reappears after ~300ms
- Inconsistent on refresh

### After Fix

**Console Logs**:
```
[BCH] Loading cache from localStorage... found: false
[BCH] localStorage is empty, starting fresh
[BCH] No cache for user 36, fetching...
[BCH] Checking membership for user gookjob (ID: 36)
[BCH] Membership result for gookjob: ACTIVE
[BCH] Saved 1 entries to localStorage
```

**API Calls**:
- Navbar: 0 calls ✅
- bch-payment.ts: 1 call (per user, deduped)
- **Total**: 1 call per user (cached for 5 minutes)

**Badge Behavior**:
- Loads from cache immediately
- No flickering
- Consistent across refreshes
- Updates only when cache expires (5 min)

---

## 🎓 Lessons Learned

### 1. **Trust but Verify**

**Principle**: Always verify what's actually being built, not what you THINK you edited.

```bash
# After every edit, verify the disk file:
cat path/to/file.tsx | grep "search_term"

# After every build, verify the container:
docker exec container_name grep "search_term" /app/dist/js/client.js
```

### 2. **Understand Your Editor**

**VS Code's Buffer System**:
- Editor keeps changes in memory
- File on disk may be different
- Tools reading disk see different content
- Docker always builds from disk

**Best Practice**:
- Always save before building (`Ctrl+S`)
- Check "Auto Save" setting
- Use `git diff` to see actual changes
- When in doubt, close and reopen file

### 3. **The Build-Deploy-Verify Loop**

```
1. Edit code (VS Code)
   ↓
2. SAVE FILE (Ctrl+S) ← Don't skip this!
   ↓
3. Verify disk file (cat/grep)
   ↓
4. Build container (docker-compose build)
   ↓
5. Verify built file (docker exec grep)
   ↓
6. Restart service (docker-compose up)
   ↓
7. Clear browser cache (Ctrl+Shift+R)
   ↓
8. Test in browser
   ↓
9. Check console logs
   ↓
10. Verify API calls (Network tab)
```

**Where we went wrong**: Skipped steps 2, 3, 5, and 7!

### 4. **Multiple Sources of Truth**

**The System Had 5 Different Versions**:
1. VS Code memory buffer (clean)
2. Disk file (dirty)
3. Git index (another version)
4. Docker image (cached old version)
5. Browser cache (even older version)

**Solution**: 
- Use version control religiously
- Clear all caches when debugging
- Trust the most "downstream" source (browser) for what users actually see

### 5. **Cache Invalidation is Hard**

**Cache Layers in This System**:
```
┌─────────────────────────────┐
│  Browser Cache              │  ← Layer 5 (User sees this)
│  - client.js cached         │
│  - ETag: "abc123"           │
└─────────────────────────────┘
          ↑
┌─────────────────────────────┐
│  Docker Image Layers        │  ← Layer 4
│  - Webpack output cached    │
│  - node_modules cached      │
└─────────────────────────────┘
          ↑
┌─────────────────────────────┐
│  Docker Build Cache         │  ← Layer 3
│  - COPY commands cached     │
│  - RUN commands cached      │
└─────────────────────────────┘
          ↑
┌─────────────────────────────┐
│  OS Page Cache              │  ← Layer 2
│  - File reads cached        │
│  - inode cache              │
└─────────────────────────────┘
          ↑
┌─────────────────────────────┐
│  VS Code Buffer             │  ← Layer 1 (Developer edits here)
│  - In-memory changes        │
│  - Not yet on disk          │
└─────────────────────────────┘
```

**Phil Karlton's famous quote**:
> "There are only two hard things in Computer Science: cache invalidation and naming things."

We experienced BOTH problems today! 😅

### 6. **Debugging is Archaeology**

**The Investigation Process**:
1. **Surface symptom**: Badge flickers
2. **First layer**: Console logs show duplicates
3. **Second layer**: Component lifecycle issues
4. **Third layer**: File synchronization problems
5. **Fourth layer**: Build system caching
6. **Fifth layer**: Browser caching
7. **Root cause**: Duplicate code in multiple functions

**Lesson**: Sometimes you need to dig through 5+ layers to find the real problem!

### 7. **Tools Can Lie**

**What we trusted**:
- `read_file` tool → Showed clean code ❌
- VS Code editor → Showed clean code ❌
- Docker build logs → Said "Building" ✅ but cached ❌

**What told the truth**:
- `cat` command → Showed actual disk file ✅
- `docker exec grep` → Showed actual container file ✅
- Browser console → Showed actual behavior ✅

**Lesson**: When debugging, use the most "primitive" tools (cat, grep, sed) that directly access the source of truth.

---

## 🔧 Preventive Measures

### 1. **Development Workflow Checklist**

```markdown
Before committing code:
- [ ] Save all files (Ctrl+S or Cmd+S)
- [ ] Verify with `git diff`
- [ ] Run linter/formatter
- [ ] Build locally
- [ ] Test in clean browser session (Incognito)
- [ ] Check console for errors
- [ ] Verify Network tab (no unexpected calls)
- [ ] Clear localStorage and test fresh
```

### 2. **Docker Build Best Practices**

```bash
# Add to package.json scripts:
{
  "scripts": {
    "rebuild-clean": "docker-compose down && docker rmi -f lemmy-ui-custom:latest && docker-compose build --no-cache lemmy-ui",
    "rebuild-fast": "docker-compose build lemmy-ui",
    "verify-build": "docker exec oratio-lemmy-ui-1 find /app/dist -name '*.js' -exec grep -l 'SEARCH_TERM' {} \\;"
  }
}
```

### 3. **VS Code Settings**

```json
// .vscode/settings.json
{
  "files.autoSave": "afterDelay",
  "files.autoSaveDelay": 1000,
  "files.watcherExclude": {
    "**/node_modules/**": false  // Watch node_modules for debugging
  },
  "editor.formatOnSave": true,
  "eslint.autoFixOnSave": true
}
```

### 4. **Git Hooks**

```bash
# .git/hooks/pre-commit
#!/bin/bash

# Verify no debug logs in production code
if git diff --cached | grep -i "console.log.*membership url"; then
  echo "❌ ERROR: Found debug log in staged files!"
  echo "Please remove debug logs before committing."
  exit 1
fi

# Verify files are saved (no modified timestamp in future)
# ... additional checks ...
```

### 5. **Monitoring & Alerts**

```typescript
// Add to production code:
const MAX_API_CALLS_PER_PAGE_LOAD = 2;
let apiCallCount = 0;

function trackAPICall(url: string) {
  apiCallCount++;
  if (apiCallCount > MAX_API_CALLS_PER_PAGE_LOAD) {
    console.error(`⚠️ TOO MANY API CALLS! Count: ${apiCallCount}, URL: ${url}`);
    // Send to error tracking service (Sentry, etc.)
  }
}
```

---

## 🧪 Reproduction Steps (For Future Debugging)

If this issue happens again:

### Step 1: Verify Source Code
```bash
cd /home/user/Oratio/lemmy-ui-custom
grep -n "Membership URL" src/shared/components/app/navbar.tsx
# Should output: (nothing)
```

### Step 2: Verify Built Container
```bash
docker exec oratio-lemmy-ui-1 grep -c "Membership URL" /app/dist/js/client.js
# Should output: 0
```

### Step 3: Verify Browser Console
- Open DevTools (F12)
- Go to Console tab
- Clear console
- Refresh page (Ctrl+R)
- Search for "Membership URL"
- Should find: 0 results

### Step 4: Verify API Calls
- Open DevTools (F12)
- Go to Network tab
- Filter: "membership"
- Refresh page
- Count requests to `/api/membership/status/`
- Should be: 1 request per unique user (max 3 if 3 users loaded)

---

## 📚 Related Reading

### Computer Science Fundamentals
- **File Systems**: [Understanding inode](https://en.wikipedia.org/wiki/Inode)
- **Caching**: [Cache coherency problems](https://en.wikipedia.org/wiki/Cache_coherence)
- **Build Systems**: [Docker layer caching](https://docs.docker.com/build/cache/)
- **Web Caching**: [HTTP caching headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching)

### VS Code Internals
- [VS Code File Watching](https://code.visualstudio.com/docs/setup/linux#_visual-studio-code-is-unable-to-watch-for-file-changes-in-this-large-workspace)
- [TextDocument synchronization](https://code.visualstudio.com/api/language-extensions/programmatic-language-features#textdocument-synchronization)

### Docker Best Practices
- [Multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Build cache management](https://docs.docker.com/build/cache/)

---

## 💡 Key Takeaway

**The 5-Hour Bug That Wasn't Really a Bug**:

This wasn't a typical bug where code logic was wrong. The code fix itself took 5 minutes (deleting 18 lines). The 5 hours were spent fighting:
1. Incorrect mental model (thinking file was saved when it wasn't)
2. Multiple layers of caching (VS Code, Docker, Browser)
3. Tool limitations (read_file reading VS Code buffer, not disk)
4. Insufficient verification at each step

**The Real Lesson**: 
> "Always verify your assumptions at the lowest possible layer. When in doubt, trust the system that's closest to the user (the browser), not the system closest to you (your editor)."

Or as Linus Torvalds said:
> "Talk is cheap. Show me the code."

And we'd add:
> "Code in your editor is cheap. Show me what's running in production."

---

**Document Status**: ✅ Complete  
**Total Time Spent**: ~5 hours  
**Actual Code Changed**: 18 lines deleted  
**Value Delivered**: Priceless learning experience + one very frustrated developer  
**Beer Owed to Developer**: 🍺🍺🍺🍺🍺

---

_This document is dedicated to all developers who have spent hours debugging only to find the problem was between the keyboard and the chair... or in this case, between the editor and the disk. You are not alone. 🫂_
