"""
Lemmy API client for the content importer.

Handles:
  - Bot account login (OratioRepostBot)
  - Community lookup / creation
  - Post creation with proper formatting
  - (Phase 2) Comment creation
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

import config
from models import NormalizedPost, NormalizedComment

logger = logging.getLogger("content_importer.lemmy_client")


class LemmyClient:
    """Minimal Lemmy API v3 client for posting content."""

    def __init__(self):
        self.base = config.LEMMY_API_URL.rstrip("/")
        self.jwt: Optional[str] = None
        self._community_cache: dict[str, int] = {}

    # ── Auth ───────────────────────────────────────────────────────

    def login(self, max_retries: int = 3) -> bool:
        """Login as the bot account."""
        if not config.LEMMY_BOT_PASSWORD:
            logger.error("LEMMY_BOT_PASSWORD is not set")
            return False

        url = f"{self.base}/api/v3/user/login"
        payload = {
            "username_or_email": config.LEMMY_BOT_USERNAME,
            "password": config.LEMMY_BOT_PASSWORD,
        }

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(1.0 * attempt)
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if "jwt" in data:
                        self.jwt = data["jwt"]
                        logger.info("✅ Logged in as %s", config.LEMMY_BOT_USERNAME)
                        return True
                logger.warning(
                    "Login attempt %d failed: %s %s",
                    attempt + 1,
                    resp.status_code,
                    resp.text[:200],
                )
            except Exception as e:
                logger.error("Login error: %s", e)

        return False

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.jwt:
            h["Authorization"] = f"Bearer {self.jwt}"
        return h

    def ensure_logged_in(self) -> bool:
        if self.jwt:
            return True
        return self.login()

    # ── Community ─────────────────────────────────────────────────

    def get_community_id(self, name: str) -> Optional[int]:
        """Resolve community name → id. Caches results."""
        if name in self._community_cache:
            return self._community_cache[name]

        url = f"{self.base}/api/v3/community"
        try:
            resp = requests.get(
                url, params={"name": name}, headers=self._headers(), timeout=10
            )
            if resp.status_code == 200:
                cid = resp.json()["community_view"]["community"]["id"]
                self._community_cache[name] = cid
                return cid
            else:
                logger.warning("Community '%s' not found: %s", name, resp.status_code)
        except Exception as e:
            logger.error("Error looking up community '%s': %s", name, e)
        return None

    def create_community(self, name: str, title: str | None = None) -> Optional[int]:
        """Create a community if it doesn't exist."""
        if not self.ensure_logged_in():
            return None

        existing = self.get_community_id(name)
        if existing:
            return existing

        url = f"{self.base}/api/v3/community"
        payload = {
            "name": name,
            "title": title or name.replace("_", " ").title(),
        }
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                cid = resp.json()["community_view"]["community"]["id"]
                self._community_cache[name] = cid
                logger.info("✅ Created community: %s (id=%d)", name, cid)
                return cid
            else:
                logger.error(
                    "Failed to create community '%s': %s %s",
                    name,
                    resp.status_code,
                    resp.text[:200],
                )
        except Exception as e:
            logger.error("Error creating community '%s': %s", name, e)
        return None

    # ── Post ──────────────────────────────────────────────────────

    @staticmethod
    def _valid_title(title: str) -> bool:
        """Lemmy rejects titles without at least one alphanumeric char."""
        import re
        stripped = (title or "").strip()
        if not stripped:
            return False
        # Must contain at least one word-character (letter/digit/underscore)
        return bool(re.search(r"\w", stripped))

    def create_post(self, post: NormalizedPost, community_name: str) -> Optional[int]:
        """
        Create a Lemmy post from a NormalizedPost.

        Returns the Lemmy post ID or None on failure.
        """
        if not self._valid_title(post.title):
            logger.warning("⏭️ Skipping post with invalid title: %r", (post.title or "")[:80])
            return None

        if not self.ensure_logged_in():
            return None

        community_id = self.get_community_id(community_name)
        if not community_id:
            # Try to create it
            community_id = self.create_community(community_name)
        if not community_id:
            logger.error("Cannot resolve community '%s', skipping post", community_name)
            return None

        # Format body with source attribution
        body = self._format_body(post)

        payload = {
            "name": post.title[:200],  # Lemmy title limit
            "community_id": community_id,
            "url": post.url,
            "body": body,
            "nsfw": False,
        }

        # If a thumbnail was scraped, pass it so Lemmy doesn't rely on og:image
        if post.thumbnail_url:
            payload["custom_thumbnail"] = post.thumbnail_url

        url = f"{self.base}/api/v3/post"
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                post_id = resp.json()["post_view"]["post"]["id"]
                logger.info("✅ Posted: [%d] %s", post_id, post.title[:60])
                return post_id
            else:
                logger.error(
                    "Failed to create post: %s %s",
                    resp.status_code,
                    resp.text[:300],
                )
        except Exception as e:
            logger.error("Error creating post: %s", e)
        return None

    def _format_body(self, post: NormalizedPost) -> str:
        """Build the Markdown body for a reposted piece of content."""
        parts = []

        # Source attribution
        # If source_permalink exists (e.g. upgoat viewpost, reddit comments),
        # link "Source" to that page. The post URL (title link) stays as the
        # original external article.
        source_link_url = post.source_permalink or post.url
        parts.append(
            f"📰 **Source**: [{post.source}]({source_link_url}) "
            f"| **{post.source_community}**"
        )

        if post.author:
            parts.append(f"✍️ **Original author**: {post.author}")

        if post.score:
            score_label = "upvotes" if post.source == "reddit" else "score"
            parts.append(f"⬆️ **{score_label}**: {post.score:,}")

        parts.append("---")

        if post.body:
            parts.append(post.body)

        # Embed media (gif/mp4) directly in body for sources like 9GAG
        if post.media_url and post.media_url.endswith((".mp4", ".webm", ".gif")):
            parts.append(f"![media]({post.media_url})")

        parts.append("")
        parts.append(
            "*This post was automatically imported by OratioRepostBot.*"
        )

        return "\n\n".join(parts)

    # ── Comment (Phase 2) ─────────────────────────────────────────

    def create_comment(
        self, post_id: int, comment: NormalizedComment
    ) -> Optional[int]:
        """Post a comment on an existing Lemmy post."""
        if not self.ensure_logged_in():
            return None

        # Format: "💬 User69's Top Comment #3 (⬆️ 1,234):"
        rank_str = f" #{comment.rank}" if comment.rank else ""
        score_label = "replies" if comment.source == "4chan" else "⬆️"
        body = (
            f"💬 **{comment.author}**'s Top Comment{rank_str} "
            f"({comment.source}, {score_label} {comment.score:,}):\n\n"
            f"> {comment.body}"
        )

        url = f"{self.base}/api/v3/comment"
        payload = {
            "post_id": post_id,
            "content": body,
        }
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                cid = resp.json()["comment_view"]["comment"]["id"]
                logger.info("✅ Comment posted on post %d", post_id)
                return cid
            else:
                logger.warning("Failed to post comment: %s", resp.text[:200])
        except Exception as e:
            logger.error("Error posting comment: %s", e)
        return None
