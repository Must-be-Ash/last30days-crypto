"""LunarCrush API client (Discover tier).

Hard rate limit: 10 req/min and 2,000 req/day. Both enforced via a
sliding-window limiter shared across the module so concurrent enrichment
calls don't blow the budget.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any
from urllib.parse import quote

from . import http

BASE_URL = "https://lunarcrush.com/api4"
DEFAULT_TIMEOUT = 25
RATE_LIMIT_PER_MINUTE = 10
RATE_LIMIT_PER_DAY = 2000

# Sliding-window limiter state.
_minute_window: deque[float] = deque()
_day_window: deque[float] = deque()
_window_lock = threading.Lock()

# Per-process cache.
_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def _wait_for_slot() -> None:
    """Block until both the minute and day windows have a free slot."""
    while True:
        with _window_lock:
            now = time.time()
            # Expire stale entries.
            while _minute_window and now - _minute_window[0] > 60:
                _minute_window.popleft()
            while _day_window and now - _day_window[0] > 86400:
                _day_window.popleft()

            if len(_minute_window) < RATE_LIMIT_PER_MINUTE and len(_day_window) < RATE_LIMIT_PER_DAY:
                _minute_window.append(now)
                _day_window.append(now)
                return

            # Compute the smaller wait between the two windows.
            minute_wait = 60 - (now - _minute_window[0]) if _minute_window else 0
            day_wait = 86400 - (now - _day_window[0]) if len(_day_window) >= RATE_LIMIT_PER_DAY else 0
            wait_for = max(minute_wait, day_wait, 0.1)
        time.sleep(min(wait_for, 6.5))


def _cached(cache_key: str, fetch):
    with _cache_lock:
        if cache_key in _cache:
            return _cache[cache_key]
    result = fetch()
    with _cache_lock:
        _cache[cache_key] = result
    return result


def _rate_limited_get(url: str, *, api_key: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    _wait_for_slot()
    if params:
        return http.get_with_params(url, params=params, headers=_headers(api_key), timeout=DEFAULT_TIMEOUT)
    return http.get(url, headers=_headers(api_key), timeout=DEFAULT_TIMEOUT)


# ---------------------------------------------------------------------------
# Topic resolution
# ---------------------------------------------------------------------------

def coins_list(*, api_key: str, limit: int = 1000, sort: str | None = None) -> dict[str, Any]:
    """Snapshot of all tracked coins with Galaxy Score, AltRank, sentiment."""
    cache_key = f"coins_list:{limit}:{sort}"

    def _fetch() -> dict[str, Any]:
        return _rate_limited_get(
            f"{BASE_URL}/public/coins/list/v2",
            api_key=api_key,
            params={"limit": limit, "sort": sort} if sort else {"limit": limit},
        )

    return _cached(cache_key, _fetch)


def resolve_topic(query: str, *, api_key: str) -> str | None:
    """Map a free-text token query to LunarCrush's `topic` slug.

    Returns the topic string (may include spaces — callers should URL-encode
    via `_encode_topic` before constructing endpoint URLs).
    """
    if not query or not api_key:
        return None
    candidate = query.strip().lower().replace("$", "").strip()

    try:
        data = coins_list(api_key=api_key)
    except http.HTTPError:
        return candidate

    coins = (data or {}).get("data") or []
    norm_query = query.strip().lower().lstrip("$")
    # 1. Exact symbol match.
    for coin in coins:
        if (coin.get("symbol") or "").lower() == norm_query:
            return coin.get("topic") or candidate
    # 2. Exact name match (case-insensitive).
    for coin in coins:
        if (coin.get("name") or "").lower() == norm_query:
            return coin.get("topic") or candidate
    # 3. Topic slug match (raw or hyphenated).
    hyphen_candidate = candidate.replace(" ", "-")
    for coin in coins:
        topic_lower = (coin.get("topic") or "").lower()
        if topic_lower == candidate or topic_lower == hyphen_candidate:
            return coin.get("topic")
    return candidate


def _encode_topic(topic: str) -> str:
    """URL-encode a topic for safe inclusion in a path. LunarCrush topics
    can contain spaces (e.g. 'hype hyperliquid')."""
    return quote(topic, safe="")


# ---------------------------------------------------------------------------
# Topic-specific endpoints
# ---------------------------------------------------------------------------

def topic_summary(topic: str, *, api_key: str) -> dict[str, Any]:
    cache_key = f"topic_summary:{topic}"
    enc = _encode_topic(topic)
    return _cached(cache_key, lambda: _rate_limited_get(
        f"{BASE_URL}/public/topic/{enc}/v1", api_key=api_key,
    ))


def topic_whatsup(topic: str, *, api_key: str) -> dict[str, Any]:
    cache_key = f"topic_whatsup:{topic}"
    enc = _encode_topic(topic)
    return _cached(cache_key, lambda: _rate_limited_get(
        f"{BASE_URL}/public/topic/{enc}/whatsup/v1", api_key=api_key,
    ))


def topic_news(topic: str, *, api_key: str) -> dict[str, Any]:
    cache_key = f"topic_news:{topic}"
    enc = _encode_topic(topic)
    return _cached(cache_key, lambda: _rate_limited_get(
        f"{BASE_URL}/public/topic/{enc}/news/v1", api_key=api_key,
    ))


def topic_posts(topic: str, *, api_key: str, start: int | None = None, end: int | None = None) -> dict[str, Any]:
    cache_key = f"topic_posts:{topic}:{start}:{end}"
    enc = _encode_topic(topic)
    return _cached(cache_key, lambda: _rate_limited_get(
        f"{BASE_URL}/public/topic/{enc}/posts/v1", api_key=api_key,
        params={"start": start, "end": end},
    ))


def topic_creators(topic: str, *, api_key: str) -> dict[str, Any]:
    cache_key = f"topic_creators:{topic}"
    enc = _encode_topic(topic)
    return _cached(cache_key, lambda: _rate_limited_get(
        f"{BASE_URL}/public/topic/{enc}/creators/v1", api_key=api_key,
    ))


def topic_time_series(topic: str, *, api_key: str, bucket: str = "hour") -> dict[str, Any]:
    cache_key = f"topic_time_series:{topic}:{bucket}"
    enc = _encode_topic(topic)
    return _cached(cache_key, lambda: _rate_limited_get(
        f"{BASE_URL}/public/topic/{enc}/time-series/v2", api_key=api_key,
        params={"bucket": bucket},
    ))


def topics_list(*, api_key: str) -> dict[str, Any]:
    cache_key = "topics_list"
    return _cached(cache_key, lambda: _rate_limited_get(
        f"{BASE_URL}/public/topics/list/v1", api_key=api_key,
    ))


def categories_list(*, api_key: str) -> dict[str, Any]:
    cache_key = "categories_list"
    return _cached(cache_key, lambda: _rate_limited_get(
        f"{BASE_URL}/public/categories/list/v1", api_key=api_key,
    ))


# ---------------------------------------------------------------------------
# Bundle builder
# ---------------------------------------------------------------------------

def enrich(topic: str, *, api_key: str, depth: str = "default") -> dict[str, Any]:
    """Fetch the LunarCrush bundle for one token topic.

    Conservative call budget:
      - quick: summary + whatsup (2 calls)
      - default: summary + whatsup + creators (3 calls)
      - deep: summary + whatsup + creators + posts + time_series (5 calls)
    """
    if not topic or not api_key:
        return {"error": "lunarcrush: missing topic or api_key"}

    bundle: dict[str, Any] = {"topic": topic}

    # 1. Summary
    try:
        summary = (topic_summary(topic, api_key=api_key) or {}).get("data") or {}
        bundle["topic_rank"] = summary.get("topic_rank")
        bundle["num_contributors"] = summary.get("num_contributors")
        bundle["num_posts"] = summary.get("num_posts")
        bundle["interactions_24h"] = summary.get("interactions_24h")
        bundle["trend"] = summary.get("trend")
        bundle["types_count"] = summary.get("types_count")
        bundle["types_sentiment"] = summary.get("types_sentiment")
        bundle["related_topics"] = summary.get("related_topics") or []
        bundle["categories"] = summary.get("categories") or []
    except http.HTTPError as exc:
        bundle["summary_error"] = str(exc)

    # 2. AI bull/bear themes
    try:
        whatsup = (topic_whatsup(topic, api_key=api_key) or {}).get("data") or {}
        bundle["ai_summary"] = whatsup.get("summary")
        bundle["bullish_themes"] = whatsup.get("supportive") or []
        bundle["bearish_themes"] = whatsup.get("critical") or []
    except http.HTTPError as exc:
        bundle["whatsup_error"] = str(exc)

    if depth == "quick":
        return bundle

    # 3. Top creators
    try:
        creators_payload = (topic_creators(topic, api_key=api_key) or {}).get("data") or []
        creators = []
        for c in creators_payload[:8]:
            handle = c.get("creator_name") or c.get("creator_id")
            if not handle:
                continue
            creators.append({
                "handle": handle,
                "display_name": c.get("creator_display_name"),
                "followers": c.get("creator_followers"),
                "rank": c.get("creator_rank"),
                "avatar": c.get("creator_avatar"),
                "interactions_24h": c.get("interactions_24h"),
            })
        bundle["top_creators"] = creators
    except http.HTTPError as exc:
        bundle["creators_error"] = str(exc)

    if depth != "deep":
        return bundle

    # 4. Top viral posts (deep only)
    try:
        posts_payload = (topic_posts(topic, api_key=api_key) or {}).get("data") or []
        bundle["top_posts"] = [
            {
                "type": p.get("post_type"),
                "title": p.get("post_title"),
                "body": p.get("post_description"),
                "url": p.get("post_link"),
                "sentiment": p.get("post_sentiment"),
                "creator": p.get("creator_name"),
                "creator_followers": p.get("creator_followers"),
                "interactions_24h": p.get("interactions_24h"),
            }
            for p in posts_payload[:8]
        ]
    except http.HTTPError as exc:
        bundle["posts_error"] = str(exc)

    # 5. Time series (deep only) — Galaxy Score / AltRank trajectory
    try:
        ts = (topic_time_series(topic, api_key=api_key, bucket="day") or {}).get("data") or []
        if ts:
            latest = ts[-1] if isinstance(ts[-1], dict) else {}
            earliest = ts[0] if isinstance(ts[0], dict) else {}
            bundle["galaxy_score_latest"] = latest.get("galaxy_score")
            bundle["galaxy_score_change_pct"] = _pct_change(earliest.get("galaxy_score"), latest.get("galaxy_score"))
            bundle["alt_rank_latest"] = latest.get("alt_rank")
            bundle["alt_rank_change"] = _delta(earliest.get("alt_rank"), latest.get("alt_rank"))
            bundle["sentiment_latest"] = latest.get("sentiment")
            bundle["social_dominance_latest"] = latest.get("social_dominance")
    except http.HTTPError as exc:
        bundle["time_series_error"] = str(exc)

    return bundle


def creators_to_items(bundle: dict[str, Any], topic: str) -> list[dict[str, Any]]:
    """Map LunarCrush top creators into pipeline-shaped item dicts so they
    can flow through the X-style normalizer when the rendering path wants
    them ranked alongside qualitative evidence."""
    items: list[dict[str, Any]] = []
    for idx, creator in enumerate(bundle.get("top_creators") or [], start=1):
        handle = (creator.get("handle") or "").lstrip("@")
        if not handle:
            continue
        items.append({
            "id": f"LC{idx}-{handle}",
            "text": f"{creator.get('display_name') or handle} is a top voice on ${topic.upper()} — followers: {creator.get('followers')}, 24h interactions: {creator.get('interactions_24h')}.",
            "url": f"https://x.com/{handle}",
            "author_handle": handle,
            "engagement": {
                "interactions_24h": creator.get("interactions_24h") or 0,
                "creator_followers": creator.get("followers") or 0,
            },
            "relevance": 0.7,
            "why_relevant": f"Top influencer for {topic} per LunarCrush",
        })
    return items


def _pct_change(start: Any, end: Any) -> float | None:
    try:
        s = float(start)
        e = float(end)
        if s == 0:
            return None
        return ((e - s) / s) * 100.0
    except (TypeError, ValueError):
        return None


def _delta(start: Any, end: Any) -> float | None:
    try:
        return float(end) - float(start)
    except (TypeError, ValueError):
        return None
