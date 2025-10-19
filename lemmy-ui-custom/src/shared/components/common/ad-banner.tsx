import { Component } from "inferno";
import { UserService } from "../../services";
import { creditCache, updateCreditCache } from "../../utils/bch-payment";

// BCH configuration constants (same as navbar.tsx)
const BCH_API_URL = "https://oratio.space/payments/api/user_credit";

// Get API key from environment or window config (same as navbar.tsx)
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
  return BCH_API_URL;
};

interface AdBannerProps {
  position: "header" | "sidebar" | "footer" | "comment";
  size?: "large" | "medium" | "small";
  className?: string;
  section?: "home" | "community" | "post" | "feed" | "comments" | "general";
  customContent?: string;
}

interface AdBannerState {
  showAd: boolean;
  adContent: string | null;
  isCheckingCredit: boolean;
  creditBalance: number | null;
}

export class AdBanner extends Component<AdBannerProps, AdBannerState> {
  state: AdBannerState = {
    showAd: true,
    adContent: null,
    isCheckingCredit: false,
    creditBalance: null,
  };

  constructor(props: any, context: any) {
    super(props, context);
    // Initialize ad content in the initial state
    this.state.adContent = this.getInitialAdContent();
  }

  componentDidMount() {
    // Check user credit if already logged in
    if (UserService.Instance.myUserInfo) {
      this.checkUserCredit();
    } else {
      // If user info not available yet, retry after a short delay
      // This handles cases where login is in progress
      setTimeout(() => {
        if (UserService.Instance.myUserInfo && this.state.creditBalance === null) {
          this.checkUserCredit();
        }
      }, 1000);
    }
    
    // Ad content is already loaded in constructor
  }

  componentDidUpdate(_prevProps: AdBannerProps) {
    // Check if user info became available in UserService
    // This handles the case where user logs in but BCH credit wasn't checked
    if (UserService.Instance.myUserInfo && this.state.isCheckingCredit === false && this.state.creditBalance === null) {
      this.checkUserCredit();
    }
  }

  getInitialAdContent(): string {
    // Get initial ad content without using setState
    const { section = "general", customContent } = this.props;
    
    // Use custom content if provided
    if (customContent) {
      return customContent;
    }
    
    // Generate section-specific ad content
    switch (section) {
      case "home":
        return this.getHomeAdContent();
      case "community":
        return this.getCommunityAdContent();
      case "post":
        return this.getPostAdContent();
      case "feed":
        return this.getFeedAdContent();
      case "comments":
        return this.getCommentsAdContent();
      default:
        return this.getGeneralAdContent();
    }
  }

  async checkUserCredit() {
    // Check if user has enough BCH credits to hide ads (same logic as navbar.tsx)
    const userInfo = UserService.Instance.myUserInfo;
    
    if (!userInfo) {
      // Retry once after a short delay in case login is still in progress
      setTimeout(() => {
        const retryUserInfo = UserService.Instance.myUserInfo;
        if (retryUserInfo && this.state.creditBalance === null) {
          this.checkUserCredit();
        } else {
          this.setState({ showAd: true, isCheckingCredit: false });
        }
      }, 2000);
      
      return;
    }

    this.setState({ isCheckingCredit: true });

    try {
      const person = userInfo.local_user_view.person;
      const userId = person.id;
      const username = person.name;
      
      // Check cache first (5 minute cache)
      const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
      const cached = creditCache.get(userId);
      const now = Date.now();
      
      if (cached && (now - cached.timestamp) < CACHE_DURATION) {
        const creditBalance = cached.credit;
        const CREDIT_THRESHOLD = 0.0003;
        const shouldShowAd = creditBalance < CREDIT_THRESHOLD;
        
        this.setState({ 
          showAd: shouldShowAd,
          creditBalance: creditBalance,
          isCheckingCredit: false
        });
        return;
      }
      
      // If not in cache, fetch from API using username (not ID)
      const apiUrl = `${getBCHAPIUrl()}/${username}`;

      const response = await fetch(apiUrl, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey() || "",
        },
      });

