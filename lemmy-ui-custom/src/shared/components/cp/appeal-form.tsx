import { Component } from "inferno";
import { submitCPAppeal, checkUserCPPermissions, CPPermissions } from "../../utils/cp-moderation";
import { checkUserHasGoldBadgeSync } from "../../utils/bch-payment";
import { UserService } from "../../services";
import { Icon, Spinner } from "../common/icon";
import { toast } from "../../toast";

interface AppealFormProps {
  onSuccess?: () => void;
}

interface AppealFormState {
  appealText: string;
  submitting: boolean;
  submitted: boolean;
  loading: boolean;
  permissions: CPPermissions | null;
  // For unauthenticated appeals
  anonUsername?: string;
  anonIsMember?: boolean;
  // User's reported posts
  userReports?: Array<{
    report_id: string;
    content_type: string;
    content_id: number;
    post_title?: string;
    post_url?: string;
    created_at: number;
    reason?: string;
  }>;
  loadingReports?: boolean;
  // Membership verification
  membershipChecked?: boolean;
  membershipActive?: boolean;
  loadingMembership?: boolean;
}

export class AppealForm extends Component<AppealFormProps, AppealFormState> {
  state: AppealFormState = {
    appealText: '',
    submitting: false,
    submitted: false,
    loading: true,
    permissions: null
  };

  async componentDidMount() {
    const user = UserService.Instance.myUserInfo;
    if (!user) {
      // Allow unauthenticated users to view the appeal form (they can submit by providing username/person_id)
      this.setState({ loading: false });
      return;
    }

    const permissions = await checkUserCPPermissions(user.local_user_view.person.name);
    this.setState({ permissions, loading: false });
    
    // Auto-load user reports if logged in
    if (user) {
      await this.loadUserReports(user.local_user_view.person.name);
    }
  }

  async loadUserReports(username: string) {
    if (!username || username.trim().length === 0) {
      this.setState({ userReports: [], loadingReports: false });
      return;
    }

    this.setState({ loadingReports: true });
    
    try {
      const response = await fetch(`/api/cp/user-reports/${username}`);
      if (response.ok) {
        const data = await response.json();
        this.setState({ userReports: data.reports || [], loadingReports: false });
      } else {
        this.setState({ userReports: [], loadingReports: false });
      }
    } catch (error) {
      console.error('Failed to load user reports:', error);
      this.setState({ userReports: [], loadingReports: false });
    }
  }

  async checkMembershipStatus(username: string) {
    if (!username || username.trim().length === 0) {
      this.setState({ 
        membershipChecked: false, 
        membershipActive: false, 
        loadingMembership: false,
        anonIsMember: false 
      });
      return;
    }

    this.setState({ loadingMembership: true });
    
    try {
      const response = await fetch(`/api/membership/check/${username}`);
      if (response.ok) {
        const data = await response.json();
        const isActive = data.is_active || false;
        this.setState({ 
          membershipChecked: true, 
          membershipActive: isActive,
          loadingMembership: false,
          anonIsMember: isActive  // Auto-check if member
        });
        
        if (isActive) {
          toast("✅ Membership verified! You can submit an appeal.", "success");
        } else {
          toast("⚠️ No active membership found. Only members can appeal.", "warning");
        }
      } else {
        this.setState({ 
          membershipChecked: true, 
          membershipActive: false, 
          loadingMembership: false,
          anonIsMember: false 
        });
        toast("⚠️ Could not verify membership. Only members can appeal.", "warning");
      }
    } catch (error) {
      console.error('Failed to check membership:', error);
      this.setState({ 
        membershipChecked: true, 
        membershipActive: false, 
        loadingMembership: false,
        anonIsMember: false 
      });
    }
  }

  handleUsernameChange(username: string) {
    this.setState({ anonUsername: username });
    
    // Debounce the report loading and membership check
    if ((this as any).usernameTimeout) {
      clearTimeout((this as any).usernameTimeout);
    }
    
    (this as any).usernameTimeout = setTimeout(() => {
      if (username && username.trim().length > 0) {
        this.loadUserReports(username);
        this.checkMembershipStatus(username);
      }
    }, 500);
  }

