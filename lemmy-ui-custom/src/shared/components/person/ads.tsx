import { Component, linkEvent } from "inferno";
import { Link } from "inferno-router";
import { GetSiteResponse } from "lemmy-js-client";
import { I18NextService } from "../../services/I18NextService";
import { Icon, Spinner } from "../common/icon";
import { toast } from "../../toast";
import { setIsoData } from "@utils/app";
import { UserService } from "../../services";
import { getApiKey } from "../../utils/bch-payment";

// Helper to get Ads API base URL
const getAdsAPIBaseUrl = () => {
  if (typeof window !== 'undefined') {
    return '/payments/api/ads';
  }
  return 'http://bitcoincash-service:8081/api/ads';
};

// Campaign status badge colors
const statusColors: Record<string, string> = {
  pending: "#ffc107",
  approved: "#28a745", 
  rejected: "#dc3545",
};

interface Campaign {
  id: string;
  title: string;
  link_url: string;
  image_url: string | null;
  monthly_budget_usd: number;
  spent_this_month_usd: number;
  approval_status: string;
  is_active: boolean;
  is_nsfw: boolean;
  target_communities: string | null;
  target_regex: string | null;
  total_impressions: number;
  total_clicks: number;
  created_at: number;
  rejection_reason?: string;
}

interface AdsPageState {
  loading: boolean;
  adCredits: number;
  campaigns: Campaign[];
  pendingCampaigns: Campaign[];
  isAdmin: boolean;
  totalActiveBudget: number;
  activeCampaignCount: number;
  // Section impression stats (last N days)
  sectionStats: Record<string, number>;
  // Create campaign form
  showCreateForm: boolean;
  formTitle: string;
  formLinkUrl: string;
  // 4개 위치별 이미지 URL
  formImageSidebar: string;
  formImagePostTop: string;
  formImagePostBottom: string;
  formImageFeedInline: string;
  // 이미지 업로드 상태
  uploadingSidebar: boolean;
  uploadingPostTop: boolean;
  uploadingPostBottom: boolean;
  uploadingFeedInline: boolean;
  formBudget: number;
  formIsNsfw: boolean;
  formTargetCommunities: string;
  formTargetRegex: string;
  formShowOnAll: boolean;
  submitting: boolean;
  siteRes: GetSiteResponse;
  // Add Credits modal state
  showAddCreditsModal: boolean;
  addCreditsAmount: number;
  addCreditsLoading: boolean;
  purchaseError: string | null;
  // BCH Balance info
  bchBalance: number;
  bchBalanceUsd: number;
  bchPriceUsd: number;
  loadingBalances: boolean;
  // Admin view: list of active campaigns (approved & running)
  adminActiveCampaigns: Campaign[];
}

// Active ad image positions: sidebar, post_top, feed_inline

export class AdsPage extends Component<any, AdsPageState> {
  private isoData = setIsoData(this.context);
  
  state: AdsPageState = {
    loading: true,
    adCredits: 0,
    campaigns: [],
    pendingCampaigns: [],
    isAdmin: false,
    totalActiveBudget: 0,
    activeCampaignCount: 0,
    showCreateForm: false,
    formTitle: "",
    formLinkUrl: "",
    // 4개 위치별 이미지
    formImageSidebar: "",
    formImagePostTop: "",
    formImagePostBottom: "",
    formImageFeedInline: "",
    uploadingSidebar: false,
    uploadingPostTop: false,
    uploadingPostBottom: false,
    uploadingFeedInline: false,
    formBudget: 10,
    formIsNsfw: false,
    formTargetCommunities: "",
    formTargetRegex: "",
    formShowOnAll: true,
    submitting: false,
    siteRes: this.isoData.site_res,
    sectionStats: {},
    // Add Credits modal
    showAddCreditsModal: false,
    addCreditsAmount: 10,
    addCreditsLoading: false,
    purchaseError: null,
    // BCH Balance info
    bchBalance: 0,
    bchBalanceUsd: 0,
    bchPriceUsd: 480,
    loadingBalances: false,
    // Admin view: active campaigns
    adminActiveCampaigns: [],
  };

  constructor(props: any, context: any) {
    super(props, context);
    this.handleCreateCampaign = this.handleCreateCampaign.bind(this);
    this.handleImageUpload = this.handleImageUpload.bind(this);
  }

  async componentDidMount() {
    if (UserService.Instance.myUserInfo) {
      const isAdmin = UserService.Instance.myUserInfo.local_user_view.local_user.admin;
      this.setState({ 
        siteRes: {
          ...this.state.siteRes,
          my_user: UserService.Instance.myUserInfo
        },
        isAdmin
      });
    }
    await this.fetchAdsData();
    // Fetch section stats (90 days) to compute monthly estimates
    this.fetchSectionStats(90).catch(e => console.error('fetchSectionStats error', e));
  }

