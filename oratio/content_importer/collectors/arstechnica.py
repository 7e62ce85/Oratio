"""
Ars Technica collector — extends RSS collector with Civis forum comment scraping.

ArsTechnica articles link to discussion threads on their Civis forum
(XenForo-based). Each article page contains a link like:
    https://arstechnica.com/civis/threads/<slug>.<thread_id>/

Comment structure (XenForo):
    article.message--post[data-author="username"]
        .bbWrapper  → comment body
        .message-footer  → "Upvote<total>(<up>/<down>)QuoteReport"
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import requests

from models import NormalizedPost, NormalizedComment
from .rss_news import RSSCollector

logger = logging.getLogger("content_importer.arstechnica")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class ArsTechnicaCollector(RSSCollector):
    """RSS collector + Civis forum comment scraping for Ars Technica."""

    # ── Comment fetching ──────────────────────────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top comments from the ArsTechnica Civis forum thread.

        1. Load the article page to find the Civis thread URL
        2. Scrape the Civis thread (XenForo SSR page)
        3. Extract comments with upvote/downvote scores
        4. Return top N by net score
        """
        article_url = post.url
        if not article_url:
            return []

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        # Step 1: Find the Civis thread URL from the article page
        civis_url = self._find_civis_url(article_url, headers)
        if not civis_url:
            logger.debug("ArsTechnica: no Civis thread found for %s", article_url)
            return []

        # Step 2: Scrape the Civis thread
        try:
            resp = requests.get(civis_url, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning("ArsTechnica Civis fetch failed for %s: %s", civis_url, e)
            return []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 not installed")
            return []

        soup = BeautifulSoup(html, "html.parser")

        # Step 3: Parse XenForo message posts
        articles = soup.select("article.message--post")
        if not articles:
            return []

        raw_comments: list[NormalizedComment] = []

        for article in articles[1:]:  # Skip first (OP / article summary)
            author = article.get("data-author", "Anonymous")

            # Body from .bbWrapper
            body_el = article.select_one(".bbWrapper")
            if not body_el:
                continue

            # Remove nested quotes (blockquote) — only keep the commenter's own words
            for quote in body_el.select("blockquote"):
                quote.decompose()

            body = body_el.get_text(strip=True)
            if not body or len(body) < 5:
                continue

            # Skip comments with URLs (spam filter)
            if re.search(r"https?://", body, re.IGNORECASE):
                continue

            # Score from .message-footer: "Upvote<total>(<up>/<down>)QuoteReport"
            score = 0
            footer = article.select_one(".message-footer")
            if footer:
                footer_text = footer.get_text(strip=True)
                m = re.search(r"Upvote\s*(\d+)\s*\((\d+)/(\d+)\)", footer_text)
                if m:
                    score = int(m.group(2)) - int(m.group(3))
                else:
                    m2 = re.search(r"Upvote\s*(\d+)", footer_text)
                    if m2:
                        score = int(m2.group(1))

            if len(body) > 1000:
                body = body[:1000] + "…"

            raw_comments.append(
                NormalizedComment(
                    body=body,
                    author=author,
                    score=score,
                    source="arstechnica",
                )
            )

        # Sort by score descending, assign ranks
        raw_comments.sort(key=lambda c: c.score, reverse=True)
        for i, c in enumerate(raw_comments):
            c.rank = i + 1

        selected = raw_comments[:limit]

        if selected:
            logger.debug(
                "ArsTechnica comments for '%s': fetched %d, selected top %d (scores: %s)",
                post.title[:40],
                len(raw_comments),
                len(selected),
                [c.score for c in selected],
            )
        return selected

    @staticmethod
    def _find_civis_url(article_url: str, headers: dict) -> Optional[str]:
        """Extract the Civis forum thread URL from an ArsTechnica article page."""
        try:
            resp = requests.get(article_url, headers=headers, timeout=15)
            resp.raise_for_status()
        except Exception:
            return None

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for link to Civis thread: <a href="...civis/threads/...">
        civis_link = soup.select_one('a[href*="/civis/threads/"]')
        if civis_link:
            return civis_link.get("href")

        return None
