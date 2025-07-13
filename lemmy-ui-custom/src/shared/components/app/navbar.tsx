import { showAvatars } from "@utils/app";
import { isBrowser } from "@utils/browser";
import { numToSI } from "@utils/helpers";
import { amAdmin, canCreateCommunity } from "@utils/roles";
import { Component, createRef, linkEvent } from "inferno";
import { NavLink } from "inferno-router";
import { GetSiteResponse } from "lemmy-js-client";
import { donateLemmyUrl } from "../../config";
import {
  I18NextService,
  UserService,
  UnreadCounterService,
} from "../../services";
import { toast } from "../../toast";
import { Icon } from "../common/icon";
import { PictrsImage } from "../common/pictrs-image";
import { Subscription } from "rxjs";
import { tippyMixin } from "../mixins/tippy-mixin";

const BCH_PAYMENT_URL = process.env.LEMMY_BCH_PAYMENT_URL || "http://localhost:8081/";
const BCH_API_URL = process.env.LEMMY_BCH_API_URL || "http://localhost:8081/api/user_credit";

// 브라우저에서는 window.__BCH_CONFIG__에서, 서버에서는 process.env에서 API 키 가져오기
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

const getBCHPaymentUrl = () => {
  if (typeof window !== 'undefined' && window.__BCH_CONFIG__) {
    return window.__BCH_CONFIG__.PAYMENT_URL;
  }
  return BCH_PAYMENT_URL;
};

// 디버깅을 위한 환경변수 출력
console.log("[BCH Debug] Environment variables:");
console.log("[BCH Debug] BCH_PAYMENT_URL:", BCH_PAYMENT_URL);
console.log("[BCH Debug] BCH_API_URL:", BCH_API_URL);
console.log("[BCH Debug] LEMMY_API_KEY:", getApiKey() ? `${getApiKey().substring(0, 3)}...` : "not set");
// Note: getApiKey() function handles both server-side (process.env.LEMMY_API_KEY) and client-side (window.__BCH_CONFIG__.API_KEY) cases

interface NavbarProps {
  siteRes?: GetSiteResponse;
}

interface NavbarState {
  onSiteBanner?(url: string): any;
  unreadInboxCount: number;
  unreadReportCount: number;
  unreadApplicationCount: number;
  userCredit: number;
}

function handleCollapseClick(i: Navbar) {
  if (
    i.collapseButtonRef.current?.attributes &&
    i.collapseButtonRef.current?.attributes.getNamedItem("aria-expanded")
      ?.value === "true"
  ) {
    i.collapseButtonRef.current?.click();
  }
}

function handleLogOut(i: Navbar) {
  UserService.Instance.logout();
  handleCollapseClick(i);
}

@tippyMixin
export class Navbar extends Component<NavbarProps, NavbarState> {
  collapseButtonRef = createRef<HTMLButtonElement>();
  mobileMenuRef = createRef<HTMLDivElement>();
  unreadInboxCountSubscription: Subscription;
  unreadReportCountSubscription: Subscription;
  unreadApplicationCountSubscription: Subscription;

  state: NavbarState = {
    unreadInboxCount: 0,
    unreadReportCount: 0,
    unreadApplicationCount: 0,
    userCredit: 0,
  };

  constructor(props: any, context: any) {
    super(props, context);

    this.handleOutsideMenuClick = this.handleOutsideMenuClick.bind(this);
  }

  async componentWillMount() {
    // Subscribe to jwt changes
    if (isBrowser()) {
      // On the first load, check the unreads
      this.requestNotificationPermission();
      this.unreadInboxCountSubscription =
        UnreadCounterService.Instance.unreadInboxCountSubject.subscribe(
          unreadInboxCount => this.setState({ unreadInboxCount }),
        );
      this.unreadReportCountSubscription =
        UnreadCounterService.Instance.unreadReportCountSubject.subscribe(
          unreadReportCount => this.setState({ unreadReportCount }),
        );
      this.unreadApplicationCountSubscription =
        UnreadCounterService.Instance.unreadApplicationCountSubject.subscribe(
          unreadApplicationCount => this.setState({ unreadApplicationCount }),
        );

      document.addEventListener("mouseup", this.handleOutsideMenuClick);
      
      // Fetch user credit if logged in
      if (UserService.Instance.myUserInfo) {
        this.fetchUserCredit();
      }
    }
  }
  
