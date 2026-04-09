"""
9gag collector — fetches hot/trending posts via 9gag's internal JSON API.

9gag's web frontend uses a JSON API internally:
  GET https://9gag.com/v1/group-posts/group/default/type/hot?...

This is not officially documented but stable and returns structured JSON
with post metadata, scores, and comment counts.

No API key or authentication required.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

from models import NormalizedPost, NormalizedComment
from .base import BaseCollector

logger = logging.getLogger("content_importer.ninegag")

NINEGAG_BASE = "https://9gag.com"
NINEGAG_API = "https://9gag.com/v1"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class NineGagCollector(BaseCollector):
    """
    Collect hot/trending posts from 9gag.

    Config keys:
      section  – "hot", "trending", "fresh" (default "hot")
      tag      – optional tag/topic (e.g. "funny", "animals")
      limit    – max posts to return (default 20)
    """

    def fetch(self) -> list[NormalizedPost]:
        limit = self.config.get("limit", 20)
        section = self.config.get("section", "hot")
        tag = self.config.get("tag", "")

        # Try internal JSON API first
        posts = self._fetch_api(section, tag, limit)

        # Fallback to HTML scraping
        if not posts:
            posts = self._fetch_html(section, tag, limit)

        return posts

    # ── JSON API ─────────────────────────────────────────────────

    def _fetch_api(self, section: str, tag: str, limit: int) -> list[NormalizedPost]:
        """Fetch posts from 9gag's internal JSON endpoint."""
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Referer": f"{NINEGAG_BASE}/",
        }

        if tag:
            url = f"{NINEGAG_API}/group-posts/group/{tag}/type/{section}"
        else:
            url = f"{NINEGAG_API}/group-posts/group/default/type/{section}"

        params = {
            "c": "10",  # count per page
        }

        all_posts: list[NormalizedPost] = []
        cursor = ""
        max_pages = 3  # Fetch up to 3 pages

        for _ in range(max_pages):
            if len(all_posts) >= limit:
                break

            if cursor:
                params["after"] = cursor

            try:
                resp = requests.get(url, headers=headers, params=params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning("9gag API fetch failed: %s", e)
                break

            posts_data = data.get("data", {}).get("posts", [])
            if not posts_data:
                break

            for post_data in posts_data:
                if len(all_posts) >= limit:
                    break
                post = self._parse_api_post(post_data)
                if post:
                    all_posts.append(post)

            # Pagination cursor
            cursor = data.get("data", {}).get("nextCursor", "")
            if not cursor:
                break

        logger.info("9gag API: fetched %d posts", len(all_posts))
        return all_posts

    def _parse_api_post(self, post_data: dict) -> Optional[NormalizedPost]:
        """Parse a single post from the 9gag JSON API response."""
        title = post_data.get("title", "")
        if not title or len(title) < 3:
            return None

        post_id = post_data.get("id", "")
        url = post_data.get("url", f"{NINEGAG_BASE}/gag/{post_id}")

        # Engagement
        upvotes = post_data.get("upVoteCount", 0)
        downvotes = post_data.get("downVoteCount", 0)
        score = upvotes - downvotes
        comment_count = post_data.get("commentsCount", 0)

        # Media
        images = post_data.get("images", {})
        thumbnail = None
        media_url = None

        # Try different image formats
        for key in ("image700", "image460", "imageFbThumbnail"):
            if key in images:
                thumbnail = images[key].get("url")
                if thumbnail:
                    break

        # For animated/video posts
        if "image460sv" in images:
            media_url = images["image460sv"].get("url")

        # Description / body
        desc = post_data.get("description", "")
        section_name = post_data.get("postSection", {}).get("name", "")
        body_parts = []
        if desc:
            body_parts.append(desc[:300])
        if section_name:
            body_parts.append(f"Section: {section_name}")
        body = " · ".join(body_parts) if body_parts else ""

        # Tags
        tags = []
        for tag_data in (post_data.get("tags") or []):
            if isinstance(tag_data, dict):
                tags.append(tag_data.get("key", ""))
            elif isinstance(tag_data, str):
                tags.append(tag_data)

        # Creator
        creator = post_data.get("creator", {})
        author = None
        if isinstance(creator, dict):
            author = creator.get("username") or creator.get("displayName")

        # Timestamp
        ts = post_data.get("creationTs", 0)
        try:
            published = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError):
            published = datetime.now(timezone.utc)

        # Post type
        post_type = post_data.get("type", "Photo")

        return NormalizedPost(
            title=title[:200],
            url=url,
            body=body or f"{post_type} · ⬆️ {upvotes:,} · 💬 {comment_count:,}",
            source="9gag",
            source_community="9gag",
            score=score,
            published_at=published,
            thumbnail_url=thumbnail,
            media_url=media_url,
            author=author,
            comment_count=comment_count,
            tags=tags[:5],
            source_permalink=url,
            source_id=post_id,
        )

    # ── HTML scraping fallback ──────────────────────────────────

    def _fetch_html(self, section: str, tag: str, limit: int) -> list[NormalizedPost]:
        """Scrape 9gag HTML page as fallback."""
        if tag:
            url = f"{NINEGAG_BASE}/{tag}/{section}"
        else:
            url = f"{NINEGAG_BASE}/{section}"

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning("9gag HTML fetch failed: %s", e)
            return []

        # 9gag embeds post data as JSON in a <script> tag
        # Look for window.__INITIAL_STATE__ or similar
        posts: list[NormalizedPost] = []

        # Method 1: Extract from __INIT_DATA__ or similar embedded JSON
        for pattern in [
            r'window\.__INIT_DATA__\s*=\s*(\{.*?\});\s*</script>',
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*</script>',
            r'"listPosts"\s*:\s*(\[.*?\])\s*[,}]',
        ]:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    # Try to find posts in the data structure
                    if isinstance(data, list):
                        for item in data[:limit]:
                            post = self._parse_api_post(item)
                            if post:
                                posts.append(post)
                    elif isinstance(data, dict):
                        # Navigate common 9gag data structures
                        for key in ("posts", "data", "items"):
                            items = data.get(key, [])
                            if isinstance(items, list):
                                for item in items[:limit]:
                                    post = self._parse_api_post(item)
                                    if post:
                                        posts.append(post)
                                if posts:
                                    break
                except (json.JSONDecodeError, TypeError):
                    continue
                if posts:
                    break

        # Method 2: Simple regex extraction of gag IDs and titles
        if not posts:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")

                articles = soup.select("article, [id^='jsid-entry-']")
                for art in articles[:limit]:
                    title_el = art.select_one("h1 a, h2 a, .post-title a")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    href = title_el.get("href", "")
                    if not title or not href:
                        continue
                    if href.startswith("/"):
                        href = f"{NINEGAG_BASE}{href}"

                    img = art.select_one("img")
                    thumb = img.get("src") if img else None

                    posts.append(
                        NormalizedPost(
                            title=title[:200],
                            url=href,
                            body="",
                            source="9gag",
                            source_community="9gag",
                            score=0,
                            published_at=datetime.now(timezone.utc),
                            thumbnail_url=thumb,
                            author=None,
                            comment_count=0,
                            tags=[],
                            source_permalink=href,
                        )
                    )
            except ImportError:
                pass

        logger.info("9gag HTML: fetched %d posts", len(posts))
        return posts

    # ── Comment fetching ────────────────────────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top comments for a 9gag post.

        Uses the 9gag comment CDN API:
          GET https://comment-cdn.9gag.com/v2/cacheable/comment-list.json?
              appId=a_dd8f2b7d304a10edaf6f29517ea0ca4100a43d1b&
              url=<post_url>&count=10&order=score&direction=desc&level=1
        """
        post_url = getattr(post, "source_permalink", None) or post.url
        if not post_url:
            return []

        # Normalize URL to http://9gag.com/gag/XXX (the canonical form the API expects)
        post_url = post_url.replace("https://9gag.com", "http://9gag.com")
        if not post_url.startswith("http://9gag.com"):
            # Try to extract gag ID and rebuild
            m = re.search(r'/gag/(\w+)', post_url)
            if m:
                post_url = f"http://9gag.com/gag/{m.group(1)}"

        # 9gag comment CDN API (the actual endpoint, not 9gag.com/v1)
        comment_api = "https://comment-cdn.9gag.com/v2/cacheable/comment-list.json"
        params = {
            "appId": "a_dd8f2b7d304a10edaf6f29517ea0ca4100a43d1b",
            "url": post_url,
            "count": str(max(limit * 2, 10)),
            "order": "score",
            "direction": "desc",
            "level": "1",
        }

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Referer": post_url,
        }

        try:
            resp = requests.get(comment_api, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("9gag comment fetch failed for %s: %s", post_url, e)
            return []

        comments: list[NormalizedComment] = []
        payload = data.get("payload", {})
        # comment-cdn API returns comments directly in payload.comments[]
        comment_list = payload.get("comments", [])
        if isinstance(comment_list, dict):
            comment_list = list(comment_list.values())

        for c in comment_list:
            if not isinstance(c, dict):
                continue

            body = c.get("text", "") or c.get("mediaText", "")
            if not body:
                continue
            # Skip URL-containing comments (spam filter)
            if re.search(r"https?://", body):
                continue
            # Skip nested replies (only top-level, level=1)
            if c.get("level", 1) != 1:
                continue

            author = "Unknown"
            user = c.get("user", {})
            if isinstance(user, dict):
                author = user.get("displayName") or user.get("username") or "Unknown"

            likes = c.get("likeCount", 0)
            dislikes = c.get("dislikeCount", 0)
            score_val = likes - dislikes

            comments.append(
                NormalizedComment(
                    author=author,
                    body=body[:500],
                    score=score_val,
                    source="9gag",
                )
            )

        # Sort by score and take top N
        comments.sort(key=lambda x: x.score, reverse=True)
        comments = comments[:limit]

        if comments:
            logger.info("9gag: fetched %d comments for %s", len(comments), post_url)
        return comments


# Need json import for HTML fallback parsing
import json
