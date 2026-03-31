"""
Main scheduler / pipeline orchestrator.

Runs the full import pipeline on a configurable interval.

Architecture (v3 — single AI call for all sources):
  1. Fetch from all enabled sources (collectors)
  2. Deduplicate against history
  3. ONE AI call to select posts across all sources
     (AI is told per-source quotas so each source gets fair picks)
  4. Post selected items to each source's dedicated Lemmy community
  5. Fetch top comments (score-based, no AI) for sources that support it
  6. Post comments on each Lemmy post
  7. Record results

This minimises API calls to 1 per cycle (vs N per source),
cutting token usage by ~90%.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timezone

import config
from ai_selector import select_posts_batch
from collectors import (
    RedditCollector,
    RSSCollector,
    IlbeCollector,
    YouTubeCollector,
    FourChanCollector,
    MGTOWCollector,
    BitchuteCollector,
)
from collectors.base import BaseCollector
from dedup import DedupStore
from lemmy_client import LemmyClient
from models import NormalizedPost

logger = logging.getLogger("content_importer.scheduler")

# Collector registry — maps source type → collector class
COLLECTOR_REGISTRY: dict[str, type] = {
    "reddit": RedditCollector,
    "rss": RSSCollector,
    "ilbe": IlbeCollector,
    "youtube": YouTubeCollector,
    "fourchan": FourChanCollector,
    "mgtow": MGTOWCollector,
    "bitchute": BitchuteCollector,
}

# Korean language community routing
KOREAN_COMMUNITY = "banmal"
_HANGUL_RE = re.compile(r"[\uAC00-\uD7A3\u3131-\u314E\u314F-\u3163]")


def _is_korean(post: NormalizedPost) -> bool:
    hangul_chars = _HANGUL_RE.findall(post.title)
    non_space = len(post.title.replace(" ", ""))
    if non_space == 0:
        return False
    return len(hangul_chars) / non_space >= 0.3


def run_import_cycle(
    dedup: DedupStore, lemmy: LemmyClient
) -> dict:
    """Execute one full import cycle. Returns a summary dict."""
    sources = config.get_sources()
    source_names = ", ".join(s["name"] for s in sources)
    run_id = dedup.start_run(source_names)

    logger.info("═══ Import cycle started (%d sources) ═══", len(sources))

    total_fetched = 0
    total_new = 0
    total_posted = 0
    source_results = {}

    # ── Phase 1: Fetch + dedup from all sources ───────────────────
    # Collect new posts per source: { source_name: (source_cfg, [posts], collector) }
    source_pools: dict[str, tuple[dict, list[NormalizedPost], BaseCollector]] = {}

    for src in sources:
        src_name = src["name"]
        collector_cls = COLLECTOR_REGISTRY.get(src["type"])
        if not collector_cls:
            logger.warning("Unknown type '%s' for '%s'", src["type"], src_name)
            source_results[src_name] = {"status": "unknown_type"}
            continue

        collector = collector_cls(src)
        try:
            posts = collector.fetch()
        except Exception as e:
            logger.error("Collector '%s' failed: %s", src_name, e)
            source_results[src_name] = {"status": "fetch_error", "error": str(e)}
            continue

        fetched = len(posts)
        total_fetched += fetched

        if not posts:
            logger.info("[%s] No posts fetched", src_name)
            source_results[src_name] = {"fetched": 0, "posted": 0, "status": "no_posts"}
            continue

        new_posts = dedup.filter_new(posts)
        total_new += len(new_posts)

        if not new_posts:
            logger.info("[%s] All %d duplicates", src_name, fetched)
            source_results[src_name] = {"fetched": fetched, "posted": 0, "status": "all_duplicates"}
            continue

        source_pools[src_name] = (src, new_posts, collector)
        logger.info("[%s] fetched=%d, new=%d", src_name, fetched, len(new_posts))

    if not source_pools:
        dedup.finish_run(run_id, total_fetched, 0, "no_new_posts")
        return {"fetched": total_fetched, "posted": 0, "status": "no_new_posts"}

    # ── Phase 2: Single AI call for all sources ───────────────────
    # Build per-source quota: { source_name: ai_picks }
    quotas = {
        name: cfg.get("ai_picks", config.AI_PICKS_PER_SOURCE)
        for name, (cfg, _, _collector) in source_pools.items()
    }
    # Flatten all new posts with source tag
    all_new: list[tuple[str, NormalizedPost]] = []
    for name, (cfg, posts, _collector) in source_pools.items():
        for p in posts:
            all_new.append((name, p))

    # Single AI/score selection — returns { source_name: [selected posts] }
    selected_by_source = select_posts_batch(all_new, quotas)

    # ── Phase 3: Post to Lemmy + fetch & post comments ──────────
    total_comments = 0
    comments_per_post = config.COMMENTS_PER_POST
    comments_enabled = config.COMMENTS_ENABLED

    for src_name, (src_cfg, _, collector) in source_pools.items():
        selected = selected_by_source.get(src_name, [])
        community = src_cfg.get("community", config.LEMMY_DEFAULT_COMMUNITY)
        posted = 0
        src_comments = 0

        for post in selected:
            target = KOREAN_COMMUNITY if _is_korean(post) else community
            post_id = lemmy.create_post(post, target)
            if post_id:
                dedup.mark_imported(post, post_id)
                posted += 1

                # ── Phase 4: Fetch & post top comments (score-based) ──
                if comments_enabled and collector.supports_comments:
                    try:
                        comments = collector.fetch_comments(post, limit=comments_per_post)
                        for comment in comments:
                            cid = lemmy.create_comment(post_id, comment)
                            if cid:
                                src_comments += 1
                            time.sleep(0.5)  # rate limit between comments
                    except Exception as e:
                        logger.warning(
                            "[%s] Comment fetch failed for '%s': %s",
                            src_name, post.title[:40], e,
                        )

                time.sleep(1.0)

        total_posted += posted
        total_comments += src_comments
        source_results[src_name] = {
            "fetched": len(source_pools[src_name][1]),
            "new": len(source_pools[src_name][1]),
            "selected": len(selected),
            "posted": posted,
            "comments": src_comments,
            "community": community,
            "status": "ok",
        }
        logger.info(
            "[%s] selected=%d, posted=%d, comments=%d → %s",
            src_name, len(selected), posted, src_comments, community,
        )

    dedup.finish_run(run_id, total_fetched, total_posted, "ok")
    logger.info(
        "═══ Import cycle done: fetched=%d, new=%d, posted=%d, comments=%d ═══",
        total_fetched, total_new, total_posted, total_comments,
    )

    return {
        "fetched": total_fetched,
        "new": total_new,
        "posted": total_posted,
        "comments": total_comments,
        "sources": source_results,
        "status": "ok",
    }


class ImportScheduler:
    """Background thread that runs import cycles on a schedule."""

    def __init__(self, dedup: DedupStore, lemmy: LemmyClient):
        self.dedup = dedup
        self.lemmy = lemmy
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.last_result: dict | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(
            "Scheduler started — interval=%d min, on_startup=%s",
            config.IMPORT_INTERVAL_MINUTES,
            config.IMPORT_ON_STARTUP,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler stopped")

    def _loop(self) -> None:
        if config.IMPORT_ON_STARTUP:
            self._run_safe()

        interval_sec = config.IMPORT_INTERVAL_MINUTES * 60
        while not self._stop.wait(timeout=interval_sec):
            self._run_safe()

    def _run_safe(self) -> None:
        try:
            self.last_result = run_import_cycle(self.dedup, self.lemmy)
        except Exception as e:
            logger.exception("Import cycle crashed: %s", e)
            self.last_result = {"status": "error", "error": str(e)}

    def trigger_now(self) -> dict:
        """Manually trigger an import cycle (from API)."""
        return run_import_cycle(self.dedup, self.lemmy)
