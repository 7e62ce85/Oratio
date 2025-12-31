import { Component } from "inferno";
import { T } from "inferno-i18next-dess";
import { Link } from "inferno-router";
import {
  AddAdmin,
  AddModToCommunity,
  BanFromCommunity,
  BanPerson,
  BlockPerson,
  CreatePostLike,
  CreatePostReport,
  DeletePost,
  EditPost,
  FeaturePost,
  HidePost,
  Language,
  LocalUserVoteDisplayMode,
  LockPost,
  MarkPostAsRead,
  PostResponse,
  PostView,
  PurgePerson,
  PurgePost,
  RemovePost,
  SavePost,
  TransferCommunity,
} from "lemmy-js-client";
import { I18NextService, UserService } from "../../services";
import { PostListing } from "./post-listing";
import { RequestState } from "../../services/HttpService";
import { getReportedContentIds, isPostReported } from "../../utils/cp-moderation";
import { canMod } from "@utils/roles";
// INACTIVE: Feed ads temporarily disabled
// import { AdBanner } from "../common/ad-banner";

interface PostListingsProps {
  posts: PostView[];
  allLanguages: Language[];
  siteLanguages: number[];
  showCommunity?: boolean;
  removeDuplicates?: boolean;
  enableDownvotes?: boolean;
  voteDisplayMode: LocalUserVoteDisplayMode;
  enableNsfw?: boolean;
  viewOnly?: boolean;
  ssrReportedPostIds?: Set<number>; // Pre-fetched CP reported IDs from SSR (optional, for performance)
  onPostEdit(form: EditPost): Promise<RequestState<PostResponse>>;
  onPostVote(form: CreatePostLike): Promise<RequestState<PostResponse>>;
  onPostReport(form: CreatePostReport): Promise<void>;
  onBlockPerson(form: BlockPerson): Promise<void>;
  onLockPost(form: LockPost): Promise<void>;
  onDeletePost(form: DeletePost): Promise<void>;
  onRemovePost(form: RemovePost): Promise<void>;
  onSavePost(form: SavePost): Promise<void>;
  onFeaturePost(form: FeaturePost): Promise<void>;
  onPurgePerson(form: PurgePerson): Promise<void>;
  onPurgePost(form: PurgePost): Promise<void>;
  onBanPersonFromCommunity(form: BanFromCommunity): Promise<void>;
  onBanPerson(form: BanPerson): Promise<void>;
  onAddModToCommunity(form: AddModToCommunity): Promise<void>;
  onAddAdmin(form: AddAdmin): Promise<void>;
  onTransferCommunity(form: TransferCommunity): Promise<void>;
  onMarkPostAsRead(form: MarkPostAsRead): Promise<void>;
  onHidePost(form: HidePost): Promise<void>;
}

interface PostListingsState {
  reportedPostIds: Set<number>;
  loadingReports: boolean;
}

export class PostListings extends Component<PostListingsProps, PostListingsState> {
  duplicatesMap = new Map<number, PostView[]>();

  constructor(props: any, context: any) {
    super(props, context);
    // Use SSR pre-fetched data if available, otherwise start with empty set
    const hasSSRData = !!props.ssrReportedPostIds;
    this.state = {
      reportedPostIds: props.ssrReportedPostIds || new Set(),
      loadingReports: !hasSSRData  // No need to load if SSR provided data
    };
    if (hasSSRData) {
      console.log(`💾 [CP Filter] Using ${props.ssrReportedPostIds.size} pre-fetched reported IDs from SSR`);
    }
  }

  async componentDidMount() {
    // Only fetch if we don't have SSR data
    if (this.state.loadingReports) {
      console.log("🔄 [CP Filter] PostListings mounted - fetching reported content...");
      const startTime = performance.now();
      await this.fetchReportedContent();
      const elapsed = performance.now() - startTime;
      console.log(`✅ [CP Filter] Initial fetch completed in ${elapsed.toFixed(1)}ms`);
    } else {
      console.log(`💾 [CP Filter] PostListings mounted - using ${this.state.reportedPostIds.size} SSR-provided reported IDs (no fetch needed)`);
    }
    
    // Refresh reported content every 30 seconds
    if (typeof window !== 'undefined') {
      this.reportRefreshInterval = window.setInterval(() => {
        console.log("🔄 [CP Filter] Periodic refresh (30s interval)");
        this.fetchReportedContent();
      }, 30000);
    }
  }

  componentWillUnmount() {
    if (this.reportRefreshInterval) {
      clearInterval(this.reportRefreshInterval);
    }
  }

  reportRefreshInterval?: number;

  async fetchReportedContent() {
    const fetchStart = performance.now();
    try {
      console.log("📡 [CP Filter] Calling getReportedContentIds()...");
      const { posts } = await getReportedContentIds();
      const fetchElapsed = performance.now() - fetchStart;
      console.log(`✅ [CP Filter] Got ${posts.size} reported posts (${fetchElapsed.toFixed(1)}ms)`);
      this.setState({ reportedPostIds: posts, loadingReports: false });
    } catch (error) {
      const fetchElapsed = performance.now() - fetchStart;
      console.error(`❌ [CP Filter] Error after ${fetchElapsed.toFixed(1)}ms:`, error);
      this.setState({ loadingReports: false });
    }
  }

