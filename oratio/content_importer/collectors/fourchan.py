"""
4chan collector — uses the public JSON API.

4chan provides a free, no-auth JSON API:
  - Thread list: https://a.4cdn.org/{board}/catalog.json
  - Thread detail: https://a.4cdn.org/{board}/thread/{no}.json

We fetch the catalog and extract the most-replied threads.
Supports comment fetching via thread JSON endpoint.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

from models import NormalizedPost, NormalizedComment
from .base import BaseCollector

logger = logging.getLogger("content_importer.fourchan")

FOURCHAN_CDN = "https://a.4cdn.org"
FOURCHAN_BOARDS = "https://boards.4chan.org"
USER_AGENT = "OratioContentImporter/1.0"


class FourChanCollector(BaseCollector):
    """Collect top threads from a 4chan board via the JSON API."""

    def fetch(self) -> list[NormalizedPost]:
        board = self.config.get("board", "pol")
        limit = self.config.get("limit", 20)

        catalog_url = f"{FOURCHAN_CDN}/{board}/catalog.json"
        headers = {"User-Agent": USER_AGENT}

        try:
            resp = requests.get(catalog_url, headers=headers, timeout=15)
            resp.raise_for_status()
            pages = resp.json()
        except Exception as e:
            logger.error("4chan catalog fetch failed for /%s/: %s", board, e)
            return []

        # Flatten all threads from all pages
        threads = []
        for page in pages:
            for thread in page.get("threads", []):
                threads.append(thread)

        # Sort by replies (most active threads first)
        threads.sort(key=lambda t: t.get("replies", 0), reverse=True)

        posts: list[NormalizedPost] = []
        for thread in threads[:limit]:
            no = thread.get("no")
            if not no:
                continue

            # Subject line (not all threads have one)
            subject = thread.get("sub", "")
            # Comment body (the OP's message)
            comment = thread.get("com", "")

            # Clean HTML entities and tags from comment
            comment = self._clean_html(comment)
            subject = self._clean_html(subject)

            # Build title: prefer subject, fall back to truncated comment
            if subject:
                title = subject
            elif comment:
                title = comment[:150] + ("…" if len(comment) > 150 else "")
            else:
                title = f"/{board}/ thread #{no}"

            # Thread URL
            url = f"{FOURCHAN_BOARDS}/{board}/thread/{no}"

            # Body preview
            body = comment[:2000] if comment else ""

            # Thumbnail
            thumbnail = None
            if thread.get("tim") and thread.get("ext"):
                thumbnail = f"https://i.4cdn.org/{board}/{thread['tim']}s.jpg"

            # Timestamp
            try:
                published = datetime.fromtimestamp(thread.get("time", 0), tz=timezone.utc)
            except Exception:
                published = datetime.now(timezone.utc)

            replies = thread.get("replies", 0)
            images = thread.get("images", 0)

            posts.append(
                NormalizedPost(
                    title=title,
                    url=url,
                    body=body,
                    source="4chan",
                    source_community=f"/{board}/",
                    score=replies,  # Use reply count as engagement metric
                    published_at=published,
                    thumbnail_url=thumbnail,
                    author="Anonymous",
                    comment_count=replies,
                    tags=[],
                )
            )

        logger.info("4chan /%s/: fetched %d threads", board, len(posts))
        return posts

    # ── Comment fetching ──────────────────────────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top replies from a 4chan thread, ranked by reply count.

        4chan doesn't have a score system, so we use "how many times a post
        is quoted/replied to" as a proxy for engagement.
        Uses: https://a.4cdn.org/{board}/thread/{no}.json
        """
        # Extract board and thread number from URL
        # URL format: https://boards.4chan.org/{board}/thread/{no}
        import re as _re
        match = _re.search(r"/([a-z]+)/thread/(\d+)", post.url)
        if not match:
            return []

        board = match.group(1)
        thread_no = match.group(2)

        thread_url = f"{FOURCHAN_CDN}/{board}/thread/{thread_no}.json"
        headers = {"User-Agent": USER_AGENT}

        try:
            resp = requests.get(thread_url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("4chan thread fetch failed for /%s/%s: %s", board, thread_no, e)
            return []

        replies = data.get("posts", [])
        if len(replies) <= 1:
            return []

        # Skip the OP (first post), only look at replies
        reply_posts = replies[1:]

        # Count how often each post number is quoted (>>12345)
        quote_counts: dict[int, int] = {}
        for r in reply_posts:
            com = r.get("com", "")
            # Find all >>12345 references
            quoted = _re.findall(r"&gt;&gt;(\d+)", com)
            for q in quoted:
                quote_counts[int(q)] = quote_counts.get(int(q), 0) + 1

        # Build comments with their "score" (quote count)
        raw_comments: list[NormalizedComment] = []
        for r in reply_posts:
            no = r.get("no", 0)
            com = r.get("com", "")
            if not com:
                continue

            body = self._clean_html(com)
            if not body or len(body) < 10:
                continue

            # Truncate long comments
            if len(body) > 1000:
                body = body[:1000] + "…"

            score = quote_counts.get(no, 0)

            raw_comments.append(
                NormalizedComment(
                    body=body,
                    author="Anonymous",
                    score=score,
                    source="4chan",
                )
            )

        # Sort by quote count (most-quoted = most engaged)
        raw_comments.sort(key=lambda c: c.score, reverse=True)

        # Assign rank (1-based) across ALL qualifying comments
        for i, c in enumerate(raw_comments):
            c.rank = i + 1

        selected = raw_comments[:limit]

        if selected:
            logger.debug(
                "4chan comments for thread %s: fetched %d, selected top %d (ranks: %s)",
                thread_no, len(raw_comments), len(selected),
                [c.rank for c in selected],
            )
        return selected

    @staticmethod
    def _clean_html(text: str) -> str:
        """Remove HTML tags and decode common entities from 4chan HTML."""
        if not text:
            return ""
        # Replace <br> with newlines
        text = re.sub(r"<br\s*/?>", "\n", text)
        # Remove quote links like <a href="#p12345" class="quotelink">&gt;&gt;12345</a>
        text = re.sub(r'<a[^>]*class="quotelink"[^>]*>[^<]*</a>', "", text)
        # Remove all remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode HTML entities
        text = text.replace("&gt;", ">").replace("&lt;", "<")
        text = text.replace("&amp;", "&").replace("&quot;", '"')
        text = text.replace("&#039;", "'").replace("&apos;", "'")
        return text.strip()