  // Fetch user credit from BCH service
  async fetchUserCredit() {
    try {
      const person = UserService.Instance.myUserInfo?.local_user_view.person;
      if (!person) {
        console.log("[BCH] fetchUserCredit: No logged in user found");
        return;
      }
      
      console.log("[BCH] fetchUserCredit: Attempting to fetch credit for user ID", person.id);
      
      const apiUrl = `${getBCHAPIUrl()}/${person.id}`;
      console.log("[BCH] fetchUserCredit: API URL", apiUrl);
      
      // 디버깅 메시지 추가 - API 키 일부 표시 (보안을 위해 전체 표시 안 함)
      const apiKeyHint = getApiKey() ? `${getApiKey().substring(0, 3)}...` : "not set";
      console.log(`[BCH] Using API key: ${apiKeyHint}`);
      
      const response = await fetch(apiUrl, {
        headers: {
          'X-API-Key': getApiKey() || ""
        }
      });
      
      console.log("[BCH] fetchUserCredit: API response status", response.status);
      
      if (response.ok) {
        const data = await response.json();
        console.log("[BCH] fetchUserCredit: Response data", data);
        
        // credit_balance 필드가 있는지 확인
        if (data.credit_balance !== undefined) {
          console.log(`[BCH] Setting userCredit state to: ${data.credit_balance}`);
          this.setState({ userCredit: data.credit_balance });
        } else {
          console.error("[BCH] Response does not contain credit_balance field:", data);
        }
      } else {
        // 응답이 실패한 경우 응답 텍스트도 로깅
        const errorText = await response.text();
        console.error(`[BCH] Failed to fetch user credit: ${response.status}`, errorText);
      }
    } catch (error) {
      console.error("[BCH] Error fetching user credit:", error);
    }
  }

  componentWillUnmount() {
    document.removeEventListener("mouseup", this.handleOutsideMenuClick);
    this.unreadInboxCountSubscription.unsubscribe();
    this.unreadReportCountSubscription.unsubscribe();
    this.unreadApplicationCountSubscription.unsubscribe();
  }

