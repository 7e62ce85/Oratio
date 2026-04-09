"""
Imgur collector — fetches popular gallery posts via the Imgur API v3.

Imgur provides a free public API that requires only a Client-ID header.
Register at https://api.imgur.com/oauth2/addclient (anonymous, free).

Endpoints used:
  GET /3/gallery/{section}/{sort}/{window}/{page}
  GET /3/gallery/{id}/comments/best

Environment variable:
  IMGUR_CLIENT_ID  – Imgur API Client-ID (required for API mode)

If no Client-ID is configured, falls back to HTML scraping of the
/t/memes or /hot page (less reliable, may hit captcha).
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

import requests

from models import NormalizedPost, NormalizedComment
from .base import BaseCollector
from .html_utils import clean_html_to_text

logger = logging.getLogger("content_importer.imgur")

IMGUR_API_BASE = "https://api.imgur.com"
IMGUR_WEB_BASE = "https://imgur.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class ImgurCollector(BaseCollector):
    """
    Collect popular posts from Imgur gallery.

    Config keys:
      section      – "hot", "top", "user"  (default "hot")
      sort         – "viral", "top", "time", "rising" (default "viral")
      window       – "day", "week", "month", "year", "all" (default "day")
      tag          – optional tag to search (e.g. "memes", "funny")
      limit        – max posts to return (default 20)
    """

    def __init__(self, source_config: dict):
        super().__init__(source_config)
        self.client_id = os.getenv("IMGUR_CLIENT_ID", "")

    def fetch(self) -> list[NormalizedPost]:
        limit = self.config.get("limit", 20)

        if self.client_id:
            posts = self._fetch_api(limit)
        else:
            logger.info("Imgur: no IMGUR_CLIENT_ID set — trying RSS feed fallback")
            posts = self._fetch_rss(limit)

        if not posts:
            logger.info("Imgur: primary method failed — trying HTML scrape fallback")
            posts = self._fetch_html(limit)

        return posts

    # ── RSS-based fetch (no API key needed) ──────────────────────

    def _fetch_rss(self, limit: int) -> list[NormalizedPost]:
        """Fetch from Imgur's public RSS feed (no auth required)."""
        tag = self.config.get("tag", "")
        if tag:
            rss_url = f"{IMGUR_WEB_BASE}/t/{tag}.rss"
        else:
            rss_url = f"{IMGUR_WEB_BASE}/hot/viral.rss"

        headers = {"User-Agent": USER_AGENT}

        try:
            resp = requests.get(rss_url, headers=headers, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Imgur RSS fetch failed: %s", e)
            return []

        try:
            import feedparser
        except ImportError:
            logger.error("feedparser not installed")
            return []

        feed = feedparser.parse(resp.text)
        posts: list[NormalizedPost] = []

        for entry in feed.entries[:limit]:
            title = entry.get("title", "")
            if not title or len(title) < 3:
                continue

            link = entry.get("link", "")
            if not link:
                continue

            # Extract description / thumbnail from content
            desc = ""
            thumbnail = None
            content = entry.get("description", "") or entry.get("summary", "")
            if content:
                # Try to find image in content
                img_match = re.search(r'<img[^>]+src="([^"]+)"', content)
                if img_match:
                    thumbnail = img_match.group(1)
                # Strip HTML for body
                desc = clean_html_to_text(content)[:300]

            author = entry.get("author") or entry.get("dc_creator")

            # Extract post ID from URL
            post_id = ""
            id_match = re.search(r'/(?:gallery|a)/(\w+)', link)
            if id_match:
                post_id = id_match.group(1)

            posts.append(
                NormalizedPost(
                    title=title[:200],
                    url=link,
                    body=desc or "",
                    source="imgur",
                    source_community="Imgur",
                    score=0,
                    published_at=datetime.now(timezone.utc),
                    thumbnail_url=thumbnail,
                    author=author,
                    comment_count=0,
                    tags=[],
                    source_permalink=link,
                    source_id=post_id,
                )
            )

        logger.info("Imgur RSS: fetched %d posts", len(posts))
        return posts

    # ── API-based fetch ──────────────────────────────────────────

    def _fetch_api(self, limit: int) -> list[NormalizedPost]:
        section = self.config.get("section", "hot")
        sort = self.config.get("sort", "viral")
        window = self.config.get("window", "day")
        tag = self.config.get("tag", "")

        headers = {
            "Authorization": f"Client-ID {self.client_id}",
            "User-Agent": USER_AGENT,
        }

        # If a tag is specified, use the tag gallery endpoint
        if tag:
            url = f"{IMGUR_API_BASE}/3/gallery/t/{tag}/{sort}/{window}/0"
        else:
            url = f"{IMGUR_API_BASE}/3/gallery/{section}/{sort}/{window}/0"

        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("Imgur API fetch failed: %s", e)
            return []

        if not data.get("success"):
            logger.warning("Imgur API error: %s", data.get("data", {}).get("error", "unknown"))
            return []

        items = data.get("data", [])
        # Tag endpoint wraps items in a "items" sub-key
        if isinstance(items, dict) and "items" in items:
            items = items["items"]

        posts: list[NormalizedPost] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue

            title = item.get("title") or ""
            if not title or len(title) < 3:
                continue

            item_id = item.get("id", "")
            is_album = item.get("is_album", False)
            link = item.get("link", f"{IMGUR_WEB_BASE}/gallery/{item_id}")

            # Description / body
            desc = item.get("description") or ""
            body_parts = []
            if desc:
                body_parts.append(desc[:300])

            score = item.get("ups", 0) or item.get("points", 0) or item.get("score", 0)
            views = item.get("views", 0)
            comment_count = item.get("comment_count", 0)
            author = item.get("account_url") or None

            # Thumbnail
            thumbnail = None
            if is_album:
                cover_id = item.get("cover")
                if cover_id:
                    thumbnail = f"https://i.imgur.com/{cover_id}m.jpg"
            else:
                thumbnail = f"https://i.imgur.com/{item_id}m.jpg"

            # Tags
            tags = []
            for t in (item.get("tags") or []):
                if isinstance(t, dict):
                    tags.append(t.get("name", ""))
                elif isinstance(t, str):
                    tags.append(t)

            published_ts = item.get("datetime", 0)
            try:
                published = datetime.fromtimestamp(published_ts, tz=timezone.utc)
            except (ValueError, OSError):
                published = datetime.now(timezone.utc)

            posts.append(
                NormalizedPost(
                    title=title[:200],
                    url=link,
                    body=" · ".join(body_parts) if body_parts else f"👁 {views:,} views",
                    source="imgur",
                    source_community="Imgur",
                    score=score,
                    published_at=published,
                    thumbnail_url=thumbnail,
                    author=author,
                    comment_count=comment_count,
                    tags=tags[:5],
                    source_permalink=link,
                    source_id=item_id,
                )
            )

        logger.info("Imgur API: fetched %d posts", len(posts))
        return posts

    # ── HTML scraping fallback ──────────────────────────────────

    def _fetch_html(self, limit: int) -> list[NormalizedPost]:
        """Scrape Imgur gallery page as fallback (no API key)."""
        tag = self.config.get("tag", "")
        if tag:
            url = f"{IMGUR_WEB_BASE}/t/{tag}"
        else:
            url = f"{IMGUR_WEB_BASE}/hot"

        headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}

        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning("Imgur HTML fetch failed: %s", e)
            return []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 not installed")
            return []

        soup = BeautifulSoup(html, "html.parser")
        posts: list[NormalizedPost] = []
        seen: set[str] = set()

        # Imgur renders gallery cards in .Post or .post elements
        cards = soup.select(".Post, .post, .gallery-item, .cards .card")

        for card in cards[:limit]:
            title_el = card.select_one("a[title], .caption, h2, .post-title")
            if not title_el:
                continue

            title = (title_el.get("title") or title_el.get_text(strip=True) or "")[:200]
            if not title or len(title) < 3:
                continue

            # URL
            link_el = card.select_one("a[href*='/gallery/'], a[href*='/a/']")
            if not link_el:
                link_el = title_el if title_el.name == "a" else card.select_one("a")
            href = (link_el.get("href", "") if link_el else "")
            if not href:
                continue
            if href.startswith("/"):
                href = f"{IMGUR_WEB_BASE}{href}"
            if href in seen:
                continue
            seen.add(href)

            # Thumbnail
            thumb = None
            img = card.select_one("img")
            if img:
                thumb = img.get("src") or img.get("data-src")

            # Points
            score = 0
            pts = card.select_one(".point-info, .points")
            if pts:
                m = re.search(r"([\d,]+)", pts.get_text(strip=True))
                if m:
                    score = int(m.group(1).replace(",", ""))

            posts.append(
                NormalizedPost(
                    title=title,
                    url=href,
                    body="",
                    source="imgur",
                    source_community="Imgur",
                    score=score,
                    published_at=datetime.now(timezone.utc),
                    thumbnail_url=thumb,
                    author=None,
                    comment_count=0,
                    tags=[],
                    source_permalink=href,
                )
            )

        logger.info("Imgur HTML: fetched %d posts", len(posts))
        return posts

    # ── Comment fetching ────────────────────────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top comments for an Imgur post via API.

        Requires IMGUR_CLIENT_ID.
        Endpoint: GET /3/gallery/{id}/comments/best
        """
        if not self.client_id:
            return []

        post_id = getattr(post, "source_id", None)
        if not post_id:
            # Try to extract from URL
            m = re.search(r"/(?:gallery|a)/(\w+)", post.url)
            if m:
                post_id = m.group(1)
            else:
                return []

        url = f"{IMGUR_API_BASE}/3/gallery/{post_id}/comments/best"
        headers = {
            "Authorization": f"Client-ID {self.client_id}",
            "User-Agent": USER_AGENT,
        }

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("Imgur comment fetch failed for %s: %s", post_id, e)
            return []

        if not data.get("success"):
            return []

        comments_data = data.get("data", [])
        comments: list[NormalizedComment] = []

        for c in comments_data:
            if not isinstance(c, dict):
                continue
            body = c.get("comment", "")
            if not body or re.search(r"https?://", body):
                continue

            author = c.get("author") or "Unknown"
            ups = c.get("ups", 0)
            downs = c.get("downs", 0)
            score_val = ups - downs

            comments.append(
                NormalizedComment(
                    author=author,
                    body=body[:500],
                    score=score_val,
                    source="imgur",
                )
            )

        # Already sorted by "best" from API, take top N
        comments = sorted(comments, key=lambda x: x.score, reverse=True)[:limit]
        logger.info("Imgur: fetched %d comments for post %s", len(comments), post_id)
        return comments
