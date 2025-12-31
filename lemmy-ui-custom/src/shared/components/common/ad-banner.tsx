import { Component } from "inferno";
import { UserService } from "../../services";
import { creditCache, updateCreditCache, checkUserHasGoldBadge } from "../../utils/bch-payment";

// BCH configuration constants (same as navbar.tsx)
const BCH_API_URL = "https://oratio.space/payments/api/user_credit";
const ADS_API_URL = "https://oratio.space/payments/api/ads";

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

const getAdsAPIUrl = () => {
  if (typeof window !== 'undefined' && window.__BCH_CONFIG__) {
    // Use same base URL but with /ads endpoint
    const baseUrl = window.__BCH_CONFIG__.API_URL.replace('/api/user_credit', '/api/ads');
    return baseUrl;
  }
  return ADS_API_URL;
};

// Ad data interface from backend (4개 위치별 이미지 포함)
interface AdData {
  campaign_id: string;
  impression_id: string;
  title: string;
  link_url: string;
  alt_text: string | null;
  advertiser: string;
  is_nsfw: boolean;
  images: {
    sidebar: string | null;
    post_top: string | null;
    post_bottom: string | null;
    feed_inline: string | null;
  };
  image_url?: string | null;  // backward compatibility
}

// 세션 캐시: 페이지당 한 캠페인만 선택 (옵션A)
// 같은 페이지 내 모든 AdBanner가 동일 광고 표시
let sessionAdCache: { ad: AdData | null; timestamp: number; pageUrl: string } | null = null;

// Promise 기반 싱글톤: 동시 요청 시 첫 번째 요청 완료까지 대기
let pendingAdFetch: Promise<AdData | null> | null = null;

// 전역 community 정보: 페이지 내 모든 AdBanner에서 공유
let globalCommunityInfo: { community: string; displayName: string } | null = null;

// 페이지 로드 세션 ID: 페이지 로드당 한 번만 생성, load_points 중복 증가 방지용
let pageLoadSessionId: string | null = null;
let lastPageUrl: string | null = null;
// 클라이언트 측 Hydration 완료 플래그
let lemmyHydrated: boolean = false;

if (typeof window !== 'undefined') {
  // 클라이언트가 hydration을 완료했을 때 발생하는 커스텀 이벤트
  window.addEventListener('lemmy-hydrated', () => {
    lemmyHydrated = true;
  });
}

const resetAdCache = () => {
  pageLoadSessionId = null; 
  sessionAdCache = null;
  pendingAdFetch = null;
  globalCommunityInfo = null;
};

