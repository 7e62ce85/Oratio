"""
Rumble collector — uses the undocumented service.php JSON API.

Discovery (2026-04-02):
  Rumble's HTML pages are behind Cloudflare Turnstile (403), but the internal
  service.php API used by the SPA frontend is accessible via cloudscraper:

    GET https://rumble.com/service.php?api=2&name=media.search
        &query=<term>&sort=views&date=today

  Returns JSON with `data.items[]`, each containing:
    id, title, url, thumb, upload_date, views, duration, by.name,
    comments.count, rumble_votes, tags, video_stats, etc.

  This is the same endpoint the Rumble web app calls internally.
  No API key needed; cloudscraper handles the Cloudflare JS challenge.

  To simulate "Trending Today", we fire multiple broad queries
  (news, politics, live, trending, breaking, world, viral) with
  date=today & sort=views, de-duplicate by video ID, and sort by views.

Config options (in config.py source entry):
  - search_queries: list of broad search terms (default: see DEFAULT_SEARCH_QUERIES)
  - sort: "views" | "date" (default: "views")
  - date: "today" | "this-week" | "this-month" | "" (default: "today")

Comments (2026-04-02 reverse-engineered):
  Rumble's comment.list API requires an authenticated session obtained via
  service.php user.login. The login flow:
    1. POST service.php?name=user.get_salts  → get 3 salts
    2. Compute password_hashes using MD5 hashStretch (pajhome.org.uk MD5Ex)
    3. POST service.php?name=user.login      → session cookies
    4. POST service.php?name=comment.list    → comments for video ID

  Set RUMBLE_USERNAME / RUMBLE_PASSWORD in .env to enable comment import.
  Without credentials, video fetching still works (comments return []).
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

from models import NormalizedPost, NormalizedComment
from .base import BaseCollector

logger = logging.getLogger("content_importer.rumble")

RUMBLE_API_URL = "https://rumble.com/service.php"
DEFAULT_SEARCH_QUERIES = ["news", "politics", "live", "trending", "breaking", "world", "viral"]

# Authenticated session cache (module-level, survives across fetch cycles)
_session_cache: dict = {
    "scraper": None,
    "logged_in": False,
    "login_time": 0,
}
# Re-login every 4 hours (sessions may expire)
SESSION_TTL_SECONDS = 4 * 60 * 60


class RumbleCollector(BaseCollector):
    """Collect videos from Rumble via the internal service.php JSON API."""

    def fetch(self) -> list[NormalizedPost]:
        limit = self.config.get("limit", 15)
        queries = self.config.get("search_queries", DEFAULT_SEARCH_QUERIES)
        sort = self.config.get("sort", "views")
        date = self.config.get("date", "today")

        scraper = self._get_scraper()
        if not scraper:
            logger.warning("Rumble: cloudscraper unavailable — cannot fetch")
            return []

        posts: list[NormalizedPost] = []
        seen_ids: set[int] = set()
        seen_authors: set[str] = set()

        for query in queries:
            if len(posts) >= limit:
                break
            try:
                items = self._search_videos(scraper, query, sort, date)
                for item in items:
                    if len(posts) >= limit:
                        break
                    vid = item.get("id")
                    if vid in seen_ids:
                        continue
                    seen_ids.add(vid)

                    post = self._item_to_post(item)
                    if post:
                        # ── Per-channel cap: max 1 video per author ──
                        # Rumble trending is dominated by daily shows from
                        # the same creators (Timcast, Bongino, X22 Report…).
                        # Keep only the highest-views video per channel.
                        author_key = (post.author or "").strip().lower()
                        if author_key and author_key in seen_authors:
                            continue
                        if author_key:
                            seen_authors.add(author_key)

                        posts.append(post)
            except Exception as e:
                logger.warning("Rumble: search '%s' failed: %s", query, e)

        # Sort by score (views) descending so the most viewed today come first
        posts.sort(key=lambda p: p.score, reverse=True)
        posts = posts[:limit]

        logger.info(
            "Rumble: fetched %d videos from %d queries (date=%s, sort=%s)"
            " (dedup: %d unique channels)",
            len(posts), len(queries), date, sort, len(seen_authors),
        )
        return posts

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """Fetch top comments for a Rumble video via authenticated comment.list API.

        Requires RUMBLE_USERNAME / RUMBLE_PASSWORD to be set in .env.
        Returns up to `limit` comments sorted by score (likes - dislikes).
        """
        from config import RUMBLE_USERNAME, RUMBLE_PASSWORD

        if not RUMBLE_USERNAME or not RUMBLE_PASSWORD:
            return []

        # Extract video ID from the post URL or metadata
        video_id = self._extract_video_id(post)
        if not video_id:
            logger.debug("Rumble: could not extract video ID from %s", post.url)
            return []

        try:
            scraper = self._get_authenticated_scraper(RUMBLE_USERNAME, RUMBLE_PASSWORD)
            if not scraper:
                return []

            comments = self._fetch_comment_list(scraper, video_id, limit)
            return comments
        except Exception as e:
            logger.warning("Rumble: comment fetch failed for %s: %s", post.url, e)
            return []

    @property
    def supports_comments(self) -> bool:
        """Comments are supported when Rumble credentials are configured."""
        from config import RUMBLE_USERNAME, RUMBLE_PASSWORD
        return bool(RUMBLE_USERNAME and RUMBLE_PASSWORD)

    # ── Internal helpers ─────────────────────────────────────────

    @staticmethod
    def _get_scraper():
        """Create a cloudscraper session. Returns None if not installed."""
        try:
            import cloudscraper

            return cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
        except ImportError:
            logger.error(
                "Rumble collector requires 'cloudscraper'. "
                "Install it: pip install cloudscraper"
            )
            return None

    @staticmethod
    def _search_videos(scraper, query: str, sort: str = "views", date: str = "today") -> list[dict]:
        """Call the Rumble service.php media.search endpoint.

        Args:
            scraper: cloudscraper session
            query: search term (e.g. "news", "politics")
            sort: "views" or "date"
            date: "today", "this-week", "this-month", or "" for all-time
        """
        params = {
            "api": "2",
            "name": "media.search",
            "query": query,
            "sort": sort,
        }
        if date:
            params["date"] = date

        resp = scraper.get(RUMBLE_API_URL, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        errors = data.get("errors", [])
        if errors:
            msg = errors[0].get("message", "unknown")
            logger.warning("Rumble API error: %s", msg)
            return []

        items = data.get("data", {}).get("items", [])
        return items

    @staticmethod
    def _item_to_post(item: dict) -> Optional[NormalizedPost]:
        """Convert a Rumble API item dict into a NormalizedPost."""
        try:
            title = item.get("title", "").strip()
            url = item.get("url", "")
            if not title or not url:
                return None

            # Author
            by = item.get("by", {})
            author = by.get("name") or by.get("title") or None

            # Views — prefer total views, fall back to rumble_plays
            views = item.get("views", 0) or 0
            stats = item.get("video_stats", {})
            if not views:
                views = (stats.get("rumble_plays", 0) or 0) + (stats.get("youtube_views", 0) or 0)

            # Votes
            votes = item.get("rumble_votes", {})
            vote_score = votes.get("num_votes_up", 0) - votes.get("num_votes_down", 0)

            # Use views as the primary score (more meaningful for sorting)
            score = views if views else vote_score

            # Thumbnail
            thumbnail = item.get("thumb") or None

            # Upload date
            upload_str = item.get("upload_date", "")
            try:
                published_at = datetime.fromisoformat(upload_str)
            except (ValueError, TypeError):
                published_at = datetime.now(timezone.utc)

            # Comments count
            comment_count = item.get("comments", {}).get("count", 0) or 0

            # Tags
            tags = item.get("tags", []) or []

            # Duration (seconds)
            duration = item.get("duration", 0)

            # Build description body
            body_parts = []
            if duration:
                mins, secs = divmod(duration, 60)
                body_parts.append(f"Duration: {mins}m {secs}s")
            if author:
                body_parts.append(f"Channel: {author}")
            if views:
                body_parts.append(f"Views: {views:,}")
            body = " | ".join(body_parts)

            return NormalizedPost(
                title=title,
                url=url,
                body=body,
                source="rumble",
                source_community="rumble",
                score=score,
                published_at=published_at,
                media_url=None,
                thumbnail_url=thumbnail,
                author=author,
                comment_count=comment_count,
                tags=tags,
                source_permalink=url,
                source_id=str(item.get("id", "")),
            )
        except Exception as e:
            logger.debug("Rumble: failed to parse item: %s", e)
            return None

    # ── Authentication & Comments ────────────────────────────────

    @staticmethod
    def _md5_raw(data: bytes) -> bytes:
        """Raw MD5 hash (returns 16 bytes)."""
        return hashlib.md5(data).digest()

    @classmethod
    def _hash_stretch(cls, password: str, salt: str, iterations: int = 128) -> str:
        """Replicate Rumble's MD5Ex.hashStretch (pajhome.org.uk MD5 v2.2).

        Algorithm (from JS source):
            h = MD5_raw(salt + password)         # initial — raw 16 bytes
            for i in range(iterations):
                h = MD5_raw(h + password)         # raw bytes + password bytes
            return hex(h)

        Note: The JS md5(str, true) returns a raw binary string, NOT hex.
        The iteration concatenates raw hash bytes with the password string.
        """
        h = cls._md5_raw((salt + password).encode("utf-8"))
        pw_bytes = password.encode("utf-8")
        for _ in range(iterations):
            h = cls._md5_raw(h + pw_bytes)
        return h.hex()

    @classmethod
    def _compute_password_hashes(cls, password: str, salts: list[str]) -> list[str]:
        """Compute the 3-element password_hashes array for user.login.

        From Rumble's JS:
            s[0] = MD5(hashStretch(password, salts[0], 128) + salts[1])
            s[1] = hashStretch(password, salts[2], 128)
            s[2] = salts[1]
        """
        stretch0 = cls._hash_stretch(password, salts[0], 128)
        stretch2 = cls._hash_stretch(password, salts[2], 128)
        hash0 = hashlib.md5((stretch0 + salts[1]).encode("utf-8")).hexdigest()
        return [hash0, stretch2, salts[1]]

    @classmethod
    def _get_authenticated_scraper(cls, username: str, password: str):
        """Return a cloudscraper session logged into Rumble.

        Uses module-level cache to avoid re-login on every call.
        Re-authenticates every SESSION_TTL_SECONDS.
        """
        global _session_cache

        now = time.time()
        if (
            _session_cache["logged_in"]
            and _session_cache["scraper"] is not None
            and (now - _session_cache["login_time"]) < SESSION_TTL_SECONDS
        ):
            return _session_cache["scraper"]

        scraper = cls._get_scraper()
        if not scraper:
            return None

        try:
            # Step 1: Get salts
            resp = scraper.post(
                f"{RUMBLE_API_URL}?name=user.get_salts&api=2",
                data={"username": username},
                timeout=15,
            )
            resp.raise_for_status()
            salts_data = resp.json().get("data", {})
            salts = salts_data.get("salts", [])
            if len(salts) < 3:
                logger.error("Rumble login: get_salts returned %d salts (need 3). "
                             "Is the username '%s' correct?", len(salts), username)
                return None

            # Step 2: Compute password hashes
            pw_hashes = cls._compute_password_hashes(password, salts)

            # Step 3: Login
            resp = scraper.post(
                f"{RUMBLE_API_URL}?name=user.login&api=2",
                data={
                    "username": username,
                    "password_hashes[0]": pw_hashes[0],
                    "password_hashes[1]": pw_hashes[1],
                    "password_hashes[2]": pw_hashes[2],
                },
                timeout=15,
            )
            resp.raise_for_status()
            login_resp = resp.json()
            login_data = login_resp.get("data", {})

            # Check login success
            session_ok = login_data.get("session", False)
            user_logged_in = login_resp.get("user", {}).get("logged_in", False)

            if session_ok or user_logged_in:
                logger.info("Rumble: login successful (user=%s)", username)
                _session_cache["scraper"] = scraper
                _session_cache["logged_in"] = True
                _session_cache["login_time"] = now
                return scraper
            else:
                reason = login_data.get("reason", "unknown")
                if "JAJSJODIH589SAD" in reason:
                    logger.error(
                        "Rumble: login blocked for '%s' (error JAJSJODIH589SAD). "
                        "This usually means Rumble is rejecting logins from "
                        "datacenter/server IPs. Try from a residential IP or VPN.",
                        username,
                    )
                else:
                    logger.error("Rumble: login failed for '%s': %s", username, reason)
                return None

        except Exception as e:
            logger.error("Rumble: login error: %s", e)
            return None

    @staticmethod
    def _extract_video_id(post: NormalizedPost) -> Optional[int]:
        """Extract Rumble numeric video ID from post URL or stored metadata.

        Rumble URLs look like: https://rumble.com/v77vwmi-some-slug.html
        The video ID is stored in the NormalizedPost from the media.search result.
        We try: 1) post metadata, 2) URL-based lookup via media.search.
        """
        # If the post has source_id stored (from fetch), use it directly
        if hasattr(post, "source_id") and post.source_id:
            try:
                return int(post.source_id)
            except (ValueError, TypeError):
                pass

        # Fallback: search for the video by its URL slug to get the numeric ID
        # Extract the slug part from URL: v77vwmi
        match = re.search(r"rumble\.com/(v[a-z0-9]+)-", post.url)
        if not match:
            return None

        fid = match.group(1)
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            resp = scraper.get(
                RUMBLE_API_URL,
                params={"api": "2", "name": "media.search", "query": fid},
                timeout=15,
            )
            resp.raise_for_status()
            items = resp.json().get("data", {}).get("items", [])
            for item in items:
                item_url = item.get("url", "")
                if fid in item_url:
                    return int(item.get("id", 0))
        except Exception as e:
            logger.debug("Rumble: video ID lookup failed for %s: %s", fid, e)

        return None

    @staticmethod
    def _fetch_comment_list(
        scraper, video_id: int, limit: int = 3
    ) -> list[NormalizedComment]:
        """Call comment.list with an authenticated scraper session.

        Args:
            scraper: authenticated cloudscraper session (with login cookies)
            video_id: numeric Rumble video ID
            limit: max comments to return

        Returns:
            List of NormalizedComment, sorted by score descending.
        """
        try:
            resp = scraper.post(
                f"{RUMBLE_API_URL}?name=comment.list&api=2",
                data={"video": video_id},
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()

            errors = result.get("errors", [])
            if errors:
                msg = errors[0].get("message", "unknown")
                logger.debug("Rumble comment.list error for video %d: %s", video_id, msg)
                return []

            data = result.get("data", {})
            # comment.list may return items as list or nested structure
            raw_comments = []
            if isinstance(data, dict):
                raw_comments = data.get("comments", data.get("items", []))
            elif isinstance(data, list):
                raw_comments = data

            if not raw_comments:
                logger.debug("Rumble: no comments returned for video %d", video_id)
                return []

            # Parse and score comments
            parsed = []
            for c in raw_comments:
                try:
                    text = c.get("text", c.get("message", c.get("body", ""))).strip()
                    if not text:
                        continue

                    author = (
                        c.get("username")
                        or c.get("user", {}).get("username", "")
                        or c.get("author", "")
                        or "Anonymous"
                    )

                    likes = int(c.get("likes", c.get("num_likes", c.get("score", 0))) or 0)
                    dislikes = int(c.get("dislikes", c.get("num_dislikes", 0)) or 0)
                    score = likes - dislikes

                    parsed.append(NormalizedComment(
                        author=author,
                        body=text,
                        score=score,
                        source="rumble",
                    ))
                except Exception:
                    continue

            # Sort by score (most liked first) and return top N
            parsed.sort(key=lambda x: x.score, reverse=True)
            return parsed[:limit]

        except Exception as e:
            logger.warning("Rumble: comment.list request failed for video %d: %s", video_id, e)
            return []
