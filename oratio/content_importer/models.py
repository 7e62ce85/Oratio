"""
Normalized data models for the content importer pipeline.

Every collector converts source-specific data into these models,
so the rest of the pipeline (AI selector, dedup, poster) is source-agnostic.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NormalizedPost:
    """Source-agnostic post representation."""

    title: str
    url: str
    body: str  # summary / description / self-text
    source: str  # "reddit", "reuters", "youtube", …
    source_community: str  # subreddit, channel, section, …
    score: int  # upvotes, views, engagement metric
    published_at: datetime
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    author: Optional[str] = None
    comment_count: int = 0
    tags: list[str] = field(default_factory=list)
    # Original source-site URL for comment fetching (e.g. Reddit permalink
    # when post.url is the external article URL)
    source_permalink: Optional[str] = None

    # Source-specific unique ID (e.g. Rumble numeric video ID, Reddit post ID)
    # Used by collectors that need the ID for API calls (e.g. comment fetching)
    source_id: Optional[str] = None

    # Top comments from the source (fetched after selection)
    top_comments: list["NormalizedComment"] = field(default_factory=list)

    # Set after AI ranking
    ai_rank: Optional[int] = None
    ai_reason: Optional[str] = None

    @property
    def fingerprint(self) -> str:
        """Deterministic hash for dedup — based on canonical URL."""
        return hashlib.sha256(self.url.encode()).hexdigest()[:32]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "body": self.body,
            "source": self.source,
            "source_community": self.source_community,
            "score": self.score,
            "published_at": self.published_at.isoformat(),
            "media_url": self.media_url,
            "thumbnail_url": self.thumbnail_url,
            "author": self.author,
            "comment_count": self.comment_count,
            "tags": self.tags,
            "source_permalink": self.source_permalink,
            "source_id": self.source_id,
            "ai_rank": self.ai_rank,
            "ai_reason": self.ai_reason,
            "fingerprint": self.fingerprint,
        }


@dataclass
class NormalizedComment:
    """A top-level comment to repost alongside a post (Phase 2)."""

    body: str
    author: str
    score: int
    source: str
    rank: int = 0  # Popularity rank among all comments (1 = best)
