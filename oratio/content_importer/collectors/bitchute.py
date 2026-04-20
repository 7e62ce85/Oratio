"""
Bitchute collector — scrapes old.bitchute.com (SSR) trending page.

old.bitchute.com is the legacy server-side-rendered version of Bitchute.
The trending tab data is embedded directly in the HTML (Bootstrap tabs),
so no JS execution is needed.

Trending page structure (as of 2026-04):
  #listing-trending > #trending-day > .video-result-container cards

Also supports comment fetching from old.bitchute.com video pages.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

from models import NormalizedPost, NormalizedComment
from .base import BaseCollector
from .html_utils import clean_html_to_text

logger = logging.getLogger("content_importer.bitchute")

BITCHUTE_BASE = "https://www.bitchute.com"
OLD_BITCHUTE_BASE = "https://old.bitchute.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ── Blocked channels / title patterns ─────────────────────────────────
# Channels whose content is repetitive spam (daily auto-generated episodes).
_BLOCKED_CHANNELS = frozenset({
    "restored republic",       # "Restored Republic via a GCR Update as of ..."
})
_BLOCKED_TITLE_RE = re.compile(
    r"Restored\s+Republic\s+via\s+a\s+GCR",
    re.IGNORECASE,
)


class BitchuteCollector(BaseCollector):
    """Collect trending videos from Bitchute via old.bitchute.com HTML scraping."""

    def fetch(self) -> list[NormalizedPost]:
        limit = self.config.get("limit", 15)
        # trending_period: "day" (default), "week", or "month"
        period = self.config.get("trending_period", "day")

        posts = self._fetch_trending(limit, period)

        # Fallback: try other periods if primary returned nothing
        if not posts:
            for fallback in ["day", "week", "month"]:
                if fallback == period:
                    continue
                posts = self._fetch_trending(limit, fallback)
                if posts:
                    break

        if not posts:
            logger.warning("Bitchute: no trending videos fetched from old.bitchute.com")

        return posts

    def _fetch_trending(self, limit: int, period: str) -> list[NormalizedPost]:
        """Fetch trending videos from old.bitchute.com homepage.

        The page has Bootstrap tabs with all data pre-rendered in HTML:
          #listing-trending > #trending-{day,week,month} > .video-result-container
        """
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            resp = requests.get(
                f"{OLD_BITCHUTE_BASE}/", headers=headers, timeout=20
            )
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning("Bitchute trending fetch failed: %s", e)
            return []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 not installed — cannot scrape old.bitchute.com")
            return []

        soup = BeautifulSoup(html, "html.parser")

        # Find the trending period tab: #trending-day, #trending-week, #trending-month
        trending_tab = soup.select_one(f"#trending-{period}")
        if not trending_tab:
            logger.debug("Bitchute: #trending-%s tab not found", period)
            return []

        video_cards = trending_tab.select(".video-result-container")
        if not video_cards:
            logger.debug("Bitchute: no .video-result-container in #trending-%s", period)
            return []

        posts: list[NormalizedPost] = []
        seen_urls: set[str] = set()
        seen_authors: set[str] = set()

        for card in video_cards:
            if len(posts) >= limit:
                break

            post = self._parse_video_card(card, seen_urls)
            if post:
                # ── Blocked channel / title filter ──
                author_lower = (post.author or "").strip().lower()
                if author_lower in _BLOCKED_CHANNELS:
                    logger.debug("Bitchute: blocked channel '%s'", post.author)
                    continue
                if _BLOCKED_TITLE_RE.search(post.title or ""):
                    logger.debug("Bitchute: blocked title pattern: %s", post.title)
                    continue
                # ── Per-channel cap: max 1 video per author ──
                # Bitchute trending is dominated by daily episodes from
                # the same channels (Alex Jones, X22 Report, And We Know…).
                # Keep only the highest-views video per channel to ensure
                # diverse channel representation in the candidate pool.
                author_key = (post.author or "").strip().lower()
                if author_key and author_key in seen_authors:
                    continue
                if author_key:
                    seen_authors.add(author_key)

                posts.append(post)

        # Already sorted by trending rank (page order), but re-sort by views
        posts.sort(key=lambda p: p.score, reverse=True)
        result = posts[:limit]

        logger.info(
            "Bitchute (old.bitchute.com trending/%s): fetched %d videos"
            " (dedup: %d unique channels)",
            period, len(result), len(seen_authors),
        )
        return result

    def _parse_video_card(
        self, card, seen_urls: set[str]
    ) -> Optional[NormalizedPost]:
        """Parse a single .video-result-container card into a NormalizedPost.

        HTML structure:
          <div class="video-result-container">
            <div class="video-result-image-container">
              <a href="/video/XXXX/">
                <div class="video-result-image">
                  <img data-src="https://static-3.bitchute.com/...jpg">
                  <span class="video-views"><svg>...</svg> 5364</span>
                  <span class="video-duration">36:52</span>
                </div>
              </a>
            </div>
            <div class="video-result-text-container">
              <div class="video-result-title"><a href="/video/XXXX/">Title</a></div>
              <div class="video-result-channel"><a href="/channel/xxx/">Channel</a></div>
              <div class="video-result-text"><p>Description...</p></div>
              <div class="video-result-details"><span>14 hours ago</span></div>
            </div>
          </div>
        """
        # Title + URL
        title_el = card.select_one(".video-result-title a")
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")

        if not title or len(title) < 3 or not href:
            return None

        # Extract video ID from href like "/video/XXXX/"
        vid_match = re.search(r"/video/([A-Za-z0-9_-]+)", href)
        if not vid_match:
            return None
        video_id = vid_match.group(1)

        # Build canonical URL (new site URL for users)
        url = f"{BITCHUTE_BASE}/video/{video_id}/"
        if url in seen_urls:
            return None
        seen_urls.add(url)

        # View count from span.video-views
        views = 0
        views_el = card.select_one(".video-views")
        if views_el:
            views_text = views_el.get_text(strip=True)
            vm = re.search(r"([\d,]+)", views_text)
            if vm:
                try:
                    views = int(vm.group(1).replace(",", ""))
                except ValueError:
                    pass

        # Thumbnail from img[data-src] (lazy-loaded)
        thumbnail = None
        thumb_el = card.select_one(".video-result-image img[data-src]")
        if thumb_el:
            thumbnail = thumb_el.get("data-src")
            if thumbnail and ("loading_" in thumbnail or "blank_" in thumbnail):
                thumbnail = None

        # Channel / author
        author = None
        channel_el = card.select_one(".video-result-channel a")
        if channel_el:
            author = channel_el.get_text(strip=True)

        # Description
        body = ""
        desc_el = card.select_one(".video-result-text")
        if desc_el:
            body = desc_el.get_text(strip=True)
            # Strip any remaining HTML entities leftovers
            body = clean_html_to_text(body)

        # Duration (informational, append to body)
        duration_el = card.select_one(".video-duration")
        duration = duration_el.get_text(strip=True) if duration_el else None

        return NormalizedPost(
            title=title[:200],
            url=url,
            body=body[:1000] if body else "",
            source="bitchute",
            source_community="Bitchute",
            score=views,
            published_at=datetime.now(timezone.utc),
            thumbnail_url=thumbnail,
            author=author,
            comment_count=0,
            tags=[],
            source_permalink=f"{OLD_BITCHUTE_BASE}/video/{video_id}/",
        )

    # ── Comment fetching (CommentFreely API) ─────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top comments for a Bitchute video via the CommentFreely API.

        Bitchute uses a separate service (commentfreely.bitchute.com) to host
        comments.  The old.bitchute.com video page embeds an `initComments(...)`
        JS call whose second argument is a ``cf_auth`` token (base64 JSON +
        HMAC + timestamp).  We extract that token, then POST to
        ``/api/get_comments/`` to receive a JSON array of all comments.

        Skips comments that contain URLs (spam/hate-link filtering).
        Sorts by (upvotes − downvotes), top-level comments only.
        """
        # Build old.bitchute.com URL from video ID
        old_url = getattr(post, "source_permalink", None)
        if not old_url:
            match = re.search(r"/video/([A-Za-z0-9_-]+)", post.url)
            if not match:
                return []
            video_id = match.group(1)
            old_url = f"{OLD_BITCHUTE_BASE}/video/{video_id}/"

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        # Step 1 — load the video page to extract the cf_auth token
        try:
            page_resp = requests.get(old_url, headers=headers, timeout=20)
            page_resp.raise_for_status()
        except Exception as e:
            logger.warning("Bitchute comment page fetch failed for %s: %s", old_url, e)
            return []

        cf_match = re.search(
            r"initComments\s*\(\s*'([^']+)'\s*,\s*'([^']+)'",
            page_resp.text,
        )
        if not cf_match:
            logger.debug("Bitchute: no initComments() found on %s", old_url)
            return []

        cf_base_url = cf_match.group(1)   # https://commentfreely.bitchute.com
        cf_auth = cf_match.group(2)        # base64-token HMAC timestamp

        # Step 2 — call the CommentFreely JSON API
        try:
            api_resp = requests.post(
                f"{cf_base_url}/api/get_comments/",
                data={
                    "cf_auth": cf_auth,
                    "commentCount": 0,
                    "isNameValuesArrays": "true",
                },
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": OLD_BITCHUTE_BASE,
                    "Referer": f"{OLD_BITCHUTE_BASE}/",
                },
                timeout=20,
            )
            api_resp.raise_for_status()
            data = api_resp.json()
        except Exception as e:
            logger.warning("Bitchute CommentFreely API failed for %s: %s", old_url, e)
            return []

        names: list[str] = data.get("names", [])
        values: list[list] = data.get("values", [])
        if not names or not values:
            return []

        # Build field-index map
        idx = {n: i for i, n in enumerate(names)}
        i_content = idx.get("content")
        i_author = idx.get("fullname")
        i_up = idx.get("up_vote_count")
        i_down = idx.get("down_vote_count")
        i_parent = idx.get("parent")

        if i_content is None:
            logger.debug("Bitchute: 'content' field not found in CommentFreely response")
            return []

        # Step 3 — parse into NormalizedComment, top-level only
        raw_comments: list[NormalizedComment] = []
        for row in values:
            # Skip replies (only top-level comments)
            if i_parent is not None and row[i_parent] is not None:
                continue

            body = str(row[i_content] or "").strip()
            if not body or len(body) < 5:
                continue

            author = str(row[i_author] or "Anonymous") if i_author is not None else "Anonymous"
            up = int(row[i_up] or 0) if i_up is not None else 0
            down = int(row[i_down] or 0) if i_down is not None else 0
            score = up - down

            # Skip comments containing URLs (spam filter)
            if re.search(r"https?://", body, re.IGNORECASE):
                logger.debug("Bitchute: skipping comment with URL by %s", author)
                continue

            if len(body) > 1000:
                body = body[:1000] + "…"

            raw_comments.append(
                NormalizedComment(
                    body=body,
                    author=author,
                    score=score,
                    source="bitchute",
                )
            )

        # Sort by score descending, assign ranks
        raw_comments.sort(key=lambda c: c.score, reverse=True)
        for i, c in enumerate(raw_comments):
            c.rank = i + 1

        selected = raw_comments[:limit]

        if selected:
            logger.debug(
                "Bitchute comments for '%s': fetched %d (API), selected top %d",
                post.title[:40], len(raw_comments), len(selected),
            )
        return selected
