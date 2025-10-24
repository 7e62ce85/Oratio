// BCH Payment utility functions
import { Person } from "lemmy-js-client";

// Get API key from environment or window config
export const getApiKey = () => {
  if (typeof window !== 'undefined' && window.__BCH_CONFIG__) {
    return window.__BCH_CONFIG__.API_KEY;
  }
  return process.env.LEMMY_API_KEY || "";
};

export const getBCHAPIUrl = () => {
  // Server-side: use internal Docker network URL
  if (typeof window === 'undefined') {
    return process.env.LEMMY_BCH_API_URL_INTERNAL || process.env.LEMMY_BCH_API_URL || "http://bitcoincash-service:8081/api/user_credit";
  }
  // Client-side: use window config or external URL
  if (window.__BCH_CONFIG__) {
    return window.__BCH_CONFIG__.API_URL;
  }
  return process.env.LEMMY_BCH_API_URL || "http://localhost:8081/api/user_credit";
};

// Cache for payment status to avoid repeated API calls
const paymentStatusCache = new Map<number, { hasPayment: boolean; timestamp: number }>();
export const creditCache = new Map<number, { credit: number; timestamp: number }>();
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes in milliseconds
const CACHE_STORAGE_KEY = 'bch_membership_cache';

// Event name for credit balance updates
export const CREDIT_CACHE_UPDATE_EVENT = 'bch-credit-cache-updated';

// Track pending requests to avoid duplicate API calls
const pendingRequests = new Map<number, Promise<boolean>>();

// Queue system for rate limiting
let requestQueue: Array<{userId: number, person: Person, resolve: (value: boolean) => void}> = [];
let isProcessingQueue = false;
const QUEUE_DELAY = 100; // 100ms between requests to avoid rate limiting

// Load cache from localStorage on initialization
if (typeof window !== 'undefined') {
  try {
    const stored = localStorage.getItem(CACHE_STORAGE_KEY);
    if (stored) {
      const data = JSON.parse(stored);
      const now = Date.now();
      let hasRestoredCache = false;
      
      // Only restore non-expired entries
      Object.entries(data).forEach(([userId, value]: [string, any]) => {
        if (value && typeof value === 'object' && (now - value.timestamp) < CACHE_DURATION) {
          creditCache.set(Number(userId), value);
          hasRestoredCache = true;
        }
      });
      
      // Notify all components that cache has been restored
      // This ensures components re-render with cached badge data
      if (hasRestoredCache) {
        const notifyComponents = () => {
          creditCache.forEach((value, userId) => {
            window.dispatchEvent(new CustomEvent(CREDIT_CACHE_UPDATE_EVENT, { 
              detail: { userId, credit: value.credit } 
            }));
          });
        };
        
        // If document is already loaded, notify immediately
        if (document.readyState === 'complete' || document.readyState === 'interactive') {
          // Use requestAnimationFrame to ensure components are mounted
          requestAnimationFrame(() => {
            requestAnimationFrame(notifyComponents);
          });
        } else {
          // Otherwise wait for DOM to be ready
          window.addEventListener('DOMContentLoaded', notifyComponents);
        }
      }
    }
  } catch (error) {
    console.error("[BCH] Error loading cache from localStorage:", error);
  }
}

// Save cache to localStorage
function saveCacheToStorage() {
  if (typeof window !== 'undefined') {
    try {
      const data: Record<string, any> = {};
      creditCache.forEach((value, userId) => {
        data[userId] = value;
      });
      localStorage.setItem(CACHE_STORAGE_KEY, JSON.stringify(data));
    } catch (error) {
      console.error("[BCH] Error saving cache to localStorage:", error);
    }
  }
}

// Function to manually update the credit cache (for use by other components)
export function updateCreditCache(userId: number, credit: number) {
  creditCache.set(userId, { credit, timestamp: Date.now() });
  
  // Save to localStorage
  saveCacheToStorage();
  
  // Dispatch custom event to notify components that cache was updated
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(CREDIT_CACHE_UPDATE_EVENT, { 
      detail: { userId, credit } 
    }));
  }
}

export async function checkUserHasPayment(person: Person): Promise<boolean> {
  try {
    const userId = person.id;
    const username = person.name;
    const now = Date.now();
    
    // Check cache first
    const cached = paymentStatusCache.get(userId);
    if (cached && (now - cached.timestamp) < CACHE_DURATION) {
      return cached.hasPayment;
    }

    const apiUrl = `${getBCHAPIUrl().replace('/user_credit', '')}/api/has_payment/${username}`;
    
    const response = await fetch(apiUrl, {
      headers: {
        'X-API-Key': getApiKey() || ""
      }
    });
    
    if (response.ok) {
      const data = await response.json();
      const hasPayment = data.has_payment || false;
      
      // Cache the result
      paymentStatusCache.set(userId, { hasPayment, timestamp: now });
      
      return hasPayment;
    } else {
      console.error(`[BCH] Failed to check payment status for user ${username}:`, response.status);
      return false;
    }
  } catch (error) {
    console.error("[BCH] Error checking user payment status:", error);
    return false;
  }
}

