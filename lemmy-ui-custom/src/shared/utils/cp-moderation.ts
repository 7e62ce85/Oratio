import { getApiKey } from "./bch-payment";

// Type definitions
export interface CPPermissions {
  username: string;
  can_report_cp: boolean;
  is_banned: boolean;
  ban_start?: number;
  ban_end?: number;
  ban_count: number;
  has_cp_review_permission: boolean;
  last_violation?: string;
  report_ability_revoked_at?: number;
}

export interface CPReportRequest {
  content_type: 'post' | 'comment';
  content_id: number;
  community_id: number;
  reporter_user_id: string;
  reporter_person_id: number;
  reporter_username: string;
  reporter_is_member: boolean;
  creator_user_id: string;
  creator_person_id: number;
  creator_username: string;
  reason?: string;
}

export interface CPReport {
  id: string;
  content_type: 'post' | 'comment';
  content_id: number;
  community_id: number;
  reporter_username: string;
  creator_username: string;
  reason: string;
  status: 'pending' | 'reviewed' | 'escalated';
  escalation_level: 'moderator' | 'admin';
  content_hidden: boolean;
  created_at: number;
}

export interface CPAppealRequest {
  username: string;
  person_id: number;
  is_member: boolean;
  appeal_type: 'ban' | 'report_ability';
  reason: string;
}

export interface CPNotification {
  id: string;
  person_id: number;
  notification_type: string;
  content_type?: string;
  content_id?: number;
  related_username?: string;
  message: string;
  is_read: boolean;
  created_at: number;
}

// Cache for permissions
const permissionsCache = new Map<string, { permissions: CPPermissions; timestamp: number }>();
const CACHE_DURATION = 60 * 1000; // 1 minute cache

// Get base API URL - supports both client-side and SSR
function getCPApiUrl(): string {
  // During SSR (server-side rendering), use absolute URL with internal Docker service
  if (typeof window === 'undefined') {
    // Call bitcoincash-service directly (not through nginx)
    return 'http://bitcoincash-service:8081/api/cp';
  }
  // Client-side: use relative URL (proxied through nginx)
  return '/payments/api/cp';
}

// Check user's CP permissions
export async function checkUserCPPermissions(
  username: string
): Promise<CPPermissions | null> {
  try {
    // Check cache
    const now = Date.now();
    const cached = permissionsCache.get(username);
    if (cached && (now - cached.timestamp) < CACHE_DURATION) {
      return cached.permissions;
    }

    // Use public endpoint (no API key required) for username-based lookup
    const response = await fetch(
      `${getCPApiUrl()}/permissions/by-username/${username}`
    );

    if (!response.ok) {
      console.error(`Failed to check CP permissions: ${response.status}`);
      return null;
    }

    const permissions = await response.json();
    
    // Cache the result
    permissionsCache.set(username, { permissions, timestamp: now });
    
    return permissions;
  } catch (error) {
    console.error("Error checking CP permissions:", error);
    return null;
  }
}

// Check if user can report CP
export async function canUserReportCP(username: string): Promise<{ can_report: boolean; message?: string }> {
  try {
    const response = await fetch(
      `${getCPApiUrl()}/permissions/can-report/${username}`,
      {
        headers: {
          'X-API-Key': getApiKey()
        }
      }
    );

    if (!response.ok) {
      return { can_report: true }; // Fail open
    }

    return await response.json();
  } catch (error) {
    console.error("Error checking report ability:", error);
    return { can_report: true }; // Fail open
  }
}

// Submit a CP report
export async function submitCPReport(
  request: CPReportRequest
): Promise<{ success: boolean; message?: string; reportId?: string }> {
  try {
    const response = await fetch(`${getCPApiUrl()}/report`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
        // No API key needed - uses JWT cookie authentication
      },
      credentials: 'include', // Include cookies for JWT authentication
      body: JSON.stringify(request)
    });

    if (!response.ok) {
      const error = await response.json();
      return { 
        success: false, 
        message: error.error || error.detail || 'Failed to submit report' 
      };
    }

    const result = await response.json();
    return { 
      success: true, 
      reportId: result.report_id,
      message: 'Content reported and hidden' 
    };
  } catch (error) {
    console.error("Error submitting CP report:", error);
    return { 
      success: false, 
      message: 'Network error while submitting report' 
    };
  }
}

