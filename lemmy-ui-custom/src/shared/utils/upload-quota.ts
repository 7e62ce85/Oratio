/**
 * Upload Quota Utilities
 * Client-side helpers for upload size validation and quota checking
 * 
 * Version: 1.0
 * Created: 2025-11-04
 */

import { toast } from "../toast";

// BCH API configuration
function getApiConfig() {
  if (typeof window !== "undefined" && (window as any).__BCH_CONFIG__) {
    return (window as any).__BCH_CONFIG__;
  }
  // Fallback for SSR - these will be replaced by webpack
  return {
    API_KEY: "",
    API_URL: "http://localhost:8081/api",
    PAYMENT_URL: "http://localhost:8081/",
  };
}

// Get base API URL for upload endpoints
function getUploadApiBaseUrl() {
  if (typeof window !== "undefined") {
    // Client-side: use relative URL with nginx proxy
    return "/payments/api";
  }
  // Server-side: use Docker internal URL
  return "http://bitcoincash-service:8081/api";
}

// Constants
const RECOMMENDED_FORMATS = ["jpg", "jpeg"];

/**
 * Format bytes to human-readable string
 */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(2)} KB`;
  if (bytes < 1_073_741_824) return `${(bytes / 1_048_576).toFixed(2)} MB`;
  return `${(bytes / 1_073_741_824).toFixed(2)} GB`;
}

/**
 * Check if file format is recommended (JPG/JPEG)
 */
export function isRecommendedFormat(filename: string): boolean {
  const ext = filename.split(".").pop()?.toLowerCase();
  return RECOMMENDED_FORMATS.includes(ext || "");
}

/**
 * Get file format warning message
 */
export function getFormatWarning(filename: string): string | null {
  if (!isRecommendedFormat(filename)) {
    return "💡 Tip: JPG/JPEG files are the most efficient format for images and will use less of your upload quota.";
  }
  return null;
}

/**
 * Get user's upload quota from API
 */
export async function getUserUploadQuota(
  userId: string
): Promise<UploadQuota | null> {
  try {
    const config = getApiConfig();
    const baseUrl = getUploadApiBaseUrl();
    const response = await fetch(
      `${baseUrl}/upload/quota/${userId}`,
      {
        headers: {
          "X-API-Key": config.API_KEY,
        },
      }
    );

    if (!response.ok) {
      console.error("Failed to fetch upload quota:", response.statusText);
      return null;
    }

    const data = await response.json();
    return data.quota;
  } catch (error) {
    console.error("Error fetching upload quota:", error);
    return null;
  }
}

/**
 * Validate upload before processing
 */
export async function validateUpload(
  userId: string,
  username: string,
  fileSize: number,
  filename: string
): Promise<UploadValidation> {
  try {
    const config = getApiConfig();
    const baseUrl = getUploadApiBaseUrl();
    
    console.log('[Upload Quota] Validating upload:', {
      userId,
      username,
      fileSize,
      filename,
      apiUrl: `${baseUrl}/upload/validate`
    });
    
    const response = await fetch(`${baseUrl}/upload/validate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": config.API_KEY,
      },
      body: JSON.stringify({
        user_id: userId,
        username: username,
        file_size_bytes: fileSize,
        filename: filename,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[Upload Quota] Validation failed:', response.status, errorText);
      throw new Error(`Validation failed: ${response.statusText}`);
    }

    const data = await response.json();
    console.log('[Upload Quota] Validation response:', data);
    return data.validation;
  } catch (error) {
    console.error("Error validating upload:", error);
    throw error;
  }
}

/**
 * Record upload transaction
 */
