// Advertisement configuration and management
export interface AdConfig {
  enabled: boolean;
  position: "header" | "sidebar" | "footer" | "comment";
  size: "large" | "medium" | "small";
  section: "home" | "community" | "post" | "feed" | "comments" | "general";
  content?: string;
  frequency?: number; // For feed ads, show every N posts
  targetAudience?: string[];
  schedule?: {
    startDate?: Date;
    endDate?: Date;
    daysOfWeek?: number[]; // 0-6, Sunday-Saturday
    hoursOfDay?: number[]; // 0-23
  };
}

export interface AdCampaign {
  id: string;
  name: string;
  configs: AdConfig[];
  priority: number;
  budget?: number;
  clicks?: number;
  impressions?: number;
  isActive: boolean;
}

// Default advertisement configurations for each section
export const DEFAULT_AD_CONFIGS: Record<string, AdConfig> = {
  header: {
    enabled: true,
    position: "header",
    size: "large",
    section: "general",
    frequency: 1,
  },
  home: {
    enabled: true,
    position: "sidebar",
    size: "medium",
    section: "home",
    frequency: 1,
  },
  community: {
    enabled: true,
    position: "sidebar",
    size: "medium",
    section: "community",
    frequency: 1,
  },
  post: {
    enabled: true,
    position: "sidebar",
    size: "medium",
    section: "post",
    frequency: 1,
  },
  feed: {
    enabled: true,
    position: "sidebar",
    size: "large",
    section: "feed",
    frequency: 3, // Show every 3 posts
  },
  comments: {
    enabled: true,
    position: "comment",
    size: "medium",
    section: "comments",
    frequency: 10, // Show every 10 comments
  },
};

// Advertisement content templates
export const AD_TEMPLATES = {
  promotional: {
    header: "🚀 특별 혜택!",
    description: "지금 가입하고 무료 크레딧을 받아보세요!",
    cta: "자세히 보기",
    colors: ["#667eea", "#764ba2"],
  },
  community: {
    header: "👥 커뮤니티 특별 혜택",
    description: "이 커뮤니티의 멤버를 위한 특별 제안",
    cta: "혜택 확인",
    colors: ["#fa709a", "#fee140"],
  },
  content: {
    header: "📝 관련 서비스",
    description: "이 콘텐츠와 관련된 유용한 도구들",
    cta: "도구 보기",
    colors: ["#a8edea", "#fed6e3"],
  },
  engagement: {
    header: "💬 토론 참여",
    description: "의견을 나누고 소통하세요",
    cta: "참여하기",
    colors: ["#ffecd2", "#fcb69f"],
  },
};

// Advertisement management utilities
export class AdManager {
  private static instance: AdManager;
  private campaigns: AdCampaign[] = [];
  private configs: Record<string, AdConfig> = { ...DEFAULT_AD_CONFIGS };

  static getInstance(): AdManager {
    if (!AdManager.instance) {
      AdManager.instance = new AdManager();
    }
    return AdManager.instance;
  }

  // Get ad configuration for a specific section
  getAdConfig(section: string): AdConfig | null {
    const config = this.configs[section];
    return config?.enabled ? config : null;
  }

  // Update ad configuration for a section
  updateAdConfig(section: string, config: Partial<AdConfig>): void {
    this.configs[section] = { ...this.configs[section], ...config };
  }

  // Disable ads for a specific section
  disableAds(section: string): void {
    if (this.configs[section]) {
      this.configs[section].enabled = false;
    }
  }

  // Enable ads for a specific section
  enableAds(section: string): void {
    if (this.configs[section]) {
      this.configs[section].enabled = true;
    }
  }

  // Get all active campaigns
  getActiveCampaigns(): AdCampaign[] {
    return this.campaigns.filter(campaign => campaign.isActive);
  }

  // Add a new campaign
  addCampaign(campaign: AdCampaign): void {
    this.campaigns.push(campaign);
  }

  // Remove a campaign
  removeCampaign(campaignId: string): void {
    this.campaigns = this.campaigns.filter(campaign => campaign.id !== campaignId);
  }

  // Check if ads should be shown based on user credits
  shouldShowAds(creditBalance: number | null): boolean {
    const CREDIT_THRESHOLD = 0.0003;
    return creditBalance === null || creditBalance < CREDIT_THRESHOLD;
  }

  // Log ad impression
  logImpression(section: string, campaignId?: string): void {
    console.log(`[AdManager] Ad impression logged for section: ${section}`, { campaignId });
    // Here you could send analytics data to your tracking service
  }

  // Log ad click
  logClick(section: string, campaignId?: string): void {
    console.log(`[AdManager] Ad click logged for section: ${section}`, { campaignId });
    // Here you could send analytics data to your tracking service
  }
}
