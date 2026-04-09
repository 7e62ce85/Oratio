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
from .html_utils import clean_html_to_text

logger = logging.getLogger("content_importer.youtube")

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# ── US TV broadcast networks whose full-episode uploads are geo-locked ──
# These channels routinely upload full shows/episodes that are only playable
# inside the US due to DRM / broadcast licensing, even though the YouTube
# Data API does NOT report regionRestriction for them.
# Matching is case-insensitive substring.
_GEO_LOCKED_CHANNEL_KEYWORDS: set[str] = {
    # US broadcast / cable TV networks
    "espn", "espn2", "fox news", "fox sports", "fox business",
    "cnn", "msnbc", "cnbc", "abc news", "cbs news", "nbc news",
    "tbs", "tnt", "tru tv", "usa network",
    "amc", "amc+", "tlc", "hgtv", "food network", "discovery",
    "bravo", "e! entertainment", "syfy", "lifetime",
    "golf channel", "nfl network", "nba tv", "mlb network",
    "nbcsn", "nbc sports", "cbs sports", "fox sports 1",
    "comedy central", "mtv", "bet", "vh1", "nickelodeon",
    "cartoon network", "adult swim", "paramount network",
    "a&e", "history", "hallmark",
    # Sports-specific
    "sec network", "acc network", "big ten network",
}


class YouTubeCollector(BaseCollector):
    """Collect trending YouTube videos via Data API v3."""

    # Maximum video duration (seconds) to import.
    # Full TV episodes / live replays are typically > 30 min.
    # We allow up to 30 min by default; override with "max_duration_sec" in source config.
    DEFAULT_MAX_DURATION_SEC = 30 * 60  # 30 minutes

    def fetch(self) -> list[NormalizedPost]:
        api_key = config.YOUTUBE_API_KEY
        if not api_key:
            logger.warning("YOUTUBE_API_KEY not set — YouTube source disabled")
            return []
        return self._fetch_trending(api_key)

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _is_geo_locked_channel(channel_title: str) -> bool:
        """Return True if channel name matches a known US-TV geo-locked network."""
        lower = channel_title.lower().strip()
        for kw in _GEO_LOCKED_CHANNEL_KEYWORDS:
            if kw in lower:
                return True
        return False

    @staticmethod
    def _parse_iso8601_duration(duration: str) -> int:
        """Parse ISO 8601 duration (e.g. PT2H38M28S) into total seconds."""
        match = re.match(
            r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", duration or ""
        )
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    # -- Trending API --------------------------------------------------

    def _fetch_trending(self, api_key: str) -> list[NormalizedPost]:
        """Fetch trending (most popular) videos via YouTube Data API v3."""
        limit = min(self.config.get("limit", 25), 50)  # API max 50
        region = self.config.get("region_code", "US")
        category = self.config.get("category_id", "")

        params: dict = {
            "part": "snippet,statistics,contentDetails,status",
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

        skipped_region = 0
        skipped_geolocked = 0
        skipped_too_long = 0
        max_duration = self.config.get(
            "max_duration_sec", self.DEFAULT_MAX_DURATION_SEC
        )

        for item in items:
            video_id = item.get("id", "")
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            content_details = item.get("contentDetails", {})
            status = item.get("status", {})

            title = snippet.get("title", "").strip()
            if not title or not video_id:
                continue

            # ── Status / region / age checks ───────────────────────
            # Skip videos that are NOT globally available, not embeddable,
            # age-restricted, or not public.

            # regionRestriction: if present => restricted in some way
            region_restriction = content_details.get("regionRestriction")
            if region_restriction:
                skipped_region += 1
                logger.debug(
                    "Skipping region-restricted video: %s (%s) — %s",
                    title[:60], video_id, region_restriction,
                )
                continue

            # privacyStatus: "public", "unlisted", "private"
            privacy = status.get("privacyStatus")
            if privacy and privacy != "public":
                logger.debug(
                    "Skipping non-public video: %s (%s) — privacy=%s",
                    title[:60], video_id, privacy,
                )
                continue

            # embeddable flag (owner can disable embedding)
            embeddable = status.get("embeddable")
            if embeddable is False:
                logger.debug(
                    "Skipping non-embeddable video: %s (%s)",
                    title[:60], video_id,
                )
                continue

            # age restriction: contentDetails.contentRating.ytRating == "ytAgeRestricted"
            content_rating = content_details.get("contentRating", {})
            if content_rating.get("ytRating") == "ytAgeRestricted":
                logger.debug(
                    "Skipping age-restricted video: %s (%s)",
                    title[:60], video_id,
                )
                continue

            # ── Geo-locked US TV network channel filter ────────────
            # Many US broadcast networks upload full episodes that are
            # DRM-locked to the US, but the API does NOT set regionRestriction.
            channel = snippet.get("channelTitle", "YouTube")
            if self._is_geo_locked_channel(channel):
                skipped_geolocked += 1
                logger.debug(
                    "Skipping geo-locked TV channel video: %s (%s) — channel=%s",
                    title[:60], video_id, channel,
                )
                continue

            # ── Duration filter (skip full episodes / live replays) ─
            duration_sec = self._parse_iso8601_duration(
                content_details.get("duration", "")
            )
            if max_duration and duration_sec > max_duration:
                skipped_too_long += 1
                logger.debug(
                    "Skipping too-long video (%ds > %ds): %s (%s)",
                    duration_sec, max_duration, title[:60], video_id,
                )
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"

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
            "YouTube Trending API (%s): fetched %d videos "
            "(skipped: %d region-restricted, %d geo-locked TV, %d too-long)",
            region, len(posts), skipped_region, skipped_geolocked,
            skipped_too_long,
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

            body = clean_html_to_text(snippet.get("textDisplay", ""))
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
