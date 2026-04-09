"""
Reddit collector — uses old.reddit.com RSS feed (most reliable, no auth needed).

Falls back to JSON API if RSS fails.  No API key or OAuth required.
Supports comment fetching via JSON API (.json endpoint).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import feedparser
import requests

from models import NormalizedPost, NormalizedComment

from .base import BaseCollector
from .html_utils import clean_html_to_text

logger = logging.getLogger("content_importer.reddit")

REDDIT_USER_AGENT = (
    "Mozilla/5.0 (compatible; OratioContentImporter/1.0; +https://oratio.space)"
)


class RedditCollector(BaseCollector):
    """Collect top/hot posts from a subreddit via RSS feed."""

    def fetch(self) -> list[NormalizedPost]:
        subreddit = self.config.get("subreddit", "all")
        sort = self.config.get("sort", "hot")
        limit = min(self.config.get("limit", 20), 100)

        # Primary: RSS feed from old.reddit.com (most reliable)
        posts = self._fetch_rss(subreddit, sort, limit)
        if posts:
            return posts

        # Fallback: JSON API
        return self._fetch_json(subreddit, sort, limit)

    def _fetch_rss(
        self, subreddit: str, sort: str, limit: int
    ) -> list[NormalizedPost]:
        """Fetch via RSS — avoids Reddit API rate limits and blocks."""
        # old.reddit.com RSS works from most IPs
        url = f"https://old.reddit.com/r/{subreddit}/{sort}/.rss"
        headers = {"User-Agent": REDDIT_USER_AGENT}

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception as e:
            logger.warning("Reddit RSS failed for r/%s: %s", subreddit, e)
            return []

        posts: list[NormalizedPost] = []
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            reddit_link = entry.get("link", "").strip()
            if not title or not reddit_link:
                continue

            # Extract body & external link from content (HTML)
            raw_html = ""
            if hasattr(entry, "content") and entry.content:
                raw_html = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                raw_html = entry.summary or ""

            # Extract the external (original article) URL from the RSS HTML.
            # Reddit RSS wraps external link posts as:
            #   <a href="https://bbc.com/...">[link]</a>
            # Self-posts only have the reddit comments link.
            external_url = self._extract_external_url(raw_html, reddit_link)

            body = clean_html_to_text(raw_html)
            if len(body) > 2000:
                body = body[:2000] + "…"

            # Published date
            published = datetime.now(timezone.utc)
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(
                        *entry.published_parsed[:6], tzinfo=timezone.utc
                    )
                except Exception:
                    pass

            # Author
            author = entry.get("author", "")
            if author.startswith("/u/"):
                author = author[3:]

            posts.append(
                NormalizedPost(
                    title=title,
                    url=external_url,  # 원본 기사 URL (없으면 Reddit URL)
                    body=body,
                    source="reddit",
                    source_community=f"r/{subreddit}",
                    score=0,  # RSS doesn't include score
                    published_at=published,
                    author=author or None,
                    source_permalink=reddit_link,  # Reddit comments page
                )
            )

        logger.info("Reddit r/%s (RSS): fetched %d posts", subreddit, len(posts))
        return posts

    @staticmethod
    def _extract_external_url(html: str, reddit_link: str) -> str:
        """
        Extract the external (original article) URL from Reddit RSS HTML.

        Reddit RSS content contains two links:
          - [link] → the external URL (e.g. BBC article)
          - [comments] → the Reddit post URL
        For self-posts, [link] points to the Reddit post itself.

        Returns the external URL if found and different from the Reddit
        post, otherwise returns the Reddit link.
        """
        # Find all href="..." with [link] or [comments] label
        link_matches = re.findall(
            r'<a\s+href="(https?://[^"]+)">\[link\]</a>', html
        )
        if link_matches:
            candidate = link_matches[0]
            # Skip if it just points back to reddit (self-post)
            if "reddit.com" not in candidate and "redd.it" not in candidate:
                return candidate
        return reddit_link

    # ── Comment fetching ──────────────────────────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top comments for a Reddit post.

        Strategy:
          1. Try JSON API ({permalink}.json) — has full scores, but often 403
          2. Fall back to RSS ({permalink}.rss) — no scores, but always works
             RSS entries arrive in Reddit's default (hot/best) sort order,
             so earlier entries are the community's top-voted comments.
        """
        reddit_url = self._get_reddit_comments_url(post)
        if not reddit_url:
            return []

        # ── Attempt 1: JSON API (has scores) ──
        comments = self._fetch_comments_json(reddit_url, limit)
        if comments:
            return comments

        # ── Attempt 2: RSS fallback (no scores, uses position as proxy) ──
        return self._fetch_comments_rss(reddit_url, post, limit)

    def _fetch_comments_json(self, reddit_url: str, limit: int) -> list[NormalizedComment]:
        """Try the JSON endpoint — returns scored comments or empty list on failure."""
        json_url = reddit_url.rstrip("/") + ".json"
        json_url = json_url.replace("www.reddit.com", "old.reddit.com")
        if "old.reddit.com" not in json_url:
            json_url = json_url.replace("reddit.com", "old.reddit.com")
        headers = {"User-Agent": REDDIT_USER_AGENT}

        try:
            resp = requests.get(
                json_url,
                headers=headers,
                params={"limit": 50, "sort": "top", "raw_json": 1},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.debug("Reddit JSON comments failed (will try RSS): %s", e)
            return []

        if not isinstance(data, list) or len(data) < 2:
            return []

        comments_data = data[1].get("data", {}).get("children", [])

        raw_comments: list[NormalizedComment] = []
        for child in comments_data:
            if child.get("kind") != "t1":
                continue
            c = child.get("data", {})

            body = c.get("body", "").strip()
            if not body or body in ("[deleted]", "[removed]"):
                continue

            author = c.get("author", "")
            if not author or author in ("[deleted]", "AutoModerator"):
                continue

            score = c.get("score", 0)
            if score < 2:
                continue

            if len(body) > 1000:
                body = body[:1000] + "…"

            raw_comments.append(
                NormalizedComment(body=body, author=author, score=score, source="reddit")
            )

        raw_comments.sort(key=lambda c: c.score, reverse=True)
        for i, c in enumerate(raw_comments):
            c.rank = i + 1

        selected = raw_comments[:limit]
        if selected:
            logger.debug(
                "Reddit JSON comments for top %d (ranks: %s)",
                len(selected), [c.rank for c in selected],
            )
        return selected

    def _fetch_comments_rss(
        self, reddit_url: str, post: NormalizedPost, limit: int
    ) -> list[NormalizedComment]:
        """
        Fallback: fetch comments via the .rss endpoint.

        Reddit RSS includes comments in the thread's default sort order
        (hot/best).  There are no score numbers, so we use the position
        in the feed as a quality proxy — earlier = better.

        The first <entry> is the original post; subsequent entries are comments.

        NOTE: feedparser's built-in HTTP client gets 403'd by Reddit,
        so we use requests first, then parse the response text.
        We must use www.reddit.com (not old.reddit.com) for per-post RSS.
        """
        rss_url = reddit_url.rstrip("/") + ".rss"
        # Per-post comment RSS works on www.reddit.com, NOT old.reddit.com
        rss_url = rss_url.replace("old.reddit.com", "www.reddit.com")

        try:
            resp = requests.get(
                rss_url,
                headers={"User-Agent": REDDIT_USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Reddit RSS comments fetch failed for %s: %s", rss_url, e)
            return []

        feed = feedparser.parse(resp.text)

        if not feed.entries:
            logger.warning("Reddit RSS comments: no entries for %s", reddit_url)
            return []

        raw_comments: list[NormalizedComment] = []

        # Skip entry[0] — it's the original post (OP)
        for idx, entry in enumerate(feed.entries[1:], start=1):
            # Author: "/u/username" → "username"
            author = getattr(entry, "author", "") or ""
            if author.startswith("/u/"):
                author = author[3:]
            if not author or author in ("[deleted]", "AutoModerator"):
                continue

            # Body: prefer content[0].value (HTML), fallback to summary
            body = ""
            if hasattr(entry, "content") and entry.content:
                body = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                body = entry.summary or ""

            # Strip HTML tags for plain text
            body = clean_html_to_text(body)
            body = re.sub(r"\s+", " ", body).strip()

            if not body or len(body) < 5:
                continue

            # Skip comments containing URLs (spam filter)
            if re.search(r"https?://", body, re.IGNORECASE):
                continue

            if len(body) > 1000:
                body = body[:1000] + "…"

            # Use inverse position as pseudo-score (higher = earlier = better)
            pseudo_score = max(100 - idx, 1)

            raw_comments.append(
                NormalizedComment(
                    body=body,
                    author=author,
                    score=pseudo_score,
                    source="reddit",
                )
            )

        # Already in quality order from RSS, assign ranks
        for i, c in enumerate(raw_comments):
            c.rank = i + 1

        selected = raw_comments[:limit]
        if selected:
            logger.info(
                "Reddit RSS comments for '%s': %d entries, selected top %d",
                post.title[:40], len(raw_comments), len(selected),
            )
        return selected

    @staticmethod
    def _get_reddit_comments_url(post: NormalizedPost) -> str | None:
        """
        Reconstruct the Reddit comments URL for a post.

        Uses source_permalink if available (stored during fetch),
        otherwise checks if post.url is a Reddit URL.
        """
        # Prefer stored permalink (always the Reddit comments page)
        if post.source_permalink:
            return post.source_permalink.split("?")[0]

        url = post.url
        # If url is already a reddit link, use it
        if "reddit.com" in url or "redd.it" in url:
            return url.split("?")[0]

        return None

    def _fetch_json(
        self, subreddit: str, sort: str, limit: int
    ) -> list[NormalizedPost]:
        """Fallback: JSON API — may be blocked from some IPs."""
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        params = {"limit": limit, "raw_json": 1}
        headers = {"User-Agent": REDDIT_USER_AGENT}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("Reddit fetch failed for r/%s: %s", subreddit, e)
            return []

        posts: list[NormalizedPost] = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            if d.get("stickied") or d.get("is_self") and not d.get("selftext"):
                continue

            # Build body: self-text or a short link-description
            body = d.get("selftext", "") or ""
            if len(body) > 2000:
                body = body[:2000] + "…"

            # Media / thumbnail
            media_url = None
            thumbnail = d.get("thumbnail")
            if thumbnail and thumbnail.startswith("http"):
                thumbnail_url = thumbnail
            else:
                thumbnail_url = None

            # If it's a direct image/video link
            if d.get("post_hint") in ("image", "hosted:video", "rich:video"):
                media_url = d.get("url_overridden_by_dest") or d.get("url")

            # Use the original article URL instead of Reddit permalink.
            # For link posts: url_overridden_by_dest = external article URL
            # For self-posts: url = reddit permalink (fallback)
            external_url = d.get("url_overridden_by_dest") or d.get("url", "")
            reddit_permalink = f"https://www.reddit.com{d.get('permalink', '')}"
            if not external_url or "reddit.com" in external_url or "redd.it" in external_url:
                external_url = reddit_permalink

            try:
                published = datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc)
            except Exception:
                published = datetime.now(timezone.utc)

            posts.append(
                NormalizedPost(
                    title=d.get("title", ""),
                    url=external_url,
                    body=body,
                    source="reddit",
                    source_community=f"r/{subreddit}",
                    score=d.get("score", 0),
                    published_at=published,
                    media_url=media_url,
                    thumbnail_url=thumbnail_url,
                    author=d.get("author"),
                    comment_count=d.get("num_comments", 0),
                    tags=[d.get("link_flair_text", "")] if d.get("link_flair_text") else [],
                    source_permalink=reddit_permalink,  # Reddit comments page
                )
            )

        logger.info("Reddit r/%s: fetched %d posts", subreddit, len(posts))
        return posts
