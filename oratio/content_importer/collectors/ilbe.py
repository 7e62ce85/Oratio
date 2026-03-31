"""
Ilbe popular-posts collector — scrapes the HTML board listing.

Ilbe does not provide a public API, so we parse the board listing page and
optionally fetch each post's detail page to extract the first image as a
thumbnail (for Lemmy's custom_thumbnail field).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from models import NormalizedPost
from .base import BaseCollector

logger = logging.getLogger("content_importer.ilbe")

ILBE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ILBE_BASE = "https://www.ilbe.com"

# ── Regex patterns for the list page ──────────────────────────────
# Each post sits inside a <li>...</li> block
_ROW_RE = re.compile(r'<li>\s*(.*?)\s*</li>', re.DOTALL)
# Post link: <a href="/view/{id}" class="subject ...">Title</a>
_LINK_RE = re.compile(
    r'<a\s+href="/view/(\d+)"\s+class="subject[^"]*"[^>]*>\s*(.*?)\s*</a>',
    re.DOTALL,
)
# Recommendation count inside same row: <span class="recomm">123</span>
_RECOMM_RE = re.compile(r'<span\s+class="recomm">(\d+)</span>')

# ── Regex for extracting the first content image from a post page ─
# The post body lives inside <div class="post-content">...</div>.
# Images can appear in two forms:
#   1) Normal:    src="https://ncache.ilbe.com/files/..."
#   2) Lazy-load: src="/img/transparent.gif" data="https://ncache.ilbe.com/..."
_POST_CONTENT_RE = re.compile(
    r'<div\s+class="post-content">(.*?)</div>',
    re.DOTALL,
)
_CONTENT_IMG_SRC_RE = re.compile(
    r'<img[^>]+src="(https://(?:ncache|cache)\.ilbe\.com/files/[^"]+\.(?:jpg|jpeg|png|gif|webp))"',
    re.IGNORECASE,
)
_CONTENT_IMG_DATA_RE = re.compile(
    r'<img[^>]+data="(https://(?:ncache|cache)\.ilbe\.com/files/[^"]+\.(?:jpg|jpeg|png|gif|webp))"',
    re.IGNORECASE,
)
# Video posts use <video poster="...">
_VIDEO_POSTER_RE = re.compile(
    r'<video[^>]+poster="(https://[^"]+)"',
    re.IGNORECASE,
)


class IlbeCollector(BaseCollector):
    """Collect popular posts from Ilbe by scraping the list page."""

    def fetch(self) -> list[NormalizedPost]:
        board = self.config.get("board", "ilbe")
        limit = min(self.config.get("limit", 20), 50)
        fetch_thumbnails = self.config.get("fetch_thumbnails", True)

        url = f"{ILBE_BASE}/list/{board}"
        params = {"page": "1"}
        headers = {
            "User-Agent": ILBE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": ILBE_BASE,
        }

        try:
            resp = self._fetch_with_retry(url, params=params, headers=headers)
            html = resp.text
        except Exception as e:
            logger.error("Ilbe fetch failed for board '%s': %s", board, e)
            return []

        posts = self._parse_list(html, board, limit)
        logger.info("Ilbe /%s: fetched %d posts", board, len(posts))

        # Fetch thumbnails from individual post pages
        if fetch_thumbnails and posts:
            self._fill_thumbnails(posts, headers)

        return posts

    # ── HTTP fetch with retry ─────────────────────────────────────

    @staticmethod
    def _fetch_with_retry(
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        max_retries: int = 3,
        timeout: int = 30,
    ) -> requests.Response:
        """GET with retry on timeout / connection errors."""
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(
                    url, params=params, headers=headers, timeout=timeout
                )
                resp.raise_for_status()
                return resp
            except Exception as e:
                last_exc = e
                if attempt < max_retries:
                    wait = 5 * attempt
                    logger.warning(
                        "Ilbe request failed (attempt %d/%d), retry in %ds: %s",
                        attempt, max_retries, wait, e,
                    )
                    time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    # ── List-page parser ──────────────────────────────────────────

    def _parse_list(
        self, html: str, board: str, limit: int
    ) -> list[NormalizedPost]:
        posts: list[NormalizedPost] = []

        # Parse each <li> block that contains a post link
        for row_match in _ROW_RE.finditer(html):
            if len(posts) >= limit:
                break

            row = row_match.group(1)
            link_match = _LINK_RE.search(row)
            if not link_match:
                continue

            post_id = link_match.group(1)
            raw_title = link_match.group(2)

            # Clean title — strip HTML tags (comment count badges, etc.)
            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            if not title:
                continue

            # Extract recomm from same row block
            recomm_match = _RECOMM_RE.search(row)
            score = int(recomm_match.group(1)) if recomm_match else 0

            post_url = f"{ILBE_BASE}/view/{post_id}"

            posts.append(
                NormalizedPost(
                    title=title,
                    url=post_url,
                    body="",
                    source="ilbe",
                    source_community=board,
                    score=score,
                    published_at=datetime.now(timezone.utc),
                    author=None,
                    thumbnail_url=None,  # filled later by _fill_thumbnails
                )
            )

        return posts

    # ── Thumbnail extractor ───────────────────────────────────────

    def _fill_thumbnails(
        self, posts: list[NormalizedPost], headers: dict[str, str]
    ) -> None:
        """
        For each post, fetch its detail page and extract the first
        content image as a thumbnail URL.

        We use a short timeout and skip gracefully on failure so that
        a slow / broken post page doesn't block the whole pipeline.
        """
        filled = 0
        for post in posts:
            try:
                resp = requests.get(
                    post.url, headers=headers, timeout=10, allow_redirects=True
                )
                if resp.status_code != 200:
                    continue

                # Extract only the post-content div to avoid ad images
                content_match = _POST_CONTENT_RE.search(resp.text)
                if not content_match:
                    continue
                content_html = content_match.group(1)

                # Try: lazy-load data attr → normal src → video poster
                img_match = _CONTENT_IMG_DATA_RE.search(content_html)
                if not img_match:
                    img_match = _CONTENT_IMG_SRC_RE.search(content_html)
                if not img_match:
                    img_match = _VIDEO_POSTER_RE.search(content_html)
                if img_match:
                    post.thumbnail_url = img_match.group(1)
                    filled += 1
            except Exception:
                # Network hiccup for one post — skip silently
                pass

        logger.info(
            "Ilbe thumbnails: filled %d / %d posts", filled, len(posts)
        )
