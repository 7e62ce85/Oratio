"""
Instagram collector — scrapes public posts from hashtag or profile pages.

Instagram has no free public API for arbitrary content scraping.
This collector uses the public web endpoint that returns JSON-LD / shared_data
for public hashtag and profile pages.

**Important**: Instagram aggressively blocks scraping. This collector:
  - Uses realistic browser headers
  - Respects rate limits (1 request/source/cycle)
  - Only accesses fully public pages
  - May stop working if Instagram changes their frontend

Environment variables:
  (none required — scrapes public pages only)

Config keys:
  hashtags      – list of hashtags to scrape (e.g. ["memes", "funny"])
  profiles      – list of public profile usernames (e.g. ["memes", "9gag"])
  limit         – max posts to return (default 20)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

from models import NormalizedPost, NormalizedComment
from .base import BaseCollector

logger = logging.getLogger("content_importer.instagram")

INSTAGRAM_BASE = "https://www.instagram.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Instagram public GraphQL API (web frontend)
GRAPHQL_URL = "https://www.instagram.com/graphql/query/"
# Query hash for tag media (may change — fallback to HTML parsing)
TAG_QUERY_HASH = "9b498c08113f1a09f78c6c4f02e55f4f"
PROFILE_QUERY_HASH = "e769aa130647d2571c27c44596cb68c6"


class InstagramCollector(BaseCollector):
    """
    Collect public posts from Instagram hashtag/profile pages.

    Config keys:
      hashtags  – list of hashtag strings (without #) to scrape
      profiles  – list of public usernames to scrape
      limit     – max posts to return (default 20)
    """

    def fetch(self) -> list[NormalizedPost]:
        limit = self.config.get("limit", 20)
        hashtags = self.config.get("hashtags", [])
        profiles = self.config.get("profiles", [])

        all_posts: list[NormalizedPost] = []

        for tag in hashtags:
            posts = self._fetch_hashtag(tag, limit)
            all_posts.extend(posts)
            if len(all_posts) >= limit:
                break

        for profile in profiles:
            if len(all_posts) >= limit:
                break
            posts = self._fetch_profile(profile, limit - len(all_posts))
            all_posts.extend(posts)

        # Deduplicate by URL
        seen: set[str] = set()
        unique: list[NormalizedPost] = []
        for p in all_posts:
            if p.url not in seen:
                seen.add(p.url)
                unique.append(p)
        unique = unique[:limit]

        # Sort by score descending
        unique.sort(key=lambda p: p.score, reverse=True)
        logger.info("Instagram: fetched %d total posts", len(unique))
        return unique

    def _get_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        })
        return session

    # ── Hashtag page ────────────────────────────────────────────

    def _fetch_hashtag(self, tag: str, limit: int) -> list[NormalizedPost]:
        """Fetch recent top posts from a hashtag page."""
        session = self._get_session()
        url = f"{INSTAGRAM_BASE}/explore/tags/{tag}/"

        try:
            resp = session.get(url, timeout=20)
            if resp.status_code in (401, 403, 429):
                logger.info("Instagram: hashtag #%s blocked (status %d) — Instagram aggressively blocks scraping from servers", tag, resp.status_code)
                return []
            resp.raise_for_status()
        except Exception as e:
            logger.info("Instagram: hashtag #%s fetch failed: %s — Instagram blocks most server IPs", tag, e)
            return []

        return self._extract_posts_from_html(resp.text, limit, f"#{tag}")

    # ── Profile page ────────────────────────────────────────────

    def _fetch_profile(self, username: str, limit: int) -> list[NormalizedPost]:
        """Fetch recent posts from a public profile page."""
        session = self._get_session()
        url = f"{INSTAGRAM_BASE}/{username}/"

        try:
            resp = session.get(url, timeout=20)
            if resp.status_code in (401, 403, 429):
                logger.info("Instagram: profile @%s blocked (status %d) — Instagram aggressively blocks scraping from servers", username, resp.status_code)
                return []
            resp.raise_for_status()
        except Exception as e:
            logger.info("Instagram: profile @%s fetch failed: %s", username, e)
            return []

        return self._extract_posts_from_html(resp.text, limit, f"@{username}")

    # ── Shared HTML/JSON parser ──────────────────────────────────

    def _extract_posts_from_html(
        self, html: str, limit: int, label: str
    ) -> list[NormalizedPost]:
        """
        Extract posts from Instagram HTML.

        Instagram embeds structured data in:
          1. window._sharedData = {...};  (legacy, may be removed)
          2. <script type="application/ld+json">  (JSON-LD)
          3. Inline <script> with "edge_" media data
        """
        posts: list[NormalizedPost] = []

        # Strategy 1: window._sharedData
        shared_data = self._extract_shared_data(html)
        if shared_data:
            posts = self._parse_shared_data(shared_data, limit, label)

        # Strategy 2: JSON-LD structured data
        if not posts:
            posts = self._parse_json_ld(html, limit, label)

        # Strategy 3: Regex extraction of shortcodes from HTML
        if not posts:
            posts = self._parse_shortcodes(html, limit, label)

        if not posts:
            logger.debug("Instagram: no posts extracted from %s", label)

        return posts

    def _extract_shared_data(self, html: str) -> Optional[dict]:
        """Extract window._sharedData JSON from HTML."""
        match = re.search(
            r"window\._sharedData\s*=\s*(\{.*?\});</script>",
            html,
            re.DOTALL,
        )
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def _parse_shared_data(
        self, data: dict, limit: int, label: str
    ) -> list[NormalizedPost]:
        """Parse posts from _sharedData structure."""
        posts: list[NormalizedPost] = []

        # Navigate to media edges
        edges: list[dict] = []

        # Hashtag page path
        tag_page = (
            data.get("entry_data", {})
            .get("TagPage", [{}])[0] if "TagPage" in data.get("entry_data", {}) else None
        )
        if tag_page:
            sections = (
                tag_page.get("graphql", {})
                .get("hashtag", {})
                .get("edge_hashtag_to_top_posts", {})
                .get("edges", [])
            )
            edges.extend(sections)

        # Profile page path
        profile_page = (
            data.get("entry_data", {})
            .get("ProfilePage", [{}])[0] if "ProfilePage" in data.get("entry_data", {}) else None
        )
        if profile_page:
            user_media = (
                profile_page.get("graphql", {})
                .get("user", {})
                .get("edge_owner_to_timeline_media", {})
                .get("edges", [])
            )
            edges.extend(user_media)

        for edge in edges[:limit]:
            node = edge.get("node", {})
            post = self._node_to_post(node, label)
            if post:
                posts.append(post)

        return posts

    def _parse_json_ld(
        self, html: str, limit: int, label: str
    ) -> list[NormalizedPost]:
        """Extract posts from JSON-LD blocks."""
        posts: list[NormalizedPost] = []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []

        soup = BeautifulSoup(html, "html.parser")
        ld_scripts = soup.select('script[type="application/ld+json"]')

        for script in ld_scripts:
            try:
                ld_data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            if isinstance(ld_data, list):
                for item in ld_data:
                    if isinstance(item, dict) and item.get("@type") in ("ImageObject", "VideoObject", "SocialMediaPosting"):
                        post = self._ld_to_post(item, label)
                        if post:
                            posts.append(post)
            elif isinstance(ld_data, dict) and ld_data.get("@type") in ("ImageObject", "VideoObject", "SocialMediaPosting"):
                post = self._ld_to_post(ld_data, label)
                if post:
                    posts.append(post)

        return posts[:limit]

    def _parse_shortcodes(
        self, html: str, limit: int, label: str
    ) -> list[NormalizedPost]:
        """Last resort: extract shortcode URLs from HTML."""
        posts: list[NormalizedPost] = []
        seen: set[str] = set()

        # Find /p/SHORTCODE/ patterns
        for match in re.finditer(r'/p/([A-Za-z0-9_-]{11})', html):
            if len(posts) >= limit:
                break
            shortcode = match.group(1)
            if shortcode in seen:
                continue
            seen.add(shortcode)

            url = f"{INSTAGRAM_BASE}/p/{shortcode}/"
            posts.append(
                NormalizedPost(
                    title=f"Instagram post ({label})",
                    url=url,
                    body=f"Source: {label}",
                    source="instagram",
                    source_community="Instagram",
                    score=0,
                    published_at=datetime.now(timezone.utc),
                    thumbnail_url=None,
                    author=None,
                    comment_count=0,
                    tags=[],
                    source_permalink=url,
                    source_id=shortcode,
                )
            )

        return posts

    def _node_to_post(self, node: dict, label: str) -> Optional[NormalizedPost]:
        """Convert an Instagram GraphQL media node to NormalizedPost."""
        shortcode = node.get("shortcode", "")
        if not shortcode:
            return None

        url = f"{INSTAGRAM_BASE}/p/{shortcode}/"

        # Caption
        caption_edges = (
            node.get("edge_media_to_caption", {}).get("edges", [])
        )
        caption = ""
        if caption_edges:
            caption = caption_edges[0].get("node", {}).get("text", "")

        title = caption[:140] if caption else f"Instagram post ({label})"
        if caption and len(caption) > 140:
            title += "…"

        likes = node.get("edge_liked_by", {}).get("count", 0)
        if not likes:
            likes = node.get("edge_media_preview_like", {}).get("count", 0)
        comments_count = node.get("edge_media_to_comment", {}).get("count", 0)

        thumbnail = node.get("thumbnail_src") or node.get("display_url")
        author = node.get("owner", {}).get("username")

        ts = node.get("taken_at_timestamp", 0)
        try:
            published = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError):
            published = datetime.now(timezone.utc)

        return NormalizedPost(
            title=title[:200],
            url=url,
            body=caption[:500] if caption else f"Source: {label}",
            source="instagram",
            source_community="Instagram",
            score=likes,
            published_at=published,
            thumbnail_url=thumbnail,
            author=author,
            comment_count=comments_count,
            tags=[],
            source_permalink=url,
            source_id=shortcode,
        )

    def _ld_to_post(self, ld: dict, label: str) -> Optional[NormalizedPost]:
        """Convert a JSON-LD media item to NormalizedPost."""
        url = ld.get("mainEntityOfPage", ld.get("url", ""))
        if not url:
            return None

        caption = ld.get("caption", ld.get("articleBody", ""))
        title = caption[:140] if caption else f"Instagram post ({label})"
        author = None
        author_data = ld.get("author")
        if isinstance(author_data, dict):
            author = author_data.get("alternateName") or author_data.get("name")

        thumbnail = ld.get("thumbnail", {})
        thumb_url = thumbnail.get("url") if isinstance(thumbnail, dict) else None

        return NormalizedPost(
            title=title[:200],
            url=url,
            body=caption[:500] if caption else f"Source: {label}",
            source="instagram",
            source_community="Instagram",
            score=0,
            published_at=datetime.now(timezone.utc),
            thumbnail_url=thumb_url,
            author=author,
            comment_count=0,
            tags=[],
            source_permalink=url,
        )

    # ── Comment fetching (limited) ──────────────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Attempt to fetch comments from an Instagram post page.

        Instagram makes this very difficult without authentication.
        We try to extract from the post HTML if it's publicly embedded.
        """
        permalink = getattr(post, "source_permalink", None) or post.url
        if not permalink:
            return []

        session = self._get_session()
        try:
            resp = session.get(permalink, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            logger.debug("Instagram comment fetch failed for %s: %s", permalink, e)
            return []

        comments: list[NormalizedComment] = []
        html = resp.text

        # Try to extract from _sharedData
        shared = self._extract_shared_data(html)
        if shared:
            try:
                post_page = shared.get("entry_data", {}).get("PostPage", [{}])[0]
                media = post_page.get("graphql", {}).get("shortcode_media", {})
                comment_edges = (
                    media.get("edge_media_to_parent_comment", {}).get("edges", [])
                    or media.get("edge_media_to_comment", {}).get("edges", [])
                )
                scored: list[tuple[int, str, str]] = []
                for edge in comment_edges:
                    node = edge.get("node", {})
                    text = node.get("text", "")
                    if not text or re.search(r"https?://", text):
                        continue
                    author = node.get("owner", {}).get("username", "Unknown")
                    likes = node.get("edge_liked_by", {}).get("count", 0)
                    scored.append((likes, author, text))

                scored.sort(key=lambda x: x[0], reverse=True)
                for score_val, author, text in scored[:limit]:
                    comments.append(
                        NormalizedComment(
                            author=author,
                            body=text[:500],
                            score=score_val,
                            source="instagram",
                        )
                    )
            except (KeyError, IndexError):
                pass

        if comments:
            logger.info("Instagram: fetched %d comments for %s", len(comments), permalink)
        return comments
