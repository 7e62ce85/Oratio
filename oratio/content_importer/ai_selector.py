"""
AI-based post selector.

v3 architecture — single AI call per cycle:
  select_posts_batch() receives ALL posts from ALL sources in one call,
  with per-source quotas. This cuts API calls from N to 1.

Token optimisation:
  - Send title + score per post (no body — saves ~60% tokens)
  - Compact JSON format (short keys)
  - No "reason" field requested — saves output tokens
  - Gemini 2.5-flash with dynamic thinking (default)

When AI is disabled or fails, falls back to score-based ranking.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Optional

from models import NormalizedPost

import config

logger = logging.getLogger("content_importer.ai_selector")


def select_posts_batch(
    tagged_posts: list[tuple[str, NormalizedPost]],
    quotas: dict[str, int],
) -> dict[str, list[NormalizedPost]]:
    """
    Single-call batch selection across all sources (v3).

    Args:
        tagged_posts: list of (source_name, post) tuples
        quotas: { source_name: num_picks }

    Returns:
        { source_name: [selected posts] }
    """
    if not tagged_posts:
        return {}

    # Group by source
    by_source: dict[str, list[NormalizedPost]] = defaultdict(list)
    for src_name, post in tagged_posts:
        by_source[src_name].append(post)

    # If AI enabled, try single batch call
    if config.AI_ENABLED and (config.OPENAI_API_KEY or config.ANTHROPIC_API_KEY or config.GEMINI_API_KEY):
        try:
            return _ai_batch_select(tagged_posts, by_source, quotas)
        except Exception as e:
            logger.warning("AI batch selection failed, falling back to score: %s", e)

    # Fallback: score-based per source
    result: dict[str, list[NormalizedPost]] = {}
    for src_name, posts in by_source.items():
        n = quotas.get(src_name, config.AI_PICKS_PER_SOURCE)
        result[src_name] = _score_select(posts, n)
    return result


def select_posts_for_source(
    posts: list[NormalizedPost],
    source_name: str,
    max_picks: int | None = None,
) -> list[NormalizedPost]:
    """Legacy per-source selection (used for manual single-source tests)."""
    if not posts:
        return []
    max_picks = max_picks or config.AI_PICKS_PER_SOURCE
    if len(posts) <= max_picks:
        for i, p in enumerate(posts):
            p.ai_rank = i + 1
            p.ai_reason = "auto-selected (small pool)"
        return posts
    return _score_select(posts, max_picks)


def select_posts(
    posts: list[NormalizedPost],
    max_picks: int | None = None,
) -> list[NormalizedPost]:
    """Legacy global selection."""
    if not posts:
        return []
    max_picks = max_picks or config.AI_MAX_PICKS
    return _score_select(posts, max_picks)


# ── Score-based fallback ──────────────────────────────────────────────


def _score_select(posts: list[NormalizedPost], n: int) -> list[NormalizedPost]:
    """Simple score-based ranking."""
    sorted_posts = sorted(posts, key=lambda p: p.score, reverse=True)
    selected = sorted_posts[:n]
    for i, p in enumerate(selected):
        p.ai_rank = i + 1
        p.ai_reason = f"score={p.score}"
    return selected


# ── AI batch selection (single call) ──────────────────────────────────

# Ultra-compact prompt to minimise tokens
_BATCH_SYSTEM_PROMPT = """You are a content curator for a community forum. Pick the most interesting, \
diverse, and discussion-worthy posts from each source according to quotas.
Respond ONLY with JSON: {{"picks":[{{"i":0}},{{"i":5}},...]}}.
"i" = 0-based index from the input array. No extra fields needed."""


def _ai_batch_select(
    tagged_posts: list[tuple[str, NormalizedPost]],
    by_source: dict[str, list[NormalizedPost]],
    quotas: dict[str, int],
) -> dict[str, list[NormalizedPost]]:
    """Single AI call selecting from all sources at once."""

    # Build payload — title + score only (no body, saves tokens)
    items = []
    post_index: list[tuple[str, NormalizedPost]] = []  # parallel index
    for src_name, post in tagged_posts:
        item = {
            "i": len(items),
            "s": src_name,
            "t": post.title[:120],
        }
        if post.score:
            item["sc"] = post.score
        items.append(item)
        post_index.append((src_name, post))

    quota_str = ", ".join(f"{s}={n}" for s, n in quotas.items())
    user_msg = f"Quotas: {quota_str}\n\n{json.dumps(items, ensure_ascii=False)}"
    system_msg = _BATCH_SYSTEM_PROMPT

    # Single API call
    if config.AI_PROVIDER == "openai":
        result = _call_openai(system_msg, user_msg)
    elif config.AI_PROVIDER == "anthropic":
        result = _call_anthropic(system_msg, user_msg)
    elif config.AI_PROVIDER == "gemini":
        result = _call_gemini(system_msg, user_msg)
    else:
        raise ValueError(f"Unknown AI provider: {config.AI_PROVIDER}")

    # Parse picks
    picks = result.get("picks", [])
    result_map: dict[str, list[NormalizedPost]] = defaultdict(list)
    source_counts: dict[str, int] = defaultdict(int)

    for pick in picks:
        idx = pick.get("i", -1)
        if not (0 <= idx < len(post_index)):
            continue
        src_name, post = post_index[idx]
        quota = quotas.get(src_name, config.AI_PICKS_PER_SOURCE)
        if source_counts[src_name] >= quota:
            continue  # already hit quota for this source
        post.ai_rank = source_counts[src_name] + 1
        post.ai_reason = "ai-selected"
        result_map[src_name].append(post)
        source_counts[src_name] += 1

    # Fill any sources that AI missed with score fallback
    for src_name, posts in by_source.items():
        quota = quotas.get(src_name, config.AI_PICKS_PER_SOURCE)
        current = len(result_map.get(src_name, []))
        if current < quota:
            already = {id(p) for p in result_map.get(src_name, [])}
            remaining = [p for p in posts if id(p) not in already]
            fill = _score_select(remaining, quota - current)
            result_map[src_name].extend(fill)

    total = sum(len(v) for v in result_map.values())
    logger.info("AI batch selection: picked %d posts (1 API call, %d sources)", total, len(by_source))
    return dict(result_map)


# ── LLM API callers ──────────────────────────────────────────────────


def _call_openai(system_msg: str, user_msg: str) -> dict:
    import httpx
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def _call_anthropic(system_msg: str, user_msg: str) -> dict:
    import httpx
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": config.ANTHROPIC_MODEL,
            "max_tokens": 1024,
            "system": system_msg,
            "messages": [{"role": "user", "content": user_msg}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["content"][0]["text"]
    if "```" in content:
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            content = match.group(1)
    return json.loads(content)


def _call_gemini(system_msg: str, user_msg: str) -> dict:
    """Call Gemini — NO retry on 429, fail fast."""
    import httpx

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system_msg}]},
        "contents": [{"parts": [{"text": user_msg}]}],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }

    resp = httpx.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()

    content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    if "```" in content:
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            content = match.group(1)
    return json.loads(content)
