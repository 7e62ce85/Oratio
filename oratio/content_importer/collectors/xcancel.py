"""
XCancel (Nitter-fork) collector — scrapes tweet search results from xcancel.com.

XCancel is a privacy-friendly Twitter/X frontend (Nitter fork).
We use it to collect tweets matching a search query without needing the
paid Twitter API.

The site has an anti-bot challenge (JS redirect), so we use cloudscraper
to bypass it.  If cloudscraper fails we fall back to requests with a retry.

Source URL example:
  https://xcancel.com/search?f=tweets&q=Liberty

Page structure (Nitter-style HTML):
  div.timeline-item  →  each tweet
    div.tweet-header  →  author info
    div.tweet-content →  tweet text
    div.tweet-stats   →  reply / retweet / like counts
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse, parse_qs

import requests

from models import NormalizedPost, NormalizedComment
from .base import BaseCollector

logger = logging.getLogger("content_importer.xcancel")

XCANCEL_BASE = "https://xcancel.com"
# Nitter instances as fallback (xcancel may have anti-bot challenges)
NITTER_INSTANCES = [
    "https://xcancel.com",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.woodland.cafe",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _get_session():
    """Return a cloudscraper session if available, else plain requests."""
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False},
            delay=3,
        )
        return scraper
    except ImportError:
        logger.warning("cloudscraper not installed — using plain requests (may be blocked)")
        sess = requests.Session()
        sess.headers.update({"User-Agent": USER_AGENT})
        return sess


class XCancelCollector(BaseCollector):
    """
    Collect tweets from xcancel.com search results.

    Config keys:
      search_url  – full xcancel search URL
                    (e.g. https://xcancel.com/search?f=tweets&q=Liberty)
      search_query – alternative: just the query string (e.g. "Liberty")
      limit       – max posts to return (default 25)
    """

    def fetch(self) -> list[NormalizedPost]:
        limit = self.config.get("limit", 25)

        # Build search URL (path portion)
        search_url = self.config.get("search_url", "")
        if not search_url:
            query = self.config.get("search_query", "Liberty")
            search_url = f"{XCANCEL_BASE}/search?f=tweets&{urlencode({'q': query})}"

        # Extract path+query for use with fallback instances
        parsed = urlparse(search_url)
        search_path = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path

        session = _get_session()

        # Try each Nitter instance in order
        for base_url in NITTER_INSTANCES:
            try_url = f"{base_url}{search_path}"
            try:
                import time
                time.sleep(1)  # polite delay
                resp = session.get(try_url, timeout=30)
                if resp.status_code == 200 and len(resp.text) > 1000:
                    posts = self._parse_html(resp.text, limit, try_url)
                    if posts:
                        logger.info("XCancel: fetched %d posts from %s", len(posts), base_url)
                        return posts
                    else:
                        logger.debug("XCancel: parsed 0 posts from %s (HTML length=%d)", base_url, len(resp.text))
                else:
                    logger.debug("XCancel: %s returned status=%d, len=%d", base_url, resp.status_code, len(resp.text))
            except Exception as e:
                logger.debug("XCancel: %s failed: %s", base_url, e)
                continue

        logger.warning("XCancel: all Nitter instances failed for query: %s", search_path)
        return []

    def _parse_html(self, html: str, limit: int, search_url: str) -> list[NormalizedPost]:
        """Parse xcancel.com search results (Nitter-style HTML)."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 not installed")
            return []

        soup = BeautifulSoup(html, "html.parser")
        posts: list[NormalizedPost] = []
        seen_urls: set[str] = set()

        # Nitter/XCancel structure: div.timeline-item contains each tweet
        items = soup.select(".timeline-item")
        if not items:
            # Fallback: try .tweet-body or .tweet
            items = soup.select(".tweet-body, .tweet")
        if not items:
            logger.debug("XCancel: no timeline-item elements found. HTML length=%d", len(html))
            return []

        for item in items:
            if len(posts) >= limit:
                break

            # ── Author ──
            author = None
            username = None
            author_el = item.select_one(".tweet-header .fullname, .fullname")
            username_el = item.select_one(".tweet-header .username, .username")
            if author_el:
                author = author_el.get_text(strip=True)
            if username_el:
                username = username_el.get_text(strip=True).lstrip("@")

            # ── Tweet link (permalink) ──
            link_el = item.select_one("a.tweet-link, .tweet-date a, a[href*='/status/']")
            tweet_url = ""
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("/"):
                    tweet_url = f"{XCANCEL_BASE}{href}"
                elif href.startswith("http"):
                    tweet_url = href
                else:
                    tweet_url = f"{XCANCEL_BASE}/{href}"

            if not tweet_url or tweet_url in seen_urls:
                continue
            seen_urls.add(tweet_url)

            # ── Tweet text ──
            content_el = item.select_one(".tweet-content, .media-body")
            text = content_el.get_text(strip=True) if content_el else ""
            if not text:
                continue

            # Title = first 140 chars of tweet text
            title = text[:140]
            if len(text) > 140:
                title += "…"

            # ── Stats (likes, retweets, replies) ──
            likes = 0
            retweets = 0
            replies = 0

            stats_el = item.select_one(".tweet-stats, .tweet-stat")
            if stats_el:
                for icon_stat in stats_el.select(".icon-container, .tweet-stat"):
                    stat_text = icon_stat.get_text(strip=True).replace(",", "")
                    # Determine type from icon class or sibling icon
                    icon = icon_stat.select_one("[class*=heart], [class*=like]")
                    rt_icon = icon_stat.select_one("[class*=retweet]")
                    reply_icon = icon_stat.select_one("[class*=comment], [class*=reply]")

                    num_match = re.search(r"(\d+)", stat_text)
                    num = int(num_match.group(1)) if num_match else 0

                    if icon:
                        likes = num
                    elif rt_icon:
                        retweets = num
                    elif reply_icon:
                        replies = num

            # If we couldn't parse stats from icons, try generic stat extraction
            if likes == 0 and retweets == 0:
                stat_spans = item.select(".tweet-stat .icon-container")
                stat_values = []
                for sp in stat_spans:
                    num_match = re.search(r"(\d[\d,]*)", sp.get_text(strip=True))
                    if num_match:
                        stat_values.append(int(num_match.group(1).replace(",", "")))
                # Nitter order: comments, retweets, quotes, likes
                if len(stat_values) >= 4:
                    replies, retweets, _, likes = stat_values[:4]
                elif len(stat_values) == 3:
                    replies, retweets, likes = stat_values[:3]

            score = likes + retweets

            # ── Media / thumbnail ──
            thumbnail = None
            img_el = item.select_one(".still-image img, .attachment img, img.tweet-image")
            if img_el:
                thumbnail = img_el.get("src", "")
                if thumbnail and thumbnail.startswith("/"):
                    thumbnail = f"{XCANCEL_BASE}{thumbnail}"

            # Build body
            body_parts = []
            if username:
                body_parts.append(f"@{username}")
            body_parts.append(text)
            if retweets:
                body_parts.append(f"🔁 {retweets}")
            if likes:
                body_parts.append(f"❤️ {likes}")
            body = " · ".join(body_parts[:2])
            if len(body_parts) > 2:
                body += " | " + " ".join(body_parts[2:])

            # Original X/Twitter URL for reference
            x_url = tweet_url.replace(XCANCEL_BASE, "https://x.com")

            posts.append(
                NormalizedPost(
                    title=title,
                    url=x_url,           # Link to original X/Twitter
                    body=body,
                    source="xcancel",
                    source_community="XCancel",
                    score=score,
                    published_at=datetime.now(timezone.utc),
                    thumbnail_url=thumbnail,
                    author=username or author,
                    comment_count=replies,
                    tags=[],
                    source_permalink=tweet_url,  # xcancel URL for comment fetching
                )
            )

        return posts

    # ── Comment fetching (tweet replies) ────────────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top replies to a tweet from xcancel.com.

        Scrapes the individual tweet page (source_permalink) for reply tweets.
        """
        permalink = getattr(post, "source_permalink", None)
        if not permalink:
            return []

        session = _get_session()

        try:
            resp = session.get(permalink, timeout=30)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning("XCancel comment fetch failed for %s: %s", permalink, e)
            return []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []

        soup = BeautifulSoup(html, "html.parser")
        comments: list[NormalizedComment] = []

        # Replies are in .reply .timeline-item or .thread-line
        reply_items = soup.select(".reply .timeline-item, .thread-line .timeline-item")
        if not reply_items:
            reply_items = soup.select(".timeline-item")
            # Skip the first one (it's the original tweet)
            if reply_items:
                reply_items = reply_items[1:]

        scored_replies: list[tuple[int, str, str]] = []  # (score, author, text)

        for item in reply_items:
            author = None
            username_el = item.select_one(".username")
            if username_el:
                author = username_el.get_text(strip=True).lstrip("@")

            content_el = item.select_one(".tweet-content, .media-body")
            text = content_el.get_text(strip=True) if content_el else ""
            if not text:
                continue

            # Skip replies containing URLs (spam filter)
            if re.search(r"https?://", text):
                continue

            # Parse likes
            reply_likes = 0
            stat_spans = item.select(".tweet-stat .icon-container")
            stat_values = []
            for sp in stat_spans:
                num_match = re.search(r"(\d[\d,]*)", sp.get_text(strip=True))
                if num_match:
                    stat_values.append(int(num_match.group(1).replace(",", "")))
            # Nitter order: comments, retweets, quotes, likes
            if len(stat_values) >= 4:
                reply_likes = stat_values[3]
            elif len(stat_values) >= 1:
                reply_likes = stat_values[-1]

            scored_replies.append((reply_likes, author or "Unknown", text))

        # Sort by likes descending, take top N
        scored_replies.sort(key=lambda x: x[0], reverse=True)

        for score_val, author, text in scored_replies[:limit]:
            comments.append(
                NormalizedComment(
                    author=author,
                    body=text[:500],
                    score=score_val,
                    source="xcancel",
                )
            )

        logger.info("XCancel: fetched %d comments for %s", len(comments), permalink)
        return comments
