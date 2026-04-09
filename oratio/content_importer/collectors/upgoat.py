"""
Upgoat.net collector — scrapes the public hot/new post listing.

Upgoat.net has no RSS feed or public API, so we parse the HTML listing page.
Uses BeautifulSoup for robust HTML parsing.

Page structure (as of 2026-04):
  - Post title + URL in .post-container / .post-container2
  - Author, subverse, votes in sibling .submission-info
  - Comment count in sibling div with a[href*=viewpost]
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import requests

from models import NormalizedPost, NormalizedComment
from .base import BaseCollector
from .html_utils import clean_html_to_text

logger = logging.getLogger("content_importer.upgoat")

UPGOAT_BASE = "https://www.upgoat.net"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class UpgoatCollector(BaseCollector):
    """Collect posts from upgoat.net by scraping HTML.

    When import_all=True (default), fetches ALL posts across multiple pages
    from the "new" view, filtering to only include posts older than
    min_age_hours (default 13h). This ensures every post is imported once
    it has had time to accumulate votes/comments.

    AI selection is bypassed for this source (handled via skip_ai=True in config).
    """

    # Upgoat pagination: 25 posts per page, param "sec" = offset
    POSTS_PER_PAGE = 25

    def fetch(self) -> list[NormalizedPost]:
        import_all = self.config.get("import_all", True)
        min_age_hours = self.config.get("min_age_hours", 13)
        limit = self.config.get("limit", 200)  # safety cap

        if import_all:
            return self._fetch_all_pages(min_age_hours, limit)

        # Legacy single-page mode
        old_limit = self.config.get("limit", 25)
        for view in ["hot", "new"]:
            posts = self._fetch_single_page(view, 0, old_limit)
            if posts:
                return posts

        logger.warning("Upgoat: no posts fetched from any view")
        return []

    def _fetch_all_pages(self, min_age_hours: int, limit: int) -> list[NormalizedPost]:
        """Fetch ALL posts from 'new' view across multiple pages.

        Keeps paginating until:
          - We hit posts older than the collection window (IMPORT_INTERVAL), or
          - We've collected enough posts, or
          - No more pages
        Posts younger than min_age_hours are skipped (too fresh).
        Posts older than max_age_cap (72h) are always skipped.
        """
        import config as _cfg

        # Collection window = interval between cycles (e.g. 360 min = 6h)
        # We go back slightly further to avoid missing edge-case posts
        interval_hours = _cfg.IMPORT_INTERVAL_MINUTES / 60
        max_age_hours = interval_hours + min_age_hours + 2  # buffer
        # Hard cap: never import posts older than 72 hours
        max_age_cap = self.config.get("max_age_hours", 72)
        max_age_hours = min(max_age_hours, max_age_cap)

        all_posts: list[NormalizedPost] = []
        seen_urls: set[str] = set()
        offset = 0
        max_pages = 12  # safety: 12 pages × 25 = 300 posts max scan

        now = datetime.now(timezone.utc)

        for page_num in range(max_pages):
            page_posts, oldest_age_h = self._fetch_page_with_age(
                "new", offset, 25, now
            )

            if not page_posts:
                logger.debug("Upgoat: no posts on page offset=%d, stopping", offset)
                break

            for post in page_posts:
                if post.url in seen_urls:
                    continue
                seen_urls.add(post.url)

                age_h = (now - post.published_at).total_seconds() / 3600

                # Skip posts that are too fresh (< min_age_hours)
                if age_h < min_age_hours:
                    continue

                # Stop collecting if post is beyond our collection window
                if age_h > max_age_hours:
                    logger.debug(
                        "Upgoat: post age %.1fh > max %.1fh, stopping pagination",
                        age_h, max_age_hours,
                    )
                    # Finish this page but stop after
                    all_posts.append(post)
                    if len(all_posts) >= limit:
                        break
                    continue

                all_posts.append(post)
                if len(all_posts) >= limit:
                    break

            if len(all_posts) >= limit:
                break

            # If oldest post on this page exceeds our window, stop
            if oldest_age_h and oldest_age_h > max_age_hours:
                break

            offset += self.POSTS_PER_PAGE
            # Be polite — small delay between page fetches
            import time
            time.sleep(0.5)

        logger.info(
            "Upgoat: fetched %d posts (min_age=%dh, window=%.1fh, pages=%d)",
            len(all_posts), min_age_hours, max_age_hours, page_num + 1,
        )
        return all_posts

    def _fetch_page_with_age(
        self, view: str, offset: int, limit: int, now: datetime
    ) -> tuple[list[NormalizedPost], float | None]:
        """Fetch a single page and return (posts, oldest_post_age_hours)."""
        posts = self._fetch_single_page(view, offset, limit)
        if not posts:
            return [], None
        oldest_age = max(
            (now - p.published_at).total_seconds() / 3600 for p in posts
        )
        return posts, oldest_age

    def _fetch_single_page(self, view: str, offset: int, limit: int) -> list[NormalizedPost]:
        if offset > 0:
            url = f"{UPGOAT_BASE}/v/all?sec={offset}&view={view}"
        else:
            url = f"{UPGOAT_BASE}/?v=all&view={view}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning("Upgoat fetch failed for view=%s offset=%d: %s", view, offset, e)
            return []

        return self._parse_html(html, limit)

    def _parse_html(self, html: str, limit: int) -> list[NormalizedPost]:
        """Parse upgoat.net listing page.

        Structure (siblings, not nested):
          <div class="post-container" id="post_XXX">
            <a href="URL"><div class="post-title">Title</div></a>
          </div>
          <div class="submission-info">
            submitted by <a href="/profile?user=X">Author</a>
            to <a href="/v/sub">sub</a> N hours ago (+up/-down)
          </div>
          <div>
            <a href="/viewpost?postid=XXX">N comments</a>
          </div>
          ...
          <div class="textcontentdisplay" id="textcontentdisplay_XXX">
            Self-post text content (if any)
          </div>
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 not installed — cannot scrape upgoat.net")
            return []

        soup = BeautifulSoup(html, "html.parser")
        posts: list[NormalizedPost] = []
        seen_urls: set[str] = set()

        # Each post starts with a .post-container or .post-container2
        post_divs = soup.select(".post-container, .post-container2")

        if not post_divs:
            logger.debug("Upgoat: no post-container elements found")
            return []

        for post_div in post_divs:
            if len(posts) >= limit:
                break

            # Title + URL: <a href="URL"><div class="post-title">Title</div></a>
            title_el = post_div.select_one(".post-title")
            if not title_el:
                continue

            parent_a = title_el.parent
            if not parent_a or parent_a.name != "a":
                continue

            title = title_el.get_text(strip=True)
            url = parent_a.get("href", "")

            if not title or len(title) < 3 or not url:
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Build full URL if relative
            if url.startswith("/"):
                url = f"{UPGOAT_BASE}{url}"

            # Submission info is the next sibling .submission-info
            author = None
            score = 0
            subverse = None
            published_at = datetime.now(timezone.utc)

            info_el = post_div.find_next_sibling(class_="submission-info")
            if info_el:
                info_text = info_el.get_text(strip=True)

                # Author: <a href="/profile?user=X">
                author_a = info_el.select_one('a[href*="profile"]')
                if author_a:
                    author = author_a.get_text(strip=True)

                # Subverse: <a href="/v/sub">
                sub_a = info_el.select_one('a[href*="/v/"]')
                if sub_a:
                    subverse = sub_a.get_text(strip=True)

                # Votes: (+33/-0)
                vote_match = re.search(r"\(\+(\d+)/\-(\d+)\)", info_text)
                if vote_match:
                    try:
                        up = int(vote_match.group(1))
                        down = int(vote_match.group(2))
                        score = up - down
                    except ValueError:
                        pass

                # Parse relative time: "N minutes/hours ago" or "N day(s) ago"
                published_at = self._parse_relative_time(info_text)

            # Comment count from sibling with viewpost link
            comment_count = 0
            viewpost_url = None
            comment_sibling = post_div.find_next_sibling(
                lambda tag: tag.name == "div"
                and tag.select_one('a[href*="viewpost"]')
            )
            if comment_sibling:
                comment_a = comment_sibling.select_one('a[href*="viewpost"]')
                if comment_a:
                    cm = re.search(r"(\d+)\s*comment", comment_a.get_text(strip=True))
                    if cm:
                        try:
                            comment_count = int(cm.group(1))
                        except ValueError:
                            pass
                    # Store viewpost URL for comment fetching
                    vp_href = comment_a.get("href", "")
                    if vp_href:
                        viewpost_url = f"{UPGOAT_BASE}{vp_href}" if vp_href.startswith("/") else vp_href

            # --- Extract self-post content from textcontentdisplay ---
            content_text = ""
            post_id_attr = post_div.get("id", "")  # e.g. "post_69cf1a9fc91f2"
            if post_id_attr.startswith("post_"):
                post_hash = post_id_attr[5:]  # "69cf1a9fc91f2"
                content_div = soup.find("div", id=f"textcontentdisplay_{post_hash}")
                if content_div:
                    # Use clean_html_to_text to preserve paragraph structure
                    raw_text = clean_html_to_text(str(content_div))
                    # Skip if content is just the post URL echoed back (exact match)
                    # or if content is trivially short / empty
                    if raw_text and len(raw_text) > 5:
                        stripped = raw_text.strip()
                        # Link-posts echo the same URL as the post link — skip only that
                        if stripped == url or stripped == url.rstrip("/"):
                            pass  # exact URL echo → skip
                        else:
                            content_text = raw_text[:2000]  # Cap at 2000 chars

            body_parts = []
            if subverse:
                body_parts.append(f"v/{subverse}")
            if author:
                body_parts.append(f"by u/{author}")
            body = " · ".join(body_parts)
            if content_text:
                # Wrap each line in blockquote for visual separation
                quoted = "\n> ".join(content_text.split("\n"))
                content_block = f"📝 **Original content**:\n\n> {quoted}"
                body = f"{body}\n\n{content_block}" if body else content_block

            posts.append(
                NormalizedPost(
                    title=title[:200],
                    url=url,
                    body=body,
                    source="upgoat.net",
                    source_community="Upgoat",
                    score=score,
                    published_at=published_at,
                    thumbnail_url=None,
                    author=author,
                    comment_count=comment_count,
                    tags=[],
                    source_permalink=viewpost_url,
                )
            )

        logger.info("Upgoat: fetched %d posts", len(posts))
        return posts

    @staticmethod
    def _parse_relative_time(text: str) -> datetime:
        """Parse 'N minutes/hours/days ago' from upgoat submission-info text.

        Examples:
          '47 minutes ago' → now - 47min
          '8 hours ago'    → now - 8h
          '1 day ago'      → now - 24h
          '2 days ago'     → now - 48h
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        # Match patterns like "5 hours ago", "47 minutes ago", "1 day ago"
        m = re.search(r"(\d+)\s+(minute|hour|day)s?\s+ago", text, re.IGNORECASE)
        if not m:
            return now

        value = int(m.group(1))
        unit = m.group(2).lower()

        if unit == "minute":
            return now - timedelta(minutes=value)
        elif unit == "hour":
            return now - timedelta(hours=value)
        elif unit == "day":
            return now - timedelta(days=value)
        return now

    # ── Comment fetching ──────────────────────────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top comments for an upgoat.net post by score.

        Scrapes the /viewpost?postid=XXX page and extracts top-level
        .comment-row elements only (depth=0), sorting by points descending.

        Upgoat nests replies inside parent .comment-row divs, so we must:
          - Skip nested rows (depth > 0) to avoid duplicate bodies
          - Extract body from direct child div.comments-container with no id
            (NOT #comment-content-container which belongs to replies)
          - Pick the profile link that has non-empty text (first one can be empty)
        """
        viewpost_url = getattr(post, "source_permalink", None)
        if not viewpost_url:
            return []

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            resp = requests.get(viewpost_url, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning("Upgoat comment fetch failed for %s: %s", viewpost_url, e)
            return []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []

        soup = BeautifulSoup(html, "html.parser")
        raw_comments: list[NormalizedComment] = []

        comment_rows = soup.select(".comment-row")

        for row in comment_rows:
            # ── Only top-level comments (not nested replies) ──
            depth = 0
            ancestor = row.parent
            while ancestor:
                if ancestor.get("class") and "comment-row" in ancestor.get("class", []):
                    depth += 1
                ancestor = ancestor.parent
            if depth > 0:
                continue

            # ── Author: profile link with non-empty text ──
            author = ""
            for a_tag in row.select('a[href*="profile?user="]'):
                text = a_tag.get_text(strip=True)
                if text:
                    author = text
                    break
            if not author:
                continue

            # ── Score: <span id="commentpoints-XXX">N points</span> ──
            points_span = row.select_one('span[id^="commentpoints-"]')
            score = 0
            if points_span:
                points_text = points_span.get_text(strip=True)
                pm = re.search(r"(-?\d+)\s*point", points_text)
                if pm:
                    try:
                        score = int(pm.group(1))
                    except ValueError:
                        pass

            # ── Body: direct child div.comments-container with no id ──
            # (NOT #comment-content-container which belongs to nested replies)
            body = ""
            for child in row.children:
                if not hasattr(child, "name") or child.name != "div":
                    continue
                cls = child.get("class", [])
                cid = child.get("id", "")
                if "comments-container" in cls and not cid:
                    body = clean_html_to_text(str(child))
                    break

            if not body or len(body) < 2:
                continue

            # Skip comments containing URLs (spam filter)
            if re.search(r"https?://", body, re.IGNORECASE):
                continue

            # Truncate very long comments
            if len(body) > 1000:
                body = body[:1000] + "…"

            raw_comments.append(
                NormalizedComment(
                    body=body,
                    author=author,
                    score=score,
                    source="upgoat.net",
                )
            )

        # Sort by score descending, assign ranks
        raw_comments.sort(key=lambda c: c.score, reverse=True)
        for i, c in enumerate(raw_comments):
            c.rank = i + 1

        selected = raw_comments[:limit]

        if selected:
            logger.debug(
                "Upgoat comments for '%s': fetched %d, selected top %d",
                post.title[:40], len(raw_comments), len(selected),
            )
        return selected
