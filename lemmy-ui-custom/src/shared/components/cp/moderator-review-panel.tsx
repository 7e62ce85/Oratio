import { Component } from "inferno";
import { UserService, I18NextService } from "../../services";
import { getPendingReports, reviewCPReport, CPReport } from "../../utils/cp-moderation";
import { Spinner, Icon } from "../common/icon";
import { toast } from "../../toast";
import { Link } from "inferno-router";

interface ModeratorReviewPanelState {
  reports: CPReport[];
  loading: boolean;
  reviewingReportId: string | null;
}

export class ModeratorReviewPanel extends Component<{}, ModeratorReviewPanelState> {
  state: ModeratorReviewPanelState = {
    reports: [],
    loading: true,
    reviewingReportId: null
  };

  async componentDidMount() {
    // Check if user is logged in and is moderator
    const user = UserService.Instance.myUserInfo;
    if (!user) {
      toast("You must be logged in as a moderator to access this page", "danger");
      window.location.href = "/login";
      return;
    }

    // Check if user is a moderator of any community
    const isModerator = user.moderates && user.moderates.length > 0;
    if (!isModerator) {
      toast("Access denied: Moderator privileges required", "danger");
      window.location.href = "/";
      return;
    }

    await this.fetchReports();
  }

  async fetchReports() {
    this.setState({ loading: true });
    const reports = await getPendingReports(undefined, 'moderator');
    this.setState({ reports, loading: false });
  }

  async handleReview(
    reportId: string,
    decision: 'cp_confirmed' | 'not_cp'
  ) {
    const user = UserService.Instance.myUserInfo;
    if (!user) return;

    this.setState({ reviewingReportId: reportId });

    const result = await reviewCPReport(
      reportId,
      user.local_user_view.person.id,
      user.local_user_view.person.name,
      'moderator',
      decision
    );

    this.setState({ reviewingReportId: null });

    if (result.success) {
      toast(
        decision === 'cp_confirmed' 
          ? "Report confirmed. User has been banned for 3 months." 
          : "Report rejected. Reporter may lose reporting privileges.",
        "success"
      );
      await this.fetchReports();
    } else {
      toast(result.message || "Failed to review report", "danger");
    }
  }

  render() {
    const { reports, loading, reviewingReportId } = this.state;

    return (
      <div className="container-lg">
        <div className="row">
          <div className="col-12">
            <h2 className="mb-4">
              <Icon icon="shield" classes="me-2" />
              CP Moderator Review
            </h2>

            {loading ? (
              <div className="text-center p-5">
                <Spinner large />
              </div>
            ) : reports.length === 0 ? (
              <div className="alert alert-info">
                <Icon icon="info" classes="me-2" />
                No pending CP reports to review
              </div>
            ) : (
              <>
                <div className="alert alert-warning mb-4">
                  <Icon icon="alert-triangle" classes="me-2" />
                  <strong>Warning:</strong> You are reviewing reports of child pornography. 
                  Your decisions will result in user bans or loss of reporting privileges.
                </div>

                <div className="list-group">
                  {reports.map(report => (
                    <div key={report.id} className="list-group-item mb-3">
                      <div className="row">
                        <div className="col-md-8">
                          <h5 className="mb-3">
                            <span className="badge bg-danger me-2">CP Report</span>
                            <span className="badge bg-secondary me-2">
                              {report.content_type === 'post' ? 'Post' : 'Comment'}
                            </span>
                            #{report.content_id}
                          </h5>
                          
                          <dl className="row mb-3">
                            <dt className="col-sm-4">Reported by:</dt>
                            <dd className="col-sm-8">
                              <strong>{report.reporter_username}</strong>
                            </dd>
                            
                            <dt className="col-sm-4">Content creator:</dt>
                            <dd className="col-sm-8">
                              <strong className="text-danger">{report.creator_username}</strong>
                            </dd>
                            
                            <dt className="col-sm-4">Reason:</dt>
                            <dd className="col-sm-8">
                              {report.reason || <em className="text-muted">No reason provided</em>}
                            </dd>
                            
                            <dt className="col-sm-4">Reported:</dt>
                            <dd className="col-sm-8">
                              {new Date(report.created_at * 1000).toLocaleString()}
                            </dd>

                            <dt className="col-sm-4">Status:</dt>
                            <dd className="col-sm-8">
                              <span className="badge bg-warning">
                                Content Hidden - Awaiting Review
                              </span>
                            </dd>
                          </dl>

                          <div className="mb-2">
                            <Link 
                              to={`/${report.content_type}/${report.content_id}`}
                              className="btn btn-sm btn-outline-primary"
                              target="_blank"
                            >
                              <Icon icon="eye" classes="me-1" />
                              View Content
                            </Link>
                          </div>
                        </div>

                        <div className="col-md-4 d-flex flex-column justify-content-center gap-2">
                          <button
                            className="btn btn-danger btn-lg"
                            onClick={() => this.handleReview(report.id, 'cp_confirmed')}
                            disabled={reviewingReportId === report.id}
                          >
                            {reviewingReportId === report.id ? (
                              <Spinner />
                            ) : (
                              <>
                                <Icon icon="x-circle" classes="me-2" />
                                Confirm CP
                              </>
                            )}
                          </button>

                          <button
                            className="btn btn-success btn-lg"
                            onClick={() => this.handleReview(report.id, 'not_cp')}
                            disabled={reviewingReportId === report.id}
                          >
                            {reviewingReportId === report.id ? (
                              <Spinner />
                            ) : (
                              <>
                                <Icon icon="check-circle" classes="me-2" />
                                Not CP
                              </>
                            )}
                          </button>

                          <div className="small text-muted mt-2">
                            <strong>If you confirm CP:</strong>
                            <ul className="mb-1">
                              <li>Creator banned for 3 months</li>
                              <li>Content stays hidden</li>
                            </ul>
                            <strong>If you reject:</strong>
                            <ul className="mb-0">
                              <li>Reporter loses report ability</li>
                              <li>Content can be unhidden</li>
                            </ul>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }
}
