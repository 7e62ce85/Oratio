import { Component } from "inferno";
import { UserService } from "../../services";

// BCH configuration constants (same as navbar.tsx)
const BCH_API_URL = process.env.LEMMY_BCH_API_URL || "http://localhost:8081/api/user_credit";

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
    console.log("[AdBanner] Constructor called with props:", props);
    // Initialize ad content in the initial state
    this.state.adContent = this.getInitialAdContent();
    console.log("[AdBanner] Initial ad content set in constructor");
  }

  componentDidMount() {
    console.log("[AdBanner] componentDidMount called");
    this.checkUserCredit();
    // Ad content is already loaded in constructor
  }

  getInitialAdContent(): string {
    // Get initial ad content without using setState
    const { section = "general", customContent } = this.props;
    console.log("[AdBanner] getInitialAdContent called for section:", section);
    
    // Use custom content if provided
    if (customContent) {
      console.log("[AdBanner] Using custom ad content");
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
    console.log("[AdBanner] checkUserCredit - userInfo:", userInfo ? "exists" : "null");
    
    if (!userInfo) {
      console.log("[AdBanner] No user info - showing ads");
      this.setState({ showAd: true, isCheckingCredit: false });
      return;
    }

    this.setState({ isCheckingCredit: true });

    try {
      const person = userInfo.local_user_view.person;
      console.log("[AdBanner] Attempting to fetch credit for user ID", person.id);
      
      const apiUrl = `${getBCHAPIUrl()}/${person.id}`;
      console.log("[AdBanner] API URL:", apiUrl);
      
      const apiKeyHint = getApiKey() ? `${getApiKey().substring(0, 3)}...` : "not set";
      console.log(`[AdBanner] Using API key: ${apiKeyHint}`);

      const response = await fetch(apiUrl, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey() || "",
        },
      });

      console.log("[AdBanner] API response status:", response.status);

      if (response.ok) {
        const data = await response.json();
        console.log("[AdBanner] Response data:", data);
        
        // credit_balance 필드가 있는지 확인 (navbar.tsx와 동일)
        if (data.credit_balance !== undefined) {
          const creditBalance = parseFloat(data.credit_balance || 0);
          console.log("[AdBanner] Credit balance:", creditBalance, "BCH");
          
          // 크레딧 임계값: 0.0003 BCH 이상이면 광고 숨김
          const CREDIT_THRESHOLD = 0.0003;
          const shouldShowAd = creditBalance < CREDIT_THRESHOLD;
          
          console.log(`[AdBanner] Credit check: ${creditBalance} BCH ${shouldShowAd ? '<' : '>='} ${CREDIT_THRESHOLD} BCH threshold`);
          console.log(`[AdBanner] Decision: ${shouldShowAd ? 'SHOW' : 'HIDE'} ads`);

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
    console.log("[AdBanner] Ad content refreshed");
  }

  getHomeAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">🏠 환영합니다!</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">대파토론 커뮤니티에서 다양한 정보를 공유해</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Home ad clicked')" 
           style="background: #fff; color: #4facfe; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          더 알아보기
        </a>
      </div>
    `;
  }

  getCommunityAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">👥 커뮤니티 특별 혜택</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">이 커뮤니티의 멤버를 위한 특별 제안</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Community ad clicked')" 
           style="background: #fff; color: #fa709a; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          혜택 확인
        </a>
      </div>
    `;
  }

  getPostAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); padding: 15px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">📝 관련 서비스</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.8;">이 포스트와 관련된 유용한 도구들</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Post ad clicked')" 
           style="background: #333; color: #fff; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          도구 보기
        </a>
      </div>
    `;
  }

  getFeedAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">📰 피드 추천</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">더 많은 흥미로운 콘텐츠를 발견해</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Feed ad clicked')" 
           style="background: #fff; color: #667eea; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          콘텐츠 탐색
        </a>
      </div>
    `;
  }

  getCommentsAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); padding: 12px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 8px 0; font-size: 16px;">💬 토론 참여</h3>
        <p style="margin: 0 0 12px 0; font-size: 13px; opacity: 0.8;">의견을 나누고 소통해</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Comments ad clicked')" 
           style="background: #333; color: #fff; padding: 6px 16px; border-radius: 4px; text-decoration: none; font-weight: bold; display: inline-block; font-size: 12px;">
          참여하기
        </a>
      </div>
    `;
  }

  getGeneralAdContent(): string {
    return `
      <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; font-family: Arial, sans-serif;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">🚀 특별 혜택!</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">지금 가입하고 무료 크레딧을 받아!</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('General ad clicked')" 
           style="background: #fff; color: #667eea; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          자세히 보기
        </a>
      </div>
    `;
  }

  render() {
    const { position, size = "medium", className = "" } = this.props;
    
    console.log("[AdBanner] render called - showAd:", this.state.showAd, "adContent:", !!this.state.adContent);
    console.log("[AdBanner] Credit status - balance:", this.state.creditBalance, "isChecking:", this.state.isCheckingCredit);

    // 크레딧 체크 중일 때는 로딩 표시
    if (this.state.isCheckingCredit) {
      return (
        <div className={`ad-container ad-${position} ad-${size} ${className}`}>
          <div style={{ padding: "10px", "text-align": "center", color: "#666" }}>
            크레딧 확인 중...
          </div>
        </div>
      );
    }

    // 광고 콘텐츠가 없거나 표시하지 않아야 하는 경우 null 반환
    if (!this.state.adContent || !this.state.showAd) {
      console.log("[AdBanner] Not rendering - showAd:", this.state.showAd, "adContent:", !!this.state.adContent);
      
      // 크레딧이 충분해서 광고가 숨겨진 경우 완전히 사라지게 함 (새로운 방식)
      if (this.state.creditBalance !== null && this.state.creditBalance >= 0.0003) {
        console.log("[AdBanner] Ad completely hidden due to sufficient BCH credits:", this.state.creditBalance);
        return null; // 완전히 사라지게 함
      }
      
      // 기존 방식 (주석처리) - 광고 대신 메시지 표시
      // if (this.state.creditBalance !== null && this.state.creditBalance >= 0.0003) {
      //   console.log("[AdBanner] Ad hidden due to sufficient BCH credits:", this.state.creditBalance);
      //   return (
      //     <div className={`ad-container ad-${position} ad-${size} ${className}`} 
      //          style={{ padding: "10px", "text-align": "center", background: "#f8f9fa", border: "1px solid #e9ecef", "border-radius": "6px" }}>
      //       <span style={{ color: "#28a745", "font-size": "14px" }} title={`현재 크레딧: ${this.state.creditBalance} BCH`}>
      //         ✅ 광고 없는 환경을 즐기고 계십니다! (BCH 크레딧 보유)
      //       </span>
      //     </div>
      //   );
      // }
      
      return null;
    }

    // 광고 표시
    const adId = `ad-${position}-${size}-${Date.now()}`;
    console.log("[AdBanner] Rendering ad with ID:", adId, "- User has insufficient credits");

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
        {/* 크레딧 정보 표시 (개발용) */}
        {this.state.creditBalance !== null && (
          <div style={{ "font-size": "10px", color: "#666", "text-align": "center", "margin-top": "5px" }}>
            현재 크레딧: {this.state.creditBalance} BCH (임계값: 0.0003 BCH)
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