export async function recordUpload(
  userId: string,
  username: string,
  filename: string,
  fileSize: number,
  uploadUrl: string,
  fileType?: string,
  postId?: number,
  commentId?: number,
  useCredit: boolean = false
): Promise<UploadTransaction> {
  try {
    const config = getApiConfig();
    const baseUrl = getUploadApiBaseUrl();
    
    console.log('[Upload Quota] Recording upload:', {
      userId,
      username,
      filename,
      fileSize,
      uploadUrl,
      apiUrl: `${baseUrl}/upload/record`
    });
    
    const response = await fetch(`${baseUrl}/upload/record`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": config.API_KEY,
      },
      body: JSON.stringify({
        user_id: userId,
        username: username,
        filename: filename,
        file_size_bytes: fileSize,
        file_type: fileType,
        upload_url: uploadUrl,
        post_id: postId,
        comment_id: commentId,
        use_credit: useCredit,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[Upload Quota] Record failed:', response.status, errorText);
      throw new Error(`Failed to record upload: ${response.statusText}`);
    }

    const data = await response.json();
    console.log('[Upload Quota] Record response:', data);
    return data;
  } catch (error) {
    console.error("[Upload Quota] Error recording upload:", error);
    throw error;
  }
}

/**
 * Show upload size warning or error
 */
export function showUploadSizeMessage(
  _fileSize: number,
  filename: string,
  validation: UploadValidation
): void {
  // Show format recommendation
  const formatWarning = getFormatWarning(filename);
  if (formatWarning) {
    toast(formatWarning, "info");
  }

  // Show validation result
  if (!validation.allowed) {
    if (validation.reason === "file_too_large") {
      toast(
        `❌ ${validation.message}`,
        "danger"
      );
    } else if (validation.reason === "insufficient_credit") {
      toast(
        `❌ ${validation.message}`,
        "danger"
      );
    } else {
      toast(`❌ Upload not allowed: ${validation.message}`, "danger");
    }
  } else if (validation.will_charge) {
    const overageBytes = validation.overage_bytes || 0;
    const chargeBch = validation.charge_amount_bch || 0;
    const chargeUsd = validation.charge_amount_usd || 0;
    toast(
      `⚠️ This upload will use ${formatBytes(overageBytes)} beyond your quota and cost ${chargeBch} BCH ($${chargeUsd}). Please check "Use Credit to Post" to proceed.`,
      "warning"
    );
  } else if (validation.reason === "within_quota") {
    toast(
      `✅ ${validation.message}`,
      "success"
    );
  }
}

/**
 * Check if user should see upload quota prompt
 */
export function shouldPromptForCredit(validation: UploadValidation): boolean {
  return validation.allowed && validation.will_charge === true;
}

/**
 * Get upload pricing info for display
 */
export async function getUploadPricing(): Promise<UploadPricing | null> {
  try {
    const baseUrl = getUploadApiBaseUrl();
    const response = await fetch(`${baseUrl}/upload/pricing`);

    if (!response.ok) {
      console.error("Failed to fetch pricing:", response.statusText);
      return null;
    }

    const data = await response.json();
    return data.pricing;
  } catch (error) {
    console.error("Error fetching pricing:", error);
    return null;
  }
}

// TypeScript interfaces
export interface UploadQuota {
  user_id: string;
  username: string;
  membership_type: string;
  is_member: boolean;
  annual_quota_bytes: number;
  annual_quota_gb: number;
  used_bytes: number;
  used_gb: number;
  remaining_bytes: number;
  remaining_gb: number;
  usage_percentage: number;
  quota_start_date: number;
  quota_end_date: number;
  is_active: boolean;
}

export interface UploadValidation {
  allowed: boolean;
  reason: string;
  message: string;
  will_charge?: boolean;
  charge_amount_usd?: number;
  charge_amount_bch?: number;
  overage_bytes?: number;
  overage_gb?: number;
  requires_membership?: boolean;
  requires_credit?: boolean;
  max_size_bytes?: number;
  remaining_after_upload_bytes?: number;
  remaining_after_upload_gb?: number;
  user_credit_bch?: number;
  remaining_credit_after_bch?: number;
}

export interface UploadTransaction {
  transaction_id: string;
  success: boolean;
  charged: boolean;
  charge_amount_bch: number;
  charge_amount_usd: number;
  quota: UploadQuota;
}

export interface UploadPricing {
  free_user_limit_bytes: number;
  free_user_limit_kb: number;
  member_annual_quota_bytes: number;
  member_annual_quota_gb: number;
  overage_usd_per_4gb: number;
  min_charge_usd: number;
  recommended_formats: string[];
}
