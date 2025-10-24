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
import { UserBadges } from "../common/user-badges";
import { checkUserHasGoldBadgeSync, updateCreditCache } from "../../utils/bch-payment";
import { Subscription } from "rxjs";
import { tippyMixin } from "../mixins/tippy-mixin";
import "./bch-button.css";

// 기본값은 실제 운영 도메인의 서브경로로 설정 (window.__BCH_CONFIG__가 우선)
const BCH_PAYMENT_URL = "https://oratio.space/payments/";
const BCH_API_URL = "https://oratio.space/payments/api/user_credit";

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

interface NavbarProps {
  siteRes?: GetSiteResponse;
}

interface NavbarState {
  onSiteBanner?(url: string): any;
  unreadInboxCount: number;
  unreadReportCount: number;
  unreadApplicationCount: number;
  userCredit: number;
  isDarkMode: boolean;
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
  creditUpdateListener?: () => void;

  state: NavbarState = {
    unreadInboxCount: 0,
    unreadReportCount: 0,
    unreadApplicationCount: 0,
    userCredit: 0,
    isDarkMode: false,
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
      
      // Initialize dark mode detection
      this.initializeDarkModeDetection();
      
      // Listen for credit cache updates to refresh badge display
      this.creditUpdateListener = () => {
        this.forceUpdate();
      };
      
      if (typeof window !== 'undefined') {
        window.addEventListener('bch-credit-cache-updated', this.creditUpdateListener);
      }
      
      // Fetch user credit if logged in
      if (UserService.Instance.myUserInfo) {
        this.fetchUserCredit();
      } else {
        // If user info not available yet, retry after a short delay
        // This handles cases where login is in progress
        setTimeout(() => {
          if (UserService.Instance.myUserInfo && this.state.userCredit === 0) {
            this.fetchUserCredit();
          }
        }, 1000);
      }
    }
  }
  
  // Initialize dark mode detection and listener
  initializeDarkModeDetection() {
    if (!isBrowser()) return;
    
    // Check initial dark mode state
    const isDarkMode = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    this.setState({ isDarkMode });
    
    // Listen for changes
    if (window.matchMedia) {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const handleChange = (e: MediaQueryListEvent) => {
        this.setState({ isDarkMode: e.matches });
      };
      
      // Modern browsers
      if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener('change', handleChange);
      } else {
        // Fallback for older browsers
        mediaQuery.addListener(handleChange);
      }
    }
  }
  
  // Get dynamic BCH button styles based on theme
  getBCHButtonStyles() {
    const baseStyles = {
      padding: "5px 10px",
      borderRadius: "6px",
      fontWeight: "bold" as const,
      marginLeft: "10px",
      transition: "all 0.3s ease",
      border: "2px solid",
      textDecoration: "none",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      cursor: "pointer",
      outline: "none",
    };

    if (this.state.isDarkMode) {
      // Dark mode: lighter, more vibrant colors for better visibility
      return {
        ...baseStyles,
        backgroundColor: "#4CAF50",
        borderColor: "#4CAF50",
        color: "#ffffff",
        boxShadow: "0 2px 4px rgba(76, 175, 80, 0.3)",
      };
    } else {
      // Light mode: standard BCH green with good contrast
      return {
        ...baseStyles,
        backgroundColor: "#2E7D32", // Darker green for better contrast
        borderColor: "#2E7D32", 
        color: "#ffffff",
        boxShadow: "0 2px 4px rgba(46, 125, 50, 0.3)",
      };
    }
  }
  
  // Get hover/focus styles for the BCH button
  getBCHButtonHoverClass() {
    return this.state.isDarkMode ? 'bch-button-dark' : 'bch-button-light';
  }
  
  // Fetch user credit from BCH service
  async fetchUserCredit() {
    try {
      // Try to get user info from UserService
      let person = UserService.Instance.myUserInfo?.local_user_view.person;
      
      if (!person) {
        // Retry once after a short delay in case login is still in progress
        setTimeout(() => {
          const retryPerson = UserService.Instance.myUserInfo?.local_user_view.person;
          if (retryPerson && this.state.userCredit === 0) {
            this.fetchUserCredit();
          }
        }, 2000);
        
        return;
      }
      
      // Fetch credit balance for display
      const creditApiUrl = `${getBCHAPIUrl()}/${person.name}`;
      
      const creditResponse = await fetch(creditApiUrl, {
        headers: {
          'X-API-Key': getApiKey() || ""
        }
      });
      
      if (creditResponse.ok) {
        const creditData = await creditResponse.json();
        
        if (creditData.credit_balance !== undefined) {
          this.setState({ userCredit: creditData.credit_balance });
        }
      }
      
      // Update membership status to cache
      const membershipApiUrl = `${getBCHAPIUrl()}/api/membership/status/${person.name}`;
      
      const membershipResponse = await fetch(membershipApiUrl, {
        headers: {
          'X-API-Key': getApiKey() || ""
        }
      });
      
      if (membershipResponse.ok) {
        const membershipData = await membershipResponse.json();
        
        if (membershipData.status === 'active') {
          // Update the cache so components using checkUserHasGoldBadgeSync will get the value
          updateCreditCache(person.id, 1.0); // 1.0 = has active membership
        } else {
          updateCreditCache(person.id, 0.0); // 0.0 = no active membership
        }
      }
      
    } catch (error) {
      console.error("[BCH] Error fetching user credit:", error);
    }
  }

  componentDidUpdate(_prevProps: NavbarProps) {
    // Check if user info became available in UserService
    // This handles the case where user logs in but BCH credit wasn't fetched
    if (UserService.Instance.myUserInfo && this.state.userCredit === 0) {
      this.fetchUserCredit();
    }
  }

  componentWillUnmount() {
    document.removeEventListener("mouseup", this.handleOutsideMenuClick);
    this.unreadInboxCountSubscription.unsubscribe();
    this.unreadReportCountSubscription.unsubscribe();
    this.unreadApplicationCountSubscription.unsubscribe();
    
    // Remove credit update listener
    if (typeof window !== 'undefined' && this.creditUpdateListener) {
      window.removeEventListener('bch-credit-cache-updated', this.creditUpdateListener);
    }
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
              {/* Bitcoin Cash payment button - only show for logged in users */}
              {person && (
              <li id="navBCH" className="nav-item">
                <a
                  href={getBCHPaymentUrl()}
                  className="nav-link d-inline-flex align-items-center d-md-inline-block bch-button-base bch-button-auto"
                  title="Add Bitcoin Cash"
                  target="_blank"
                  rel="noopener"
                  onMouseUp={linkEvent(this, handleCollapseClick)}
                  aria-label="Add Bitcoin Cash to your account"
                  tabIndex={0}
                >
                  <svg 
                    xmlns="http://www.w3.org/2000/svg"
                    width="24" 
                    height="24" 
                    viewBox="0 0 32 32" 
                    className="me-1 bch-icon" 
                    aria-hidden="true"
                    role="img"
                    style={{ flexShrink: 0 }}
                  >
                    <circle cx="16" cy="16" r="16" fill="#8DC351"/>
                    <path fill="#FFFFFF" d="M21.207 10.534c-.776-1.972-2.722-2.15-4.988-1.71l-.807-2.813-1.712.491.786 2.74c-.45.128-.908.27-1.363.41l-.79-2.758-1.711.49.805 2.813c-.368.114-.73.226-1.085.328l-.003-.01-2.362.677.525 1.83s1.258-.388 1.243-.358c.694-.199 1.035.139 1.2.468l.92 3.204c.047-.013.11-.029.184-.04l-.181.052 1.287 4.49c.032.227.004.612-.48.752.027.013-1.246.356-1.246.356l.247 2.143 2.228-.64c.415-.117.825-.227 1.226-.34l.817 2.845 1.71-.49-.807-2.815a65.74 65.74 0 001.372-.38l.802 2.803 1.713-.491-.814-2.84c2.831-.991 4.638-2.294 4.113-5.07-.422-2.234-1.724-2.912-3.471-2.836.848-.79 1.213-1.858.642-3.3zm-.65 6.77c.61 2.127-3.1 2.929-4.26 3.263l-1.081-3.77c1.16-.333 4.704-1.71 5.34.508zm-2.322-5.09c.554 1.935-2.547 2.58-3.514 2.857l-.98-3.419c.966-.277 3.915-1.455 4.494.563z"/>
                  </svg>
                  <span className="d-inline ms-1 d-md-inline ms-md-1">
                    Add BCH
                  </span>
                </a>
              </li>
              )}
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
                        <span className="d-inline-flex align-items-center">
                          {person.display_name ?? person.name}
                          <UserBadges
                            classNames="ms-1"
                            isPremium={checkUserHasGoldBadgeSync(person)}
                          />
                        </span>
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
                            <span className="fw-bold">Credits: {this.state.userCredit} BCH</span>
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
                          <NavLink
                            to="/wallet"
                            className="dropdown-item px-2"
                            title="My Wallet"
                            onMouseUp={linkEvent(this, handleCollapseClick)}
                          >
                            <Icon icon="wallet" classes="me-1" />
                            My Wallet
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
