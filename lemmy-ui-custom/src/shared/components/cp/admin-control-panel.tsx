import { Component } from "inferno";
import { UserService } from "../../services";
import { 
  getPendingReports, 
  reviewCPReport, 
  adminBanUser,
  adminRevokeReportAbility,
  adminRestoreUser,
  checkUserCPPermissions,
  CPReport,
  CPPermissions
} from "../../utils/cp-moderation";
import { getApiKey, invalidateReferralBadgeCache } from "../../utils/bch-payment";
import { Spinner, Icon } from "../common/icon";
import { toast } from "../../toast";

interface ReportedContent {
  content_type: 'post' | 'comment';
  content_id: number;
  reason?: string;
  created_at: number;
}

interface CPAppeal {
  id: string;
  user_id: string;
  person_id: number;
  username: string;
  appeal_type: string;
  appeal_reason: string;
  status: string;
  created_at: number;
  reviewed_by_username?: string;
  reviewed_at?: number;
  admin_decision?: string;
  admin_notes?: string;
  reported_content?: ReportedContent[];
}

interface ReferralLink {
  link_id: string;
  url: string;
  domain: string;
  submitted_by: string;
  status: 'pending' | 'approved' | 'rejected';
  verified: boolean;
  submitted_at: number;
  reject_reason: string | null;
}

interface AdminControlPanelState {
  activeTab: 'reports' | 'users' | 'appeals' | 'referrals';
  reports: CPReport[];
  appeals: CPAppeal[];
  referralLinks: ReferralLink[];
  referralFilter: 'pending' | 'approved' | 'rejected' | 'all';
  referralTotal: number;
  loadingReferrals: boolean;
  rejectingLinkId: string | null;
  rejectReason: string;
  verifyingLinkId: string | null;
  loading: boolean;
  loadingAppeals: boolean;
  userSearchQuery: string;
  searchedUserPermissions: CPPermissions | null;
  actionInProgress: boolean;
}

export class AdminControlPanel extends Component<{}, AdminControlPanelState> {
  state: AdminControlPanelState = {
    activeTab: 'reports',
    reports: [],
    appeals: [],
    referralLinks: [],
    referralFilter: 'pending',
    referralTotal: 0,
    loadingReferrals: false,
    rejectingLinkId: null,
    rejectReason: '',
    verifyingLinkId: null,
    loading: false,
    loadingAppeals: false,
    userSearchQuery: '',
    searchedUserPermissions: null,
    actionInProgress: false
  };

  async componentDidMount() {
    // Check if user is logged in and is admin
    const user = UserService.Instance.myUserInfo;
    if (!user) {
      toast("You must be logged in as an admin to access this page", "danger");
      window.location.href = "/login";
      return;
    }

    // Check if user is admin (admin property is in local_user, not person)
    const isAdmin = user.local_user_view.local_user.admin;
    if (!isAdmin) {
      toast("Access denied: Admin privileges required", "danger");
      window.location.href = "/";
      return;
    }

    await this.loadReports();
    // Also pre-load appeals so we can show a count preview in the tabs
    // (non-blocking - don't await to avoid delaying page render)
    this.loadAppeals();
    this.loadReferrals();
  }

  async loadReports() {
    this.setState({ loading: true });
    const reports = await getPendingReports(undefined, 'admin');
    this.setState({ reports, loading: false });
  }

