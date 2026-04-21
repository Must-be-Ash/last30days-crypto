"""CoinGecko Pro API client for crypto enrichment.

Returns flattened bundles consumed by the Market & On-chain renderer in
``render.py``. All endpoints are read-only public market data — no PII.
"""

from __future__ import annotations

import threading
from typing import Any

from . import http

BASE_URL = "https://pro-api.coingecko.com/api/v3"
AUTH_HEADER = "x-cg-pro-api-key"
DEFAULT_TIMEOUT = 20

# Per-process cache. Cleared between processes (daemon-free CLI), so safe.
_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


def _headers(api_key: str) -> dict[str, str]:
    return {AUTH_HEADER: api_key, "Accept": "application/json"}


def _cached(cache_key: str, fetch):
    with _cache_lock:
        if cache_key in _cache:
            return _cache[cache_key]
    result = fetch()
    with _cache_lock:
        _cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Endpoint helpers
# ---------------------------------------------------------------------------

def resolve_token(query: str, *, api_key: str) -> dict[str, Any] | None:
    """Resolve a free-text query to the best-matching CoinGecko coin.

    Returns dict with keys: id, symbol, name, market_cap_rank, thumb. None if
    no match.
    """
    if not query or not api_key:
        return None
    cache_key = f"resolve:{query.lower()}"

    def _fetch() -> dict[str, Any] | None:
        try:
            data = http.get_with_params(
                f"{BASE_URL}/search",
                params={"query": query},
                headers=_headers(api_key),
                timeout=DEFAULT_TIMEOUT,
            )
        except http.HTTPError:
            return None
        coins = (data or {}).get("coins") or []
        if not coins:
            return None
        # CoinGecko ranks /search results by market-cap relevance already.
        top = coins[0]
        return {
            "id": top.get("id"),
            "symbol": (top.get("symbol") or "").lower(),
            "name": top.get("name"),
            "market_cap_rank": top.get("market_cap_rank"),
            "thumb": top.get("thumb") or top.get("large"),
        }

    return _cached(cache_key, _fetch)


def coin_profile(coin_id: str, *, api_key: str) -> dict[str, Any]:
    """Full coin profile: price, market data, community, developer, links."""
    cache_key = f"profile:{coin_id}"

    def _fetch() -> dict[str, Any]:
        return http.get_with_params(
            f"{BASE_URL}/coins/{coin_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "true",
                "developer_data": "true",
                "sparkline": "false",
            },
            headers=_headers(api_key),
            timeout=DEFAULT_TIMEOUT,
        )

    return _cached(cache_key, _fetch)


def market_chart(coin_id: str, *, days: int = 30, api_key: str) -> dict[str, Any]:
    """Historical price/volume/marketcap series."""
    cache_key = f"chart:{coin_id}:{days}"

    def _fetch() -> dict[str, Any]:
        return http.get_with_params(
            f"{BASE_URL}/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": days},
            headers=_headers(api_key),
            timeout=DEFAULT_TIMEOUT,
        )

    return _cached(cache_key, _fetch)


def tickers(coin_id: str, *, api_key: str, page: int = 1) -> dict[str, Any]:
    """Exchange tickers — where the token actually trades."""
    cache_key = f"tickers:{coin_id}:{page}"

    def _fetch() -> dict[str, Any]:
        return http.get_with_params(
            f"{BASE_URL}/coins/{coin_id}/tickers",
            params={"page": page, "depth": "true", "order": "volume_desc"},
            headers=_headers(api_key),
            timeout=DEFAULT_TIMEOUT,
        )

    return _cached(cache_key, _fetch)


def trending(*, api_key: str) -> dict[str, Any]:
    """Top 7 trending coins in the last 24h by search volume."""
    cache_key = "trending"

    def _fetch() -> dict[str, Any]:
        return http.get(
            f"{BASE_URL}/search/trending",
            headers=_headers(api_key),
            timeout=DEFAULT_TIMEOUT,
        )

    return _cached(cache_key, _fetch)


