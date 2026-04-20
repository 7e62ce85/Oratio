import { capitalizeFirstLetter } from "@utils/helpers";
import { Component } from "inferno";
import { T } from "inferno-i18next-dess";
import { Link } from "inferno-router";
import {
  CommentResponse,
  CreateComment,
  EditComment,
  Language,
} from "lemmy-js-client";
import { CommentNodeI } from "../../interfaces";
import { I18NextService, UserService } from "../../services";
import { Icon, Spinner } from "../common/icon";
import { MarkdownTextArea } from "../common/markdown-textarea";
import { RequestState } from "../../services/HttpService";
import { checkUserCPPermissions } from "../../utils/cp-moderation";
import { computeCommentPoW } from "../../utils/proof-of-work";
import { checkUserHasGoldBadgeSync } from "../../utils/bch-payment";
import { toast } from "../../toast";

interface CommentFormProps {
  /**
   * Can either be the parent, or the editable comment. The right side is a postId.
   */
  node: CommentNodeI | number;
  edit?: boolean;
  disabled?: boolean;
  focus?: boolean;
  onReplyCancel?(): void;
  allLanguages: Language[];
  siteLanguages: number[];
  containerClass?: string;
  onUpsertComment(
    form: EditComment | CreateComment,
  ): Promise<RequestState<CommentResponse>>;
}

interface CommentFormState {
  // PoW 관련 상태
  powChallenge?: string;
  powNonce?: number;
  powHash?: string;
  powDifficulty?: number;
  powComputing: boolean;
  powProgress: number;
  powAttempts: number;
  powReady: boolean;
}

export class CommentForm extends Component<CommentFormProps, CommentFormState> {
  state: CommentFormState = {
    powComputing: false,
    powProgress: 0,
    powAttempts: 0,
    powReady: false,
  };

  constructor(props: any, context: any) {
    super(props, context);

    this.handleCommentSubmit = this.handleCommentSubmit.bind(this);
    this.handleContentChange = this.handleContentChange.bind(this);
  }

  componentDidMount() {
    // Check CP permissions - ban users from commenting if banned
    const user = UserService.Instance.myUserInfo;
    if (user && !this.props.edit) { // Only check for new comments, not edits
      checkUserCPPermissions(user.local_user_view.person.name).then(permissions => {
        if (permissions && permissions.is_banned) {
          const banEndDate = new Date((permissions.ban_end || 0) * 1000);
          toast(
            `You are banned from commenting until ${banEndDate.toLocaleDateString()} due to CP violation`,
            "danger"
          );
          this.props.onReplyCancel?.();
        }
      });
    }
  }

  /**
   * 글자 입력 시작 시 PoW 자동 시작 (페이지 접속 시가 아닌, 실제 타이핑 시작 시점)
   * 이미 계산 완료되었거나 계산 중이면 무시
   * 수정 모드 또는 멤버십 유저는 PoW 불필요
   */
  maybeAutoStartCommentPoW() {
    if (this.props.edit) return;
    if (this.state.powReady || this.state.powComputing) return;

    const user = UserService.Instance.myUserInfo;
    if (!user) return;

    const isMember = checkUserHasGoldBadgeSync(user.local_user_view.person);
    if (isMember) {
      console.log("[PoW] Membership user — comment PoW exempted");
      return;
    }

    this.startCommentPoW();
  }

  handleContentChange(_val: string) {
    this.maybeAutoStartCommentPoW();
  }

  /**
   * 댓글용 PoW 계산 시작 (경량 난이도)
   * 댓글 폼이 열릴 때 자동으로 백그라운드에서 계산
   */
  async startCommentPoW() {
    if (this.state.powReady || this.state.powComputing) return;

    try {
      this.setState({ powComputing: true, powProgress: 0, powAttempts: 0 });

      const result = await computeCommentPoW((progress, attempts) => {
        this.setState({ powProgress: progress, powAttempts: attempts });
      });

      this.setState({
        powChallenge: result.challenge,
        powNonce: result.nonce,
        powHash: result.hash,
        powDifficulty: result.difficulty,
        powComputing: false,
        powProgress: 100,
        powReady: true,
      });
    } catch (error) {
      console.error("[PoW] Comment PoW computation failed:", error);
      // PoW 실패 시에도 댓글 작성 허용 (graceful degradation)
      // pow-validator 서버에서 최종 판단
      this.setState({
        powComputing: false,
        powProgress: 0,
        powReady: false,
      });
    }
  }