  async handleSubmit(e: Event) {
    e.preventDefault();
    
    const user = UserService.Instance.myUserInfo;
    const { appealText, anonUsername, anonPersonId, anonIsMember } = this.state as any;

    // Determine submission payload for logged-in vs anonymous
    let payload: any = null;

    if (user) {
      // Logged-in flow
      const hasGoldBadge = checkUserHasGoldBadgeSync(user);
      if (!hasGoldBadge) {
        toast("Only membership users can submit appeals. Please verify your membership status.", "danger");
        return;
      }

      if (!appealText.trim()) {
        toast("Please provide a reason for your appeal", "warning");
        return;
      }

      if (appealText.length > 2000) {
        toast("Appeal text must be under 2000 characters", "warning");
        return;
      }

      payload = {
        username: user.local_user_view.person.name,
        person_id: user.local_user_view.person.id,
        is_member: hasGoldBadge,
        appeal_type: 'ban',
        appeal_reason: appealText.trim()
      };
    } else {
      // Unauthenticated flow: require username and membership confirmation only
      if (!anonUsername || !anonIsMember) {
        toast("Please provide your username and confirm membership status.", "warning");
        return;
      }

      if (!appealText.trim()) {
        toast("Please provide a reason for your appeal", "warning");
        return;
      }

      if (appealText.length > 2000) {
        toast("Appeal text must be under 2000 characters", "warning");
        return;
      }

      payload = {
        username: anonUsername,
        is_member: !!anonIsMember,
        appeal_type: 'ban',
        appeal_reason: appealText.trim()
      };
    }

    this.setState({ submitting: true });

    const result = await submitCPAppeal(payload as any);

    this.setState({ submitting: false });

    if (result.success) {
      toast("✅ Appeal submitted successfully. An admin will review it.", "success");
      this.setState({ submitted: true, appealText: '' });
      if (this.props.onSuccess) {
        this.props.onSuccess();
      }
    } else {
      // Display detailed error message from backend (e.g., window expired, already appealed, etc.)
      const errorMsg = result.message || "Failed to submit appeal. Please try again.";
      
      // Show toast with detailed error (toast accepts only 2 args in this codebase)
      if (errorMsg.includes("7 days") || errorMsg.includes("expired") || errorMsg.includes("window")) {
        toast(`⏰ ${errorMsg}`, "danger");
      } else {
        toast(`❌ ${errorMsg}`, "danger");
      }
    }
  }

