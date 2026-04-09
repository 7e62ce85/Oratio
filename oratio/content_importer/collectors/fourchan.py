"""
4chan collector — uses the public JSON API.

4chan provides a free, no-auth JSON API:
  - Board list: https://a.4cdn.org/boards.json
  - Thread list: https://a.4cdn.org/{board}/catalog.json
  - Thread detail: https://a.4cdn.org/{board}/thread/{no}.json

Supports two modes:
  - Single board: fetch from one board (e.g. "pol")
  - All boards:   fetch top threads across ALL boards, ranked globally
                   (set board="" or board="all" in config)

Scoring: composite score = unique_ips × log2(replies + 1)
  - Prioritises threads with broad participation over small-group chats.
  - Falls back to replies-only when unique_ips is unavailable.

Filters: sticky, closed, bumplimit, max age, general-thread patterns.
Supports comment fetching via thread JSON endpoint.
Supports pre-post liveness verification (404 check).
"""

from __future__ import annotations

import logging
import math
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from models import NormalizedPost, NormalizedComment
from .base import BaseCollector
from .html_utils import clean_html_to_text

logger = logging.getLogger("content_importer.fourchan")

FOURCHAN_CDN = "https://a.4cdn.org"
FOURCHAN_BOARDS = "https://boards.4chan.org"
USER_AGENT = "OratioContentImporter/1.0"

# Maximum thread age (hours) — threads older than this are likely to 404 soon
MAX_THREAD_AGE_HOURS = 24

# Minimum unique IPs to filter out tiny clique/chat threads
MIN_UNIQUE_IPS = 8

# Regex patterns for "general" / recurring threads that lack standalone context
# These threads repeat endlessly (#1, #2, ...) and are meaningless to outsiders
# Matches: /mlb/, /ptg/, brit/pol/, "edition", "general", "gossip", etc.
_GENERAL_PATTERN = re.compile(
    r"(^/\w{2,12}/\s*$"         # title is ONLY "/xxx/" (e.g. "/deutsch/", "/sauna/")
    r"|/\w{2,6}/\s*[-–—+]"     # "/mlb/ - ...", "/v4/ + ..."
    r"|/\w{1,5}g/"              # "/ptg/", "/cvg/" (abbreviation + g)
    r"|\bgeneral\b"             # "general" standalone word
    r"|\bgossip\b"              # "gossip" standalone word
    r"|\bedition\b"             # "edition" (recurring thread marker)
    r"|\bdrawthread\b"          # recurring draw threads
    r"|\bthread\s*#\s*\d+"     # "thread #123"
    r"|\b\w{2,6}/pol/"          # "brit/pol/", "aus/pol/" country-specific politics general
    r"|\b/\w+/\s+/\w+/)",      # "/v4/ /ori/" multi-slug generals
    re.IGNORECASE,
)

# Known recurring country/language generals on /int/ board
# These are daily chat rooms for specific nationalities — no value to outsiders
_INT_COUNTRY_GENERALS = frozenset({
    "/deutsch/", "/sauna/", "/brit/", "/fr/", "/ita/", "/nederdraad/",
    "/balt/", "/mena/", "/norgetråden/", "/sverigetråden/", "/cum/",
    "/lat/", "/esp/", "/luso/", "/asean/", "/flag/", "/dixie/",
    "/med/", "/ex-ussr/", "/v4/", "/polska/", "/rus/", "/ukr/",
    "/desi/", "/sino/", "/jp/", "/ausnz/", "/bra/", "/chirp/",
})

# Popular boards to scan when collecting from "all" boards
# (avoids scanning 70+ dead/niche boards — focuses on active ones)
# /b/ (Random) and /gif/ (Adult GIF) excluded: NSFW boards with
# frequent porn/gore content unsuitable for a global audience.
# /pol/ kept despite NSFW tag — primarily political discussion, not porn.
POPULAR_BOARDS = [
    "pol", "v", "int", "k", "tv", "g", "fit", "sci",
    "biz", "sp", "out", "news", "his", "wsg",
    "ck", "diy", "lit", "mu", "o", "an", "tg",
]


