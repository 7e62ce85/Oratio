import { setIsoData } from "@utils/app";
import { isBrowser } from "@utils/browser";
import { resourcesSettled, validEmail } from "@utils/helpers";
import { scrollMixin } from "../mixins/scroll-mixin";
import { Component, linkEvent } from "inferno";
import { T } from "inferno-i18next-dess";
import {
  CaptchaResponse,
  GetCaptchaResponse,
  GetSiteResponse,
  LoginResponse,
  SiteView,
} from "lemmy-js-client";
import { joinLemmyUrl, validActorRegexPattern } from "../../config";
import { mdToHtml } from "../../markdown";
import { I18NextService, UserService } from "../../services";
import {
  EMPTY_REQUEST,
  HttpService,
  LOADING_REQUEST,
  RequestState,
} from "../../services/HttpService";
import { toast } from "../../toast";
import { HtmlTags } from "../common/html-tags";
import { Icon, Spinner } from "../common/icon";
import { MarkdownTextArea } from "../common/markdown-textarea";
import PasswordInput from "../common/password-input.tsx";
import { RouteComponentProps } from "inferno-router/dist/Route";
import { 
  computeProofOfWork, 
  POW_DIFFICULTY_PRESETS
} from "../../utils/proof-of-work";

interface State {
  registerRes: RequestState<LoginResponse>;
  captchaRes: RequestState<GetCaptchaResponse>;
  form: {
    username?: string;
    email?: string;
    password?: string;
    password_verify?: string;
    show_nsfw: boolean;
    captcha_uuid?: string;
    captcha_answer?: string;
    honeypot?: string;
    answer?: string;
  };
  captchaPlaying: boolean;
  siteRes: GetSiteResponse;
  // Proof of Work 관련 상태
  powChallenge?: string;        // 서버에서 받은 PoW 챌린지
  powNonce?: number;            // 계산된 nonce
  powHash?: string;             // 계산된 해시
  powComputing: boolean;        // PoW 계산 중 여부
  powProgress: number;          // PoW 계산 진행률 (0-100)
  powAttempts: number;          // PoW 시도 횟수
  powDifficulty: number;        // PoW 난이도
}

@scrollMixin
export class Signup extends Component<
  RouteComponentProps<Record<string, never>>,
  State
