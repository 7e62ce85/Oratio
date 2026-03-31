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

from models import NormalizedPost
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
                )
            )

        logger.info("MGTOW.tv: fetched %d videos", len(posts))
        return posts
