"""
Generic RSS/Atom collector.

Works with any standard RSS or Atom feed — Reuters, Ars Technica,
ScienceDaily, etc.  Just point it at a feed URL.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import requests

from models import NormalizedPost

from .base import BaseCollector

logger = logging.getLogger("content_importer.rss")


class RSSCollector(BaseCollector):
    """Collect posts from any RSS / Atom feed URL."""

    def fetch(self) -> list[NormalizedPost]:
        url = self.config.get("url", "")
        source_label = self.config.get("source_label", "rss")
        limit = self.config.get("limit", 20)
        community = self.config.get("community", "news")

        if not url:
            logger.error("RSS collector %s has no url configured", self.name)
            return []

        try:
            # feedparser can parse from URL directly, but we want timeout control
            resp = requests.get(url, timeout=15, headers={"User-Agent": "OratioContentImporter/1.0"})
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception as e:
            logger.error("RSS fetch failed for %s (%s): %s", self.name, url, e)
            return []

        posts: list[NormalizedPost] = []
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            # Body: prefer summary, fall back to content
            body = ""
            if hasattr(entry, "summary"):
                body = entry.summary
            elif hasattr(entry, "content"):
                body = entry.content[0].get("value", "") if entry.content else ""
            # Strip HTML tags (simple)
            import re

            body = re.sub(r"<[^>]+>", "", body).strip()
            if len(body) > 2000:
                body = body[:2000] + "…"

            # Published date
            published = datetime.now(timezone.utc)
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                try:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            # Thumbnail / media
            thumbnail = None
            media_url = None
            if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                thumbnail = entry.media_thumbnail[0].get("url")
            if hasattr(entry, "media_content") and entry.media_content:
                media_url = entry.media_content[0].get("url")

            # Tags
            tags = []
            if hasattr(entry, "tags"):
                tags = [t.get("term", "") for t in entry.tags if t.get("term")]

            posts.append(
                NormalizedPost(
                    title=title,
                    url=link,
                    body=body,
                    source=source_label,
                    source_community=feed.feed.get("title", source_label),
                    score=0,  # RSS feeds don't have scores
                    published_at=published,
                    media_url=media_url,
                    thumbnail_url=thumbnail,
                    author=entry.get("author"),
                    comment_count=0,
                    tags=tags,
                )
            )

        logger.info("RSS %s: fetched %d posts", self.name, len(posts))
        return posts