  async fetchSectionStats(days: number = 90) {
    try {
      const response = await fetch(`/payments/api/ads/stats/sections?days=${days}`);
      if (!response.ok) return;
      const data = await response.json();
      if (data && data.by_slot) {
        this.setState({ sectionStats: data.by_slot });
      }
    } catch (e) {
      console.error('Error fetching section stats', e);
    }
  }

  get currentUser() {
    const myUser = UserService.Instance.myUserInfo || this.state.siteRes.my_user;
    return myUser?.local_user_view.person;
  }

  get username() {
    return this.currentUser?.name || "";
  }

  async fetchAdsData() {
    if (!this.currentUser) {
      this.setState({ loading: false });
      return;
    }

    this.setState({ loading: true });
    const baseUrl = getAdsAPIBaseUrl();
    const apiKey = getApiKey();

    try {
      // Fetch ad credits
      const creditsResponse = await fetch(`${baseUrl}/credits/${this.username}`, {
        headers: { 'X-API-Key': apiKey || "" }
      });
      if (creditsResponse.ok) {
        const data = await creditsResponse.json();
        this.setState({ adCredits: data.credit_balance_usd || 0 });
      }

      // Fetch total active budget (for probability calculation)
      const totalBudgetResponse = await fetch(`${baseUrl}/total-budget`);
      if (totalBudgetResponse.ok) {
        const data = await totalBudgetResponse.json();
        this.setState({ 
          totalActiveBudget: data.total_budget_usd || 0,
          activeCampaignCount: data.active_campaign_count || 0
        });
      }

      // Fetch user campaigns
      const campaignsResponse = await fetch(`${baseUrl}/campaigns/user/${this.username}`, {
        headers: { 'X-API-Key': apiKey || "" }
      });
      if (campaignsResponse.ok) {
        const data = await campaignsResponse.json();
        this.setState({ campaigns: data.campaigns || [] });
      }

      // If admin, fetch pending campaigns
      if (this.state.isAdmin) {
        const pendingResponse = await fetch(`${baseUrl}/admin/pending`, {
          headers: { 
            'X-API-Key': apiKey || "",
            'X-Admin-Username': this.username
          }
        });
        if (pendingResponse.ok) {
          const data = await pendingResponse.json();
          this.setState({ pendingCampaigns: data.campaigns || [] });
        }
        // Also fetch active campaigns for admin overview
        try {
          const activeResponse = await fetch(`${baseUrl}/admin/active`, {
            headers: {
              'X-API-Key': apiKey || "",
              'X-Admin-Username': this.username
            }
          });
          if (activeResponse.ok) {
            const adata = await activeResponse.json();
            this.setState({ adminActiveCampaigns: adata.campaigns || [] });
          }
        } catch (e) {
          console.error('Error fetching admin active campaigns', e);
        }
      }
    } catch (e) {
      console.error("Error fetching ads data:", e);
      toast(I18NextService.i18n.t("error") || "Error loading ads data", "danger");
    }

    this.setState({ loading: false });
  }

  // Pictrs 이미지 업로드 핸들러
  async handleImageUpload(position: string, file: File) {
    const uploadingKey = `uploading${position.charAt(0).toUpperCase() + position.slice(1).replace(/_(\w)/g, (_, c) => c.toUpperCase())}` as keyof AdsPageState;
    const imageKey = `formImage${position.charAt(0).toUpperCase() + position.slice(1).replace(/_(\w)/g, (_, c) => c.toUpperCase())}` as keyof AdsPageState;
    
    this.setState({ [uploadingKey]: true } as any);
    
    try {
      const formData = new FormData();
      formData.append('images[]', file);
      
      // Lemmy pictrs 이미지 업로드
      const response = await fetch('/pictrs/image', {
        method: 'POST',
        body: formData,
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.files && data.files.length > 0) {
          const imageUrl = `/pictrs/image/${data.files[0].file}`;
          this.setState({ [imageKey]: imageUrl } as any);
          toast(`Image uploaded for ${position}`, "success");
        }
      } else {
        toast("Failed to upload image", "danger");
      }
    } catch (e) {
      console.error("Image upload error:", e);
      toast("Image upload failed", "danger");
    }
    
    this.setState({ [uploadingKey]: false } as any);
  }

  async handleCreateCampaign(i: AdsPage, e: Event) {
    if (e && e.preventDefault) {
      e.preventDefault();
    }
    
    if (!i.username) return;

    i.setState({ submitting: true });

    const baseUrl = getAdsAPIBaseUrl();
    const apiKey = getApiKey();

    // 4개 위치별 이미지 URL
    const campaignData = {
      advertiser_username: i.username,
      title: i.state.formTitle,
      link_url: i.state.formLinkUrl,
      image_sidebar_url: i.state.formImageSidebar || null,
      image_post_top_url: i.state.formImagePostTop || null,
      image_post_bottom_url: i.state.formImagePostBottom || null,
      image_feed_inline_url: i.state.formImageFeedInline || null,
      monthly_budget_usd: i.state.formBudget,
      is_nsfw: i.state.formIsNsfw,
      show_on_all: i.state.formShowOnAll,
      target_communities: i.state.formShowOnAll ? null : 
        i.state.formTargetCommunities.split(',').map(s => s.trim()).filter(s => s),
      target_regex: i.state.formTargetRegex || null,
      // 기간은 기본 1개월 (백엔드에서 처리)
    };

    try {
      const response = await fetch(`${baseUrl}/campaigns`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': apiKey || ""
        },
        body: JSON.stringify(campaignData)
      });

