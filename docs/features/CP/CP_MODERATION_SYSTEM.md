# CP (Child Pornography) Content Moderation System

> **Version**: v2.3 | **Created**: 2025-11-07 | **Last Update**: 2025-11-22 | **Status**: ✅ **IN PRODUCTION** (Stabilization Phase)



------



## 📋 Table of Contents## 📋 Table of Contents



1. [Quick Start](#-quick-start)1. [Quick Start](#-quick-start)

2. [System Overview](#-system-overview)2. [System Overview](#-system-overview)

3. [How It Works](#-how-it-works)3. [How It Works](#-how-it-works)

4. [User Guide](#-user-guide)4. [API Reference](#-api-reference)

5. [Technical Implementation](#-technical-implementation)5. [Frontend Implementation](#-frontend-implementation-guide)

6. [API Reference](#-api-reference)6. [Database Schema](#-database-schema)

7. [Database Schema](#-database-schema)7. [Deployment](#-deployment)

8. [Deployment](#-deployment)8. [Testing](#-testing)

9. [Testing](#-testing)9. [Troubleshooting](#-troubleshooting)

10. [Troubleshooting](#-troubleshooting)10. [Monitoring](#-monitoring)



------



## 🚀 Quick Start## 🚀 Quick Start



### Complete System Deployment### Deploy Backend (2 minutes)



```bash```bash

# 1. Deploy backendcd /home/user/Oratio/oratio

cd /home/user/Oratio/oratiobash deploy_cp_system.sh

bash deploy_cp_system.sh```



# 2. Rebuild UI with CP moderation components### Verify Deployment

docker-compose stop lemmy-ui

docker-compose build --no-cache lemmy-ui```bash

docker-compose up -d lemmy-ui# Check health

curl -H "X-API-Key: YOUR_KEY" http://localhost:8081/api/cp/health

# 3. Verify deployment

curl -H "X-API-Key: YOUR_KEY" https://oratio.space/payments/api/cp/health# Expected: {"status": "healthy", "service": "cp-moderation"}

``````



### What's Included### What's Included



✅ **Backend (100% Complete)**✅ **Backend (100% Complete)**

- Database schema with 7 tables- Database schema with 7 tables

- 15+ API endpoints- 15+ API endpoints

- Business logic for all 8 rules- Business logic for all 8 rules

- Background tasks (auto-unban, auto-delete)- Background tasks (auto-unban, auto-delete)

- Complete audit trail- Complete audit trail

- Notification system- Notification system



✅ **Frontend (100% Complete)**❌ **Frontend (Not Started)**

- CP Report button on posts/comments- UI components needed (see [Frontend Implementation](#-frontend-implementation-guide))

- Moderator review panel

- Admin control panel---

- Appeal form for banned users

- Permission checks on content creation## 🎯 System Overview

- Navbar notification badges

- Complete UI/UX flow**CP Moderation System**: Comprehensive content moderation framework for handling child pornography reports with automatic content hiding, moderator review, admin escalation, user bans, and appeals.



---### Core Features



## 🎯 System Overview| Feature | Status | Description |

|---------|--------|-------------|

**CP Moderation System**: Production-ready framework for handling CP content reports with automatic hiding, multi-level review, user management, and appeals process.| **CP Reporting** | ✅ Complete | Anyone can report CP content |

| **Auto-Hide** | ✅ Complete | Content immediately hidden on report |

### Core Features| **Moderator Review** | ✅ Complete | Community moderators review reports |

| **Admin Escalation** | ✅ Complete | Re-reports go to admin |

| Feature | Status | Location || **User Bans** | ✅ Complete | 3-month automatic bans for CP violations |

|---------|--------|----------|| **Report Ability Loss** | ✅ Complete | False reporters lose reporting rights |

| **CP Reporting** | ✅ Deployed | Three-dot menu on posts/comments || **Appeals System** | ✅ Complete | Membership users can appeal decisions |

| **Auto-Hide** | ✅ Deployed | Backend service || **Admin Management** | ✅ Complete | Manual user permission control |

| **Moderator Review** | ✅ Deployed | `/cp/moderator-review` || **Auto-Unban** | ✅ Complete | Automatic unban after 3 months |

| **Admin Control** | ✅ Deployed | `/cp/admin-panel` || **Auto-Delete** | ✅ Complete | Unreviewed admin cases deleted after 1 week |

| **User Bans** | ✅ Deployed | Automatic 3-month bans || **Notifications** | ✅ Complete | System-wide notification framework |

| **Report Ability Loss** | ✅ Deployed | Automatic revocation for false reports || **Frontend UI** | ❌ Pending | React components needed |

| **Appeals System** | ✅ Deployed | `/cp/appeal` |

| **Permission Checks** | ✅ Deployed | Post/comment creation |---

| **Navbar Notifications** | ✅ Deployed | Red badge counters |

| **Auto-Unban** | ✅ Deployed | Background task (15s interval) |## 📖 How It Works

| **Auto-Delete** | ✅ Deployed | Background task (7-day timeout) |

### The 8 Rules

---

#### Rule 1: Anyone can report CP content

## 📖 How It Works

```

### The 8 Rules (All Implemented)User clicks "Report CP" → API validates permission → Report created

```

#### Rule 1: Anyone can report CP content ✅

**Who can report:**

**User Experience:**- ✅ Free users (until revoked)

1. Open post or comment- ✅ Membership users (can appeal if revoked)

2. Click three-dot menu (⋮)- ❌ Banned users

3. Click "Report CP" (red alert-triangle icon ⚠️)

4. Confirm in modal dialog#### Rule 2: Content immediately hidden

5. Optionally add reason

6. Submit```

Report submitted → content_hidden = TRUE → Users cannot see it

**Technical Flow:**```

```

User clicks "Report CP" → Frontend checks membership status → **Visibility:**

API validates permission → Report created → Content hidden immediately- ❌ Regular users: Cannot see

```- ✅ Moderators: Can see for review

- ✅ Admins: Can see for review

#### Rule 2: Content immediately hidden ✅

#### Rule 3: Moderators notified for review

**Visibility Matrix:**

- ❌ Regular users: Cannot see hidden content```

- ✅ Moderators: Can see for reviewReport created → Notify community moderators → Review panel updated

- ✅ Admins: Can see for review```

- ❌ Creator: Cannot see own hidden content

**Notification includes:**

#### Rule 3: Moderators notified for review ✅- Content type (post/comment)

- Reporter username

**Moderator Experience:**- Creator username

1. See red badge on navbar (⚠️ icon)- Report reason

2. Click to navigate to `/cp/moderator-review`

3. View list of pending reports#### Rule 4: Moderator decision consequences

4. See content details, reporter, creator

5. Choose "Confirm CP" or "Not CP"**Decision: "CP Confirmed"**

```

**Consequences:**→ Creator banned for 3 months

- **Confirm CP** → Creator banned 3 months, content stays hidden→ Content stays hidden permanently

- **Not CP** → Reporter loses report ability, content unhidden→ Creator can appeal (if membership user)

```

#### Rule 4: Moderator decisions have consequences ✅

**Decision: "Not CP"**

Both parties can appeal if they have membership (Gold Badge).```

→ Reporter loses report ability

#### Rule 5: Membership users can appeal ✅→ Content can be unhidden

→ Reporter can appeal (if membership user)

**Appeal Experience:**```

1. Banned user navigates to `/cp/appeal`

2. System checks for active ban#### Rule 5: Membership users can appeal

3. Checks for Gold Badge membership

4. User writes appeal (max 2000 chars)```

5. Submits for admin reviewBan/Loss → Membership user submits appeal → Admin reviews → Decision

6. Only one active appeal allowed```



#### Rule 6: Re-report escalation logic ✅**Appeal types:**

- Ban appeal

**Scenario: Moderator marks as "Not CP"**- Report ability restoration

- Free user tries to re-report → ❌ BLOCKED

- Membership user re-reports → ✅ ESCALATES TO ADMIN#### Rule 6: Re-report escalation logic

Note: Membership status is now derived server-side (membership service lookup) when a report is submitted. This prevents client-side cache differences from blocking membership users from re-reporting on feed pages — membership users (e.g., `gookjob`) will be allowed to re-report from the feed as well as the post page and the report will correctly escalate to Admin when appropriate.



**Scenario: Admin approves****After moderator approves as "Not CP":**

- Anyone tries to re-report → ❌ BLOCKED PERMANENTLY

```

#### Rule 7: Auto-delete unreviewed admin cases ✅Free user tries to re-report → ❌ BLOCKED

Membership user re-reports → ✅ ESCALATES TO ADMIN

``````

Admin case created → 7-day countdown → Not reviewed? → PERMANENT DELETE

```**After admin approves:**
Note: When an Admin performs a final "Confirm CP" decision on an escalated report, the system attempts to remove the content from Lemmy immediately and marks the CP report as permanently deleted in the CP DB. After a successful admin confirmation the content is considered permanently deleted and will not be visible to regular users, moderators, or admins.

```

Runs automatically every 15 seconds in background task.Anyone tries to re-report → ❌ BLOCKED PERMANENTLY

```

#### Rule 8: Admin manual controls ✅

#### Rule 7: Auto-delete unreviewed admin cases

**Admin Panel** (`/cp/admin-panel`) has 3 tabs:

```

**Tab 1: Pending Reports**Admin case created → 7-day countdown → Not reviewed? → PERMANENT DELETE

- Admin-escalated cases```

- Approve (Not CP) or Reject (Confirm CP) buttons

- Shows escalation context#### Rule 8: Admin manual controls



**Tab 2: Manage Users**Admin can manually:

- Search by username- ✅ Ban/unban users

- View full permission status- ✅ Revoke/restore report ability

- Manual actions: Ban/Unban, Revoke/Restore report ability- ✅ Set moderator CP review permissions

- ✅ Review appeals

**Tab 3: Appeals**

- Placeholder (use "Manage Users" tab to restore privileges)---



---## 📡 API Reference



## 👤 User Guide### Base URL

```

### For Regular Usershttp://localhost:8081/api/cp

```

#### How to Report CP Content

### Authentication

1. **Find the Content** - Navigate to the post or commentAll endpoints require `X-API-Key` header.

2. **Open Actions Menu** - Click the three-dot menu (⋮)

3. **Report CP** - Click "Report CP" (red ⚠️ icon)### Endpoints Summary

4. **WARNING**: False reports may result in losing report ability

5. **Confirm & Submit** - Optionally add reason, click "Yes, Report CP"#### User Permissions

```http

#### What Happens After ReportingGET  /api/cp/permissions/{user_id}

GET  /api/cp/permissions/can-report/{user_id}

**If Confirmed as CP:**POST /api/cp/permissions/initialize

- ✅ Creator banned for 3 months```

- ✅ Content stays hidden permanently

- ✅ You maintain report ability#### CP Reports

```http

**If Rejected as Not CP:**POST /api/cp/report                          # Submit report

- ❌ You lose CP report abilityGET  /api/cp/report/{report_id}              # Get report

- ℹ️ If you have membership, you can appealGET  /api/cp/reports/pending                 # List pending

POST /api/cp/report/{report_id}/review       # Review report

### For Moderators```



#### Accessing Review Panel#### Appeals

```http

1. Look for red badge on navbar (⚠️ icon with count)POST /api/cp/appeal                          # Submit appeal

2. Click to navigate to `/cp/moderator-review`GET  /api/cp/appeal/{appeal_id}              # Get appeal

POST /api/cp/appeal/{appeal_id}/review       # Admin review

#### Reviewing Reports```



**Decision Options:**#### Admin Management

```http

**🔴 Confirm CP**POST /api/cp/admin/user/{user_id}/ban

- Creator automatically banned 3 monthsPOST /api/cp/admin/user/{user_id}/revoke-report

- Content remains hiddenPOST /api/cp/admin/user/{user_id}/restore

- Creator can appeal if membership user```



**🟢 Not CP**#### Notifications

- Reporter loses reporting ability```http

- Content unhiddenGET  /api/cp/notifications/{person_id}

- Reporter can appeal if membership userPOST /api/cp/notifications/{notification_id}/read

- If membership user re-reports, escalates to admin```



### For Admins#### System

```http

#### Accessing Admin PanelGET  /api/cp/health

POST /api/cp/background/run-tasks

1. Look for shield badge on navbar (🛡️ with count)```

2. Click to navigate to `/cp/admin-panel`

### API Examples

#### Tab 1: Pending Reports

#### Submit CP Report

- Admin-escalated cases (moderator said "Not CP", membership user re-reported)

- **Approve**: Moderator was right```bash

- **Reject**: Content is CP, ban creatorcurl -X POST http://localhost:8081/api/cp/report \

  -H "Content-Type: application/json" \

#### Tab 2: Manage Users  -H "X-API-Key: YOUR_KEY" \

  -d '{

1. Search username    "content_type": "post",

2. View permissions: Can Report, Is Banned, Ban Count, etc.    "content_id": 123,

3. Manual actions: Ban, Unban, Revoke Report, Restore Report    "community_id": 1,

    "reporter_user_id": "user123",

---    "reporter_person_id": 456,

    "reporter_username": "john",

## 🔧 Technical Implementation    "reporter_is_member": true,

    "creator_user_id": "baduser",

### Frontend Components    "creator_person_id": 789,

#### 1. CP Report Button    "creator_username": "violator",

**File**: `content-action-dropdown.tsx`    "reason": "Contains inappropriate content"

**Route**: Three-dot menu on posts/comments  ```

**Features**: Confirmation modal, membership check, API integration

#### Check User Permissions

#### 2. Permission Checks

**Files**: `post-form.tsx`, `comment-form.tsx`  ```bash

**Features**: Check on mount, block if banned, show expiration datecurl -H "X-API-Key: YOUR_KEY" \

  http://localhost:8081/api/cp/permissions/can-report/user123

#### 3. Moderator Review Panel

**File**: `moderator-review-panel.tsx`  # Response: {"can_report": true, "message": null}

**Route**: `/cp/moderator-review`  ```

**Features**: List pending reports, review buttons, auto-refresh

#### Get Pending Reports (Moderator)

#### 4. Admin Control Panel

**File**: `admin-control-panel.tsx`  ```bash

**Route**: `/cp/admin-panel`  curl -H "X-API-Key: YOUR_KEY" \

**Features**: 3-tab interface, user search, manual actions  "http://localhost:8081/api/cp/reports/pending?community_id=1&escalation_level=moderator"

```

#### 5. Appeal Form

**File**: `appeal-form.tsx`  #### Review Report

**Route**: `/cp/appeal`  

**Features**: Membership check, 2000 char limit, guidelines```bash

curl -X POST http://localhost:8081/api/cp/report/REPORT_ID/review \

#### 6. CP Utility Module  -H "Content-Type: application/json" \

**File**: `cp-moderation.ts`    -H "X-API-Key: YOUR_KEY" \

**Exports**: All API wrapper functions with 1-min caching  -d '{

    "reviewer_person_id": 456,

#### 7. Navbar Integration    "reviewer_username": "moderator",

**File**: `navbar.tsx`      "reviewer_role": "moderator",

**Features**: Notification badges (30s polling), mod/admin links    "decision": "cp_confirmed",

    "notes": "Clearly violates content policy"

---  }'



## 📡 API Reference# Decisions: "cp_confirmed" | "not_cp" | "admin_approved" | "admin_rejected"

```

### Base URL

```---

https://oratio.space/payments/api/cp

```## 💻 Frontend Implementation Guide



### Authentication### Required Components

All endpoints require `X-API-Key` header.

#### 1. CP Report Button

### Key Endpoints

**Files to modify:**

**User Permissions**- `lemmy-ui-custom/src/shared/components/post/post-listing.tsx`

```http- `lemmy-ui-custom/src/shared/components/comment/comment-node.tsx`

GET /api/cp/permissions/<username>

``````tsx

// Example implementation

**CP Reports**const handleCPReport = async () => {

```http  const response = await fetch('/payments/api/cp/report', {

POST /api/cp/report    method: 'POST',

GET  /api/cp/reports/pending?escalation_level=moderator    headers: {

POST /api/cp/report/<id>/review      'Content-Type': 'application/json',

```      'X-API-Key': getApiKey()

    },

**Appeals**    body: JSON.stringify({

```http      content_type: 'post', // or 'comment'

POST /api/cp/appeal      content_id: post.post.id,

```      community_id: post.community.id,

      reporter_user_id: myUserInfo.username,

**Admin Actions**      reporter_person_id: myUserInfo.local_user_view.person.id,

```http      reporter_username: myUserInfo.local_user_view.person.name,

POST /api/cp/admin/user/<username>/ban      reporter_is_member: await checkUserHasGoldBadge(myUserInfo.local_user_view.person),

POST /api/cp/admin/user/<username>/revoke-report      creator_user_id: post.creator.name,

POST /api/cp/admin/user/<username>/restore      creator_person_id: post.creator.id,

```      creator_username: post.creator.name,

      reason: reportReason

**Notifications**    })

```http  });

GET /api/cp/notifications/<person_id>?unread_only=true  

```  if (response.ok) {

    toast("Content reported and hidden", "success");

---  }

};

## 🗄️ Database Schema```



### Tables#### 2. Moderator Review Panel



- `user_cp_permissions` - User permissions & ban status**New file:** `lemmy-ui-custom/src/shared/components/cp/moderator-review.tsx`

- `cp_reports` - All CP reports

- `cp_reviews` - Review history```tsx

- `cp_appeals` - User appealsimport { Component } from "inferno";

- `cp_notifications` - System notificationsimport { getApiKey } from "@utils/bch-payment";

- `cp_audit_log` - Complete audit trailimport { UserService } from "../../services";

- `moderator_cp_assignments` - Moderator permissionsimport { toast } from "../toast";

import { Spinner } from "../common/icon";

### Useful Queries

interface CPReport {

```sql  id: string;

-- Check user status  content_type: 'post' | 'comment';

SELECT username, can_report_cp, is_banned,   content_id: number;

       datetime(ban_end, 'unixepoch') as ban_expires  reporter_username: string;

FROM user_cp_permissions   creator_username: string;

WHERE username = 'username';  reason: string;

  created_at: number;

-- Recent reports}

SELECT content_type, content_id, reporter_username, creator_username,

       status, datetime(created_at, 'unixepoch') as createdinterface ModeratorReviewState {

FROM cp_reports   reports: CPReport[];

ORDER BY created_at DESC   loading: boolean;

LIMIT 10;}



-- Active bansexport class ModeratorReviewPanel extends Component<{}, ModeratorReviewState> {

SELECT username, ban_count, datetime(ban_end, 'unixepoch') as expires  state: ModeratorReviewState = {

FROM user_cp_permissions     reports: [],

WHERE is_banned = 1;    loading: true

```  };



---  async componentDidMount() {

    await this.fetchPendingReports();

## 🚀 Deployment  }



### Complete Deployment  async fetchPendingReports() {

    const response = await fetch(

```bash      '/payments/api/cp/reports/pending?escalation_level=moderator',

# 1. Deploy backend      { headers: { 'X-API-Key': getApiKey() } }

cd /home/user/Oratio/oratio    );

bash deploy_cp_system.sh    

    const data = await response.json();

# 2. Rebuild frontend    this.setState({ reports: data.reports, loading: false });

docker-compose stop lemmy-ui  }

docker-compose build --no-cache lemmy-ui

docker-compose up -d lemmy-ui  async handleReview(reportId: string, decision: 'cp_confirmed' | 'not_cp', notes: string) {

    const user = UserService.Instance.myUserInfo;

# 3. Restart BCH service    if (!user) return;

docker-compose restart bitcoincash-service

    const response = await fetch(`/payments/api/cp/report/${reportId}/review`, {

# 4. Verify      method: 'POST',

curl -H "X-API-Key: YOUR_KEY" https://oratio.space/payments/api/cp/health      headers: {

```        'Content-Type': 'application/json',

        'X-API-Key': getApiKey()

---      },

      body: JSON.stringify({

## 🧪 Testing        reviewer_person_id: user.local_user_view.person.id,

        reviewer_username: user.local_user_view.person.name,

### Browser Testing        reviewer_role: 'moderator',

        decision,

- [ ] Report button visible on posts/comments        notes

- [ ] Confirmation modal appears      })

- [ ] Toast notifications work    });

- [ ] Banned users blocked from posting

- [ ] Moderator panel loads    if (response.ok) {

- [ ] Admin panel loads with 3 tabs      toast(`Report ${decision === 'cp_confirmed' ? 'confirmed' : 'rejected'}`, 'success');

- [ ] Appeal form validates membership      await this.fetchPendingReports();

- [ ] Navbar badges update    }

  }

### End-to-End Scenario

  render() {

1. User reports CP → Content hidden    if (this.state.loading) return <Spinner />;

2. Moderator reviews → Confirms CP

3. Creator banned → Gets notification    return (

4. Creator appeals (if membership)      <div className="cp-moderator-panel">

5. Admin reviews → Restores or upholds        <h3>Pending CP Reports ({this.state.reports.length})</h3>

        

---        {this.state.reports.map(report => (

          <div key={report.id} className="cp-report-card">

## 🐛 Troubleshooting            <div className="report-info">

              <strong>{report.content_type}</strong> #{report.content_id}

### Report Button Not Visible              <br />

              Reported by: {report.reporter_username}

```bash              <br />

# Hard refresh: Ctrl + Shift + R              Creator: {report.creator_username}

# Or rebuild UI:              <br />

docker-compose stop lemmy-ui              Reason: {report.reason || 'No reason provided'}

docker-compose build --no-cache lemmy-ui            </div>

docker-compose up -d lemmy-ui            

```            <div className="report-actions">

              <button 

### API Returns 404 for Permissions                onClick={() => this.handleReview(report.id, 'cp_confirmed', '')}

                className="btn btn-danger"

**This is normal for first-time users!** Backend now returns default permissions.              >

                Confirm CP

### Navbar Badges Not Updating              </button>

              

Check browser console for polling. Should poll every 30 seconds.              <button 

                onClick={() => this.handleReview(report.id, 'not_cp', '')}

### Background Tasks Not Running                className="btn btn-success"

              >

```bash                Not CP

docker-compose logs bitcoincash-service | grep "CP background"              </button>

# Should see updates every 15 seconds            </div>

```          </div>

        ))}

---      </div>

    );

## 📊 Monitoring  }

}

### Health Check```



```bash#### 3. Permission Checks

curl -H "X-API-Key: YOUR_KEY" https://oratio.space/payments/api/cp/health

```**File to modify:** `lemmy-ui-custom/src/shared/components/post/post-form.tsx`



### Key Metrics```tsx

// Add to post-form.tsx

```sqlasync componentDidMount() {

-- System overview  // Check if user is banned

SELECT   const user = UserService.Instance.myUserInfo;

  (SELECT COUNT(*) FROM user_cp_permissions WHERE is_banned = 1) as active_bans,  if (user) {

  (SELECT COUNT(*) FROM cp_reports WHERE status = 'pending') as pending_reports,    const response = await fetch(

  (SELECT COUNT(*) FROM cp_appeals WHERE status = 'pending') as pending_appeals;      `/payments/api/cp/permissions/${user.local_user_view.person.name}`,

```      { headers: { 'X-API-Key': getApiKey() } }

    );

---    

    if (response.ok) {

## 📝 Changelog      const perms = await response.json();

      if (perms.is_banned) {

      const banEnd = new Date(perms.ban_end * 1000);

        toast(`You are banned until ${banEnd.toLocaleDateString()}`, 'danger');

      }

    }

  }

### v2.0 (2025-11-07)}

- ✅ Complete frontend implementation        const user = UserService.Instance.myUserInfo;

- ✅ All UI components deployed        if (user) {

- ✅ Backend fix: Permissions endpoint returns defaults      this.checkUserStatus(user.local_user_view.person.name);

- ✅ Production tested on oratio.space    }

  }

### v1.0 (2025-11-07)}

- ✅ Backend complete```

- ✅ Database schema

- ✅ All API endpoints#### 4. Utility Functions

- ✅ Background tasks

**New file:** `lemmy-ui-custom/src/shared/utils/cp-moderation.ts`

---

```typescript

**Document Version**: 2.0  import { getApiKey } from "./bch-payment";

**System Version**: v2.0 **PRODUCTION READY**  

**Status**: ✅ Fully Deployed and Tested  export async function checkUserCPPermissions(

**Last Updated**: 2025-11-07    username: string

**Deployment**: oratio.space): Promise<{canPost: boolean, canReport: boolean, message?: string}> {

  

---  try {

    const response = await fetch(

## 🎉 Quick Links      `/payments/api/cp/permissions/${username}`,

      { headers: { 'X-API-Key': getApiKey() } }

- **Report CP**: Three-dot menu on any post/comment    );

- **Moderator Panel**: https://oratio.space/cp/moderator-review    

- **Admin Panel**: https://oratio.space/cp/admin-panel    if (!response.ok) {

- **Submit Appeal**: https://oratio.space/cp/appeal      return { canPost: true, canReport: true }; // Fail open

- **API Health**: https://oratio.space/payments/api/cp/health    }

    
    const perms = await response.json();
    
    return {
      canPost: !perms.is_banned,
      canReport: perms.can_report_cp,
      message: perms.is_banned 
        ? `You are banned until ${new Date(perms.ban_end * 1000).toLocaleDateString()}`
        : !perms.can_report_cp
        ? 'Your CP reporting ability has been revoked'
        : undefined
    };
  } catch (error) {
    console.error("Error checking CP permissions:", error);
    return { canPost: true, canReport: true }; // Fail open
  }
}

export async function submitCPReport(
  contentType: 'post' | 'comment',
  contentId: number,
  communityId: number,
  reporterUsername: string,
  reporterPersonId: number,
  reporterIsMember: boolean,
  creatorUsername: string,
  creatorPersonId: number,
  reason?: string
): Promise<boolean> {
  
  try {
    const response = await fetch('/payments/api/cp/report', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey()
      },
      body: JSON.stringify({
        content_type: contentType,
        content_id: contentId,
        community_id: communityId,
        reporter_user_id: reporterUsername,
        reporter_person_id: reporterPersonId,
        reporter_username: reporterUsername,
        reporter_is_member: reporterIsMember,
        creator_user_id: creatorUsername,
        creator_person_id: creatorPersonId,
        creator_username: creatorUsername,
        reason: reason || ''
      })
    });
    
    return response.ok;
  } catch (error) {
    console.error("Error submitting CP report:", error);
    return false;
  }
}
```

---

## 🗄️ Database Schema

### Tables Overview

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `user_cp_permissions` | User permissions & ban status | `can_report_cp`, `is_banned`, `ban_end` |
| `cp_reports` | All CP reports | `status`, `escalation_level`, `content_hidden` |
| `cp_reviews` | Review history | `decision`, `reviewer_role` |
| `cp_appeals` | User appeals | `appeal_type`, `status` |
| `cp_notifications` | System notifications | `notification_type`, `is_read` |
| `cp_audit_log` | Complete audit trail | `action_type`, `action_details` |
| `moderator_cp_assignments` | Moderator CP permissions | `can_review_cp` |

### Database Inspection

```bash
# Access database
docker exec -it bitcoincash-service sqlite3 /app/data/payment.db
```

```sql
-- Check recent reports
SELECT 
  id, 
  content_type, 
  content_id, 
  reporter_username, 
  creator_username,
  status,
  datetime(created_at, 'unixepoch') as created
FROM cp_reports 
ORDER BY created_at DESC 
LIMIT 10;

-- Check banned users
SELECT 
  username,
  datetime(ban_start, 'unixepoch') as banned_at,
  datetime(ban_end, 'unixepoch') as ban_expires,
  ban_count
FROM user_cp_permissions 
WHERE is_banned = 1;

-- Check users who lost report ability
SELECT username, last_violation
FROM user_cp_permissions 
WHERE can_report_cp = 0;

-- Check pending appeals
SELECT 
  username,
  appeal_type,
  status,
  datetime(created_at, 'unixepoch') as submitted
FROM cp_appeals 
WHERE status = 'pending';

-- Audit trail
SELECT 
  action_type,
  actor_username,
  target_username,
  datetime(created_at, 'unixepoch') as when_happened
FROM cp_audit_log 
ORDER BY created_at DESC 
LIMIT 20;

.exit
```

---

## 🚀 Deployment

### Automated Deployment

```bash
cd /home/user/Oratio/oratio
bash deploy_cp_system.sh
```

The script will:
1. ✅ Verify all files exist
2. ✅ Check Docker containers
3. ✅ Restart bitcoincash-service
4. ✅ Create CP database tables
5. ✅ Test API endpoints
6. ✅ Show deployment summary

### Manual Deployment

```bash
# 1. Restart service
docker-compose restart bitcoincash-service

# 2. Verify tables
docker exec -it bitcoincash-service sqlite3 /app/data/payment.db ".tables"

# 3. Test health
curl -H "X-API-Key: YOUR_KEY" http://localhost:8081/api/cp/health
```

---

## 🧪 Testing

### Backend API Testing

```bash
# Set API key
export API_KEY="YOUR_LEMMY_API_KEY"

# Test health
curl -H "X-API-Key: $API_KEY" http://localhost:8081/api/cp/health

# Initialize test user
curl -X POST http://localhost:8081/api/cp/permissions/initialize \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "user_id": "test_user",
    "person_id": 999,
    "username": "testuser"
  }'

# Check if user can report
curl -H "X-API-Key: $API_KEY" \
  http://localhost:8081/api/cp/permissions/can-report/test_user

# Create test report
curl -X POST http://localhost:8081/api/cp/report \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "content_type": "post",
    "content_id": 1,
    "community_id": 1,
    "reporter_user_id": "test_user",
    "reporter_person_id": 999,
    "reporter_username": "testuser",
    "reporter_is_member": false,
    "creator_user_id": "bad_user",
    "creator_person_id": 888,
    "creator_username": "baduser",
    "reason": "Test CP report"
  }'

# Get pending reports
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8081/api/cp/reports/pending?escalation_level=moderator"
```

### Test Scenarios

#### Scenario 1: Normal CP Report Flow
```
1. User A reports User B's post as CP
2. Post is immediately hidden
3. Moderator reviews: confirms CP
4. User B is banned for 3 months
5. User B (if membership user) can appeal
6. Admin reviews appeal: restores or upholds
```

#### Scenario 2: False Report Flow
```
1. User A reports User B's post as CP
2. Post is immediately hidden
3. Moderator reviews: not CP
4. User A loses CP reporting ability
5. User A (if membership user) can appeal
6. Admin reviews appeal: restores or upholds
```

#### Scenario 3: Re-report Escalation
```
1. User A (free) reports User B's post
2. Moderator: not CP, content unhidden
3. User A cannot re-report (blocked)
4. User C (membership) reports same post
5. Report escalates to admin automatically
6. Admin reviews within 7 days or content auto-deleted
```

---

## 🐛 Troubleshooting

### Issue: CP tables not created

**Check:**
```bash
docker-compose logs bitcoincash-service | grep "초기화"
```

**Fix:**
```bash
docker-compose restart bitcoincash-service
```

### Issue: API returns 401 Unauthorized

**Check:** API key in request matches `.env` file

```bash
grep LEMMY_API_KEY /home/user/Oratio/oratio/.env
```

### Issue: Reports not appearing

**Check:** Database has reports
```bash
docker exec -it bitcoincash-service sqlite3 /app/data/payment.db \
  "SELECT COUNT(*) FROM cp_reports;"
```

### Issue: Background tasks not running

**Check:** Logs for background task errors
```bash
docker-compose logs bitcoincash-service | grep "background\|CP background"
```

---

## 📊 Monitoring

### Key Metrics

```sql
-- Active bans
SELECT COUNT(*) FROM user_cp_permissions WHERE is_banned = 1;

-- Pending moderator reviews
SELECT COUNT(*) FROM cp_reports 
WHERE status = 'pending' AND escalation_level = 'moderator';

-- Pending admin reviews
SELECT COUNT(*) FROM cp_reports 
WHERE status = 'pending' AND escalation_level = 'admin';

-- Appeals pending
SELECT COUNT(*) FROM cp_appeals WHERE status = 'pending';

-- Reports per day
SELECT DATE(created_at, 'unixepoch') as date, COUNT(*) as count
FROM cp_reports 
GROUP BY date 
ORDER BY date DESC 
LIMIT 30;
```

### Background Tasks

Runs automatically every 15 seconds:
1. **Auto-Unban**: Restore privileges after 3-month ban expires
2. **Auto-Delete**: Delete unreviewed admin cases after 7 days

Manual trigger:
```bash
curl -X POST -H "X-API-Key: YOUR_KEY" \
  http://localhost:8081/api/cp/background/run-tasks
```

---

## 🔒 Security Considerations

1. **API Key Protection**: Never expose API keys in frontend code
2. **Permission Checks**: All actions validate user permissions
3. **Audit Trail**: Complete logging of all CP system actions
4. **Rate Limiting**: Consider adding rate limits to prevent abuse
5. **Content Privacy**: Hidden content only visible to moderators/admins

---

## 📝 Configuration

### Environment Variables

Add to `/home/user/Oratio/oratio/.env`:

```bash
# CP System Configuration
LEMMY_CP_BAN_DURATION_DAYS=90  # Default: 90 days
LEMMY_CP_AUTO_DELETE_DAYS=7     # Default: 7 days
LEMMY_CP_NOTIFICATIONS_ENABLED=true
```

### Constants

Edit in `/oratio/bitcoincash_service/services/cp_moderation.py`:

```python
BAN_DURATION_SECONDS = 90 * 24 * 60 * 60  # 3 months
AUTO_DELETE_DURATION_SECONDS = 7 * 24 * 60 * 60  # 1 week
```

---

## 📖 Related Documentation

- [Environment Variables Flow](../deployment/environment-variables-flow.md)
- [Membership System](./MEMBERSHIP_SYSTEM.md)
- [Production Setup](../deployment/production-setup.md)

---

---

## 🔄 Recent Updates (v2.3 - 2025-11-22)

### Key Improvements
- ✅ **Permission Separation**: User/Moderator/Admin 3-tier access control
- ✅ **Appeal Logic Fix**: Only count pending appeals (allow re-appeal after approval/rejection)
- ✅ **Database Optimization**: SQLite WAL mode enabled to prevent lock errors
- ✅ **Auto-Restore**: Report ability expiry and auto-restore confirmed working
- ✅ **User Messages**: Ban/revocation messages now show "X days remaining"

### Known Limitations
- Nginx post URL blocking rule documented but not yet deployed
- Banned users cannot log in (Lemmy limitation) - cannot show ban toast on login
- Background tasks require WAL mode to avoid "database is locked" errors

---

**Document Version**: 2.3  
**System Version**: v2.3 (In Production)  
**Status**: ✅ Deployed - Stabilization Phase  
**Last Updated**: 2025-11-22  
**Deployment**: oratio.space

---

## Developer notes — programming changes (2026-03-24)

Short summary for engineers:

- Backend: Made CP admin endpoints more tolerant of frontend payloads. Endpoints under `oratio/bitcoincash_service/routes/cp.py` now accept an empty JSON body (`request.json or {}`), require the admin identity fields, and will resolve a target user's `person_id` from the URL or via Lemmy lookup when the client omits it. Each admin endpoint now calls `ensure_user_permissions()` before updating the SQLite CP row to avoid silent no-op updates.

- Lemmy integration: Added helpers `get_user_info_by_username()` / `get_person_id_by_username()` in `oratio/bitcoincash_service/lemmy_integration.py` to resolve person IDs from usernames when incoming requests don't include `person_id`.

- Frontend: Updated `lemmy-ui-custom/src/shared/components/person/profile.tsx` to fetch CP permissions for the viewed profile when the current user is an admin, and to expose the same ban/revoke/restore controls that exist in the Admin CP Control Panel. Actions call the CP admin APIs and then clear the client permissions cache and re-fetch to keep UI state consistent.

- Robustness: Ban/unban flows will attempt to call Lemmy admin endpoints when a `person_id` can be resolved; failures there produce a `warning` flag so the UI can surface partial success (SQLite updated, Lemmy action failed).

Why this change: a number of 400 (Bad Request) errors occurred when admin UI callers omitted `person_id` or other optional fields. These server-side fallbacks avoid requiring callers to duplicate identifiers already present in the URL and make the Admin CP and profile flows consistent.

Notes & follow-ups:

- Rebuild/deploy: After pulling these changes, restart or rebuild the `bitcoincash-service` container and rebuild the `lemmy-ui` frontend to see the UI updates.
- Validate: Test the following flows as an admin: ban/unban via Admin CP, ban/unban via profile, revoke/restore report ability via Admin CP, revoke/restore via profile. Confirm CP DB (`user_cp_permissions`) reflects changes and that UI badges update.
- Env: Ensure Lemmy admin credentials in the Oratio `.env` are correct (e.g. `LEMMY_ADMIN_USER` / `LEMMY_ADMIN_PASS`) so Lemmy ban/unban calls succeed.

---
