"""
Bitchute collector — uses the Bitchute search API.

Bitchute is a Vue.js SPA with no server-rendered HTML, so scraping is
impossible. However, it has a public POST API at:
  POST https://api.bitchute.com/api/beta/search/videos

We search for broad terms (news, politics, technology) and merge results
to simulate a "trending" feed.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

from models import NormalizedPost
from .base import BaseCollector

logger = logging.getLogger("content_importer.bitchute")

BITCHUTE_BASE = "https://www.bitchute.com"
BITCHUTE_API = "https://api.bitchute.com/api/beta/search/videos"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Search queries to simulate a "trending" feed
DEFAULT_QUERIES = ["news", "politics", "technology", "world", "breaking"]


class BitchuteCollector(BaseCollector):
    """Collect recent popular videos from Bitchute via search API."""

    def fetch(self) -> list[NormalizedPost]:
        limit = self.config.get("limit", 15)
        queries = self.config.get("search_queries", DEFAULT_QUERIES)

        all_posts: list[NormalizedPost] = []
        seen_ids: set[str] = set()

        per_query = max(limit // len(queries), 5)

        for query in queries:
            try:
                videos = self._search(query, per_query)
                for v in videos:
                    vid = v.get("video_id", "")
                    if vid and vid not in seen_ids:
                        seen_ids.add(vid)
                        post = self._to_post(v)
                        if post:
                            all_posts.append(post)
            except Exception as e:
                logger.warning("Bitchute search '%s' failed: %s", query, e)

        # Sort by view count descending, pick top N
        all_posts.sort(key=lambda p: p.score, reverse=True)
        result = all_posts[:limit]

        logger.info("Bitchute (API): fetched %d videos from %d queries", len(result), len(queries))
        return result

    def _search(self, query: str, limit: int) -> list[dict]:
        """Call Bitchute search API."""
        resp = requests.post(
            BITCHUTE_API,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
            },
            json={"query": query, "limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("videos", [])

    def _to_post(self, video: dict) -> Optional[NormalizedPost]:
        """Convert Bitchute API video object to NormalizedPost."""
        title = video.get("video_name", "").strip()
        video_id = video.get("video_id", "")

        if not title or not video_id:
            return None

        url = f"{BITCHUTE_BASE}/video/{video_id}/"
        description = video.get("description", "") or ""
        # Strip HTML tags from description
        body = re.sub(r"<[^>]+>", "", description).strip()

        thumbnail = video.get("thumbnail_url")
        view_count = video.get("view_count", 0) or 0

        # Channel info
        author = None
        channel = video.get("channel")
        if channel:
            author = channel.get("channel_name")

        # Published date
        published = datetime.now(timezone.utc)
        date_str = video.get("date_published")
        if date_str:
            try:
                # Format: "2026-03-30T21:38:52.935962Z"
                published = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                pass

        return NormalizedPost(
            title=title[:200],
            url=url,
            body=body[:1000] if body else "",
            source="bitchute",
            source_community="Bitchute",
            score=view_count,
            published_at=published,
            thumbnail_url=thumbnail,
            author=author,
            comment_count=0,
            tags=[],
        )