  async loadAppeals() {
    this.setState({ loadingAppeals: true });
    try {
      const response = await fetch('/api/cp/appeals/pending', {
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey()
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        this.setState({ appeals: data.appeals || [], loadingAppeals: false });
      } else {
        toast("Failed to load appeals", "danger");
        this.setState({ appeals: [], loadingAppeals: false });
      }
    } catch (error) {
      console.error('Failed to load appeals:', error);
      toast("Error loading appeals", "danger");
      this.setState({ appeals: [], loadingAppeals: false });
    }
  }

  async handleReviewReport(reportId: string, decision: 'admin_approved' | 'admin_rejected') {
    const user = UserService.Instance.myUserInfo;
    if (!user) return;

    this.setState({ actionInProgress: true });

    const result = await reviewCPReport(
      reportId,
      user.local_user_view.person.id,
      user.local_user_view.person.name,
      'admin',
      decision
    );

    this.setState({ actionInProgress: false });

    if (result.success) {
      toast("Report reviewed successfully", "success");
      await this.loadReports();
    } else {
      toast(result.message || "Failed to review report", "danger");
    }
  }

  async handleSearchUser() {
    const { userSearchQuery } = this.state;
    if (!userSearchQuery.trim()) {
      toast("Please enter a username", "warning");
      return;
    }

    this.setState({ loading: true });
    const permissions = await checkUserCPPermissions(userSearchQuery.trim());
    
    if (!permissions) {
      toast("User not found or error checking permissions", "danger");
      this.setState({ loading: false, searchedUserPermissions: null });
      return;
    }

    this.setState({ 
      searchedUserPermissions: permissions,
      loading: false 
    });
  }

  async handleUserAction(
    action: 'ban' | 'revoke_report' | 'restore_ban' | 'restore_report'
  ) {
    const user = UserService.Instance.myUserInfo;
    const { searchedUserPermissions } = this.state;
    if (!user || !searchedUserPermissions) return;

    this.setState({ actionInProgress: true });

    let result;
    switch (action) {
      case 'ban':
        result = await adminBanUser(
          searchedUserPermissions.username,
          user.local_user_view.person.id,
          user.local_user_view.person.name,
          "Manual admin ban"
        );
        break;
      case 'revoke_report':
        result = await adminRevokeReportAbility(
          searchedUserPermissions.username,
          user.local_user_view.person.id,
          user.local_user_view.person.name,
          "Manual admin revoke"
        );
        break;
      case 'restore_ban':
        result = await adminRestoreUser(
          searchedUserPermissions.username,
          user.local_user_view.person.id,
          user.local_user_view.person.name,
          true,
          false,
          "Manual admin unban"
        );
        break;
      case 'restore_report':
        result = await adminRestoreUser(
          searchedUserPermissions.username,
          user.local_user_view.person.id,
          user.local_user_view.person.name,
          false,
          true,
          "Manual admin restore report ability"
        );
        break;
    }

    this.setState({ actionInProgress: false });

    if (result?.success) {
      if (result.warning) {
        toast(`⚠️ ${result.warning}`, "warning");
      } else {
        toast(result.message || "Action completed successfully", "success");
      }
      await this.handleSearchUser(); // Refresh user data
    } else {
      toast(result?.message || "Action failed", "danger");
    }
  }

  renderReportsTab() {
    const { reports, loading, actionInProgress } = this.state;

    if (loading) {
      return (
        <div className="text-center p-5">
          <Spinner large />
        </div>
      );
    }

    if (reports.length === 0) {
      return (
        <div className="alert alert-info">
          <Icon icon="info" classes="me-2" />
          No pending admin-level reports
        </div>
      );
    }

    return (
      <div className="list-group">
        {reports.map(report => (
          <div key={report.id} className="list-group-item mb-3">
            <h5 className="mb-3">
              <span className="badge bg-warning text-dark me-2">Admin Review</span>
              <span className="badge bg-secondary me-2">
                {report.content_type === 'post' ? 'Post' : 'Comment'} #{report.content_id}
              </span>
              <a 
                href={report.content_type === 'post' ? `/post/${report.content_id}` : `/comment/${report.content_id}`}
                className="btn btn-sm btn-outline-primary ms-2"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Icon icon="external-link" classes="me-1" />
                View Content
              </a>
            </h5>
            
            <dl className="row mb-3">
              <dt className="col-sm-3">Reporter:</dt>
              <dd className="col-sm-9">{report.reporter_username}</dd>
              
              <dt className="col-sm-3">Creator:</dt>
              <dd className="col-sm-9"><strong className="text-danger">{report.creator_username}</strong></dd>
              
              <dt className="col-sm-3">Reason:</dt>
              <dd className="col-sm-9">{report.reason || <em>None provided</em>}</dd>
              
              <dt className="col-sm-3">Escalated:</dt>
              <dd className="col-sm-9">{new Date(report.created_at * 1000).toLocaleString()}</dd>
            </dl>
            
            <div className="alert alert-warning small mb-3">
              <Icon icon="alert-triangle" classes="me-2" />
              This case requires admin review. The content has been removed (hidden) from public view 
              but is still accessible to admins. You have <strong>7 days</strong> from escalation to review 
              before it is auto-purged. Choose "Approve (Not CP)" to restore the content, or "Reject (Confirm CP)" to permanently delete it.
            </div>
            
            <div className="btn-group">
              <button
                className="btn btn-success"
                onClick={() => this.handleReviewReport(report.id, 'admin_approved')}
                disabled={actionInProgress}
              >
                <Icon icon="check" classes="me-1" /> Approve (Not CP)
              </button>
              <button
                className="btn btn-danger"
                onClick={() => this.handleReviewReport(report.id, 'admin_rejected')}
                disabled={actionInProgress}
              >
                <Icon icon="x" classes="me-1" /> Reject (Confirm CP)
              </button>
            </div>
          </div>
        ))}
      </div>
    );
  }

  renderUsersTab() {
    const { userSearchQuery, searchedUserPermissions, loading, actionInProgress } = this.state;

    return (
      <div>
        <div className="card mb-4">
          <div className="card-body">
            <h5 className="card-title">Search User</h5>
            <div className="input-group">
              <input
                type="text"
                className="form-control"
                placeholder="Enter username..."
                value={userSearchQuery}
                onInput={(e: any) => this.setState({ userSearchQuery: e.target.value })}
                onKeyPress={(e: any) => e.key === 'Enter' && this.handleSearchUser()}
              />
              <button
                className="btn btn-primary"
                onClick={() => this.handleSearchUser()}
                disabled={loading}
              >
                {loading ? <Spinner /> : <><Icon icon="search" classes="me-1" /> Search</>}
              </button>
            </div>
          </div>
        </div>

        {searchedUserPermissions && (
          <div className="card">
            <div className="card-header bg-primary text-white">
              <h5 className="mb-0">
                <Icon icon="user" classes="me-2" />
                {searchedUserPermissions.username}
              </h5>
            </div>
            <div className="card-body">
              <dl className="row mb-4">
                <dt className="col-sm-4">Can Report CP:</dt>
                <dd className="col-sm-8">
                  <span className={`badge ${searchedUserPermissions.can_report_cp ? 'bg-success' : 'bg-danger'}`}>
                    {searchedUserPermissions.can_report_cp ? 'Yes' : 'No (Revoked)'}
                  </span>
                </dd>

                <dt className="col-sm-4">Is Banned:</dt>
                <dd className="col-sm-8">
                  <span className={`badge ${searchedUserPermissions.is_banned ? 'bg-danger' : 'bg-success'}`}>
                    {searchedUserPermissions.is_banned ? 'Yes' : 'No'}
                  </span>
                  {searchedUserPermissions.is_banned && searchedUserPermissions.ban_end && (
                    <div className="text-muted small mt-1">
                      <Icon icon="clock" classes="me-1" />
                      Until: {new Date(searchedUserPermissions.ban_end * 1000).toLocaleString()}
                    </div>
                  )}
                </dd>

                <dt className="col-sm-4">Ban Count:</dt>
                <dd className="col-sm-8">
                  <span className="badge bg-secondary">{searchedUserPermissions.ban_count}</span>
                </dd>

                <dt className="col-sm-4">CP Review Permission:</dt>
                <dd className="col-sm-8">
                  <span className={`badge ${searchedUserPermissions.has_cp_review_permission ? 'bg-success' : 'bg-secondary'}`}>
                    {searchedUserPermissions.has_cp_review_permission ? 'Yes (Can review as moderator)' : 'No'}
                  </span>
                </dd>
              </dl>

              <h6 className="mb-3">Admin Actions</h6>
              <div className="d-grid gap-2">
                {!searchedUserPermissions.is_banned ? (
                  <button
                    className="btn btn-danger"
                    onClick={() => this.handleUserAction('ban')}
                    disabled={actionInProgress}
                  >
                    {actionInProgress ? <Spinner /> : <><Icon icon="ban" classes="me-2" /> Ban User (3 months)</>}
                  </button>
                ) : (
                  <button
                    className="btn btn-success"
                    onClick={() => this.handleUserAction('restore_ban')}
                    disabled={actionInProgress}
                  >
                    {actionInProgress ? <Spinner /> : <><Icon icon="user-check" classes="me-2" /> Unban User</>}
                  </button>
                )}

                {searchedUserPermissions.can_report_cp ? (
                  <button
                    className="btn btn-warning"
                    onClick={() => this.handleUserAction('revoke_report')}
                    disabled={actionInProgress}
                  >
                    {actionInProgress ? <Spinner /> : <><Icon icon="user-x" classes="me-2" /> Revoke Report Ability</>}
                  </button>
                ) : (
                  <button
                    className="btn btn-info"
                    onClick={() => this.handleUserAction('restore_report')}
                    disabled={actionInProgress}
                  >
                    {actionInProgress ? <Spinner /> : <><Icon icon="user-plus" classes="me-2" /> Restore Report Ability</>}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  renderAppealsTab() {
    const { appeals, loadingAppeals, actionInProgress } = this.state;

    if (loadingAppeals) {
      return (
        <div className="text-center p-5">
          <Spinner large />
        </div>
      );
    }

    if (appeals.length === 0) {
      return (
        <div className="alert alert-info">
          <Icon icon="info" classes="me-2" />
          No pending appeals at this time.
        </div>
      );
    }

    return (
      <div>
        <h5 className="mb-3">Pending Appeals ({appeals.length})</h5>
        {appeals.map(appeal => (
          <div key={appeal.id} className="card mb-3">
            <div className="card-header bg-warning text-dark">
              <strong>Appeal from {appeal.username}</strong>
              <span className="badge bg-secondary ms-2">{appeal.appeal_type}</span>
              <small className="float-end">
                {new Date(appeal.created_at * 1000).toLocaleString()}
              </small>
            </div>
            <div className="card-body">
              <p className="card-text"><strong>Reason:</strong></p>
              <p className="card-text bg-light p-3 rounded">{appeal.appeal_reason}</p>
              
              {appeal.reported_content && appeal.reported_content.length > 0 && (
                <div className="mt-3 mb-3">
                  <p className="card-text"><strong>Reported Content:</strong></p>
                  <ul className="list-group">
                    {appeal.reported_content.map((content, idx) => (
                      <li key={idx} className="list-group-item d-flex justify-content-between align-items-center">
                        <span>
                          <span className="badge bg-secondary me-2">
                            {content.content_type === 'post' ? 'Post' : 'Comment'} #{content.content_id}
                          </span>
                          {content.reason && <small className="text-muted">{content.reason}</small>}
                        </span>
                        <a 
                          href={content.content_type === 'post' ? `/post/${content.content_id}` : `/comment/${content.content_id}`}
                          className="btn btn-sm btn-outline-primary"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <Icon icon="external-link" classes="me-1" />
                          View
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              
              <div className="mt-3">
                <button
                  className="btn btn-success me-2"
                  onClick={() => this.handleReviewAppeal(appeal.id, 'approved')}
                  disabled={actionInProgress}
                >
                  {actionInProgress ? <Spinner /> : <><Icon icon="check" classes="me-1" /> Approve & Restore</>}
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => this.handleReviewAppeal(appeal.id, 'rejected')}
                  disabled={actionInProgress}
                >
                  {actionInProgress ? <Spinner /> : <><Icon icon="x" classes="me-1" /> Reject</>}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  async handleReviewAppeal(appealId: string, decision: 'approved' | 'rejected') {
    const user = UserService.Instance.myUserInfo;
    if (!user) return;

    this.setState({ actionInProgress: true });

    try {
      const response = await fetch(`/api/cp/appeals/${appealId}/review`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey()
        },
        body: JSON.stringify({
          reviewer_person_id: user.local_user_view.person.id,
          reviewer_username: user.local_user_view.person.name,
          decision: decision,
          admin_notes: `Reviewed by ${user.local_user_view.person.name}`
        })
      });

      if (response.ok) {
        toast(`Appeal ${decision} successfully`, "success");
        await this.loadAppeals();
      } else {
        const error = await response.json();
        toast(error.error || `Failed to ${decision} appeal`, "danger");
      }
    } catch (error) {
      console.error('Failed to review appeal:', error);
      toast("Error reviewing appeal", "danger");
    }

    this.setState({ actionInProgress: false });
  }

  // ==================== Referral Methods ====================

  async loadReferrals() {
    this.setState({ loadingReferrals: true });
    try {
      const filter = this.state.referralFilter === 'all' ? '' : `?status=${this.state.referralFilter}`;
      const response = await fetch(`/payments/api/referral/list${filter}`, {
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey()
        }
      });

      if (response.ok) {
        const data = await response.json();
        this.setState({
          referralLinks: data.links || [],
          referralTotal: data.total || 0,
          loadingReferrals: false
        });
      } else {
        toast("Failed to load referral links", "danger");
        this.setState({ referralLinks: [], loadingReferrals: false });
      }
    } catch (error) {
      console.error('Failed to load referrals:', error);
      toast("Error loading referrals", "danger");
      this.setState({ referralLinks: [], loadingReferrals: false });
    }
  }

  async handleApproveReferral(linkId: string) {
    this.setState({ actionInProgress: true });
    try {
      const response = await fetch(`/payments/api/referral/approve/${linkId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey()
        }
      });

      if (response.ok) {
        toast("Referral approved ✅", "success");
        await this.loadReferrals();
      } else {
        const error = await response.json();
        toast(error.error || "Failed to approve referral", "danger");
      }
    } catch (error) {
      console.error('Failed to approve referral:', error);
      toast("Error approving referral", "danger");
    }
    this.setState({ actionInProgress: false });
  }

  async handleRejectReferral(linkId: string) {
    const reason = this.state.rejectReason.trim();
    this.setState({ actionInProgress: true });
    try {
      const response = await fetch(`/payments/api/referral/reject/${linkId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey()
        },
        body: JSON.stringify({ reason })
      });

      if (response.ok) {
        // Invalidate the submitter's referral badge cache so badge disappears immediately
        const rejectedLink = this.state.referralLinks.find(l => l.link_id === linkId);
        if (rejectedLink) {
          invalidateReferralBadgeCache(rejectedLink.submitted_by);
        }
        toast("Referral rejected", "success");
        this.setState({ rejectingLinkId: null, rejectReason: '' });
        await this.loadReferrals();
      } else {
        const error = await response.json();
        toast(error.error || "Failed to reject referral", "danger");
      }
    } catch (error) {
      console.error('Failed to reject referral:', error);
      toast("Error rejecting referral", "danger");
    }
    this.setState({ actionInProgress: false });
  }

  async handleVerifyReferral(linkId: string) {
    this.setState({ actionInProgress: true, verifyingLinkId: linkId });
    try {
      const response = await fetch(`/payments/api/referral/verify/${linkId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey()
        }
      });

      const data = await response.json();

      if (response.ok && data.success) {
        if (data.auto_approved) {
          toast("✅ Backlink found — auto-approved + membership granted!", "success");
        } else {
          toast("⚠️ Backlink NOT found — still pending", "warning");
        }
        await this.loadReferrals();
      } else {
        toast(data.error || "Verification failed", "danger");
      }
    } catch (error) {
      console.error('Failed to verify referral:', error);
      toast("Error verifying referral", "danger");
    }
    this.setState({ actionInProgress: false, verifyingLinkId: null });
  }

  renderReferralsTab() {
    const { referralLinks, loadingReferrals, referralFilter, referralTotal, actionInProgress, rejectingLinkId, rejectReason, verifyingLinkId } = this.state;

    return (
      <div>
        {/* Filter buttons */}
        <div className="btn-group mb-3">
          {(['pending', 'approved', 'rejected', 'all'] as const).map(f => (
            <button
              key={f}
              className={`btn btn-sm ${referralFilter === f ? 'btn-primary' : 'btn-outline-primary'}`}
              onClick={() => this.setState({ referralFilter: f }, () => this.loadReferrals())}
            >
              {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        <p className="text-muted small mb-3">
          Total: {referralTotal} link(s) — Showing: {referralLinks.length}
        </p>

        {loadingReferrals ? (
          <div className="text-center p-5">
            <Spinner large />
          </div>
        ) : referralLinks.length === 0 ? (
          <div className="alert alert-info">
            <Icon icon="info" classes="me-2" />
            No {referralFilter === 'all' ? '' : referralFilter + ' '}referral links found.
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table table-striped table-hover">
              <thead className="table-dark">
                <tr>
                  <th>Submitted By</th>
                  <th>URL</th>
                  <th>Domain</th>
                  <th>Status</th>
                  <th>Submitted</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {referralLinks.map(link => (
                  <tr key={link.link_id}>
                    <td>
                      <a href={`/u/${link.submitted_by}`} target="_blank" rel="noopener noreferrer">
                        {link.submitted_by}
                      </a>
                    </td>
                    <td style={{ maxWidth: '300px', wordBreak: 'break-all' }}>
                      <a href={link.url} target="_blank" rel="noopener noreferrer" className="text-decoration-none">
                        {link.url.length > 60 ? link.url.substring(0, 60) + '...' : link.url}
                        <Icon icon="external-link" classes="ms-1" />
                      </a>
                    </td>
                    <td><span className="badge bg-secondary">{link.domain}</span></td>
                    <td>
                      <span className={`badge ${
                        link.status === 'approved' ? 'bg-success' :
                        link.status === 'rejected' ? 'bg-danger' :
                        'bg-warning text-dark'
                      }`}>
                        {link.status}
                      </span>
                      {link.reject_reason && (
                        <div className="text-muted small mt-1" title={link.reject_reason}>
                          Reason: {link.reject_reason.length > 30 ? link.reject_reason.substring(0, 30) + '...' : link.reject_reason}
                        </div>
                      )}
                    </td>
                    <td className="small">
                      {new Date(link.submitted_at * 1000).toLocaleString()}
                    </td>
                    <td>
                      {/* Verify button — available for pending and approved */}
                      {(link.status === 'pending' || link.status === 'approved') && (
                        <button
                          className={`btn btn-sm ${link.status === 'pending' ? 'btn-info' : 'btn-outline-info'} me-1`}
                          onClick={() => this.handleVerifyReferral(link.link_id)}
                          disabled={actionInProgress}
                          title="Verify backlink (crawl the URL and check for oratio.space link)"
                        >
                          {verifyingLinkId === link.link_id ? (
                            <Spinner />
                          ) : (
                            <Icon icon="search" />
                          )}
                          {' '}Verify
                        </button>
                      )}
                      {link.status === 'pending' && (
                        <>
                          <button
                            className="btn btn-sm btn-success me-1"
                            onClick={() => this.handleApproveReferral(link.link_id)}
                            disabled={actionInProgress}
                            title="Approve this referral link"
                          >
                            <Icon icon="check" />
                          </button>
                          {rejectingLinkId === link.link_id ? (
                            <div className="d-inline-flex align-items-center mt-1">
                              <input
                                type="text"
                                className="form-control form-control-sm me-1"
                                placeholder="Reject reason (optional)"
                                value={rejectReason}
                                style={{ width: '180px' }}
                                onInput={(e: any) => this.setState({ rejectReason: e.target.value })}
                              />
                              <button
                                className="btn btn-sm btn-danger me-1"
                                onClick={() => this.handleRejectReferral(link.link_id)}
                                disabled={actionInProgress}
                              >
                                Reject
                              </button>
                              <button
                                className="btn btn-sm btn-outline-secondary"
                                onClick={() => this.setState({ rejectingLinkId: null, rejectReason: '' })}
                              >
                                ✕
                              </button>
                            </div>
                          ) : (
                            <button
                              className="btn btn-sm btn-outline-danger"
                              onClick={() => this.setState({ rejectingLinkId: link.link_id, rejectReason: '' })}
                              disabled={actionInProgress}
                              title="Reject this referral link"
                            >
                              <Icon icon="x" />
                            </button>
                          )}
                        </>
                      )}
                      {link.status === 'approved' && (
                        <span className="text-success small">
                          <Icon icon="check-circle" classes="me-1" /> Approved
                          {link.verified && <span className="badge bg-success ms-1">✓ Verified</span>}
                        </span>
                      )}
                      {link.status === 'rejected' && (
                        <span className="text-danger small">
                          <Icon icon="x-circle" classes="me-1" /> Rejected
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  render() {
    const { activeTab } = this.state;

    return (
      <div className="container-lg">
        <div className="row">
          <div className="col-12">
            <h2 className="mb-4">
              <Icon icon="shield-check" classes="me-2" />
              Admin Control Panel
            </h2>

            <ul className="nav nav-tabs mb-4">
              <li className="nav-item">
                <button
                  className={`nav-link ${activeTab === 'reports' ? 'active' : ''}`}
                  onClick={() => this.setState({ activeTab: 'reports' }, () => {
                    if (activeTab !== 'reports') this.loadReports();
                  })}
                >
                  <Icon icon="flag" classes="me-1" />
                  Pending CP Reports ({this.state.reports.length})
                </button>
              </li>
              <li className="nav-item">
                <button
                  className={`nav-link ${activeTab === 'users' ? 'active' : ''}`}
                  onClick={() => this.setState({ activeTab: 'users' })}
                >
                  <Icon icon="users" classes="me-1" />
                  Manage Users
                </button>
              </li>
              <li className="nav-item">
                <button
                  className={`nav-link ${activeTab === 'appeals' ? 'active' : ''}`}
                  onClick={() => this.setState({ activeTab: 'appeals' }, () => {
                    // Only load appeals if we weren't already on the appeals tab
                    if (activeTab !== 'appeals') this.loadAppeals();
                  })}
                >
                  <Icon icon="file-text" classes="me-1" />
                  CP Appeals ({this.state.appeals.length})
                </button>
              </li>
              <li className="nav-item">
                <button
                  className={`nav-link ${activeTab === 'referrals' ? 'active' : ''}`}
                  onClick={() => this.setState({ activeTab: 'referrals' }, () => {
                    if (activeTab !== 'referrals') this.loadReferrals();
                  })}
                >
                  <Icon icon="link" classes="me-1" />
                  Referrals ({this.state.referralLinks.length})
                </button>
              </li>
            </ul>

            {activeTab === 'reports' && this.renderReportsTab()}
            {activeTab === 'users' && this.renderUsersTab()}
            {activeTab === 'appeals' && this.renderAppealsTab()}
            {activeTab === 'referrals' && this.renderReferralsTab()}
          </div>
        </div>
      </div>
    );
  }
}
