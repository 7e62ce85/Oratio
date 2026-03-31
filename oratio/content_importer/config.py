"""
Configuration for the content-importer service.

All secrets / tunables come from environment variables so they can be set
in docker-compose.yml / .env without touching code.

Architecture: Per-source independent AI selection.
Each source gets its own community and independent AI picks.
"""

import os

# ─── Lemmy API ────────────────────────────────────────────────────────
LEMMY_API_URL = os.getenv("LEMMY_API_URL", "http://lemmy:8536")
LEMMY_BOT_USERNAME = os.getenv("LEMMY_BOT_USERNAME", "OratioRepostBot")
LEMMY_BOT_PASSWORD = os.getenv("LEMMY_BOT_PASSWORD", "")
# Fallback community — each source should define its own
LEMMY_DEFAULT_COMMUNITY = os.getenv("LEMMY_DEFAULT_COMMUNITY", "trending")

# ─── AI / LLM ─────────────────────────────────────────────────────────
AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")  # "openai" | "anthropic" | "gemini"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Legacy global max — now each source has its own "ai_picks"
AI_MAX_PICKS = int(os.getenv("AI_MAX_PICKS", "10"))
# Default per-source picks (fallback if source doesn't specify ai_picks)
AI_PICKS_PER_SOURCE = int(os.getenv("AI_PICKS_PER_SOURCE", "3"))

# ─── Comments ──────────────────────────────────────────────────────────
# How many top comments to import per post (score-based, no AI)
COMMENTS_PER_POST = int(os.getenv("COMMENTS_PER_POST", "3"))
COMMENTS_ENABLED = os.getenv("COMMENTS_ENABLED", "true").lower() == "true"

# ─── YouTube Data API v3 ──────────────────────────────────────────────
# Used for Trending videos + official comment fetching (free, 10k units/day)
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# ─── Scheduler ─────────────────────────────────────────────────────────
IMPORT_INTERVAL_MINUTES = int(os.getenv("IMPORT_INTERVAL_MINUTES", "360"))  # 6 hours
IMPORT_ON_STARTUP = os.getenv("IMPORT_ON_STARTUP", "true").lower() == "true"

# ─── Database (SQLite for dedup state) ─────────────────────────────────
DB_PATH = os.getenv("IMPORTER_DB_PATH", "/data/importer.db")

# ─── Admin API ─────────────────────────────────────────────────────────
ADMIN_API_KEY = os.getenv("LEMMY_API_KEY", "changeme")
ADMIN_API_PORT = int(os.getenv("IMPORTER_API_PORT", "8085"))

# ─── Source definitions ───────────────────────────────────────────────
# Each source has its own community and independent AI picks count.
# "ai_picks" = how many posts AI selects per source per cycle.
import json

_SOURCES_JSON = os.getenv("IMPORTER_SOURCES", "")

DEFAULT_SOURCES = [
    # ── Reddit ─────────────────────────────────────────────────────
    {
        "name": "reddit_technology",
        "type": "reddit",
        "subreddit": "technology",
        "sort": "hot",
        "limit": 25,
        "community": "reddit",
        "ai_picks": 3,
        "enabled": True,
    },
    {
        "name": "reddit_worldnews",
        "type": "reddit",
        "subreddit": "worldnews",
        "sort": "hot",
        "limit": 25,
        "community": "reddit",
        "ai_picks": 3,
        "enabled": True,
    },
    # ── Ars Technica ───────────────────────────────────────────────
    {
        "name": "ars_technica",
        "type": "rss",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "source_label": "arstechnica",
        "community": "arstechnica",
        "ai_picks": 3,
        "limit": 20,
        "enabled": True,
    },
    # ── ScienceDaily ───────────────────────────────────────────────
    {
        "name": "science_daily",
        "type": "rss",
        "url": "https://www.sciencedaily.com/rss/all.xml",
        "source_label": "sciencedaily",
        "community": "sciencedaily",
        "ai_picks": 2,
        "limit": 20,
        "enabled": True,
    },
    # ── Reuters (via Google News RSS) ──────────────────────────────
    {
        "name": "reuters",
        "type": "rss",
        "url": "https://news.google.com/rss/search?q=site:reuters.com&hl=en&gl=US&ceid=US:en",
        "source_label": "reuters",
        "community": "reuters",
        "ai_picks": 3,
        "limit": 25,
        "follow_redirects": True,
        "enabled": True,
    },
    # ── YouTube Trending (Data API v3) ────────────────────────────
    {
        "name": "youtube_trending",
        "type": "youtube",
        "region_code": "US",       # Trending region (US, KR, GB, etc.)
        "category_id": "",         # Empty = all categories. "10"=Music, "20"=Gaming, etc.
        "community": "youtube",
        "ai_picks": 2,
        "limit": 25,
        "enabled": True,
    },
    # ── 4chan /pol/ ─────────────────────────────────────────────────
    {
        "name": "fourchan_pol",
        "type": "fourchan",
        "board": "pol",
        "community": "fourchan",
        "ai_picks": 2,
        "limit": 20,
        "enabled": True,
    },
    # ── MGTOW.tv ───────────────────────────────────────────────────
    {
        "name": "mgtow_tv",
        "type": "mgtow",
        "community": "mgtowtv",
        "ai_picks": 2,
        "limit": 15,
        "enabled": True,
    },
    # ── Bitchute ───────────────────────────────────────────────────
    {
        "name": "bitchute_popular",
        "type": "bitchute",
        "community": "bitchute",
        "ai_picks": 2,
        "limit": 15,
        "enabled": True,
    },
    # ── Disabled sources ───────────────────────────────────────────
    {
        "name": "bbc_world",
        "type": "rss",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "source_label": "bbc",
        "community": "bbc",
        "ai_picks": 3,
        "limit": 25,
        "enabled": False,
    },
    {
        "name": "ilbe_popular",
        "type": "ilbe",
        "board": "ilbe",
        "fetch_thumbnails": True,
        "community": "ilbe",
        "ai_picks": 2,
        "limit": 20,
        "enabled": False,
    },
]


def get_sources() -> list[dict]:
    """Return the active source configs, preferring env override."""
    if _SOURCES_JSON:
        try:
            sources = json.loads(_SOURCES_JSON)
            return [s for s in sources if s.get("enabled", True)]
        except json.JSONDecodeError:
            pass
    return [s for s in DEFAULT_SOURCES if s.get("enabled", True)]