> {
  private isoData = setIsoData(this.context);
  private audio?: HTMLAudioElement;

  state: State = {
    registerRes: EMPTY_REQUEST,
    captchaRes: EMPTY_REQUEST,
    form: {
      show_nsfw: !!this.isoData.site_res.site_view.site.content_warning,
    },
    captchaPlaying: false,
    siteRes: this.isoData.site_res,
    // Proof of Work 초기값
    powComputing: false,
    powProgress: 0,
    powAttempts: 0,
    powDifficulty: 20, // 기본 난이도 (약 10초 예상)
  };

  loadingSettled() {
    return (
      !this.state.siteRes.site_view.local_site.captcha_enabled ||
      resourcesSettled([this.state.captchaRes])
    );
  }

  constructor(props: any, context: any) {
    super(props, context);

    this.handleAnswerChange = this.handleAnswerChange.bind(this);
  }

  async componentWillMount() {
    if (
      this.state.siteRes.site_view.local_site.captcha_enabled &&
      isBrowser()
    ) {
      await this.fetchCaptcha();
    }
  }

  async fetchCaptcha() {
    this.setState({ captchaRes: LOADING_REQUEST });
    this.setState({
      captchaRes: await HttpService.client.getCaptcha(),
    });

    this.setState(s => {
      if (s.captchaRes.state === "success") {
        s.form.captcha_uuid = s.captchaRes.data.ok?.uuid;
      }
      return s;
    });
  }

  get documentTitle(): string {
    const siteView = this.state.siteRes.site_view;
    return `${this.titleName(siteView)} - ${siteView.site.name}`;
  }

  titleName(siteView: SiteView): string {
    return I18NextService.i18n.t(
      siteView.local_site.private_instance ? "apply_to_join" : "sign_up",
    );
  }

  get isLemmyMl(): boolean {
    return isBrowser() && window.location.hostname === "lemmy.ml";
  }

  render() {
    return (
      <div className="home-signup container-lg">
        <HtmlTags
          title={this.documentTitle}
          path={this.context.router.route.match.url}
        />
        <div className="row">
          <div className="col-12 col-lg-6 offset-lg-3">
            {this.registerForm()}
          </div>
        </div>
      </div>
    );
  }

  registerForm() {
    const siteView = this.state.siteRes.site_view;
    return (
      <form
        className="was-validated"
        onSubmit={linkEvent(this, this.handleRegisterSubmit)}
      >
        <h1 className="h4 mb-4">{this.titleName(siteView)}</h1>

        {this.isLemmyMl && (
          <div className="mb-3 row">
            <div className="mt-2 mb-0 alert alert-warning" role="alert">
              <T i18nKey="lemmy_ml_registration_message">
                #<a href={joinLemmyUrl}>#</a>
              </T>
            </div>
          </div>
        )}

        <div className="mb-3 row">
          <label
            className="col-sm-2 col-form-label"
            htmlFor="register-username"
          >
            {I18NextService.i18n.t("username")}
          </label>

          <div className="col-sm-10">
            <input
              type="text"
              id="register-username"
              className="form-control"
              value={this.state.form.username}
              onInput={linkEvent(this, this.handleRegisterUsernameChange)}
              required
              minLength={3}
              pattern={validActorRegexPattern}
              title={I18NextService.i18n.t("community_reqs")}
            />
          </div>
        </div>

        <div className="mb-3 row">
          <label className="col-sm-2 col-form-label" htmlFor="register-email">
            {I18NextService.i18n.t("email")}
          </label>
          <div className="col-sm-10">
            <input
              type="email"
              id="register-email"
              className="form-control"
              placeholder={
                siteView.local_site.require_email_verification
                  ? I18NextService.i18n.t("required")
                  : I18NextService.i18n.t("optional")
              }
              value={this.state.form.email}
              autoComplete="email"
              onInput={linkEvent(this, this.handleRegisterEmailChange)}
              required={siteView.local_site.require_email_verification}
              minLength={3}
            />
            {!siteView.local_site.require_email_verification &&
              this.state.form.email &&
              !validEmail(this.state.form.email) && (
                <div className="mt-2 mb-0 alert alert-warning" role="alert">
                  <Icon icon="alert-triangle" classes="icon-inline me-2" />
                  {I18NextService.i18n.t("no_password_reset")}
                </div>
              )}
          </div>
        </div>

        <div className="mb-3">
          <PasswordInput
            id="register-password"
            value={this.state.form.password}
            onInput={linkEvent(this, this.handleRegisterPasswordChange)}
            showStrength
            label={I18NextService.i18n.t("password")}
            isNew
          />
        </div>

        <div className="mb-3">
          <PasswordInput
            id="register-verify-password"
            value={this.state.form.password_verify}
            onInput={linkEvent(this, this.handleRegisterPasswordVerifyChange)}
            label={I18NextService.i18n.t("verify_password")}
            isNew
          />
        </div>

        {siteView.local_site.registration_mode === "RequireApplication" && (
          <>
            <div className="mb-3 row">
              <div className="offset-sm-2 col-sm-10">
                <div className="mt-2 alert alert-warning" role="alert">
                  <Icon icon="alert-triangle" classes="icon-inline me-2" />
                  {I18NextService.i18n.t("fill_out_application")}
                </div>
                {siteView.local_site.application_question && (
                  <div
                    className="md-div"
                    dangerouslySetInnerHTML={mdToHtml(
                      siteView.local_site.application_question,
                      () => this.forceUpdate(),
                    )}
                  />
                )}
              </div>
            </div>

            <div className="mb-3 row">
              <label
                className="col-sm-2 col-form-label"
                htmlFor="application_answer"
              >
                {I18NextService.i18n.t("answer")}
              </label>
              <div className="col-sm-10">
                <MarkdownTextArea
                  initialContent=""
                  onContentChange={this.handleAnswerChange}
                  hideNavigationWarnings
                  allLanguages={[]}
                  siteLanguages={[]}
                />
              </div>
            </div>
          </>
        )}
        {this.renderCaptcha()}
        {this.renderProofOfWork()}
        <div className="mb-3 row">
          <div className="col-sm-10">
            <div className="form-check">
              <input
                className="form-check-input"
                id="register-show-nsfw"
                type="checkbox"
                checked={this.state.form.show_nsfw}
                onChange={linkEvent(this, this.handleRegisterShowNsfwChange)}
              />
              <label className="form-check-label" htmlFor="register-show-nsfw">
                {I18NextService.i18n.t("show_nsfw")}
              </label>
            </div>
          </div>
        </div>
        <input
          tabIndex={-1}
          autoComplete="false"
          name="a_password"
          type="text"
          className="form-control honeypot"
          id="register-honey"
          value={this.state.form.honeypot}
          onInput={linkEvent(this, this.handleHoneyPotChange)}
        />
        <div className="mb-3 row">
          <div className="col-sm-10">
            <button type="submit" className="btn btn-secondary">
              {this.state.registerRes.state === "loading" ? (
                <Spinner />
              ) : (
                this.titleName(siteView)
              )}
            </button>
          </div>
        </div>
      </form>
    );
  }

  renderCaptcha() {
    switch (this.state.captchaRes.state) {
      case "loading":
        return <Spinner />;
      case "success": {
        const res = this.state.captchaRes.data;
        return (
          <div className="mb-3 row">
            <label className="col-sm-2" htmlFor="register-captcha">
              <span className="me-2">
                {I18NextService.i18n.t("enter_code")}
              </span>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={linkEvent(this, this.handleRegenCaptcha)}
                aria-label={I18NextService.i18n.t("captcha")}
              >
                <Icon icon="refresh-cw" classes="icon-refresh-cw" />
              </button>
            </label>
            {this.showCaptcha(res)}
            <div className="col-sm-6">
              <input
                type="text"
                className="form-control"
                id="register-captcha"
                value={this.state.form.captcha_answer}
                onInput={linkEvent(
                  this,
                  this.handleRegisterCaptchaAnswerChange,
                )}
                required
              />
            </div>
          </div>
        );
      }
    }
  }

  renderProofOfWork() {
    return (
      <div className="mb-3 row">
        <label className="col-sm-2 col-form-label">
          �️ Bot Verification
        </label>
        <div className="col-sm-10">
          {this.state.powComputing ? (
            <div className="card">
              <div className="card-body">
                <div className="d-flex align-items-center mb-2">
                  <Spinner />
                  <span className="ms-2">
                    🤖 Verifying you're human... ({this.state.powProgress.toFixed(0)}%)
                  </span>
                </div>
                <div className="progress">
                  <div
                    className="progress-bar progress-bar-striped progress-bar-animated"
                    role="progressbar"
                    style={`width: ${this.state.powProgress}%`}
                    aria-valuenow={this.state.powProgress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  />
                </div>
                <small className="text-muted mt-2 d-block">
                  Attempts: {this.state.powAttempts.toLocaleString()}
                </small>
              </div>
            </div>
          ) : this.state.powHash ? (
            <div className="alert alert-success mb-0" role="alert">
              <Icon icon="check-circle" classes="icon-inline me-2" />
              ✓ Verification Complete!
              <small className="d-block text-muted mt-1">
                Completed in {this.state.powAttempts.toLocaleString()} attempts
              </small>
            </div>
          ) : (
            <button
              type="button"
              className="btn btn-outline-secondary"
              onClick={linkEvent(this, this.handleComputePoW)}
            >
              <Icon icon="shield" classes="icon-inline me-2" />
              Verify I'm Not a Bot
            </button>
          )}
          <small className="form-text text-muted d-block mt-2">
            To prevent spam, we perform an automatic verification check.
            This runs in your browser and takes about 10 seconds.
          </small>
        </div>
      </div>
    );
  }

  showCaptcha(res: GetCaptchaResponse) {
    const captchaRes = res?.ok;
    return captchaRes ? (
      <div className="col-sm-4">
        <>
          <img
            className="rounded-top img-fluid"
            src={this.captchaPngSrc(captchaRes)}
            style="border-bottom-right-radius: 0; border-bottom-left-radius: 0;"
            alt={I18NextService.i18n.t("captcha")}
          />
          {captchaRes.wav && (
            <button
              className="rounded-bottom btn btn-sm btn-secondary d-block"
              style="border-top-right-radius: 0; border-top-left-radius: 0;"
              title={I18NextService.i18n.t("play_captcha_audio")}
              onClick={linkEvent(this, this.handleCaptchaPlay)}
              type="button"
              disabled={this.state.captchaPlaying}
            >
              <Icon icon="play" classes="icon-play" />
            </button>
          )}
        </>
      </div>
    ) : (
      <></>
    );
  }

  async handleRegisterSubmit(i: Signup, event: any) {
    event.preventDefault();
    
    // PoW 검증
    if (!i.state.powHash || !i.state.powNonce || !i.state.powChallenge) {
      toast("Please complete the bot verification first.", "danger");
      return;
    }

    const {
      show_nsfw,
      answer,
      captcha_answer,
      captcha_uuid,
      email,
      honeypot,
      password,
      password_verify,
      username,
    } = i.state.form;
    if (username && password && password_verify) {
      i.setState({ registerRes: LOADING_REQUEST });

      // TODO: 백엔드 API가 준비되면 아래와 같이 PoW 정보 전송
      // const registerRes = await HttpService.client.register({
      //   username,
      //   password,
      //   password_verify,
      //   email,
      //   show_nsfw,
      //   captcha_uuid,
      //   captcha_answer,
      //   honeypot,
      //   answer,
      //   // PoW 필드 추가
      //   pow_challenge: i.state.powChallenge,
      //   pow_nonce: i.state.powNonce,
      //   pow_hash: i.state.powHash,
      // });

      // 임시: 기존 방식 유지 (백엔드 수정 전까지)
      const registerRes = await HttpService.client.register({
        username,
        password,
        password_verify,
        email,
        show_nsfw,
        captcha_uuid,
        captcha_answer,
        honeypot,
        answer,
      });
      
      switch (registerRes.state) {
        case "failed": {
          toast(registerRes.err.message, "danger");
          i.setState({ registerRes: EMPTY_REQUEST });
          break;
        }

        case "success": {
          const data = registerRes.data;

          // Only log them in if a jwt was set
          if (data.jwt) {
            UserService.Instance.login({
              res: data,
            });

            const site = await HttpService.client.getSite();

            if (site.state === "success") {
              UserService.Instance.myUserInfo = site.data.my_user;
            }

            i.props.history.replace("/communities");
          } else {
            if (data.verify_email_sent) {
              toast(I18NextService.i18n.t("verify_email_sent"));
            }
            if (data.registration_created) {
              toast(I18NextService.i18n.t("registration_application_sent"));
            }
            i.props.history.push("/");
          }
          break;
        }
      }
    }
  }

  handleRegisterUsernameChange(i: Signup, event: any) {
    i.state.form.username = event.target.value.trim();
    i.setState(i.state);
  }

  handleRegisterEmailChange(i: Signup, event: any) {
    i.state.form.email = event.target.value;
    if (i.state.form.email === "") {
      i.state.form.email = undefined;
    }
    i.setState(i.state);
  }

  handleRegisterPasswordChange(i: Signup, event: any) {
    i.state.form.password = event.target.value;
    i.setState(i.state);
  }

  handleRegisterPasswordVerifyChange(i: Signup, event: any) {
    i.state.form.password_verify = event.target.value;
    i.setState(i.state);
  }

  handleRegisterShowNsfwChange(i: Signup, event: any) {
    i.state.form.show_nsfw = event.target.checked;
    i.setState(i.state);
  }

  handleRegisterCaptchaAnswerChange(i: Signup, event: any) {
    i.state.form.captcha_answer = event.target.value;
    i.setState(i.state);
  }

  handleAnswerChange(val: string) {
    this.setState(s => ((s.form.answer = val), s));
  }

  handleHoneyPotChange(i: Signup, event: any) {
    i.state.form.honeypot = event.target.value;
    i.setState(i.state);
  }

  async handleComputePoW(i: Signup) {
    try {
      // 챌린지 생성 (타임스탬프 + 랜덤값)
      // 이미 챌린지가 있다면 재사용 (중복 클릭 방지)
      let challenge = i.state.powChallenge;
      if (!challenge) {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substring(2);
        challenge = `${timestamp}-${random}`;
      }
      
      i.setState({ 
        powChallenge: challenge,
        powComputing: true,
        powProgress: 0,
        powAttempts: 0,
        powNonce: undefined,
        powHash: undefined
      });

      // PoW 계산 (진행률 콜백 포함)
      const result = await computeProofOfWork(
        challenge,
        i.state.powDifficulty,
        (progress, attempts) => {
          i.setState({ 
            powProgress: progress,
            powAttempts: attempts
          });
        }
      );

      // 계산 완료
      i.setState({
        powNonce: result.nonce,
        powHash: result.hash,
        powAttempts: result.attempts,
        powComputing: false,
        powProgress: 100
      });

      toast("✓ Verification complete!", "success");
    } catch (error) {
      console.error('PoW computation failed:', error);
      toast("Verification failed. Please try again.", "danger");
      i.setState({ 
        powComputing: false,
        powProgress: 0
      });
    }
  }

  async handleRegenCaptcha(i: Signup) {
    i.audio = undefined;
    i.setState({ captchaPlaying: false });
    await i.fetchCaptcha();
  }

  handleCaptchaPlay(i: Signup) {
    // This was a bad bug, it should only build the new audio on a new file.
    // Replays would stop prematurely if this was rebuilt every time.

    if (i.state.captchaRes.state === "success" && i.state.captchaRes.data.ok) {
      const captchaRes = i.state.captchaRes.data.ok;
      if (!i.audio) {
        const base64 = `data:audio/wav;base64,${captchaRes.wav}`;
        i.audio = new Audio(base64);
        i.audio.play();

        i.setState({ captchaPlaying: true });

        i.audio.addEventListener("ended", () => {
          if (i.audio) {
            i.audio.currentTime = 0;
            i.setState({ captchaPlaying: false });
          }
        });
      }
    }
  }

  captchaPngSrc(captcha: CaptchaResponse) {
    return `data:image/png;base64,${captcha.png}`;
  }
}
