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

# ─── Rumble Login (댓글 수집용) ────────────────────────────────────────
# rumble.com 계정 — 있으면 인증된 세션으로 댓글 가져옴, 없으면 댓글 스킵
RUMBLE_USERNAME = os.getenv("RUMBLE_USERNAME", "")
RUMBLE_PASSWORD = os.getenv("RUMBLE_PASSWORD", "")

# ─── Imgur API ─────────────────────────────────────────────────────────
# Register free at https://api.imgur.com/oauth2/addclient (anonymous)
# If empty, falls back to HTML scraping (less reliable)
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID", "")

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
        "ai_picks": 5,
        "fallback_thumbnail": "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png",
        "enabled": True,
    },
    {
        "name": "reddit_worldnews",
        "type": "reddit",
        "subreddit": "worldnews",
        "sort": "hot",
        "limit": 25,
        "community": "reddit",
        "ai_picks": 5,
        "fallback_thumbnail": "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png",
        "enabled": True,
    },
    # ── Ars Technica ───────────────────────────────────────────────
    {
        "name": "ars_technica",
        "type": "arstechnica",
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
        "ai_picks": 3,
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
        "ai_picks": 10,
        "limit": 25,
        "follow_redirects": True,
        "fallback_thumbnail": "https://cdn.brandfetch.io/id81tTzGrw/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1758338730664",
        "enabled": True,
    },
    # ── YouTube Trending (Data API v3) ────────────────────────────
    {
        "name": "youtube_trending",
        "type": "youtube",
        "region_code": "US",       # Trending region (US, KR, GB, etc.)
        "category_id": "",         # Empty = all categories. "10"=Music, "20"=Gaming, etc.
        "community": "youtube",
        "ai_picks": 10,
        "limit": 25,
        "enabled": True,
    },
    # ── 4chan (전체 인기 보드) ──────────────────────────────────────────
    {
        "name": "fourchan_all",
        "type": "fourchan",
        "board": "all",             # "all" = scan popular boards globally
        "per_board_fetch": 10,      # Top N threads per board before global sort
        "community": "fourchan",
        "ai_picks": 10,
        "limit": 20,
        "enabled": True,
    },
    # ── MGTOW.tv ───────────────────────────────────────────────────
    {
        "name": "mgtow_tv",
        "type": "mgtow",
        "community": "mgtowtv",
        "ai_picks": 3,
        "limit": 15,
        "enabled": True,
    },
    # ── Bitchute (old.bitchute.com SSR trending) ─────────────────
    {
        "name": "bitchute_trending",
        "type": "bitchute",
        "trending_period": "day",  # "day", "week", or "month"
        "community": "bitchute",
        "ai_picks": 3,
        "limit": 15,
        "enabled": True,
    },
    # ── Rumble (service.php JSON API + cloudscraper) ────────────────
    {
        "name": "rumble_trending",
        "type": "rumble",
        # search_queries: broad terms to simulate trending (multiple = more variety)
        "search_queries": ["news", "politics", "live", "trending", "breaking", "world", "viral"],
        "sort": "views",   # "views" or "date"
        "date": "today",   # "today" | "this-week" | "this-month" | "" (all-time)
        "community": "rumble",
        "ai_picks": 10,
        "limit": 20,
        "enabled": True,
    },
    # ── Upgoat (AI 선별, 사이클당 10개) ──────────────────────────────────
    {
        "name": "upgoat",
        "type": "upgoat",
        "community": "upgoat",
        "import_all": False,
        "min_age_hours": 13,        # Only import posts older than 13 hours
        "max_age_hours": 72,        # Never import posts older than 72 hours
        "ai_picks": 10,
        "limit": 25,                # Fetch top 25, AI picks 10
        "fallback_thumbnail": "https://oratio.space/files/logos/upgoat.png",
        "enabled": True,
    },
    # ── XCancel (Twitter/X search via xcancel.com) ─────────────────────
    {
        "name": "xcancel_liberty",
        "type": "xcancel",
        "search_url": "https://xcancel.com/search?f=tweets&q=Liberty",
        "community": "xcancel",
        "ai_picks": 5,
        "limit": 25,
        "enabled": True,
    },
    # ── Imgur (Gallery / Memes) ────────────────────────────────────────
    {
        "name": "imgur_hot",
        "type": "imgur",
        "section": "hot",
        "sort": "viral",
        "window": "day",
        "tag": "",           # Empty = all. Set to "memes", "funny", etc.
        "community": "imgur",
        "ai_picks": 3,
        "limit": 20,
        "enabled": True,
    },
    # ── Instagram (public hashtags) ────────────────────────────────────
    {
        "name": "instagram_memes",
        "type": "instagram",
        "hashtags": ["memes", "funny", "viral"],
        "profiles": [],
        "community": "instagram",
        "ai_picks": 3,
        "limit": 20,
        "enabled": True,
    },
    # ── 9gag (Popular / Hot) ──────────────────────────────────────────
    {
        "name": "ninegag_hot",
        "type": "ninegag",
        "section": "hot",
        "tag": "",           # Empty = all. Set to "funny", "animals", etc.
        "community": "ninegag",
        "ai_picks": 3,
        "limit": 20,
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
