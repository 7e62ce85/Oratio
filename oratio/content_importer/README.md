# Content Importer — Oratio Bootstrapping System

Automatically imports trending posts from popular websites into Oratio, combating the "empty forum" problem for new deployments.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                  Content Importer Pipeline                  │
│                                                            │
│  ┌──────────┐   ┌────────────┐   ┌──────────────┐         │
│  │Collectors│──▶│ Normalizer │──▶│ Deduplicator │         │
│  │(per-site)│   │ (unified   │   │ (SQLite)     │         │
│  └──────────┘   │  format)   │   └──────┬───────┘         │
│       │         └────────────┘          │                  │
│  ┌────┴─────┐                    ┌──────▼───────┐         │
│  │ Reddit   │                    │ AI Selector  │         │
│  │ RSS/News │                    │ (or score    │         │
│  │ YouTube* │                    │  fallback)   │         │
│  │ 4chan*    │                    └──────┬───────┘         │
│  │ ...      │                           │                  │
│  └──────────┘                    ┌──────▼───────┐         │
│                                  │ LemmyPoster  │         │
│                                  │ (Lemmy API)  │         │
│                                  └──────────────┘         │
└────────────────────────────────────────────────────────────┘
           * = not yet implemented, add collector class
```

**Key design**: The pipeline is source-agnostic. Adding a new source = writing one Collector class (~50 lines). Everything else (AI selection, dedup, posting) works automatically.

## Quick Start

### 1. Set up bot account

```bash
cd oratio

# Add to .env:
LEMMY_BOT_USERNAME=OratioRepostBot
LEMMY_BOT_PASSWORD=<strong-password>

# Create bot account & default communities
chmod +x setup_content_importer.sh
./setup_content_importer.sh
```

### 2. Build & run

```bash
# Build only the importer
docker compose build content-importer

# Start
docker compose up -d content-importer

# Watch logs
docker compose logs -f content-importer
```

### 3. Verify

```bash
# Health check
curl http://localhost:8085/health

# Check stats (requires API key)
curl -H "X-API-Key: YOUR_LEMMY_API_KEY" http://localhost:8085/api/importer/stats

# Manually trigger an import
curl -X POST -H "X-API-Key: YOUR_LEMMY_API_KEY" http://localhost:8085/api/importer/trigger
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LEMMY_BOT_USERNAME` | `OratioRepostBot` | Bot account username |
| `LEMMY_BOT_PASSWORD` | — | **Required**. Bot account password |
| `LEMMY_DEFAULT_COMMUNITY` | `trending` | Default community to post into |
| `IMPORT_INTERVAL_MINUTES` | `360` | Minutes between import cycles (6h) |
| `IMPORT_ON_STARTUP` | `true` | Run import immediately on start |
| `AI_ENABLED` | `false` | Use AI to select most interesting posts |
| `AI_PROVIDER` | `openai` | `openai` or `anthropic` |
| `OPENAI_API_KEY` | — | Required if AI enabled + openai |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model for selection |

### Default Sources

| Source | Type | Community | Posts |
|--------|------|-----------|-------|
| Reddit r/technology | reddit | trending | 20 |
| Reddit r/worldnews | reddit | trending | 20 |
| Reuters Top News | rss | news | 20 |
| Ars Technica | rss | technology | 15 |
| ScienceDaily | rss | science | 15 (disabled) |

Override with `IMPORTER_SOURCES` env var (JSON array).

## Adding a New Source

Create a file in `collectors/`, e.g. `collectors/youtube.py`:

```python
from models import NormalizedPost
from collectors.base import BaseCollector

class YouTubeCollector(BaseCollector):
    def fetch(self) -> list[NormalizedPost]:
        # Your scraping/API logic here
        # Return list of NormalizedPost objects
        ...
```

Then register it in `scheduler.py`:

```python
from collectors.youtube import YouTubeCollector

COLLECTOR_REGISTRY["youtube"] = YouTubeCollector
```

And add a source config (in env or DEFAULT_SOURCES):

```python
{
    "name": "youtube_trending",
    "type": "youtube",
    "community": "videos",
    "limit": 10,
    "enabled": True
}
```

That's it — the AI selector, dedup, and poster work automatically.

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | — | Health check |
| POST | `/api/importer/trigger` | API key | Manually trigger import |
| GET | `/api/importer/stats` | API key | Import statistics |
| GET | `/api/importer/history` | API key | Recent imports & runs |
| GET | `/api/importer/last-run` | API key | Last run result |
| GET | `/api/importer/sources` | API key | List active sources |

## AI Selection

When `AI_ENABLED=true`, all fetched posts are sent to the LLM with this prompt:

> "Pick the N most novel, interesting, and discussion-worthy posts.
> Prefer diversity of sources and topics. Avoid clickbait."

When AI is disabled, posts are ranked by their source score (upvotes, views) — still effective, just less curated.

### Cost Estimate (AI mode)

With default settings (4 sources × ~20 posts, 4 cycles/day):

| Model | Cost/month |
|-------|-----------|
| gpt-4o-mini | ~$2–5 |
| gpt-4o | ~$20–50 |
| Claude Haiku | ~$1–3 |

Very affordable for this use case since we're only sending titles + short previews.

## Phase 2 (Future)

- Auto-import top comments alongside posts
- More collectors: YouTube, 4chan, TikTok, Bitchute, Rumble, X/Twitter
- Manual approval queue UI
- Per-community source mapping
- Comment summarization via AI