      if (response.ok) {
        const data = await response.json();
        
        // credit_balance 필드가 있는지 확인 (navbar.tsx와 동일)
        if (data.credit_balance !== undefined) {
          const creditBalance = parseFloat(data.credit_balance || 0);
          
          // Update the shared cache (same as navbar does)
          if (creditBalance > 0) {
            updateCreditCache(userId, creditBalance);
          }
          
          // 크레딧 임계값: 0.0003 BCH 이상이면 광고 숨김
          const CREDIT_THRESHOLD = 0.0003;
          const shouldShowAd = creditBalance < CREDIT_THRESHOLD;

          this.setState({ 
            showAd: shouldShowAd,
            creditBalance: creditBalance,
            isCheckingCredit: false
          });
        } else {
          console.error("[AdBanner] Response does not contain credit_balance field:", data);
          // 데이터 형식 오류시 기본적으로 광고 표시
          this.setState({ showAd: true, isCheckingCredit: false });
        }
      } else {
        // 응답이 실패한 경우 응답 텍스트도 로깅
        const errorText = await response.text();
        console.error(`[AdBanner] Failed to fetch credits: ${response.status}`, errorText);
        // API 실패시 기본적으로 광고 표시
        this.setState({ 
          showAd: true, 
          creditBalance: null,
          isCheckingCredit: false 
        });
      }
    } catch (error) {
      console.error("[AdBanner] Error checking user credits:", error);
      // 에러 발생시 기본적으로 광고 표시
      this.setState({ showAd: true, isCheckingCredit: false });
    }
  }

  loadAdContent() {
    // This method can be used to refresh ad content if needed
    const adContent = this.getInitialAdContent();
    this.setState({ adContent });
  }

  getHomeAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">🏠 Welcome!</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">Share diverse information in our community</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Home ad clicked')" 
           style="background: #fff; color: #4facfe; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          Learn More
        </a>
      </div>
    `;
  }

  getCommunityAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">👥 Community Special Benefits</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">Special offer for members of this community</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Community ad clicked')" 
           style="background: #fff; color: #fa709a; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          Check Benefits
        </a>
      </div>
    `;
  }

  getPostAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); padding: 15px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">📝 Related Services</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.8;">Useful tools related to this post</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Post ad clicked')" 
           style="background: #333; color: #fff; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          View Tools
        </a>
      </div>
    `;
  }

  getFeedAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">📰 Feed Recommendations</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">Discover more interesting content</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Feed ad clicked')" 
           style="background: #fff; color: #667eea; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          Explore Content
        </a>
      </div>
    `;
  }

  getCommentsAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); padding: 12px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 8px 0; font-size: 16px;">💬 Join the Discussion</h3>
        <p style="margin: 0 0 12px 0; font-size: 13px; opacity: 0.8;">Share opinions and connect</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Comments ad clicked')" 
           style="background: #333; color: #fff; padding: 6px 16px; border-radius: 4px; text-decoration: none; font-weight: bold; display: inline-block; font-size: 12px;">
          Join Now
        </a>
      </div>
    `;
  }

  getGeneralAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">🚀 Special Offer!</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">Sign up now and join the awesome community!</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('General ad clicked')" 
           style="background: #fff; color: #667eea; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          Learn More
        </a>
      </div>
    `;
  }

  render() {
    const { position, size = "medium", className = "" } = this.props;

    // Check credit during initialization if user is logged in
    if (this.state.isCheckingCredit) {
      return (
        <div className={`ad-container ad-${position} ad-${size} ${className}`}>
          <div style={{ padding: "10px", "text-align": "center", color: "#666" }}>
            Checking credits...
          </div>
        </div>
      );
    }

    // Don't show ad if user doesn't want to see it or no content available
    if (!this.state.adContent || !this.state.showAd) {
      // Ad completely hidden if user has sufficient credits
      if (this.state.creditBalance !== null && this.state.creditBalance >= 0.0003) {
        return null;
      }
      
      return null;
    }

    // Display advertisement
    const adId = `ad-${position}-${size}-${Date.now()}`;

    return (
      <div className={`ad-container ad-${position} ad-${size} ${className}`} id={adId}>
        <div 
          dangerouslySetInnerHTML={{ __html: this.state.adContent }}
          style={{
            "max-width": "100%",
            height: size === "large" ? "120px" : size === "medium" ? "90px" : "60px",
            overflow: "hidden"
          }}
        />
        {/* Credit info display (for development) */}
        {this.state.creditBalance !== null && (
          <div style={{ "font-size": "10px", color: "#666", "text-align": "center", "margin-top": "5px" }}>
            Current credit: {this.state.creditBalance.toFixed(8)} BCH (threshold: 0.0003 BCH)
          </div>
        )}
      </div>
    );
  }
}

// Global window extensions for BCH configuration (same as navbar.tsx)
declare global {
  interface Window {
    __BCH_CONFIG__?: {
      API_KEY: string;
      API_URL: string;
      PAYMENT_URL: string;
    };
  }
}