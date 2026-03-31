"""
YouTube collector — uses YouTube Data API v3.

Fetches trending (most popular) videos for a given region and optionally
a video category.  Also supports official comment fetching via
commentThreads.list endpoint.

Requires YOUTUBE_API_KEY environment variable (free, 10k units/day).

API quota usage per cycle:
  - videos.list (trending):      1 unit
  - commentThreads.list:         1 unit x number_of_selected_posts
  Total: ~3 units/cycle -> ~12 units/day -> 0.12% of free 10k limit
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

import config
from models import NormalizedPost, NormalizedComment
from .base import BaseCollector

logger = logging.getLogger("content_importer.youtube")

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeCollector(BaseCollector):
    """Collect trending YouTube videos via Data API v3."""

    def fetch(self) -> list[NormalizedPost]:
        api_key = config.YOUTUBE_API_KEY
        if not api_key:
            logger.warning("YOUTUBE_API_KEY not set — YouTube source disabled")
            return []
        return self._fetch_trending(api_key)

    # -- Trending API --------------------------------------------------

    def _fetch_trending(self, api_key: str) -> list[NormalizedPost]:
        """Fetch trending (most popular) videos via YouTube Data API v3."""
        limit = min(self.config.get("limit", 25), 50)  # API max 50
        region = self.config.get("region_code", "US")
        category = self.config.get("category_id", "")

        params: dict = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": region,
            "maxResults": limit,
            "key": api_key,
        }
        if category:
            params["videoCategoryId"] = category

        url = f"{YOUTUBE_API_BASE}/videos"

        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("YouTube Trending API failed: %s", e)
            return []

        items = data.get("items", [])
        posts: list[NormalizedPost] = []

        for item in items:
            video_id = item.get("id", "")
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})

            title = snippet.get("title", "").strip()
            if not title or not video_id:
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            channel = snippet.get("channelTitle", "YouTube")

            # Description (truncated)
            body = snippet.get("description", "")
            if len(body) > 1000:
                body = body[:1000] + "..."

            # Thumbnail -- prefer high, then medium, then default
            thumbs = snippet.get("thumbnails", {})
            thumbnail = (
                thumbs.get("high", {}).get("url")
                or thumbs.get("medium", {}).get("url")
                or thumbs.get("default", {}).get("url")
            )

            # Stats
            view_count = int(stats.get("viewCount", 0))
            comment_count = int(stats.get("commentCount", 0))

            # Published date
            published = datetime.now(timezone.utc)
            pub_str = snippet.get("publishedAt", "")
            if pub_str:
                try:
                    published = datetime.fromisoformat(
                        pub_str.replace("Z", "+00:00")
                    )
                except Exception:
                    pass

            posts.append(
                NormalizedPost(
                    title=title,
                    url=video_url,
                    body=body,
                    source="youtube",
                    source_community=channel,
                    score=view_count,
                    published_at=published,
                    thumbnail_url=thumbnail,
                    author=channel,
                    comment_count=comment_count,
                    tags=[snippet.get("categoryId", "")],
                )
            )

        logger.info(
            "YouTube Trending API (%s): fetched %d videos",
            region, len(posts),
        )
        return posts

    # -- Comment fetching (official API) --------------------------------

    def fetch_comments(
        self, post: NormalizedPost, limit: int = 3
    ) -> list[NormalizedComment]:
        """
        Fetch top comments via YouTube Data API v3 commentThreads.list.

        Costs 1 quota unit per call. Comments are sorted by relevance
        (YouTube default = top comments).
        """
        api_key = config.YOUTUBE_API_KEY
        if not api_key:
            return []

        video_id = self._extract_video_id(post.url)
        if not video_id:
            return []

        params = {
            "part": "snippet",
            "videoId": video_id,
            "order": "relevance",
            "maxResults": 20,
            "textFormat": "plainText",
            "key": api_key,
        }

        url = f"{YOUTUBE_API_BASE}/commentThreads"

        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(
                "YouTube comments API failed for %s: %s", video_id, e
            )
            return []

        items = data.get("items", [])
        raw_comments: list[NormalizedComment] = []

        for item in items:
            snippet = (
                item.get("snippet", {})
                .get("topLevelComment", {})
                .get("snippet", {})
            )
            if not snippet:
                continue

            body = snippet.get("textDisplay", "").strip()
            if not body:
                continue

            author = snippet.get("authorDisplayName", "")
            if not author:
                continue

            likes = snippet.get("likeCount", 0)

            # Truncate long comments
            if len(body) > 1000:
                body = body[:1000] + "..."

            raw_comments.append(
                NormalizedComment(
                    body=body,
                    author=author,
                    score=likes,
                    source="youtube",
                )
            )

        # Sort by likes descending, assign rank
        raw_comments.sort(key=lambda c: c.score, reverse=True)
        for i, c in enumerate(raw_comments):
            c.rank = i + 1

        selected = raw_comments[:limit]

        if selected:
            logger.debug(
                "YouTube comments for '%s': fetched %d, selected top %d "
                "(ranks: %s)",
                post.title[:40],
                len(raw_comments),
                len(selected),
                [c.rank for c in selected],
            )
        return selected

    @staticmethod
    def _extract_video_id(url: str) -> Optional[str]:
        """Extract video ID from a YouTube URL."""
        if "watch?v=" in url:
            return url.split("watch?v=")[-1].split("&")[0]
        match = re.search(r"youtu\.be/([a-zA-Z0-9_-]+)", url)
        if match:
            return match.group(1)
        return None