const generateSessionId = () => {
  if (!pageLoadSessionId) {
    pageLoadSessionId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
  return pageLoadSessionId;
};

// URL에서 community 이름 추출 (/c/communityName 또는 /c/communityName@instance 형식)
const parseCommunityFromUrl = (): string | null => {
  if (typeof window === 'undefined') return null;
  const pathname = window.location.pathname;
  
  // /c/communityName 또는 /c/communityName@instance 패턴 매칭
  const communityMatch = pathname.match(/^\/c\/([^\/\?@]+)/i);
  if (communityMatch) {
    return communityMatch[1].toLowerCase();
  }
  
  // /post/123 형태의 URL에서는 community를 알 수 없음 (props로 받아야 함)
  return null;
};

// 페이지 URL이 바뀌면 캐시 리셋 (SPA 네비게이션 감지)
const checkPageChange = () => {
  if (typeof window !== 'undefined') {
    const currentUrl = window.location.pathname;
    if (lastPageUrl && lastPageUrl !== currentUrl) {
      resetAdCache();
    }
    lastPageUrl = currentUrl;
  }
};

// 새 페이지 로드 시 세션 ID 리셋 (브라우저 뒤로/앞으로)
if (typeof window !== 'undefined') {
  window.addEventListener('popstate', resetAdCache);
}

interface AdBannerProps {
  position: "header" | "sidebar" | "footer" | "comment";
  size?: "large" | "medium" | "small";
  className?: string;
  section?: "home" | "community" | "post" | "feed" | "comments" | "general" | "post_bottom" | "website_bottom";
  customContent?: string;
  community?: string;  // Current community name for targeting
  communityDisplayName?: string;  // Current community display name (title) for targeting
  isNsfw?: boolean;    // Whether current page is NSFW
}

interface AdBannerState {
  showAd: boolean;
  adContent: string | null;
  isCheckingCredit: boolean;
  creditBalance: number | null;
  adData: AdData | null;       // Dynamic ad from backend
  isLoadingAd: boolean;        // Loading state for ad fetch
}

export class AdBanner extends Component<AdBannerProps, AdBannerState> {
  state: AdBannerState = {
    showAd: true,
    adContent: null,
    // Start with checking-credit true so the initial render shows a Loading
    // placeholder instead of the fallback default ad content. This prevents
    // a brief flash of the static default ad before the dynamic ad is
    // fetched (fixes the ~1s purple gradient flash on initial page load).
    isCheckingCredit: true,
    creditBalance: null,
    adData: null,
    isLoadingAd: false,
  };

  constructor(props: any, context: any) {
    super(props, context);
    // Initialize ad content in the initial state
    this.state.adContent = this.getInitialAdContent();
  }

  componentDidMount() {
    // Ensure we check credit first, then fetch ads only if ads should be shown.
    // This prevents recording impressions for users who have BCH credits (ad-free members).
    (async () => {
      try {
        const shouldShowAd = await this.checkUserCredit();
        // Use the returned value directly instead of state (setState is async)
        if (shouldShowAd) {
          await this.fetchDynamicAd();
        }
      } catch (e) {
        console.error('[AdBanner] componentDidMount error:', e);
      }
    })();
  }

  componentDidUpdate(prevProps: AdBannerProps) {
    // Don't do anything while checking credit - wait for membership check to complete
    if (this.state.isCheckingCredit) {
      return;
    }

    // Check if user info became available in UserService
    // This handles the case where user logs in but BCH credit wasn't checked
    // Use creditChecked flag to prevent infinite loop
    if (UserService.Instance.myUserInfo && 
        this.state.creditBalance === null &&
        !this.creditChecked) {
      this.creditChecked = true;  // Prevent re-checking
      this.checkUserCredit();
      return; // Wait for credit check to complete
    }

    // 페이지 URL이 바뀌면 광고 다시 fetch (SPA 네비게이션)
    const currentUrl = typeof window !== 'undefined' ? window.location.pathname : '';
    const urlChanged = this.lastUrl && this.lastUrl !== currentUrl;
    if (urlChanged) {
      this.lastUrl = currentUrl;
      this.adFetched = false;  // 리셋해서 다시 fetch 허용
      resetAdCache();  // 캐시도 리셋
      if (this.state.showAd && !this.state.isLoadingAd) {
        this.adFetched = true;
        this.fetchDynamicAd();
      }
      return;
    }
    if (!this.lastUrl) {
      this.lastUrl = currentUrl;
    }

    // If ads are allowed and we don't yet have adData, fetch it (e.g., user credit was just checked)
    if (this.state.showAd && !this.state.adData && !this.state.isLoadingAd && !this.adFetched) {
      this.adFetched = true;  // Prevent re-fetching
      this.fetchDynamicAd();
    }
  }

  // Flags to prevent infinite loops in componentDidUpdate
  private creditChecked = false;
  private adFetched = false;
  private lastUrl: string | null = null;

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

  async checkUserCredit(): Promise<boolean> {
    // SSR에서는 광고 표시하지 않음 (impression 카운트 방지)
    if (typeof window === 'undefined') {
      this.setState({ showAd: false, isCheckingCredit: false });
      return false;
    }

    // Check if user has enough BCH credits to hide ads (same logic as navbar.tsx)
    // Returns true if ads should be shown, false if user is a member (no ads)
    const userInfo = UserService.Instance.myUserInfo;
    
    if (!userInfo) {
      // Retry once after a short delay in case login is still in progress
      return new Promise((resolve) => {
        setTimeout(() => {
          const retryUserInfo = UserService.Instance.myUserInfo;
          if (retryUserInfo && this.state.creditBalance === null) {
            this.checkUserCredit().then(resolve);
          } else {
            // Show ads for non-logged-in users, set isLoadingAd=true to prevent flicker
            this.setState({ showAd: true, isCheckingCredit: false, isLoadingAd: true });
            resolve(true); // Show ads for non-logged-in users
          }
        }, 2000);
      });
    }

    this.setState({ isCheckingCredit: true });

    try {
      const person = userInfo.local_user_view.person;
      
      // NEW BEHAVIOR: Only hide ads for active membership users.
      // Use async version to ensure we wait for API response before deciding.
      // This prevents counting impressions for members whose cache hasn't loaded yet.
      try {
        const isMember = await checkUserHasGoldBadge(person);

        if (isMember) {
          // Member: hide ads
          this.setState({ showAd: false, creditBalance: 1.0, isCheckingCredit: false });
          return false; // Don't show ads for members
        } else {
          // Not a member: always show ads. Set isLoadingAd=true to prevent flicker
          // while fetchDynamicAd() is running (keeps showing "Loading..." instead of default ad)
          this.setState({ showAd: true, creditBalance: 0.0, isCheckingCredit: false, isLoadingAd: true });
          return true; // Show ads for non-members
        }
      } catch (err) {
        // If membership check fails for any reason, fall back to showing ads
        console.error('[AdBanner] Membership check failed, falling back to show ads', err);
        this.setState({ showAd: true, creditBalance: -1, isCheckingCredit: false, isLoadingAd: true });
        return true; // Show ads on error
      }
    } catch (error) {
      console.error("[AdBanner] Error checking user credits:", error);
      // 에러 발생시 기본적으로 광고 표시, creditBalance를 -1로 설정하여 재시도 방지
      this.setState({ showAd: true, creditBalance: -1, isCheckingCredit: false, isLoadingAd: true });
      return true; // Show ads on error
    }
  }

  loadAdContent() {
    // This method can be used to refresh ad content if needed
    const adContent = this.getInitialAdContent();
    this.setState({ adContent });
  }

  async fetchDynamicAd() {
    // SSR에서는 광고 fetch 금지 - 클라이언트에서만 실행
    if (typeof window === 'undefined') {
      return;
    }

    // 옵션1: 페이지 이동마다 새 광고 (표준 방식)
    const { community, communityDisplayName, isNsfw = false } = this.props;
    const currentPageUrl = typeof window !== 'undefined' ? window.location.pathname : '';
    
    // 페이지가 바뀌면 캐시 리셋
    checkPageChange();
    
    // URL에서 community 파싱 (props나 globalCommunityInfo보다 확실한 소스)
    const urlCommunity = parseCommunityFromUrl();
    
    // community 정보가 있으면 전역에 저장 (다른 AdBanner에서 사용)
    // URL에서 파싱한 값 우선, 그 다음 props
    const communityToStore = urlCommunity || community;
    if (communityToStore && !globalCommunityInfo) {
      globalCommunityInfo = { community: communityToStore, displayName: communityDisplayName || '' };
    }
    
    // 1. 유효한 캐시가 있고 같은 페이지면 사용
    if (sessionAdCache && sessionAdCache.pageUrl === currentPageUrl) {
      this.setState({ 
        adData: sessionAdCache.ad,
        isLoadingAd: false 
      });
      return;
    }
    
    // 2. 이미 진행 중인 요청이 있으면 그 결과를 기다림
    if (pendingAdFetch) {
      try {
        const ad = await pendingAdFetch;
        this.setState({ adData: ad, isLoadingAd: false });
      } catch (e) {
        this.setState({ isLoadingAd: false });
      }
      return;
    }
    
    // 3. URL에서 community를 파싱했는지 확인
    // URL 기반 community가 있으면 바로 사용 (대기 불필요)
    // URL 기반 community가 없고, props/global도 없으면 대기
    const hasUrlCommunity = !!urlCommunity;
    
    if (!hasUrlCommunity && !community && !globalCommunityInfo) {
      // URL에서 community 패턴이 감지되면 (/c/) 더 오래 대기
      const isCommunityPage = currentPageUrl.startsWith('/c/');
      const waitTime = isCommunityPage ? 250 : 100;
      
      // 만약 클라이언트 hydration이 아직 끝나지 않았다면, hydration 이벤트를
      // 최대 timeout 동안 기다려준다. post 페이지 같은 경우 hydration 후에
      // 사이드바가 community 정보를 갖고 오기 때문에 이 대기가 필요하다.
      const hydrationTimeout = Math.max(waitTime, 300);
      if (!lemmyHydrated) {
        await Promise.race([
          new Promise<void>(resolve => {
            const onHydrated = () => {
              window.removeEventListener('lemmy-hydrated', onHydrated);
              resolve();
            };
            window.addEventListener('lemmy-hydrated', onHydrated);
          }),
          new Promise<void>(resolve => setTimeout(resolve, hydrationTimeout))
        ]);
      } else {
        await new Promise(resolve => setTimeout(resolve, waitTime));
      }
      // 대기 후 캐시가 생겼으면 사용
      if (sessionAdCache) {
        this.setState({ adData: sessionAdCache.ad, isLoadingAd: false });
        return;
      }
      // 대기 후 다른 요청이 진행 중이면 그 결과를 기다림
      if (pendingAdFetch) {
        try {
          const ad = await pendingAdFetch;
          this.setState({ adData: ad, isLoadingAd: false });
        } catch (e) {
          this.setState({ isLoadingAd: false });
        }
        return;
      }
    }
    
    // 4. 첫 번째 요청: Promise를 생성하고 다른 컴포넌트들이 기다리게 함
    this.setState({ isLoadingAd: true });
    
    // community 정보 우선순위: URL 파싱 > props > globalCommunityInfo
    const effectiveCommunity = urlCommunity || community || globalCommunityInfo?.community;
    const effectiveDisplayName = communityDisplayName || globalCommunityInfo?.displayName;
    
    pendingAdFetch = (async (): Promise<AdData | null> => {
      try {
        const pageUrl = typeof window !== 'undefined' ? window.location.href : '';
        
        const params = new URLSearchParams();
        if (effectiveCommunity) params.append('community', effectiveCommunity);
        if (effectiveDisplayName) params.append('community_display_name', effectiveDisplayName);
        params.append('is_nsfw', isNsfw.toString());
        if (pageUrl) params.append('page_url', pageUrl);
        params.append('session_id', generateSessionId());
        
        const apiUrl = `${getAdsAPIUrl()}/display?${params.toString()}`;
        
        const response = await fetch(apiUrl, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        });

        if (response.ok) {
          const data = await response.json();
          if (data.success && data.ad) {
            sessionAdCache = { ad: data.ad, timestamp: Date.now(), pageUrl: currentPageUrl };
            return data.ad;
          }
        }
        
        sessionAdCache = { ad: null, timestamp: Date.now(), pageUrl: currentPageUrl };
        return null;
      } catch (error) {
        console.error("[AdBanner] Error fetching dynamic ad:", error);
        return null;
      } finally {
        pendingAdFetch = null;
      }
    })();
    
    try {
      const ad = await pendingAdFetch;
      this.setState({ adData: ad, isLoadingAd: false }, () => {
        // Confirm impression after state is set
        if (ad) {
          try {
            const positionMap: Record<string, string> = {
              'sidebar': 'sidebar',
              'header': 'post_top',
              'footer': 'post_bottom',
              'comment': 'feed_inline',
            };
            const slot = positionMap[this.props.position] || 'sidebar';
            fetch(`${getAdsAPIUrl()}/confirm`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ impression_id: ad.impression_id, ad_slot: slot })
            }).catch(() => {});
          } catch (e) {
            // Silently ignore
          }
        }
      });
    } catch (e) {
      this.setState({ isLoadingAd: false });
    }
  }

  // 현재 position에 맞는 이미지 URL 가져오기
  getImageForPosition(): string | null {
    const { position, section } = this.props;
    const { adData } = this.state;
    
    if (!adData || !adData.images) return null;
    
    // position/section prop을 images 키로 매핑
    // Active ad sections (2025-12-25): sidebar, post_top (header), post_bottom (footer)
    // Removed: feed_inline (comments)
    const positionMap: Record<string, keyof AdData['images']> = {
      'sidebar': 'sidebar',
      'header': 'post_top',
      'footer': 'post_bottom',  // footer uses post_bottom image
      'comment': 'feed_inline',  // legacy, now removed but keep for compatibility
    };
    
    // website_bottom section also uses post_bottom image (same as footer)
    if (section === 'website_bottom') {
      return adData.images.post_bottom || null;
    }
    
    const imageKey = positionMap[position] || 'sidebar';
    return adData.images[imageKey] || null;
  }

  async recordAdClick(impressionId: string) {
    // Record click when user clicks on dynamic ad
    try {
      const apiUrl = `${getAdsAPIUrl()}/click`;
      
      await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ impression_id: impressionId }),
      });
    } catch (error) {
      console.error("[AdBanner] Error recording click:", error);
    }
  }

  renderDynamicAd(adData: AdData, size: string): any {
    // 현재 position에 맞는 이미지 가져오기
    const imageUrl = this.getImageForPosition();
    
    // 해당 위치에 이미지가 없으면 null 반환 (기본 광고 표시)
    if (!imageUrl) {
      return null;
    }
    
    const heightStyle = size === "large" ? "120px" : size === "medium" ? "90px" : "60px";
    
    // 위치별 최대 높이 설정 (권장 사이즈 기준)
    // Sidebar: 300x250 or 300x600 → maxHeight 600px
    // Top/Bottom: 728x90 → maxHeight 90px
    const { position } = this.props;
    const maxHeightMap: Record<string, string> = {
      'sidebar': '600px',
      'header': '90px',
      'footer': '90px',
      'comment': '250px',
    };
    const maxHeight = maxHeightMap[position] || '250px';
    
    const handleClick = () => {
      this.recordAdClick(adData.impression_id);
    };
    
    return (
      <div style={{
        background: "#ffffff",
        padding: "15px",
        borderRadius: "8px",
        textAlign: "center",
        color: "#333",
        fontFamily: "Arial, sans-serif",
        minHeight: heightStyle,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        border: "1px solid #e6e6e6"
      }}>
        <a 
          href={adData.link_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={handleClick}
          style={{ display: "block" }}
        >
          <img 
            src={imageUrl} 
            alt={adData.alt_text || adData.title}
            style={{ maxWidth: "100%", maxHeight: maxHeight, objectFit: "contain", borderRadius: "4px" }}
          />
        </a>
        {adData.is_nsfw === true && (
          <span style={{ fontSize: "10px", opacity: 0.7, marginTop: "4px" }}>NSFW</span>
        )}
      </div>
    );
  }

  getHomeAdContent(): string {
    return `
      <div style="background: #ffffff; padding: 15px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif; border: 1px solid #e6e6e6;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">🏠 Welcome!</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">Share diverse information in our community</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Home ad clicked')" 
           style="background: #4facfe; color: #fff; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          Learn More
        </a>
      </div>
    `;
  }

  getCommunityAdContent(): string {
    return `
      <div style="background: #ffffff; padding: 15px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif; border: 1px solid #e6e6e6;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">👥 Community Special Benefits</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">Special offer for members of this community</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Community ad clicked')" 
           style="background: #fa709a; color: #fff; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          Check Benefits
        </a>
      </div>
    `;
  }

  getPostAdContent(): string {
    return `
      <div style="background: #ffffff; padding: 15px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif; border: 1px solid #e6e6e6;">
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
      <div style="background: #ffffff; padding: 15px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif; border: 1px solid #e6e6e6;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">📰 Feed Recommendations</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">Discover more interesting content</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('Feed ad clicked')" 
           style="background: #667eea; color: #fff; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          Explore Content
        </a>
      </div>
    `;
  }

  getCommentsAdContent(): string {
    return `
      <div style="background: #ffffff; padding: 12px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif; border: 1px solid #e6e6e6;">
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
      <div style="background: #ffffff; padding: 15px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif; border: 1px solid #e6e6e6;">
        <h3 style="margin: 0 0 10px 0; font-size: 18px;">🚀 Special Offer!</h3>
        <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">Sign up now and join the awesome community!</p>
        <a href="#" target="_blank" rel="noopener" onclick="console.log('General ad clicked')" 
           style="background: #667eea; color: #fff; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
          Learn More
        </a>
      </div>
    `;
  }

  render() {
    const { position, size = "medium", className = "" } = this.props;

    // Check credit during initialization if user is logged in
    if (this.state.isCheckingCredit || this.state.isLoadingAd) {
      return (
        <div className={`ad-container ad-${position} ad-${size} ${className}`}>
          <div style={{ padding: "10px", "text-align": "center", color: "#666" }}>
            Loading...
          </div>
        </div>
      );
    }

    // Don't show ad if user has sufficient credits
    if (!this.state.showAd) {
      return null;
    }

    // Display advertisement
    const adId = `ad-${position}-${size}-${Date.now()}`;

    // Dynamic ad에서 해당 위치 이미지가 있는지 확인
    const dynamicAdContent = this.state.adData ? this.renderDynamicAd(this.state.adData, size) : null;

    return (
      <div className={`ad-container ad-${position} ad-${size} ${className}`} id={adId}>
        {/* Priority 1: Dynamic ad from backend (해당 위치에 이미지가 있을 때만) */}
        {dynamicAdContent ? (
          dynamicAdContent
        ) : this.state.adContent ? (
          /* Priority 2: Static fallback content (기본 광고) */
          <div 
            dangerouslySetInnerHTML={{ __html: this.state.adContent }}
            style={{
              "max-width": "100%",
              minHeight: size === "large" ? "120px" : size === "medium" ? "90px" : "60px",
              overflow: "hidden"
            }}
          />
        ) : null}
        {/* Credit info display removed - was showing "0" next to ads */}
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