def top_gainers_losers(*, api_key: str) -> dict[str, Any]:
    """Top gainers and losers by 24h % price change."""
    cache_key = "gainers_losers"

    def _fetch() -> dict[str, Any]:
        return http.get_with_params(
            f"{BASE_URL}/coins/top_gainers_losers",
            params={"vs_currency": "usd", "duration": "24h", "top_coins": 1000},
            headers=_headers(api_key),
            timeout=DEFAULT_TIMEOUT,
        )

    return _cached(cache_key, _fetch)


# ---------------------------------------------------------------------------
# Bundle builder for the Market & On-chain renderer
# ---------------------------------------------------------------------------

def enrich(coin_id: str, *, api_key: str, depth: str = "default") -> dict[str, Any]:
    """Fetch the full bundle for one token and return a flat dict ready to
    render. Returns ``{"error": "..."}`` on failure rather than raising so
    the pipeline can render partial reports."""
    if not coin_id or not api_key:
        return {"error": "coingecko: missing coin_id or api_key"}
    try:
        profile = coin_profile(coin_id, api_key=api_key)
    except http.HTTPError as exc:
        return {"error": f"coingecko profile: {exc}"}

    market = profile.get("market_data") or {}
    community = profile.get("community_data") or {}
    developer = profile.get("developer_data") or {}
    links = profile.get("links") or {}

    bundle: dict[str, Any] = {
        "coin_id": coin_id,
        "symbol": (profile.get("symbol") or "").upper(),
        "name": profile.get("name"),
        "market_cap_rank": profile.get("market_cap_rank"),
        "categories": profile.get("categories") or [],
        "price_usd": _safe_float((market.get("current_price") or {}).get("usd")),
        "market_cap_usd": _safe_float((market.get("market_cap") or {}).get("usd")),
        "fully_diluted_valuation_usd": _safe_float((market.get("fully_diluted_valuation") or {}).get("usd")),
        "total_volume_usd": _safe_float((market.get("total_volume") or {}).get("usd")),
        "pct_change_24h": _safe_float(market.get("price_change_percentage_24h")),
        "pct_change_7d": _safe_float(market.get("price_change_percentage_7d")),
        "pct_change_30d": _safe_float(market.get("price_change_percentage_30d")),
        "ath_usd": _safe_float((market.get("ath") or {}).get("usd")),
        "ath_change_pct": _safe_float((market.get("ath_change_percentage") or {}).get("usd")),
        "circulating_supply": _safe_float(market.get("circulating_supply")),
        "total_supply": _safe_float(market.get("total_supply")),
        "twitter_followers": community.get("twitter_followers"),
        "reddit_subscribers": community.get("reddit_subscribers"),
        "telegram_users": community.get("telegram_channel_user_count"),
        "github_stars": developer.get("stars"),
        "github_commits_4w": developer.get("commit_count_4_weeks"),
        "twitter_handle": links.get("twitter_screen_name"),
        "homepage": _first(links.get("homepage")),
        "subreddit_url": links.get("subreddit_url"),
    }

    # Tickers (top 5 exchanges by volume) — skip on quick depth.
    if depth != "quick":
        try:
            tickers_data = tickers(coin_id, api_key=api_key)
            top_tickers = []
            for t in (tickers_data.get("tickers") or [])[:5]:
                market_obj = t.get("market") or {}
                top_tickers.append({
                    "exchange": market_obj.get("name"),
                    "pair": f"{t.get('base')}/{t.get('target')}",
                    "volume_usd": _safe_float(t.get("converted_volume", {}).get("usd")),
                    "trust_score": t.get("trust_score"),
                    "url": t.get("trade_url"),
                })
            bundle["top_exchanges"] = top_tickers
        except http.HTTPError as exc:
            bundle["tickers_error"] = str(exc)

    return bundle


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _first(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            if item:
                return item
        return None
    return value or None