// Process the request queue with rate limiting
async function processQueue() {
  if (isProcessingQueue || requestQueue.length === 0) {
    return;
  }
  
  isProcessingQueue = true;
  
  while (requestQueue.length > 0) {
    const item = requestQueue.shift();
    if (!item) break;
    
    try {
      const result = await checkUserHasGoldBadgeInternal(item.person);
      item.resolve(result);
    } catch (error) {
      console.error("[BCH] Error in queue processing:", error);
      item.resolve(false);
    }
    
    // Wait before next request
    if (requestQueue.length > 0) {
      await new Promise(resolve => setTimeout(resolve, QUEUE_DELAY));
    }
  }
  
  isProcessingQueue = false;
}

// Internal function that actually makes the API call
async function checkUserHasGoldBadgeInternal(person: Person): Promise<boolean> {
  const userId = person.id;
  const username = person.name;
  const now = Date.now();
  
  const apiUrl = getBCHAPIUrl();
  const baseUrl = apiUrl.replace('/api/user_credit', '');
  const membershipUrl = `${baseUrl}/api/membership/status/${username}`;
  
  try {
    const response = await fetch(membershipUrl, {
      headers: {
        'X-API-Key': getApiKey() || ""
      }
    });
    
    if (response.ok) {
      const data = await response.json();
      const isActive = data.membership?.is_active || false;
      
      // Cache the result
      const cacheValue = isActive ? 1.0 : 0.0;
      creditCache.set(userId, { credit: cacheValue, timestamp: now });
      
      // Save to localStorage
      saveCacheToStorage();
      
      // Dispatch event to notify components
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent(CREDIT_CACHE_UPDATE_EVENT, { 
          detail: { userId, credit: cacheValue, membership: data.membership } 
        }));
      }
      
      return isActive;
    } else {
      return false;
    }
  } catch (error) {
    console.error("[BCH] Error checking membership:", error);
    return false;
  }
}

// Check if user has enough credit for gold badge (0.0001 BCH or more)
// UPDATED: Now checks for active annual membership with rate limiting
export async function checkUserHasGoldBadge(person: Person): Promise<boolean> {
  const userId = person.id;
  const now = Date.now();
  
  // Check cache first
  const cached = creditCache.get(userId);
  if (cached && (now - cached.timestamp) < CACHE_DURATION) {
    return cached.credit >= 1.0;
  }

  // Check if there's already a pending request for this user
  const pending = pendingRequests.get(userId);
  if (pending) {
    return pending;
  }

  // Create a promise that will be resolved when the queue processes it
  const promise = new Promise<boolean>((resolve) => {
    requestQueue.push({ userId, person, resolve });
    // Start processing the queue
    processQueue();
  });
  
  pendingRequests.set(userId, promise);
  
  // Clean up after promise resolves
  promise.then(
    () => pendingRequests.delete(userId),
    () => pendingRequests.delete(userId)
  );
  
  return promise;
}

// Synchronous version for components - triggers async check in background
// Now works for all users (logged in or not) with rate limiting queue
export function checkUserHasGoldBadgeSync(person: Person): boolean {
  const userId = person.id;
  const cached = creditCache.get(userId);
  const now = Date.now();
  
  // If we have a recent cache hit, use it
  if (cached && (now - cached.timestamp) < CACHE_DURATION) {
    // Cached value: 1.0 = active membership, 0.0 = no membership
    return cached.credit >= 1.0;
  }
  
  // If cache exists but expired, trigger refresh but still use old value
  // This prevents badges from flickering during refresh
  if (cached) {
    // Trigger async fetch in background
    checkUserHasGoldBadge(person).catch((err) => {
      console.error("[BCH] Error checking gold badge status:", err);
    });
    // Return the old cached value while waiting for refresh
    return cached.credit >= 1.0;
  }
  
  // No cache at all - trigger async fetch and return false for now
  checkUserHasGoldBadge(person).catch((err) => {
    console.error("[BCH] Error checking gold badge status:", err);
  });
  
  return false;
}

// List of community names that require gold badge access
const PREMIUM_COMMUNITIES = ['test']; // 나중에 변경 가능

// Check if a community name is restricted to gold badge holders
export function isPremiumCommunity(communityName: string): boolean {
  return PREMIUM_COMMUNITIES.includes(communityName.toLowerCase());
}

// Check if current user can access a premium community
export async function canAccessPremiumCommunity(communityName: string, person?: Person): Promise<boolean> {
  // If not a premium community, everyone can access
  if (!isPremiumCommunity(communityName)) {
    return true;
  }
  
  // If no user is logged in, deny access to premium communities
  if (!person) {
    return false;
  }
  
  // Check if user has active annual membership
  return await checkUserHasGoldBadge(person);
}

// Synchronous version - returns false if unknown, triggers async check
export function canAccessPremiumCommunitySync(communityName: string, person?: Person): boolean {
  // If not a premium community, everyone can access
  if (!isPremiumCommunity(communityName)) {
    return true;
  }
  
  // If no user is logged in, deny access to premium communities
  if (!person) {
    return false;
  }
  
  // Check cache for gold badge status
  const userId = person.id;
  const cached = creditCache.get(userId);
  
  if (cached && (Date.now() - cached.timestamp) < CACHE_DURATION) {
    return cached.credit >= 0.0001;
  }
  
  // Trigger async check in background
  checkUserHasGoldBadge(person).catch((err) => {
    console.error("[BCH] Error in canAccessPremiumCommunitySync:", err);
  });
  
  // Return false by default if we don't have cached data
  return false;
}

// Global window extensions for BCH configuration
declare global {
  interface Window {
    __BCH_CONFIG__?: {
      API_KEY: string;
      API_URL: string;
      PAYMENT_URL: string;
    };
  }
}