  // TODO class active corresponding to current pages
  render() {
    const siteView = this.props.siteRes?.site_view;
    const person = UserService.Instance.myUserInfo?.local_user_view.person;
    return (
      <div className="shadow-sm">
        <nav
          className="navbar navbar-expand-md navbar-light p-0 px-3 container-lg"
          id="navbar"
        >
          <NavLink
            id="navTitle"
            to="/"
            title={siteView?.site.description ?? siteView?.site.name}
            className="d-flex align-items-center navbar-brand me-md-3"
            onMouseUp={linkEvent(this, handleCollapseClick)}
          >
            {siteView?.site.icon && showAvatars() && (
              <PictrsImage src={siteView.site.icon} icon />
            )}
            {siteView?.site.name}
          </NavLink>
          {person && (
            <ul className="navbar-nav d-flex flex-row ms-auto d-md-none">
              <li id="navMessages" className="nav-item nav-item-icon">
                <NavLink
                  to="/inbox"
                  className="p-1 nav-link border-0 nav-messages"
                  title={I18NextService.i18n.t("unread_messages", {
                    count: Number(this.state.unreadInboxCount),
                    formattedCount: numToSI(this.state.unreadInboxCount),
                  })}
                  onMouseUp={linkEvent(this, handleCollapseClick)}
                >
                  <Icon icon="bell" />
                  {this.state.unreadInboxCount > 0 && (
                    <span className="mx-1 badge text-bg-light">
                      {numToSI(this.state.unreadInboxCount)}
                    </span>
                  )}
                </NavLink>
              </li>
              {UserService.Instance.moderatesSomething && (
                <li className="nav-item nav-item-icon">
                  <NavLink
                    to="/reports"
                    className="p-1 nav-link border-0"
                    title={I18NextService.i18n.t("unread_reports", {
                      count: Number(this.state.unreadReportCount),
                      formattedCount: numToSI(this.state.unreadReportCount),
                    })}
                    onMouseUp={linkEvent(this, handleCollapseClick)}
                  >
                    <Icon icon="shield" />
                    {this.state.unreadReportCount > 0 && (
                      <span className="mx-1 badge text-bg-light">
                        {numToSI(this.state.unreadReportCount)}
                      </span>
                    )}
                  </NavLink>
                </li>
              )}
              {amAdmin() && (
                <li className="nav-item nav-item-icon">
                  <NavLink
                    to="/registration_applications"
                    className="p-1 nav-link border-0"
                    title={I18NextService.i18n.t(
                      "unread_registration_applications",
                      {
                        count: Number(this.state.unreadApplicationCount),
                        formattedCount: numToSI(
                          this.state.unreadApplicationCount,
                        ),
                      },
                    )}
                    onMouseUp={linkEvent(this, handleCollapseClick)}
                  >
                    <Icon icon="clipboard" />
                    {this.state.unreadApplicationCount > 0 && (
                      <span className="mx-1 badge text-bg-light">
                        {numToSI(this.state.unreadApplicationCount)}
                      </span>
                    )}
                  </NavLink>
                </li>
              )}
            </ul>
          )}
          <button
            className="navbar-toggler border-0 p-1"
            type="button"
            aria-label="menu"
            data-tippy-content={I18NextService.i18n.t("expand_here")}
            data-bs-toggle="collapse"
            data-bs-target="#navbarDropdown"
            aria-controls="navbarDropdown"
            aria-expanded="false"
            ref={this.collapseButtonRef}
          >
            <Icon icon="menu" />
          </button>
          <div
            className="collapse navbar-collapse my-2"
            id="navbarDropdown"
            ref={this.mobileMenuRef}
          >
            <ul id="navbarLinks" className="me-auto navbar-nav">
              <li className="nav-item">
                <NavLink
                  to="/communities"
                  className="nav-link"
                  title={I18NextService.i18n.t("communities")}
                  onMouseUp={linkEvent(this, handleCollapseClick)}
                >
                  {I18NextService.i18n.t("communities")}
                </NavLink>
              </li>
              <li className="nav-item">
                {/* TODO make sure this works: https://github.com/infernojs/inferno/issues/1608 */}
                <NavLink
                  to={{
                    pathname: "/create_post",
                    search: "",
                    hash: "",
                    key: "",
                    state: { prevPath: this.currentLocation },
                  }}
                  className="nav-link"
                  title={I18NextService.i18n.t("create_post")}
                  onMouseUp={linkEvent(this, handleCollapseClick)}
                >
                  {I18NextService.i18n.t("create_post")}
                </NavLink>
              </li>
              {this.props.siteRes && canCreateCommunity(this.props.siteRes) && (
                <li className="nav-item">
                  <NavLink
                    to="/create_community"
                    className="nav-link"
                    title={I18NextService.i18n.t("create_community")}
                    onMouseUp={linkEvent(this, handleCollapseClick)}
                  >
                    {I18NextService.i18n.t("create_community")}
                  </NavLink>
                </li>
              )}
              <li className="nav-item">
                <a
                  className="nav-link d-inline-flex align-items-center d-md-inline-block"
                  title={I18NextService.i18n.t("support_lemmy")}
                  href={donateLemmyUrl}
                >
                  <Icon icon="heart" classes="small" />
                  <span className="d-inline ms-1 d-md-none ms-md-0">
                    {I18NextService.i18n.t("support_lemmy")}
                  </span>
                </a>
              </li>
            </ul>
            <ul id="navbarIcons" className="navbar-nav">
              <li id="navSearch" className="nav-item">
                <NavLink
                  to="/search"
                  className="nav-link d-inline-flex align-items-center d-md-inline-block"
                  title={I18NextService.i18n.t("search")}
                  onMouseUp={linkEvent(this, handleCollapseClick)}
                >
                  <Icon icon="search" />
                  <span className="d-inline ms-1 d-md-none ms-md-0">
                    {I18NextService.i18n.t("search")}
                  </span>
                </NavLink>
              </li>
              {/* Bitcoin Cash payment button */}
              <li id="navBCH" className="nav-item">
                <a
                  href={getBCHPaymentUrl()}
                  className="nav-link d-inline-flex align-items-center d-md-inline-block"
                  title="Add Bitcoin Cash"
                  target="_blank"
                  rel="noopener"
                  onMouseUp={linkEvent(this, handleCollapseClick)}
                  style={{ 
                    backgroundColor: "#8DC351", 
                    borderColor: "#8DC351",
                    color: "white",
                    padding: "5px 10px",
                    borderRadius: "6px",
                    fontWeight: "bold",
                    marginLeft: "10px"
                  } as React.CSSProperties}
                >
                  <svg 
                    width="18" 
                    height="18" 
                    viewBox="0 0 16 16" 
                    className="me-1" 
                    style={{ fill: "currentColor" }}
                  >
                    <path d="M8 0C3.59 0 0 3.59 0 8s3.59 8 8 8 8-3.59 8-8-3.59-8-8-8zm1.4 11.8c-.16.59-.82.85-1.39.58-.38-.18-.74-.58-.74-1.03 0-.19.05-.38.14-.55.09-.18.22-.33.38-.44.37-.27.88-.29 1.28-.07.4.22.64.65.63 1.09.01.15-.03.29-.09.42h.24zm-4.01-3.26c-.26-.13-.35-.5-.21-.76.14-.26.5-.37.76-.23.26.14.36.5.22.76-.14.26-.51.37-.77.23zm3.47-3.98c-.42-.15-.88-.08-1.26.14-.38.22-.66.6-.77 1.03l-.1.42h2.85l-.1-.42c-.11-.43-.4-.8-.78-1.03l.16-.14zm1.46 1.68h-4.55c-.25 0-.41.26-.32.49l.69 1.7c.14.33.41.66.77.89.43.27.94.37 1.43.27l.39-.08-1.11-2.54h2.28l-1.14 2.49.41.09c.5.1 1-.01 1.43-.28.35-.22.63-.55.76-.88l.69-1.7c.1-.23-.06-.46-.31-.46zm-4.4 4.58c.18-.11.39-.18.61-.19-.08-.21-.05-.45.07-.63.12-.18.32-.29.53-.29s.41.11.53.29c.12.18.16.42.07.63.22.01.43.08.61.19.18.11.33.27.41.47.08.2.09.41.03.61-.13.43-.58.72-1.05.67-.22-.02-.43-.11-.6-.26s-.28-.35-.3-.57c-.04-.47.27-.91.7-1.03.16-.05.33-.06.5-.02-.03-.1-.1-.17-.2-.21-.1-.04-.2-.04-.3 0-.1.04-.17.12-.2.21-.03.1-.03.2 0 .3.03.09.01.19-.06.25-.07.06-.17.08-.25.04s-.14-.12-.14-.21c0-.09.05-.17.13-.22z"/>
                  </svg>
                  <span className="d-inline ms-1 d-md-inline ms-md-1">
                    Add BCH
                  </span>
                </a>
              </li>
              {amAdmin() && (
                <li id="navAdmin" className="nav-item">
                  <NavLink
                    to="/admin"
                    className="nav-link d-inline-flex align-items-center d-md-inline-block"
                    title={I18NextService.i18n.t("admin_settings")}
                    onMouseUp={linkEvent(this, handleCollapseClick)}
                  >
                    <Icon icon="settings" />
                    <span className="d-inline ms-1 d-md-none ms-md-0">
                      {I18NextService.i18n.t("admin_settings")}
                    </span>
                  </NavLink>
                </li>
              )}
              {person ? (
                <>
                  <li id="navMessages" className="nav-item">
                    <NavLink
                      className="nav-link d-inline-flex align-items-center d-md-inline-block"
                      to="/inbox"
                      title={I18NextService.i18n.t("unread_messages", {
                        count: Number(this.state.unreadInboxCount),
                        formattedCount: numToSI(this.state.unreadInboxCount),
                      })}
                      onMouseUp={linkEvent(this, handleCollapseClick)}
                    >
                      <Icon icon="bell" />
                      <span className="badge text-bg-light d-inline ms-1 d-md-none ms-md-0">
                        {I18NextService.i18n.t("unread_messages", {
                          count: Number(this.state.unreadInboxCount),
                          formattedCount: numToSI(this.state.unreadInboxCount),
                        })}
                      </span>
                      {this.state.unreadInboxCount > 0 && (
                        <span className="mx-1 badge text-bg-light">
                          {numToSI(this.state.unreadInboxCount)}
                        </span>
                      )}
                    </NavLink>
                  </li>
                  {UserService.Instance.moderatesSomething && (
                    <li id="navModeration" className="nav-item">
                      <NavLink
                        className="nav-link d-inline-flex align-items-center d-md-inline-block"
                        to="/reports"
                        title={I18NextService.i18n.t("unread_reports", {
                          count: Number(this.state.unreadReportCount),
                          formattedCount: numToSI(this.state.unreadReportCount),
                        })}
                        onMouseUp={linkEvent(this, handleCollapseClick)}
                      >
                        <Icon icon="shield" />
                        <span className="badge text-bg-light d-inline ms-1 d-md-none ms-md-0">
                          {I18NextService.i18n.t("unread_reports", {
                            count: Number(this.state.unreadReportCount),
                            formattedCount: numToSI(
                              this.state.unreadReportCount,
                            ),
                          })}
                        </span>
                        {this.state.unreadReportCount > 0 && (
                          <span className="mx-1 badge text-bg-light">
                            {numToSI(this.state.unreadReportCount)}
                          </span>
                        )}
                      </NavLink>
                    </li>
                  )}
                  {amAdmin() && (
                    <li id="navApplications" className="nav-item">
                      <NavLink
                        to="/registration_applications"
                        className="nav-link d-inline-flex align-items-center d-md-inline-block"
                        title={I18NextService.i18n.t(
                          "unread_registration_applications",
                          {
                            count: Number(this.state.unreadApplicationCount),
                            formattedCount: numToSI(
                              this.state.unreadApplicationCount,
                            ),
                          },
                        )}
                        onMouseUp={linkEvent(this, handleCollapseClick)}
                      >
                        <Icon icon="clipboard" />
                        <span className="badge text-bg-light d-inline ms-1 d-md-none ms-md-0">
                          {I18NextService.i18n.t(
                            "unread_registration_applications",
                            {
                              count: Number(this.state.unreadApplicationCount),
                              formattedCount: numToSI(
                                this.state.unreadApplicationCount,
                              ),
                            },
                          )}
                        </span>
                        {this.state.unreadApplicationCount > 0 && (
                          <span className="mx-1 badge text-bg-light">
                            {numToSI(this.state.unreadApplicationCount)}
                          </span>
                        )}
                      </NavLink>
                    </li>
                  )}
                  {person && (
                    <li id="dropdownUser" className="dropdown">
                      <button
                        type="button"
                        className="btn dropdown-toggle"
                        aria-expanded="false"
                        data-bs-toggle="dropdown"
                      >
                        {showAvatars() && person.avatar && (
                          <PictrsImage src={person.avatar} icon />
                        )}
                        {person.display_name ?? person.name}
                      </button>
                      <ul
                        className="dropdown-menu"
                        style={{ "min-width": "fit-content" }}
                      >
                        {/* User BCH Credit information */}
                        <li className="px-2 py-1">
                          <div className="d-flex align-items-center" style={{ color: '#8DC351' }}>
                            <svg 
                              width="16" 
                              height="16" 
                              viewBox="0 0 16 16" 
                              className="me-2" 
                              style={{ fill: "currentColor" }}
                            >
                              <path d="M8 0C3.59 0 0 3.59 0 8s3.59 8 8 8 8-3.59 8-8-3.59-8-8-8zm1.4 11.8c-.16.59-.82.85-1.39.58-.38-.18-.74-.58-.74-1.03 0-.19.05-.38.14-.55.09-.18.22-.33.38-.44.37-.27.88-.29 1.28-.07.4.22.64.65.63 1.09.01.15-.03.29-.09.42h.24zm-4.01-3.26c-.26-.13-.35-.5-.21-.76.14-.26.5-.37.76-.23.26.14.36.5.22.76-.14.26-.51.37-.77.23zm3.47-3.98c-.42-.15-.88-.08-1.26.14-.38.22-.66.6-.77 1.03l-.1.42h2.85l-.1-.42c-.11-.43-.4-.8-.78-1.03l.16-.14zm1.46 1.68h-4.55c-.25 0-.41.26-.32.49l.69 1.7c.14.33.41.66.77.89.43.27.94.37 1.43.27l.39-.08-1.11-2.54h2.28l-1.14 2.49.41.09c.5.1 1-.01 1.43-.28.35-.22.63-.55.76-.88l.69-1.7c.1-.23-.06-.46-.31-.46zm-4.4 4.58c.18-.11.39-.18.61-.19-.08-.21-.05-.45.07-.63.12-.18.32-.29.53-.29s.41.11.53.29c.12.18.16.42.07.63.22.01.43.08.61.19.18.11.33.27.41.47.08.2.09.41.03.61-.13.43-.58.72-1.05.67-.22-.02-.43-.11-.6-.26s-.28-.35-.3-.57c-.04-.47.27-.91.7-1.03.16-.05.33-.06.5-.02-.03-.1-.1-.17-.2-.21-.1-.04-.2-.04-.3 0-.1.04-.17.12-.2.21-.03.1-.03.2 0 .3.03.09.01.19-.06.25-.07.06-.17.08-.25.04s-.14-.12-.14-.21c0-.09.05-.17.13-.22z"/>
                            </svg>
                            <span className="fw-bold">보유 크레딧: {this.state.userCredit} BCH</span>
                          </div>
                        </li>
                        <li><hr className="dropdown-divider" /></li>
                        <li>
                          <NavLink
                            to={`/u/${person.name}`}
                            className="dropdown-item px-2"
                            title={I18NextService.i18n.t("profile")}
                            onMouseUp={linkEvent(this, handleCollapseClick)}
                          >
                            <Icon icon="user" classes="me-1" />
                            {I18NextService.i18n.t("profile")}
                          </NavLink>
                        </li>
                        <li>
                          <NavLink
                            to="/settings"
                            className="dropdown-item px-2"
                            title={I18NextService.i18n.t("settings")}
                            onMouseUp={linkEvent(this, handleCollapseClick)}
                          >
                            <Icon icon="settings" classes="me-1" />
                            {I18NextService.i18n.t("settings")}
                          </NavLink>
                        </li>
                        <li>
                          <hr className="dropdown-divider" />
                        </li>
                        <li>
                          <button
                            className="dropdown-item btn btn-link px-2"
                            onClick={linkEvent(this, handleLogOut)}
                          >
                            <Icon icon="log-out" classes="me-1" />
                            {I18NextService.i18n.t("logout")}
                          </button>
                        </li>
                      </ul>
                    </li>
                  )}
                </>
              ) : (
                <>
                  <li className="nav-item">
                    <NavLink
                      to="/login"
                      className="nav-link"
                      title={I18NextService.i18n.t("login")}
                      onMouseUp={linkEvent(this, handleCollapseClick)}
                    >
                      {I18NextService.i18n.t("login")}
                    </NavLink>
                  </li>
                  <li className="nav-item">
                    <NavLink
                      to="/signup"
                      className="nav-link"
                      title={I18NextService.i18n.t("sign_up")}
                      onMouseUp={linkEvent(this, handleCollapseClick)}
                    >
                      {I18NextService.i18n.t("sign_up")}
                    </NavLink>
                  </li>
                </>
              )}
            </ul>
          </div>
        </nav>
      </div>
    );
  }

  handleOutsideMenuClick(event: MouseEvent) {
    if (!this.mobileMenuRef.current?.contains(event.target as Node | null)) {
      handleCollapseClick(this);
    }
  }

  get currentLocation() {
    return this.context.router.history.location.pathname;
  }

  requestNotificationPermission() {
    if (UserService.Instance.myUserInfo) {
      document.addEventListener("lemmy-hydrated", function () {
        if (!Notification) {
          toast(I18NextService.i18n.t("notifications_error"), "danger");
          return;
        }

        if (Notification.permission !== "granted")
          Notification.requestPermission();
      });
    }
  }
}

// Global window extensions for BCH configuration
declare global {
  interface Window {
    __BCH_CONFIG__?: {
      API_KEY: string;
      API_URL: string;
      PAYMENT_URL: string;
    };
    checkLazyScripts?: () => void;
  }
}