  render() {
    const user = UserService.Instance.myUserInfo;
    const { appealText, submitting, submitted, loading, permissions } = this.state;

    if (loading) {
      return (
        <div className="text-center p-5">
          <Spinner large />
        </div>
      );
    }

    // Allow unauthenticated appeals: show either logged-in view or anonymous form
    if (!user) {
      // Anonymous appeal form
      const { appealText, submitting, submitted, anonUsername, anonIsMember } = this.state as any;

      return (
        <div className="card">
          <div className="card-header bg-danger text-white">
            <h4 className="mb-0">
              <Icon icon="alert-triangle" classes="me-2" />
              Submit CP Ban Appeal (Not logged in)
            </h4>
          </div>
          <div className="card-body">
            <div className="alert alert-warning">
              <Icon icon="info" classes="me-2" />
              You are not logged in. If you are a membership user but cannot log in due to a ban, you may submit an appeal here by providing your username. The server will validate your membership and ban status.
            </div>

            {submitted ? (
              <div className="alert alert-success">
                <Icon icon="check-circle" classes="me-2" />
                <strong>Appeal Submitted</strong>
                <p className="mb-0 mt-2">Your appeal has been submitted and is pending admin review.</p>
              </div>
            ) : (
              <form onSubmit={(e: any) => this.handleSubmit(e)}>
                <div className="mb-3">
                  <label className="form-label"><strong>Username</strong></label>
                  <input 
                    className="form-control" 
                    placeholder="Enter your username"
                    value={anonUsername || ''} 
                    onInput={(e: any) => this.handleUsernameChange(e.target.value)} 
                  />
                  {this.state.loadingReports && (
                    <div className="form-text">
                      <Spinner /> Loading your reported posts...
                    </div>
                  )}
                </div>

                {this.state.userReports && this.state.userReports.length > 0 && (
                  <div className="alert alert-warning mb-3">
                    <strong>⚠️ Your Reported Posts:</strong>
                    <ul className="mt-2 mb-0">
                      {this.state.userReports.map((report, idx) => (
                        <li key={report.report_id}>
                          <strong>{report.post_title || `Post #${report.content_id}`}</strong>
                          <br />
                          <small className="text-muted">
                            Reported on: {new Date(report.created_at * 1000).toLocaleDateString()}
                            {report.reason && ` | Reason: ${report.reason}`}
                          </small>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {this.state.loadingMembership && (
                  <div className="alert alert-info mb-3">
                    <Spinner /> Verifying membership status...
                  </div>
                )}

                {this.state.membershipChecked && !this.state.membershipActive && (
                  <div className="alert alert-danger mb-3">
                    <Icon icon="x-circle" classes="me-2" />
                    <strong>No Active Membership</strong>
                    <p className="mb-0 mt-2">
                      Only users with active Gold Badge membership can submit appeals. 
                      Please purchase a membership first.
                    </p>
                  </div>
                )}

                {this.state.membershipChecked && this.state.membershipActive && (
                  <div className="alert alert-success mb-3">
                    <Icon icon="check-circle" classes="me-2" />
                    <strong>✅ Membership Verified</strong>
                    <p className="mb-0 mt-2">
                      You have an active Gold Badge membership. You can proceed with your appeal.
                    </p>
                  </div>
                )}
                <div className="mb-3">
                  <label className="form-label"><strong>Appeal Reason</strong></label>
                  <textarea 
                    className="form-control" 
                    rows={6} 
                    placeholder="Explain why you believe your ban should be reconsidered..."
                    value={appealText || ''} 
                    onInput={(e: any) => this.setState({ appealText: e.target.value })} 
                    maxLength={2000} 
                  />
                  <div className="form-text">{(appealText || '').length} / 2000 characters</div>
                </div>

                <div className="d-grid">
                  <button 
                    type="submit" 
                    className="btn btn-primary btn-lg" 
                    disabled={submitting || !anonUsername || !this.state.membershipActive || this.state.loadingMembership}
                  >
                    {submitting ? (
                      <><Spinner /> Submitting...</>
                    ) : !this.state.membershipActive && this.state.membershipChecked ? (
                      <><Icon icon="lock" classes="me-2" />Membership Required</>
                    ) : (
                      <><Icon icon="send" classes="me-2" />Submit Appeal</>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      );
    }

    if (!permissions) {
      return (
        <div className="alert alert-danger">
          <Icon icon="alert-triangle" classes="me-2" />
          Failed to load your CP status.
        </div>
      );
    }

    if (!permissions.is_banned) {
      return (
        <div className="alert alert-info">
          <Icon icon="info" classes="me-2" />
          You are not currently banned. Appeals are only available for banned users.
        </div>
      );
    }

    const hasGoldBadge = checkUserHasGoldBadgeSync(user);

    return (
      <div className="card">
        <div className="card-header bg-danger text-white">
          <h4 className="mb-0">
            <Icon icon="alert-triangle" classes="me-2" />
            Submit CP Ban Appeal
          </h4>
        </div>
        <div className="card-body">
          {!hasGoldBadge && (
            <div className="alert alert-warning">
              <Icon icon="lock" classes="me-2" />
              <strong>Membership Required:</strong> Only membership users (Gold Badge holders) can submit appeals.
              Please renew or purchase membership to appeal this ban.
            </div>
          )}

          {permissions.ban_end && (
            <div className="alert alert-info">
              <Icon icon="clock" classes="me-2" />
              <strong>Current Ban:</strong> Your ban expires on {new Date(permissions.ban_end * 1000).toLocaleString()}
            </div>
          )}

          {submitted ? (
            <div className="alert alert-success">
              <Icon icon="check-circle" classes="me-2" />
              <strong>Appeal Submitted</strong>
              <p className="mb-0 mt-2">
                Your appeal has been submitted and is pending admin review. 
                You will be notified of the decision. Only one active appeal is allowed at a time.
              </p>
            </div>
          ) : (
            <form onSubmit={(e: any) => this.handleSubmit(e)}>
              <div className="mb-3">
                <label className="form-label">
                  <strong>Why should your ban be lifted?</strong>
                </label>
                <textarea
                  className="form-control"
                  rows={8}
                  placeholder="Explain why you believe your ban was incorrect or should be reconsidered. Be honest and specific. False or abusive appeals may result in permanent restrictions."
                  value={appealText}
                  onChange={(e: any) => this.setState({ appealText: e.target.value })}
                  disabled={submitting || !hasGoldBadge}
                  maxLength={2000}
                />
                <div className="form-text">
                  {appealText.length} / 2000 characters
                </div>
              </div>

              <div className="alert alert-warning small">
                <Icon icon="info" classes="me-2" />
                <strong>Appeal Guidelines:</strong>
                <ul className="mb-0 mt-2">
                  <li>Appeals are reviewed by admins only</li>
                  <li>You can only have one active appeal at a time</li>
                  <li>Be honest and specific about your situation</li>
                  <li>Abusive or false appeals may lead to permanent restrictions</li>
                  <li>Review decisions are final</li>
                </ul>
              </div>

              <div className="d-grid">
                <button
                  type="submit"
                  className="btn btn-primary btn-lg"
                  disabled={submitting || !hasGoldBadge || !appealText.trim()}
                >
                  {submitting ? (
                    <>
                      <Spinner /> Submitting...
                    </>
                  ) : (
                    <>
                      <Icon icon="send" classes="me-2" />
                      Submit Appeal
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    );
  }
}
