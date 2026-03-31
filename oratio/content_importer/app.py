"""
Content Importer — Main application entry point.

Starts:
  1. Background import scheduler
  2. FastAPI admin/monitoring API (optional)
"""

from __future__ import annotations

import logging
import os
import sys
import time

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("content_importer")

import config
from dedup import DedupStore
from lemmy_client import LemmyClient
from scheduler import ImportScheduler, run_import_cycle

# ── FastAPI admin API ─────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="Oratio Content Importer", version="1.0.0")

# Global singletons — initialized in lifespan
dedup_store: DedupStore | None = None
lemmy_client: LemmyClient | None = None
import_scheduler: ImportScheduler | None = None


def _check_api_key(x_api_key: str = Header(default="")) -> None:
    if x_api_key != config.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.on_event("startup")
def on_startup() -> None:
    global dedup_store, lemmy_client, import_scheduler

    logger.info("═══════════════════════════════════════════════")
    logger.info("  Oratio Content Importer starting up…")
    logger.info("═══════════════════════════════════════════════")

    # Initialize components
    dedup_store = DedupStore()
    lemmy_client = LemmyClient()

    # Wait for Lemmy to be ready
    _wait_for_lemmy(lemmy_client)

    # Start scheduler
    import_scheduler = ImportScheduler(dedup_store, lemmy_client)
    import_scheduler.start()


def _wait_for_lemmy(client: LemmyClient, max_wait: int = 120) -> None:
    """Block until we can login to Lemmy."""
    start = time.time()
    while time.time() - start < max_wait:
        if client.login():
            return
        logger.warning("Waiting for Lemmy to become available…")
        time.sleep(5)
    logger.error("Could not connect to Lemmy after %ds — continuing anyway", max_wait)


# ── Health ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "ai_enabled": config.AI_ENABLED,
        "sources": [s["name"] for s in config.get_sources()],
        "interval_minutes": config.IMPORT_INTERVAL_MINUTES,
    }


# ── Manual trigger ────────────────────────────────────────────────────

@app.post("/api/importer/trigger")
def trigger_import(x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
    if not import_scheduler:
        raise HTTPException(500, "Scheduler not initialized")
    result = import_scheduler.trigger_now()
    return result


# ── Stats & history ───────────────────────────────────────────────────

@app.get("/api/importer/stats")
def get_stats(x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
    if not dedup_store:
        raise HTTPException(500, "Not initialized")
    return dedup_store.stats()


@app.get("/api/importer/history")
def get_history(
    x_api_key: str = Header(default=""),
    limit: int = Query(default=50, le=200),
):
    _check_api_key(x_api_key)
    if not dedup_store:
        raise HTTPException(500, "Not initialized")
    return {
        "posts": dedup_store.recent_imports(limit),
        "runs": dedup_store.recent_runs(20),
    }


@app.get("/api/importer/last-run")
def last_run(x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
    if import_scheduler:
        return import_scheduler.last_result or {"status": "not_run_yet"}
    return {"status": "scheduler_not_started"}


# ── Source management ─────────────────────────────────────────────────

@app.get("/api/importer/sources")
def list_sources(x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
    return {"sources": config.get_sources()}


# ── Run with uvicorn ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=config.ADMIN_API_PORT,
        log_level="info",
    )