  render() {
    const initialContent =
      typeof this.props.node !== "number"
        ? this.props.edit
          ? this.props.node.comment_view.comment.content
          : undefined
        : undefined;

    return (
      <div
        className={["comment-form", "mb-3", this.props.containerClass].join(
          " ",
        )}
      >
        {UserService.Instance.myUserInfo ? (
          <>
            {/* PoW 진행 상태 표시 (새 댓글만, 수정 시 표시 안함) */}
            {!this.props.edit && this.state.powComputing && (
              <div className="alert alert-info py-1 px-2 mb-1 d-flex align-items-center" style="font-size: 0.8rem;">
                <Spinner />
                <span className="ms-2">
                  🔒 Verifying... {this.state.powProgress.toFixed(0)}%
                </span>
              </div>
            )}
            <MarkdownTextArea
              initialContent={initialContent}
              showLanguage
              buttonTitle={this.buttonTitle}
              replyType={typeof this.props.node !== "number"}
              focus={this.props.focus}
              disabled={this.props.disabled}
              onSubmit={this.handleCommentSubmit}
              onReplyCancel={this.props.onReplyCancel}
              onContentChange={this.handleContentChange}
              placeholder={I18NextService.i18n.t("comment_here") ?? undefined}
              allLanguages={this.props.allLanguages}
              siteLanguages={this.props.siteLanguages}
            />
          </>
        ) : (
          <div className="alert alert-warning" role="alert">
            <Icon icon="alert-triangle" classes="icon-inline me-2" />
            <T i18nKey="must_login" class="d-inline">
              #
              <Link className="alert-link" to="/login">
                #
              </Link>
            </T>
          </div>
        )}
      </div>
    );
  }

  get buttonTitle(): string {
    return typeof this.props.node === "number"
      ? capitalizeFirstLetter(I18NextService.i18n.t("post"))
      : this.props.edit
        ? capitalizeFirstLetter(I18NextService.i18n.t("save"))
        : capitalizeFirstLetter(I18NextService.i18n.t("reply"));
  }

  async handleCommentSubmit(
    content: string,
    language_id?: number,
  ): Promise<boolean> {
    const { node, onUpsertComment, edit } = this.props;
    let response: RequestState<CommentResponse>;

    // PoW 데이터 (새 댓글에만 추가, 수정에는 불필요)
    const powData = (!edit && this.state.powReady) ? {
      pow_challenge: this.state.powChallenge,
      pow_nonce: this.state.powNonce,
      pow_hash: this.state.powHash,
    } : {};

    if (typeof node === "number") {
      const post_id = node;
      response = await onUpsertComment({
        content,
        post_id,
        language_id,
        ...powData,
      } as CreateComment);
    } else if (edit) {
      const comment_id = node.comment_view.comment.id;
      response = await onUpsertComment({
        content,
        comment_id,
        language_id,
      });
    } else {
      const post_id = node.comment_view.post.id;
      const parent_id = node.comment_view.comment.id;
      response = await onUpsertComment({
        content,
        parent_id,
        post_id,
        language_id,
        ...powData,
      } as CreateComment);
    }

    // 댓글 전송 후 PoW 상태 초기화 (다음 댓글 작성 시 타이핑 시작하면 자동으로 다시 계산됨)
    if (response.state !== "failed" && !edit) {
      this.setState({
        powChallenge: undefined,
        powNonce: undefined,
        powHash: undefined,
        powDifficulty: undefined,
        powReady: false,
        powProgress: 0,
        powAttempts: 0,
      });
    }

    return response.state !== "failed";
  }
}