class FourChanCollector(BaseCollector):
    """Collect top threads from 4chan board(s) via the JSON API."""

    def fetch(self) -> list[NormalizedPost]:
        board = self.config.get("board", "pol")
        limit = self.config.get("limit", 20)

        if board in ("", "all"):
            return self._fetch_all_boards(limit)
        else:
            return self._fetch_single_board(board, limit)

    def _fetch_single_board(self, board: str, limit: int) -> list[NormalizedPost]:
        """Fetch top threads from a single board."""
        threads = self._get_catalog(board)
        if not threads:
            return []

        threads = self._filter_threads(threads, board)
        threads.sort(key=lambda t: self._composite_score(t), reverse=True)
        return self._threads_to_posts(threads[:limit], board)

    def _fetch_all_boards(self, limit: int) -> list[NormalizedPost]:
        """Fetch top threads across all popular boards, ranked by composite score."""
        boards_to_scan = self.config.get("boards", POPULAR_BOARDS)
        per_board_fetch = self.config.get("per_board_fetch", 10)

        all_threads: list[tuple[str, dict]] = []  # (board, thread_dict)

        for board in boards_to_scan:
            threads = self._get_catalog(board)
            if not threads:
                continue

            # Filter out unsuitable threads, then sort by composite score
            threads = self._filter_threads(threads, board)
            threads.sort(key=lambda t: self._composite_score(t), reverse=True)
            for t in threads[:per_board_fetch]:
                all_threads.append((board, t))

            # Rate limit: 4chan asks for 1 req/sec
            time.sleep(1.0)

        if not all_threads:
            logger.warning("4chan all-boards: no threads fetched from any board")
            return []

        # Global sort by composite score across all boards
        all_threads.sort(key=lambda bt: self._composite_score(bt[1]), reverse=True)

        posts: list[NormalizedPost] = []
        for board, thread in all_threads[:limit]:
            p = self._thread_to_post(thread, board)
            if p:
                posts.append(p)

        logger.info(
            "4chan all-boards: scanned %d boards, collected %d top threads",
            len(boards_to_scan), len(posts),
        )
        return posts

    # ── Thread filtering & scoring ────────────────────────────────

    @staticmethod
    def _composite_score(thread: dict) -> float:
        """
        Composite engagement score: unique_ips × log2(replies + 1).

        Prioritises threads with broad participation (many unique posters)
        over small-group chat threads where 2-3 people spam 700+ replies.
        Falls back to replies-only when unique_ips is unavailable.
        """
        replies = thread.get("replies", 0)
        unique_ips = thread.get("unique_ips", 0)

        if unique_ips and unique_ips > 0:
            return unique_ips * math.log2(replies + 1)
        # Fallback: just replies (legacy behaviour)
        return float(replies)

    @staticmethod
    def _filter_threads(threads: list[dict], board: str) -> list[dict]:
        """
        Pre-filter threads before scoring. Removes:
        - sticky/closed threads (admin pins, locked threads)
        - bumplimit-reached threads (about to be archived → 404 risk)
        - threads older than MAX_THREAD_AGE_HOURS
        - threads with fewer than MIN_UNIQUE_IPS participants
        - "general" / recurring pattern threads (niche gossip, no standalone value)
        """
        now_ts = time.time()
        filtered: list[dict] = []

        for t in threads:
            # Skip stickies and closed threads
            if t.get("sticky") or t.get("closed"):
                continue

            # Skip threads that hit bump limit (archive imminent → 404 risk)
            if t.get("bumplimit"):
                continue

            # Skip threads older than threshold
            thread_time = t.get("time", 0)
            if thread_time and (now_ts - thread_time) > MAX_THREAD_AGE_HOURS * 3600:
                continue

            # Skip threads with too few unique participants (small clique chats)
            unique_ips = t.get("unique_ips", 0)
            if unique_ips and unique_ips < MIN_UNIQUE_IPS:
                continue

            # Skip "general" / recurring threads (meaningless to outsiders)
            title_text = t.get("sub", "") or ""
            comment_text = t.get("com", "") or ""
            combined = f"{title_text} {comment_text[:200]}"
            if _GENERAL_PATTERN.search(combined):
                continue

            # Skip known /int/ country generals by exact title match
            title_stripped = title_text.strip().lower()
            if title_stripped and any(
                title_stripped == g.lower() or title_stripped.startswith(g.lower())
                for g in _INT_COUNTRY_GENERALS
            ):
                continue

            filtered.append(t)

        removed = len(threads) - len(filtered)
        if removed:
            logger.debug(
                "4chan /%s/: filtered %d → %d threads (%d removed)",
                board, len(threads), len(filtered), removed,
            )
        return filtered

    def _get_catalog(self, board: str) -> list[dict]:
        """Fetch catalog.json for a board and return flat thread list."""
        catalog_url = f"{FOURCHAN_CDN}/{board}/catalog.json"
        headers = {"User-Agent": USER_AGENT}

        try:
            resp = requests.get(catalog_url, headers=headers, timeout=15)
            resp.raise_for_status()
            pages = resp.json()
        except Exception as e:
            logger.warning("4chan catalog fetch failed for /%s/: %s", board, e)
            return []

        threads = []
        for page in pages:
            for thread in page.get("threads", []):
                threads.append(thread)
        return threads

    def _thread_to_post(self, thread: dict, board: str) -> NormalizedPost | None:
        """Convert a single 4chan thread dict to NormalizedPost."""
        no = thread.get("no")
        if not no:
            return None

        subject = thread.get("sub", "")
        comment = thread.get("com", "")
        comment = clean_html_to_text(self._strip_quotelinks(comment))
        subject = clean_html_to_text(subject, preserve_newlines=False)

        if subject:
            title = subject
        elif comment:
            title = comment[:150] + ("…" if len(comment) > 150 else "")
        else:
            title = f"/{board}/ thread #{no}"

        url = f"{FOURCHAN_BOARDS}/{board}/thread/{no}"
        body = comment[:2000] if comment else ""

        thumbnail = None
        if thread.get("tim") and thread.get("ext"):
            thumbnail = f"https://i.4cdn.org/{board}/{thread['tim']}s.jpg"

        try:
            published = datetime.fromtimestamp(thread.get("time", 0), tz=timezone.utc)
        except Exception:
            published = datetime.now(timezone.utc)

        replies = thread.get("replies", 0)

        return NormalizedPost(
            title=title,
            url=url,
            body=body,
            source="4chan",
            source_community=f"/{board}/",
            score=int(self._composite_score(thread)),
            published_at=published,
            thumbnail_url=thumbnail,
            author="Anonymous",
            comment_count=replies,
            tags=[],
        )

    def _threads_to_posts(self, threads: list[dict], board: str) -> list[NormalizedPost]:
        """Convert a list of thread dicts to NormalizedPost list."""
        posts = []
        for thread in threads:
            p = self._thread_to_post(thread, board)
            if p:
                posts.append(p)
        logger.info("4chan /%s/: fetched %d threads", board, len(posts))
        return posts

    # ── Comment fetching ──────────────────────────────────────────

    def fetch_comments(self, post: NormalizedPost, limit: int = 3) -> list[NormalizedComment]:
        """
        Fetch top layer-1 replies from a 4chan thread, ranked by quote count.

        Only selects "layer-1" replies — posts that directly quote the OP
        (>>op_no). This ensures the imported comments are contextually
        understandable to Oratio users who can only see the OP body,
        without needing to see intermediate reply chains.

        Among layer-1 replies, ranks by how many times OTHER posts in the
        thread quoted them (quote-count), as a proxy for engagement.

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

        # OP post number — used to identify layer-1 replies (direct replies to OP)
        op_no = replies[0].get("no", 0)

        # Skip the OP (first post), only look at replies
        reply_posts = replies[1:]

        # Identify layer-1 posts: those that directly quote the OP (>>op_no)
        # This ensures imported comments are contextually understandable
        # without needing to see intermediate replies.
        layer1_nos: set[int] = set()
        for r in reply_posts:
            com = r.get("com", "")
            quoted = _re.findall(r"&gt;&gt;(\d+)", com)
            if str(op_no) in quoted:
                layer1_nos.add(r.get("no", 0))

        # Count how often each layer-1 post is quoted by others (engagement proxy)
        quote_counts: dict[int, int] = {}
        for r in reply_posts:
            com = r.get("com", "")
            quoted = _re.findall(r"&gt;&gt;(\d+)", com)
            for q in quoted:
                q_int = int(q)
                if q_int in layer1_nos:
                    quote_counts[q_int] = quote_counts.get(q_int, 0) + 1

        # Build comments ONLY from layer-1 replies (direct responses to OP)
        raw_comments: list[NormalizedComment] = []
        for r in reply_posts:
            no = r.get("no", 0)
            if no not in layer1_nos:
                continue

            com = r.get("com", "")
            if not com:
                continue

            body = clean_html_to_text(self._strip_quotelinks(com))
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
                "4chan comments for thread %s: %d layer-1 (of %d total), selected top %d (ranks: %s)",
                thread_no, len(layer1_nos), len(reply_posts), len(selected),
                [c.rank for c in selected],
            )
        return selected

    @staticmethod
    def _strip_quotelinks(text: str) -> str:
        """Remove 4chan quotelink anchors (>>12345) before general HTML cleaning."""
        if not text:
            return ""
        return re.sub(r'<a[^>]*class="quotelink"[^>]*>[^<]*</a>', "", text)

    # ── Pre-post liveness check ───────────────────────────────────

    @staticmethod
    def verify_alive(post: NormalizedPost) -> bool:
        """
        Check if a 4chan thread still exists before posting to Lemmy.

        4chan threads (especially on fast boards like /b/) can 404 between
        collection and posting. This HEAD check catches dead threads.

        Returns True if alive or on error (fail-open), False if 404.
        """
        match = re.search(r"/([a-z]+)/thread/(\d+)", post.url)
        if not match:
            return True  # not a 4chan URL, skip check

        board, thread_no = match.group(1), match.group(2)
        check_url = f"{FOURCHAN_CDN}/{board}/thread/{thread_no}.json"

        try:
            resp = requests.head(
                check_url,
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            if resp.status_code == 404:
                logger.info(
                    "4chan thread /%s/%s is 404 — skipping post to Lemmy",
                    board, thread_no,
                )
                return False
            return True
        except Exception as e:
            logger.debug("4chan liveness check failed for /%s/%s: %s (assuming alive)", board, thread_no, e)
            return True  # fail-open: network error → assume alive