// Get pending reports for moderator/admin
export async function getPendingReports(
  communityId?: number,
  escalationLevel: 'moderator' | 'admin' = 'moderator'
): Promise<CPReport[]> {
  try {
    const params = new URLSearchParams({
      escalation_level: escalationLevel
    });
    
    if (communityId) {
      params.append('community_id', communityId.toString());
    }

    const response = await fetch(
      `${getCPApiUrl()}/reports/pending?${params}`,
      {
        headers: {
          'X-API-Key': getApiKey()
        }
      }
    );

    if (!response.ok) {
      console.error(`Failed to get pending reports: ${response.status}`);
      return [];
    }

    const result = await response.json();
    return result.reports || [];
  } catch (error) {
    console.error("Error getting pending reports:", error);
    return [];
  }
}

// Review a report (moderator/admin)
export async function reviewCPReport(
  reportId: string,
  reviewerPersonId: number,
  reviewerUsername: string,
  reviewerRole: 'moderator' | 'admin',
  decision: 'cp_confirmed' | 'not_cp' | 'admin_approved' | 'admin_rejected',
  notes?: string
): Promise<{ success: boolean; message?: string }> {
  try {
    const response = await fetch(
      `${getCPApiUrl()}/report/${reportId}/review`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey()
        },
        body: JSON.stringify({
          reviewer_person_id: reviewerPersonId,
          reviewer_username: reviewerUsername,
          reviewer_role: reviewerRole,
          decision,
          notes
        })
      }
    );

    if (!response.ok) {
      const error = await response.json();
      return { 
        success: false, 
        message: error.detail || 'Failed to review report' 
      };
    }

    return { success: true };
  } catch (error) {
    console.error("Error reviewing CP report:", error);
    return { 
      success: false, 
      message: 'Network error while reviewing report' 
    };
  }
}

// Submit an appeal
export async function submitCPAppeal(
  request: CPAppealRequest
): Promise<{ success: boolean; message?: string; appealId?: string }> {
  try {
    const response = await fetch(`${getCPApiUrl()}/appeal`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey()
      },
      body: JSON.stringify(request)
    });

    if (!response.ok) {
      const error = await response.json();
      return { 
        success: false, 
        message: error.detail || 'Failed to submit appeal' 
      };
    }

    const result = await response.json();
    return { 
      success: true, 
      appealId: result.appeal_id,
      message: 'Appeal submitted successfully' 
    };
  } catch (error) {
    console.error("Error submitting appeal:", error);
    return { 
      success: false, 
      message: 'Network error while submitting appeal' 
    };
  }
}

// Get CP notifications for a user
export async function getCPNotifications(
  personId: number,
  unreadOnly: boolean = true
): Promise<CPNotification[]> {
  try {
    const params = new URLSearchParams({
      unread_only: unreadOnly.toString()
    });

    const response = await fetch(
      `${getCPApiUrl()}/notifications/${personId}?${params}`,
      {
        headers: {
          'X-API-Key': getApiKey()
        }
      }
    );

    if (!response.ok) {
      console.error(`Failed to get CP notifications: ${response.status}`);
      return [];
    }

    const result = await response.json();
    return result.notifications || [];
  } catch (error) {
    console.error("Error getting CP notifications:", error);
    return [];
  }
}

// Mark notification as read
export async function markCPNotificationRead(
  notificationId: string
): Promise<boolean> {
  try {
    const response = await fetch(
      `${getCPApiUrl()}/notifications/${notificationId}/read`,
      {
        method: 'POST',
        headers: {
          'X-API-Key': getApiKey()
        }
      }
    );

    return response.ok;
  } catch (error) {
    console.error("Error marking notification as read:", error);
    return false;
  }
}

// Admin: Ban user
export async function adminBanUser(
  username: string,
  adminPersonId: number,
  adminUsername: string,
  reason?: string
): Promise<{ success: boolean; message?: string }> {
  try {
    const response = await fetch(
      `${getCPApiUrl()}/admin/user/${username}/ban`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey()
        },
        body: JSON.stringify({
          admin_person_id: adminPersonId,
          admin_username: adminUsername,
          reason
        })
      }
    );

    if (!response.ok) {
      const error = await response.json();
      return { 
        success: false, 
        message: error.detail || 'Failed to ban user' 
      };
    }

    return { success: true };
  } catch (error) {
    console.error("Error banning user:", error);
    return { success: false, message: 'Network error' };
  }
}

