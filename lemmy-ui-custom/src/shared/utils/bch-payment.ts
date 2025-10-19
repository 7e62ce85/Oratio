// BCH Payment utility functions
import { Person } from "lemmy-js-client";

// Get API key from environment or window config
const getApiKey = () => {
  if (typeof window !== 'undefined' && window.__BCH_CONFIG__) {
    return window.__BCH_CONFIG__.API_KEY;
  }
  return process.env.LEMMY_API_KEY || "";
};

const getBCHAPIUrl = () => {
  if (typeof window !== 'undefined' && window.__BCH_CONFIG__) {
    return window.__BCH_CONFIG__.API_URL;
  }
  return process.env.LEMMY_BCH_API_URL || "http://localhost:8081/api/user_credit";
};

// Cache for payment status to avoid repeated API calls
const paymentStatusCache = new Map<number, { hasPayment: boolean; timestamp: number }>();
export const creditCache = new Map<number, { credit: number; timestamp: number }>();
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

// Event name for credit cache updates
const CREDIT_CACHE_UPDATE_EVENT = 'bch-credit-cache-updated';

// Function to manually update the credit cache (for use by other components)
export function updateCreditCache(userId: number, credit: number) {
  creditCache.set(userId, { credit, timestamp: Date.now() });
  
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

// Check if user has enough credit for gold badge (0.0001 BCH or more)
export async function checkUserHasGoldBadge(person: Person): Promise<boolean> {
  try {
    const userId = person.id;
    const username = person.name;
    const now = Date.now();
    
    // Check cache first
    const cached = creditCache.get(userId);
    if (cached && (now - cached.timestamp) < CACHE_DURATION) {
      return cached.credit >= 0.0001;
    }

    const apiUrl = getBCHAPIUrl();
    
    // Use username instead of ID for API call
    const response = await fetch(`${apiUrl}/${username}`, {
      headers: {
        'X-API-Key': getApiKey() || ""
      }
    });
    
    if (response.ok) {
      const data = await response.json();
      const credit = parseFloat(data.credit_balance || data.credit) || 0;
      
      // Cache the result
      creditCache.set(userId, { credit, timestamp: now });
      
      // Dispatch event to notify components
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent(CREDIT_CACHE_UPDATE_EVENT, { 
          detail: { userId, credit } 
        }));
      }
      
      return credit >= 0.0001;
    } else {
      return false;
    }
  } catch (error) {
    console.error("[BCH] Error checking gold badge status:", error);
    return false;
  }
}

// Synchronous version for components - triggers async check in background
export function checkUserHasGoldBadgeSync(person: Person): boolean {
  const userId = person.id;
  const cached = creditCache.get(userId);
  
  // If we have a recent cache hit, use it
  if (cached && (Date.now() - cached.timestamp) < CACHE_DURATION) {
    return cached.credit >= 0.0001;
  }
  
  // Otherwise, trigger async fetch and return false for now
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
  
  // Check if user has gold badge (0.0001 BCH or more)
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