      // HTTP 에러 체크 (401, 403, 500 등)
      if (!response.ok) {
        let errorMsg = `Server error: ${response.status} ${response.statusText}`;
        try {
          const errorData = await response.json();
          if (errorData.error) {
            errorMsg = `Error: ${errorData.error}`;
          }
        } catch {
          // JSON 파싱 실패시 텍스트로 시도
          try {
            const errorText = await response.text();
            if (errorText) {
              errorMsg = `Error: ${errorText.substring(0, 200)}`;
            }
          } catch {
            // 무시
          }
        }
        console.error("Campaign creation failed:", response.status, errorMsg);
        toast(errorMsg, "danger");
        i.setState({ submitting: false });
        return;
      }

      const result = await response.json();

      if (result.success) {
        toast("Campaign created! Awaiting admin approval. (Default period: 1 month)", "success");
        i.setState({
          showCreateForm: false,
          formTitle: "",
          formLinkUrl: "",
          formImageSidebar: "",
          formImagePostTop: "",
          formImageFeedInline: "",
          formBudget: 10,
          formIsNsfw: false,
          formTargetCommunities: "",
          formTargetRegex: "",
          formShowOnAll: true,
        });
        await i.fetchAdsData();
      } else {
        // 서버가 success: false 반환한 경우 상세 에러 표시
        const errorDetail = result.error || "Unknown error";
        const extraInfo = result.required_usd ? ` (Required: $${result.required_usd}, Available: $${result.available_usd})` : "";
        toast(`Failed: ${errorDetail}${extraInfo}`, "danger");
      }
    } catch (e: any) {
      console.error("Error creating campaign:", e);
      toast(`Error creating campaign: ${e.message || e}`, "danger");
    }

    i.setState({ submitting: false });
  }

  async handleApproveCampaign(campaignId: string) {
    const baseUrl = getAdsAPIBaseUrl();
    const apiKey = getApiKey();

    try {
      const response = await fetch(`${baseUrl}/admin/approve/${campaignId}`, {
        method: 'POST',
        headers: {
          'X-API-Key': apiKey || "",
          'X-Admin-Username': this.username
        }
      });

      const result = await response.json();
      if (result.success) {
        toast("Campaign approved!", "success");
        await this.fetchAdsData();
      } else {
        toast(result.error || "Failed to approve", "danger");
      }
    } catch (e) {
      toast("Error approving campaign", "danger");
    }
  }

  async handleRejectCampaign(campaignId: string) {
    const reason = prompt("Enter rejection reason:");
    if (!reason) return;

    const baseUrl = getAdsAPIBaseUrl();
    const apiKey = getApiKey();

    try {
      const response = await fetch(`${baseUrl}/admin/reject/${campaignId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': apiKey || "",
          'X-Admin-Username': this.username
        },
        body: JSON.stringify({ reason })
      });

      const result = await response.json();
      if (result.success) {
        toast("Campaign rejected", "info");
        await this.fetchAdsData();
      } else {
        toast(result.error || "Failed to reject", "danger");
      }
    } catch (e) {
      toast("Error rejecting campaign", "danger");
    }
  }

  render() {
    if (!this.currentUser) {
      return (
        <div className="container-lg">
          <div className="alert alert-warning mt-4">
            Please <Link to="/login">log in</Link> to manage advertisements.
          </div>
        </div>
      );
    }

    return (
      <div className="container-lg">
        <div className="row">
          <div className="col-12">
            <h1 className="h4 mb-4">
              <Icon icon="megaphone" classes="me-2" />
              Advertisement Management
            </h1>
          </div>
        </div>

        {this.state.loading ? (
          <div className="text-center py-5">
            <Spinner />
          </div>
        ) : (
          <>
            {/* Credits Section */}
            {this.renderCreditsSection()}

            {/* Create Campaign Button/Form */}
            {this.renderCreateSection()}

            {/* My Campaigns */}
            {this.renderMyCampaigns()}

            {/* Admin: Pending Approvals & Active Campaigns */}
            {this.state.isAdmin && this.renderPendingApprovals()}
            {this.state.isAdmin && this.renderAdminActiveCampaigns()}
          </>
        )}
      </div>
    );
  }

  // Calculate expected probability for a given budget
  calculateExpectedProbability(budget: number): number {
    const totalWithMine = this.state.totalActiveBudget + budget;
    if (totalWithMine <= 0) return 100;
    return (budget / totalWithMine) * 100;
  }

  renderCreditsSection() {
    return (
      <div className="card mb-4">
        <div className="card-header">
          <h5 className="mb-0">Ad Credits</h5>
        </div>
        <div className="card-body">
          <div className="row align-items-center">
            <div className="col-md-6">
              <h2 className="text-success mb-0">
                ${this.state.adCredits.toFixed(2)} USD
              </h2>
              <small className="text-muted">Available ad credits</small>
            </div>
            <div className="col-md-6 text-md-end mt-3 mt-md-0">
              <button 
                className="btn btn-outline-primary"
                onClick={() => this.openAddCreditsModal()}
              >
                <Icon icon="plus" classes="me-1" />
                Add Credits via BCH
              </button>
            </div>
          </div>
          <hr />
          <div className="alert alert-info mb-0">
            <strong>How it works:</strong> Your display probability = Your budget / Total all advertisers' budgets × 100%<br/>
            <small>
              Current total active budgets: <strong>${this.state.totalActiveBudget.toFixed(2)}</strong> 
              ({this.state.activeCampaignCount} active campaigns)
            </small>
          </div>
        </div>
        {/* Add Credits Modal */}
        {this.renderAddCreditsModal()}
      </div>
    );
  }

  renderCreateSection() {
    if (!this.state.showCreateForm) {
      return (
        <div className="mb-4">
          <button 
            className="btn btn-primary"
            onClick={() => this.setState({ showCreateForm: true })}
          >
            <Icon icon="plus" classes="me-1" />
            Create New Campaign
          </button>
        </div>
      );
    }

    return (
      <div className="card mb-4">
        <div className="card-header d-flex justify-content-between align-items-center">
          <h5 className="mb-0">Create New Campaign</h5>
          <button 
            className="btn btn-sm btn-outline-secondary"
            onClick={() => this.setState({ showCreateForm: false })}
          >
            Cancel
          </button>
        </div>
        <div className="card-body">
          <form onSubmit={linkEvent(this, this.handleCreateCampaign)}>
            <div className="mb-3">
              <label className="form-label">Ad Title *</label>
              <input
                type="text"
                className="form-control"
                value={this.state.formTitle}
                onInput={linkEvent(this, (s, e: any) => s.setState({ formTitle: e.target.value }))}
                required
                placeholder="Your awesome product"
              />
            </div>

            <div className="mb-3">
              <label className="form-label">Link URL *</label>
              <input
                type="url"
                className="form-control"
                value={this.state.formLinkUrl}
                onInput={linkEvent(this, (s, e: any) => s.setState({ formLinkUrl: e.target.value }))}
                required
                placeholder="https://example.com/landing"
              />
            </div>

            {/* 4개 위치별 이미지 업로드 */}
            <div className="mb-4">
              <h6 className="mb-3">Ad Images (at least one required)</h6>
              <div className="alert alert-info small mb-3">
                <strong>Note:</strong> Upload images for each position. Positions without images will show default ads.
                <br/>Campaign is selected once per page load - all registered images will be shown simultaneously.
                <br/><strong>Default campaign period: 1 month</strong>
              </div>
              
              {/* Load Points System Info */}
              <div className="alert alert-warning small mb-3">
                <strong>🎯 Load Points System:</strong>
                <br/>When your targeted ad (community/regex) doesn't match the current page, it earns "load points" instead of being wasted.
                <br/>Ads with load points get <strong>priority display</strong> on matching pages.
                <br/>This ensures fair exposure even with specific targeting.
              </div>
              
              {/* Sidebar Image */}
              <div className="card mb-2">
                <div className="card-body py-2">
                  <div className="d-flex align-items-center justify-content-between">
                    <div>
                      <strong>Sidebar</strong>
                      <small className="text-muted ms-2">300×250 or 300×600px</small>
                    </div>
                    <div className="d-flex align-items-center gap-2">
                      {this.state.formImageSidebar && (
                        <img src={this.state.formImageSidebar} alt="Sidebar preview" style={{maxHeight: "40px"}} />
                      )}
                      <input
                        type="file"
                        accept="image/*"
                        className="form-control form-control-sm"
                        style={{width: "200px"}}
                        onChange={(e: any) => e.target.files?.[0] && this.handleImageUpload("Sidebar", e.target.files[0])}
                        disabled={this.state.uploadingSidebar}
                      />
                      {this.state.uploadingSidebar && <Spinner />}
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Post Top Image */}
              <div className="card mb-2">
                <div className="card-body py-2">
                  <div className="d-flex align-items-center justify-content-between">
                    <div>
                      <strong>Top</strong>
                      <small className="text-muted ms-2">728×90 or 970×90px</small>
                    </div>
                    <div className="d-flex align-items-center gap-2">
                      {this.state.formImagePostTop && (
                        <img src={this.state.formImagePostTop} alt="Top preview" style={{maxHeight: "40px"}} />
                      )}
                      <input
                        type="file"
                        accept="image/*"
                        className="form-control form-control-sm"
                        style={{width: "200px"}}
                        onChange={(e: any) => e.target.files?.[0] && this.handleImageUpload("PostTop", e.target.files[0])}
                        disabled={this.state.uploadingPostTop}
                      />
                      {this.state.uploadingPostTop && <Spinner />}
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Post Bottom Image */}
              <div className="card mb-2">
                <div className="card-body py-2">
                  <div className="d-flex align-items-center justify-content-between">
                    <div>
                      <strong>Bottom</strong>
                      <small className="text-muted ms-2">728×90px</small>
                    </div>
                    <div className="d-flex align-items-center gap-2">
                      {this.state.formImagePostBottom && (
                        <img src={this.state.formImagePostBottom} alt="Bottom preview" style={{maxHeight: "40px"}} />
                      )}
                      <input
                        type="file"
                        accept="image/*"
                        className="form-control form-control-sm"
                        style={{width: "200px"}}
                        onChange={(e: any) => e.target.files?.[0] && this.handleImageUpload("PostBottom", e.target.files[0])}
                        disabled={this.state.uploadingPostBottom}
                      />
                      {this.state.uploadingPostBottom && <Spinner />}
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Comments Inline removed - 2025-12-20 */}
            </div>

            <div className="mb-3">
              <label className="form-label">Campaign Cost (USD) *</label>
              <div className="input-group">
                <span className="input-group-text">$</span>
                <input
                  type="number"
                  className="form-control"
                  value={this.state.formBudget}
                  onInput={linkEvent(this, (s, e: any) => s.setState({ formBudget: parseFloat(e.target.value) || 10 }))}
                  min="10"
                  step="1"
                  required
                />
              </div>
              <div className="alert alert-info mt-2 mb-0 py-2">
                <strong>⚡ Instant Deduction:</strong> This amount will be <strong>immediately deducted</strong> from your credits when you create the campaign.
              </div>
              <div className="mt-2 p-2 bg-light border rounded">
                <strong>Expected Display Probability: </strong>
                <span className="text-primary fs-5">
                  {this.calculateExpectedProbability(this.state.formBudget).toFixed(1)}%
                </span>
                <br/>
                <small className="text-muted">
                  Formula: ${this.state.formBudget} / (${this.state.totalActiveBudget.toFixed(2)} + ${this.state.formBudget}) × 100%
                </small>
              </div>
              {/* Estimated monthly impressions based on last 90 days */}
              <div className="mt-2 p-2 bg-white border rounded">
                <strong>Estimated Monthly Impressions (based on last 90 days): </strong>
                {(() => {
                  const stats = this.state.sectionStats || {};
                  const postTop = stats['post_top'] || 0;
                  const toMonthly = (n: number) => Math.round((n / 90) * 30);
                  return <strong>{toMonthly(postTop).toLocaleString()}</strong>;
                })()} / month
              </div>
              <small className="text-muted d-block mt-1">
                Minimum $10. Your ad will be shown with this probability on each page load.
              </small>
            </div>

            <div className="mb-3">
              <div className="form-check">
                <input
                  type="checkbox"
                  className="form-check-input"
                  id="formIsNsfw"
                  checked={this.state.formIsNsfw}
                  onChange={linkEvent(this, (s, e: any) => s.setState({ formIsNsfw: e.target.checked }))}
                />
                <label className="form-check-label" htmlFor="formIsNsfw">
                  NSFW Content
                </label>
              </div>
              <small className="text-muted">NSFW ads only shown on NSFW pages</small>
            </div>

            <div className="mb-3">
              <div className="form-check">
                <input
                  type="checkbox"
                  className="form-check-input"
                  id="formShowOnAll"
                  checked={this.state.formShowOnAll}
                  onChange={linkEvent(this, (s, e: any) => s.setState({ formShowOnAll: e.target.checked }))}
                />
                <label className="form-check-label" htmlFor="formShowOnAll">
                  Show on all communities
                </label>
              </div>
            </div>

            {!this.state.formShowOnAll && (
              <div className="mb-3">
                <label className="form-label">Target Communities</label>
                <input
                  type="text"
                  className="form-control"
                  value={this.state.formTargetCommunities}
                  onInput={linkEvent(this, (s, e: any) => s.setState({ formTargetCommunities: e.target.value }))}
                  placeholder="technology, programming, gaming"
                />
                <small className="text-muted">Comma-separated community names</small>
              </div>
            )}

            <div className="mb-3">
              <label className="form-label">Target Regex (optional, advanced)</label>
              <input
                type="text"
                className="form-control"
                value={this.state.formTargetRegex}
                onInput={linkEvent(this, (s, e: any) => s.setState({ formTargetRegex: e.target.value }))}
                placeholder="bitcoin|crypto|blockchain"
              />
              <small className="text-muted">
                Regex pattern to match page content. Leave empty for no filtering.
              </small>
            </div>

            <button 
              type="submit" 
              className="btn btn-success"
              disabled={this.state.submitting || this.state.adCredits < this.state.formBudget}
            >
              {this.state.submitting ? <Spinner /> : `Create Campaign (−$${this.state.formBudget.toFixed(2)})`}
            </button>

            {this.state.adCredits < this.state.formBudget && (
              <div className="alert alert-warning mt-3">
                Insufficient credits. Campaign cost is ${this.state.formBudget.toFixed(2)} but you have ${this.state.adCredits.toFixed(2)}.
              </div>
            )}
          </form>
        </div>
      </div>
    );
  }

  renderMyCampaigns() {
    return (
      <div className="card mb-4">
        <div className="card-header">
          <h5 className="mb-0">My Campaigns ({this.state.campaigns.length})</h5>
        </div>
        <div className="card-body">
          {this.state.campaigns.length === 0 ? (
            <p className="text-muted mb-0">No campaigns yet. Create your first ad!</p>
          ) : (
            <div className="table-responsive">
              <table className="table table-hover">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Cost</th>
                    <th>End Date</th>
                    <th>Spent</th>
                    <th>Impressions</th>
                    <th>Clicks</th>
                    <th>CTR</th>
                  </tr>
                </thead>
                <tbody>
                  {this.state.campaigns.map(campaign => (
                    <tr key={campaign.id}>
                      <td>
                        <strong>{campaign.title}</strong>
                        {/* Image preview: prefer position-specific images (post_top/sidebar/feed), fall back to legacy image_url */}
                        <br />
                        {(
                          (campaign as any).image_post_top_url || (campaign as any).image_sidebar_url || campaign.image_url
                        ) && (
                          <img
                            src={(campaign as any).image_post_top_url || (campaign as any).image_sidebar_url || campaign.image_url}
                            alt="Ad preview"
                            style={{ maxHeight: '60px', maxWidth: '220px' }}
                            className="mt-2"
                          />
                        )}
                        {campaign.is_nsfw && <span className="badge bg-danger ms-2">NSFW</span>}
                        <br />
                        <small className="text-muted">
                          <a href={campaign.link_url} target="_blank" rel="noopener">
                            {campaign.link_url.substring(0, 40)}...
                          </a>
                        </small>
                      </td>
                      <td>
                        <span 
                          className="badge"
                          style={{ backgroundColor: statusColors[campaign.approval_status] || "#6c757d", color: "#000" }}
                        >
                          {campaign.approval_status}
                        </span>
                        {campaign.rejection_reason && (
                          <small className="d-block text-danger mt-1">
                            {campaign.rejection_reason}
                          </small>
                        )}
                      </td>
                      <td>${campaign.monthly_budget_usd.toFixed(2)}</td>
                      <td>
                        {(campaign as any).end_date 
                          ? new Date((campaign as any).end_date * 1000).toLocaleDateString()
                          : '-'}
                      </td>
                      <td>${campaign.spent_this_month_usd.toFixed(2)}</td>
                      <td>{campaign.total_impressions.toLocaleString()}</td>
                      <td>{campaign.total_clicks.toLocaleString()}</td>
                      <td>
                        {campaign.total_impressions > 0 
                          ? ((campaign.total_clicks / campaign.total_impressions) * 100).toFixed(2) + '%'
                          : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    );
  }

  renderPendingApprovals() {
    return (
      <div className="card mb-4 border-warning">
        <div className="card-header bg-warning text-dark">
          <h5 className="mb-0">
            <Icon icon="shield" classes="me-2" />
            Admin: Pending Approvals ({this.state.pendingCampaigns.length})
          </h5>
        </div>
        <div className="card-body">
          {this.state.pendingCampaigns.length === 0 ? (
            <p className="text-muted mb-0">No campaigns awaiting approval.</p>
          ) : (
            <div className="list-group">
              {this.state.pendingCampaigns.map(campaign => (
                <div key={campaign.id} className="list-group-item">
                  <div className="d-flex justify-content-between align-items-start">
                    <div className="flex-grow-1">
                      <h6 className="mb-1">
                        {campaign.title}
                        {campaign.is_nsfw && <span className="badge bg-danger ms-2">NSFW</span>}
                      </h6>
                      <p className="mb-1">
                        <a href={campaign.link_url} target="_blank" rel="noopener">
                          {campaign.link_url}
                        </a>
                      </p>
                      {/* Image previews: show all position-specific images */}
                      <div className="d-flex flex-wrap gap-2 mb-2">
                        {(campaign as any).image_post_top_url && (
                          <div className="text-center">
                            <img 
                              src={(campaign as any).image_post_top_url} 
                              alt="Post Top" 
                              style={{ maxHeight: '50px', maxWidth: '150px' }}
                            />
                            <div className="small text-muted">Top</div>
                          </div>
                        )}
                        {(campaign as any).image_sidebar_url && (
                          <div className="text-center">
                            <img 
                              src={(campaign as any).image_sidebar_url} 
                              alt="Sidebar" 
                              style={{ maxHeight: '50px', maxWidth: '100px' }}
                            />
                            <div className="small text-muted">Sidebar</div>
                          </div>
                        )}
                        {(campaign as any).image_post_bottom_url && (
                          <div className="text-center">
                            <img 
                              src={(campaign as any).image_post_bottom_url} 
                              alt="Post Bottom" 
                              style={{ maxHeight: '50px', maxWidth: '150px' }}
                            />
                            <div className="small text-muted">Bottom</div>
                          </div>
                        )}
                        {/* Legacy image_url fallback */}
                        {!((campaign as any).image_post_top_url || (campaign as any).image_sidebar_url || (campaign as any).image_post_bottom_url) && campaign.image_url && (
                          <img 
                            src={campaign.image_url} 
                            alt="Ad preview" 
                            style={{ maxHeight: '60px', maxWidth: '200px' }}
                          />
                        )}
                      </div>
                      <p className="mb-1 text-muted small">
                        Cost: ${campaign.monthly_budget_usd.toFixed(2)} |
                        Target: {campaign.target_communities || 'All'} |
                        Regex: {campaign.target_regex || 'None'}
                      </p>
                    </div>
                    <div className="btn-group">
                      <button
                        className="btn btn-sm btn-success"
                        onClick={() => this.handleApproveCampaign(campaign.id)}
                      >
                        <Icon icon="check" /> Approve
                      </button>
                      <button
                        className="btn btn-sm btn-danger"
                        onClick={() => this.handleRejectCampaign(campaign.id)}
                      >
                        <Icon icon="x" /> Reject
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  renderAdminActiveCampaigns() {
    return (
      <div className="card mb-4 border-info">
        <div className="card-header bg-info text-white">
          <h5 className="mb-0">
            <Icon icon="list" classes="me-2" />
            Admin: Active Campaigns ({this.state.adminActiveCampaigns.length})
          </h5>
        </div>
        <div className="card-body">
          {this.state.adminActiveCampaigns.length === 0 ? (
            <p className="text-muted mb-0">No active campaigns.</p>
          ) : (
            <div className="list-group">
              {this.state.adminActiveCampaigns.map(campaign => (
                <div key={campaign.id} className="list-group-item">
                  <div className="d-flex justify-content-between align-items-start">
                    <div className="flex-grow-1">
                      <h6 className="mb-1">
                        {campaign.title}
                        {campaign.is_nsfw && <span className="badge bg-danger ms-2">NSFW</span>}
                      </h6>
                      <p className="mb-1">
                        <a href={campaign.link_url} target="_blank" rel="noopener">
                          {campaign.link_url}
                        </a>
                      </p>
                      {/* image preview */}
                      {(
                        (campaign as any).image_post_top_url || (campaign as any).image_sidebar_url || campaign.image_url
                      ) && (
                        <img
                          src={(campaign as any).image_post_top_url || (campaign as any).image_sidebar_url || campaign.image_url}
                          alt="Ad preview"
                          style={{ maxHeight: '60px', maxWidth: '220px' }}
                          className="mb-2"
                        />
                      )}
                      <p className="mb-1 text-muted small">
                        Cost: ${campaign.monthly_budget_usd.toFixed(2)} |
                        End: {(campaign as any).end_date ? new Date((campaign as any).end_date * 1000).toLocaleDateString() : '-'} |
                        Impr: {campaign.total_impressions.toLocaleString()} |
                        Clicks: {campaign.total_clicks.toLocaleString()}
                      </p>
                    </div>
                    <div className="btn-group">
                      <button
                        className="btn btn-sm btn-outline-secondary"
                        onClick={() => window.open(campaign.link_url, '_blank')}
                        title="Open advertiser link"
                      >
                        <Icon icon="external-link" /> Visit Link
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ============================================================
  // Add Credits Modal & BCH Credit → Ad Credit Transfer
  // ============================================================

  renderAddCreditsModal() {
    if (!this.state.showAddCreditsModal) return null;

    const { bchBalance, bchBalanceUsd, bchPriceUsd, addCreditsAmount, addCreditsLoading, purchaseError, loadingBalances } = this.state;
    
    // Calculate required BCH for the requested USD amount
    const requiredBch = bchPriceUsd > 0 ? addCreditsAmount / bchPriceUsd : 0;
    const hasEnoughBalance = bchBalance >= requiredBch;

    return (
      <div className="modal d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,0.5)' }}>
        <div className="modal-dialog modal-dialog-centered">
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title">
                <Icon icon="dollar-sign" classes="me-2" />
                Purchase Ad Credits
              </h5>
              <button
                type="button"
                className="btn-close"
                onClick={() => this.closeAddCreditsModal()}
              />
            </div>
            <div className="modal-body">
              {loadingBalances ? (
                <div className="text-center py-4">
                  <Spinner />
                  <div className="mt-2 text-muted">Loading balances...</div>
                </div>
              ) : (
                <>
                  {/* BCH Balance Info */}
                  <div className="alert alert-info mb-3">
                    <div className="d-flex justify-content-between align-items-center">
                      <span><strong>Your BCH Balance:</strong></span>
                      <span className="badge bg-primary fs-6">
                        {bchBalance.toFixed(6)} BCH
                      </span>
                    </div>
                    <small className="text-muted">
                      ≈ ${bchBalanceUsd.toFixed(2)} USD (@ ${bchPriceUsd.toFixed(0)}/BCH)
                    </small>
                  </div>

                  {/* Amount Input */}
                  <div className="mb-3">
                    <label className="form-label fw-bold">Ad Credits Amount (USD)</label>
                    <div className="input-group">
                      <span className="input-group-text">$</span>
                      <input
                        type="number"
                        className="form-control"
                        value={addCreditsAmount}
                        min={1}
                        max={1000}
                        step={1}
                        onChange={(e: any) => this.setState({ 
                          addCreditsAmount: parseFloat(e.target.value) || 1,
                          purchaseError: null 
                        })}
                      />
                    </div>
                    <small className="text-muted">
                      Requires: <strong>{requiredBch.toFixed(6)} BCH</strong>
                    </small>
                  </div>

                  {/* Quick Amount Buttons */}
                  <div className="mb-3">
                    <div className="btn-group w-100" role="group">
                      {[0.1, 10, 25, 50, 100].map(amt => (
                        <button
                          key={amt}
                          type="button"
                          className={`btn btn-outline-secondary ${addCreditsAmount === amt ? 'active' : ''}`}
                          onClick={() => this.setState({ addCreditsAmount: amt, purchaseError: null })}
                        >
                          ${amt}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Balance Warning */}
                  {!hasEnoughBalance && (
                    <div className="alert alert-warning mb-3">
                      <Icon icon="alert-triangle" classes="me-2" />
                      Insufficient BCH balance. You need {requiredBch.toFixed(6)} BCH but have {bchBalance.toFixed(6)} BCH.
                      <br />
                      <small>Please deposit more BCH to your account first.</small>
                    </div>
                  )}

                  {/* Error Message */}
                  {purchaseError && (
                    <div className="alert alert-danger mb-3">
                      {purchaseError}
                    </div>
                  )}

                  {/* Purchase Button */}
                  <button
                    className="btn btn-success w-100"
                    disabled={addCreditsLoading || !hasEnoughBalance || addCreditsAmount <= 0}
                    onClick={() => this.purchaseAdCredits()}
                  >
                    {addCreditsLoading ? (
                      <Spinner />
                    ) : (
                      <>
                        <Icon icon="shopping-cart" classes="me-2" />
                        Purchase ${addCreditsAmount.toFixed(2)} Ad Credits
                      </>
                    )}
                  </button>

                  <div className="mt-3 text-center">
                    <small className="text-muted">
                      BCH will be deducted from your account balance instantly.
                    </small>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  async openAddCreditsModal() {
    this.setState({ 
      showAddCreditsModal: true, 
      loadingBalances: true,
      purchaseError: null,
      addCreditsAmount: 10,
    });
    
    // Fetch user's BCH balance
    const baseUrl = getAdsAPIBaseUrl();
    const apiKey = getApiKey();

    try {
      const response = await fetch(`${baseUrl}/credits/balance/${this.username}`, {
        headers: { 'X-API-Key': apiKey || '' },
      });
      const data = await response.json();
      
      if (data.success) {
        this.setState({
          bchBalance: data.bch_balance || 0,
          bchBalanceUsd: data.bch_balance_usd || 0,
          bchPriceUsd: data.bch_price_usd || 480,
          loadingBalances: false,
        });
      } else {
        this.setState({
          loadingBalances: false,
          purchaseError: data.error || 'Failed to load balance',
        });
      }
    } catch (e) {
      console.error('openAddCreditsModal error', e);
      this.setState({
        loadingBalances: false,
        purchaseError: 'Failed to load balance',
      });
    }
  }

  closeAddCreditsModal() {
    this.setState({
      showAddCreditsModal: false,
      addCreditsLoading: false,
      purchaseError: null,
    });
  }

  async purchaseAdCredits() {
    this.setState({ addCreditsLoading: true, purchaseError: null });
    const baseUrl = getAdsAPIBaseUrl();
    const apiKey = getApiKey();

    try {
      const response = await fetch(`${baseUrl}/credits/purchase`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': apiKey || '',
        },
        body: JSON.stringify({
          username: this.username,
          usd_amount: this.state.addCreditsAmount,
        }),
      });

      const data = await response.json();
      
      if (data.success) {
        toast(`Successfully purchased $${data.usd_added.toFixed(2)} ad credits!`, 'success');
        this.closeAddCreditsModal();
        await this.fetchAdsData();
      } else {
        this.setState({ 
          purchaseError: data.error || 'Purchase failed',
          addCreditsLoading: false,
        });
      }
    } catch (e) {
      console.error('purchaseAdCredits error', e);
      this.setState({ 
        purchaseError: 'Purchase failed. Please try again.',
        addCreditsLoading: false,
      });
    }
  }
}