// Admin: Revoke report ability
export async function adminRevokeReportAbility(
  username: string,
  adminPersonId: number,
  adminUsername: string,
  reason?: string
): Promise<{ success: boolean; message?: string }> {
  try {
    const response = await fetch(
      `${getCPApiUrl()}/admin/user/${username}/revoke-report`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey()
        },
        body: JSON.stringify({
          admin_person_id: adminPersonId,
          admin_username: adminUsername,
          reason
        })
      }
    );

    if (!response.ok) {
      const error = await response.json();
      return { 
        success: false, 
        message: error.detail || 'Failed to revoke report ability' 
      };
    }

    return { success: true };
  } catch (error) {
    console.error("Error revoking report ability:", error);
    return { success: false, message: 'Network error' };
  }
}

// Admin: Restore user
export async function adminRestoreUser(
  username: string,
  adminPersonId: number,
  adminUsername: string,
  restoreBan: boolean,
  restoreReport: boolean,
  reason?: string
): Promise<{ success: boolean; message?: string }> {
  try {
    const response = await fetch(
      `${getCPApiUrl()}/admin/user/${username}/restore`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey()
        },
        body: JSON.stringify({
          admin_person_id: adminPersonId,
          admin_username: adminUsername,
          restore_ban: restoreBan,
          restore_report_ability: restoreReport,
          reason
        })
      }
    );

    if (!response.ok) {
      const error = await response.json();
      return { 
        success: false, 
        message: error.detail || 'Failed to restore user' 
      };
    }

    return { success: true };
  } catch (error) {
    console.error("Error restoring user:", error);
    return { success: false, message: 'Network error' };
  }
}

// Clear permissions cache
export function clearCPPermissionsCache(username?: string) {
  if (username) {
    permissionsCache.delete(username);
  } else {
    permissionsCache.clear();
  }
}

// ==========================================
// Content Filtering for CP Reports
// ==========================================

// Cache for reported content IDs
const reportedContentCache = new Map<string, Set<number>>();
const REPORTED_CONTENT_CACHE_DURATION = 30 * 1000; // 30 seconds
let lastReportedContentFetch = 0;

// Get all pending CP reported content IDs (for filtering)
export async function getReportedContentIds(): Promise<{ posts: Set<number>; comments: Set<number> }> {
  const now = Date.now();
  const cacheAge = now - lastReportedContentFetch;
  
  // Return cached data if still valid
  if (cacheAge < REPORTED_CONTENT_CACHE_DURATION) {
    const cachedPosts = reportedContentCache.get('posts') || new Set();
    const cachedComments = reportedContentCache.get('comments') || new Set();
    console.log(`💾 [CP API] Using cached data (age: ${(cacheAge/1000).toFixed(1)}s, ${cachedPosts.size} posts, ${cachedComments.size} comments)`);
    return {
      posts: cachedPosts,
      comments: cachedComments
    };
  }

  const apiUrl = `${getCPApiUrl()}/reported-content-ids`;
  console.log(`📡 [CP API] Cache expired - fetching from ${apiUrl}`);
  const fetchStart = performance.now();

  try {
    const response = await fetch(
      apiUrl,
      {
        headers: {
          'X-API-Key': getApiKey()
        }
      }
    );
    
    const fetchElapsed = performance.now() - fetchStart;

    if (!response.ok) {
      console.error(`❌ [CP API] Failed (${response.status}) after ${fetchElapsed.toFixed(1)}ms`);
      return { posts: new Set(), comments: new Set() };
    }

    const result = await response.json();
    const posts = new Set<number>(result.post_ids || []);
    const comments = new Set<number>(result.comment_ids || []);
    
    console.log(`✅ [CP API] Got ${posts.size} posts, ${comments.size} comments in ${fetchElapsed.toFixed(1)}ms`);
    
    // Update cache
    reportedContentCache.set('posts', posts);
    reportedContentCache.set('comments', comments);
    lastReportedContentFetch = now;
    
    return { posts, comments };
  } catch (error) {
    const fetchElapsed = performance.now() - fetchStart;
    console.error(`❌ [CP API] Error after ${fetchElapsed.toFixed(1)}ms:`, error);
    return { posts: new Set(), comments: new Set() };
  }
}

// Check if a post is reported
export function isPostReported(postId: number): boolean {
  const reportedPosts = reportedContentCache.get('posts');
  return reportedPosts ? reportedPosts.has(postId) : false;
}

// Check if a comment is reported
export function isCommentReported(commentId: number): boolean {
  const reportedComments = reportedContentCache.get('comments');
  return reportedComments ? reportedComments.has(commentId) : false;
}

// Force refresh reported content cache
export async function refreshReportedContentCache(): Promise<void> {
  lastReportedContentFetch = 0;
  await getReportedContentIds();
}
