"""
MGTOW.tv collector — scrapes the public trending/recent video listing.

MGTOW.tv has no public API or RSS, so we parse the HTML listing page.
Uses BeautifulSoup for robust HTML parsing.

Correct URL structure (as of 2026-03):
  /videos/trending  — trending videos
  /videos/top       — top rated
  /videos/latest    — newest uploads
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

from models import NormalizedPost, NormalizedComment
from .base import BaseCollector

logger = logging.getLogger("content_importer.mgtow")

MGTOW_BASE = "https://www.mgtow.tv"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class MGTOWCollector(BaseCollector):
    """Collect trending/recent videos from MGTOW.tv by scraping HTML."""

    def fetch(self) -> list[NormalizedPost]:
        limit = self.config.get("limit", 15)

        # Correct URL paths: /videos/trending, /videos/top, /videos/latest
        for path in ["/videos/trending", "/videos/top", "/videos/latest"]:
            posts = self._fetch_page(path, limit)
            if posts:
                return posts

        logger.warning("MGTOW.tv: no posts fetched from any page")
        return []

    def _fetch_page(self, path: str, limit: int) -> list[NormalizedPost]:
        url = f"{MGTOW_BASE}{path}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning("MGTOW.tv fetch failed for %s: %s", path, e)
            return []

        return self._parse_html(html, limit)

    def _parse_html(self, html: str, limit: int) -> list[NormalizedPost]:
        """Parse MGTOW.tv listing page using actual HTML structure.

        Structure:
          <div class="video-latest-list video-wrapper">
            <div class="video-thumb">
              <a href="..."><img src="..."></a>
              <span class="video-duration">12:34</span>
            </div>
            <div class="video-title"><a href="...">Title</a></div>
            <div class="video-info">AuthorName · 123 Views · 2 days ago</div>
          </div>
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 not installed — cannot scrape MGTOW.tv")
            return []

        soup = BeautifulSoup(html, "html.parser")
        posts: list[NormalizedPost] = []

        # Each video is a .video-latest-list card
        video_cards = soup.select(".video-latest-list")

        if not video_cards:
            logger.debug("MGTOW.tv: no .video-latest-list cards found")
            return []

        seen_urls: set[str] = set()
        for card in video_cards:
            if len(posts) >= limit:
                break

            # Title + URL from .video-title a
            title_el = card.select_one(".video-title a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")

            if not title or len(title) < 5 or not href:
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Build full URL
            if href.startswith("/"):
                video_url = f"{MGTOW_BASE}{href}"
            elif href.startswith("http"):
                video_url = href
            else:
                continue

            # Thumbnail from .video-thumb img (may be lazy-loaded SVG placeholder)
            thumbnail = None
            thumb_el = card.select_one(".video-thumb img")
            if thumb_el:
                # Try data-src first (lazy load), then src
                thumbnail = thumb_el.get("data-src") or thumb_el.get("src")
                if thumbnail and thumbnail.startswith("data:"):
                    thumbnail = None  # skip SVG placeholders
                if thumbnail and thumbnail.startswith("/"):
                    thumbnail = f"{MGTOW_BASE}{thumbnail}"

            # Author + views from .video-info text like "AuthorName · 123 Views · 2 days ago"
            author = None
            views = 0
            info_el = card.select_one(".video-info")
            if info_el:
                info_text = info_el.get_text(strip=True)
                # Extract view count
                view_match = re.search(r"([\d,]+)\s*Views?", info_text, re.IGNORECASE)
                if view_match:
                    try:
                        views = int(view_match.group(1).replace(",", ""))
                    except ValueError:
                        pass
                # Author is typically the first part before views
                # e.g. "Better Bachelor61 Views·1 day ago" or "T F Monkey · 662 Views"
                author_match = re.match(r"^(.+?)[\d,]+\s*Views?", info_text, re.IGNORECASE)
                if author_match:
                    author = author_match.group(1).strip().rstrip("·").strip()

            posts.append(
                NormalizedPost(
                    title=title[:200],
                    url=video_url,
                    body="",
                    source="mgtow.tv",
                    source_community="MGTOW.tv",
                    score=views,
                    published_at=datetime.now(timezone.utc),
                    thumbnail_url=thumbnail,
                    author=author,
                    comment_count=0,
                    tags=[],
                    source_permalink=video_url,
                )
            )

        logger.info("MGTOW.tv: fetched %d videos", len(posts))
        return posts

    # ── Comment fetching ──────────────────────────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top comments for an MGTOW.tv video by like count.

        Scrapes the /watch/... page and extracts comment blocks using the
        actual DOM structure (as of 2026-04):

          <div class="main-comment">
            <a href="/@AuthorName">AuthorName</a>
            <div class="comment-text"><p>Comment body…</p></div>
            <div class="div-vote-comment-btn">
              <span data-comment-likes="..."><span>N</span></span>
              <span data-comment-dislikes="..."><span>N</span></span>
            </div>
          </div>

        Skips comments that contain URLs (spam filtering).
        """
        watch_url = getattr(post, "source_permalink", None) or post.url
        if not watch_url or "/watch/" not in watch_url:
            return []

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            resp = requests.get(watch_url, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning("MGTOW.tv comment fetch failed for %s: %s", watch_url, e)
            return []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []

        soup = BeautifulSoup(html, "html.parser")
        raw_comments: list[NormalizedComment] = []
        seen_keys: set[str] = set()

        for el in soup.select(".main-comment"):
            # ── Author ──
            author_el = el.select_one('a[href*="/@"]')
            author = author_el.get_text(strip=True) if author_el else "Anonymous"

            # ── Body ──
            body_el = el.select_one(".comment-text")
            if not body_el:
                continue
            p_tag = body_el.select_one("p")
            body = (p_tag.get_text(strip=True) if p_tag
                    else body_el.get_text(strip=True))
            if not body or len(body) < 5:
                continue

            # ── Skip comments containing URLs (spam filter) ──
            if re.search(r"https?://", body, re.IGNORECASE):
                logger.debug("MGTOW.tv: skipping comment with URL by %s", author)
                continue

            # ── Likes / Dislikes ──
            likes = 0
            dislikes = 0
            likes_el = el.select_one("span[data-comment-likes]")
            if likes_el:
                inner = likes_el.select_one("span")
                if inner:
                    try:
                        likes = int(inner.get_text(strip=True))
                    except ValueError:
                        pass
            dislikes_el = el.select_one("span[data-comment-dislikes]")
            if dislikes_el:
                inner = dislikes_el.select_one("span")
                if inner:
                    try:
                        dislikes = int(inner.get_text(strip=True))
                    except ValueError:
                        pass

            score = likes - dislikes

            # ── Dedup by author + body prefix ──
            dedup_key = f"{author}:{body[:50]}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            if len(body) > 1000:
                body = body[:1000] + "…"

            raw_comments.append(
                NormalizedComment(
                    body=body,
                    author=author,
                    score=score,
                    source="mgtow.tv",
                )
            )

        # Sort by score descending, assign ranks
        raw_comments.sort(key=lambda c: c.score, reverse=True)
        for i, c in enumerate(raw_comments):
            c.rank = i + 1

        selected = raw_comments[:limit]

        if selected:
            logger.debug(
                "MGTOW.tv comments for '%s': fetched %d, selected top %d",
                post.title[:40], len(raw_comments), len(selected),
            )
        return selected