  get posts() {
    const user = UserService.Instance.myUserInfo;
    const rawPosts = this.props.removeDuplicates
      ? this.removeDuplicates()
      : this.props.posts;
    
    // CRITICAL: If still loading reported content list, return empty array
    // This prevents "flash" of CP content before filter is ready
    if (this.state.loadingReports) {
      console.log("⏳ [CP Filter] Still loading reported IDs - showing no posts yet");
      return [];
    }
    
    // Filter posts based on hidden status and CP reports
    return rawPosts.filter(post_view => {
      // IMPORTANT: Don't filter hidden posts here - Lemmy handles this
      // Hidden posts should be visible in user's own profile but not in feeds
      // This is handled by Lemmy's backend API response, not frontend filtering
      
      // Filter out CP reported posts (only pending reports) for non-moderators
      if (!this.state.reportedPostIds.has(post_view.post.id)) {
        return true; // Not reported or report was resolved, show it
      }
      
      // Post is in reported list - check if user is moderator/admin
      if (!user) {
        return false; // Not logged in, hide reported content
      }
      
      // Check if user is moderator of the community or admin
      const isModerator = post_view.community.moderators?.some(
        mod => mod.moderator.id === user.local_user_view.person.id
      );
      const isAdmin = user.local_user_view.person.admin;
      
      // Show reported content only to moderators and admins
      return isModerator || isAdmin;
    });
  }

  render() {
    return (
      <div className="post-listings">
        {this.posts.length > 0 ? (
          this.posts.map((post_view, idx) => (
            <>
              <PostListing
                post_view={post_view}
                crossPosts={this.duplicatesMap.get(post_view.post.id)}
                showCommunity={this.props.showCommunity}
                enableDownvotes={this.props.enableDownvotes}
                voteDisplayMode={this.props.voteDisplayMode}
                enableNsfw={this.props.enableNsfw}
                viewOnly={this.props.viewOnly}
                allLanguages={this.props.allLanguages}
                siteLanguages={this.props.siteLanguages}
                onPostEdit={this.props.onPostEdit}
                onPostVote={this.props.onPostVote}
                onPostReport={this.props.onPostReport}
                onBlockPerson={this.props.onBlockPerson}
                onLockPost={this.props.onLockPost}
                onDeletePost={this.props.onDeletePost}
                onRemovePost={this.props.onRemovePost}
                onSavePost={this.props.onSavePost}
                onFeaturePost={this.props.onFeaturePost}
                onPurgePerson={this.props.onPurgePerson}
                onPurgePost={this.props.onPurgePost}
                onBanPersonFromCommunity={this.props.onBanPersonFromCommunity}
                onBanPerson={this.props.onBanPerson}
                onAddModToCommunity={this.props.onAddModToCommunity}
                onAddAdmin={this.props.onAddAdmin}
                onTransferCommunity={this.props.onTransferCommunity}
                onMarkPostAsRead={this.props.onMarkPostAsRead}
                onHidePost={this.props.onHidePost}
              />
              {idx + 1 !== this.posts.length && <hr className="my-3" />}
              {/* INACTIVE: Feed ads temporarily disabled (2025-10-23) */}
              {/* Add advertisement every 3 posts for optimal balance */}
              {/* {(idx + 1) % 3 === 0 && idx + 1 !== this.posts.length && (
                <div className="my-4">
                  <AdBanner position="sidebar" size="large" section="feed" />
                </div>
              )} */}
            </>
          ))
        ) : (
          <>
            <div>{I18NextService.i18n.t("no_posts")}</div>
            {this.props.showCommunity && (
              <T i18nKey="subscribe_to_communities">
                #<Link to="/communities">#</Link>
              </T>
            )}
          </>
        )}
      </div>
    );
  }

  removeDuplicates(): PostView[] {
    // Must use a spread to clone the props, because splice will fail below otherwise.
    const posts = [...this.props.posts].filter(empty => empty);

    // A map from post url to list of posts (dupes)
    const urlMap = new Map<string, PostView[]>();

    // Loop over the posts, find ones with same urls
    for (const pv of posts) {
      const url = pv.post.url;
      if (
        !pv.post.deleted &&
        !pv.post.removed &&
        !pv.community.deleted &&
        !pv.community.removed &&
        url
      ) {
        if (!urlMap.get(url)) {
          urlMap.set(url, [pv]);
        } else {
          urlMap.get(url)?.push(pv);
        }
      }
    }

    // Sort by oldest
    // Remove the ones that have no length
    for (const e of urlMap.entries()) {
      if (e[1].length === 1) {
        urlMap.delete(e[0]);
      } else {
        e[1].sort((a, b) => a.post.published.localeCompare(b.post.published));
      }
    }

    for (let i = 0; i < posts.length; i++) {
      const pv = posts[i];
      const url = pv.post.url;
      if (url) {
        const found = urlMap.get(url);
        if (found) {
          // If its the oldest, add
          if (pv.post.id === found[0].post.id) {
            this.duplicatesMap.set(pv.post.id, found.slice(1));
          }
          // Otherwise, delete it
          else {
            posts.splice(i--, 1);
          }
        }
      }
    }

    return posts;
  }
}
