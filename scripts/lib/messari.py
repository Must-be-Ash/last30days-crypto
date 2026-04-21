"""Messari API client for crypto-data enrichment.

Only the working free-tier endpoints are wrapped here. Signal/news/sentiment
endpoints are paywalled (x402 pay-per-call) and intentionally NOT included —
LunarCrush + X cover those use cases.
"""

from __future__ import annotations

import threading
from typing import Any

from . import http

BASE_URL = "https://api.messari.io"
AUTH_HEADER = "X-Messari-API-Key"
DEFAULT_TIMEOUT = 25

# Per-process cache.
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

def asset_details(slugs: list[str], *, api_key: str) -> dict[str, Any]:
    """Rich metadata for up to 20 assets in one call."""
    if not slugs:
        return {"data": []}
    slugs = slugs[:20]
    cache_key = f"details:{','.join(sorted(slugs))}"

    def _fetch() -> dict[str, Any]:
        return http.get_with_params(
            f"{BASE_URL}/metrics/v2/assets/details",
            params={"slugs": ",".join(slugs)},
            headers=_headers(api_key),
            timeout=DEFAULT_TIMEOUT,
        )

    return _cached(cache_key, _fetch)


def resolve_slug(query: str, *, api_key: str) -> str | None:
    """Confirm a Messari slug for a token. Tries the literal slug first, then
    falls back to a search via /metrics/v2/assets?search=. Returns the
    canonical slug string or None.
    """
    if not query or not api_key:
        return None
    slug_candidate = query.strip().lower().replace(" ", "-")
    cache_key = f"resolve:{slug_candidate}"

    def _fetch() -> str | None:
        try:
            data = asset_details([slug_candidate], api_key=api_key)
            entries = (data or {}).get("data") or []
            if entries:
                return entries[0].get("slug") or slug_candidate
        except http.HTTPError:
            pass
        # Fallback: search list endpoint.
        try:
            data = http.get_with_params(
                f"{BASE_URL}/metrics/v2/assets",
                params={"search": query, "limit": 1},
                headers=_headers(api_key),
                timeout=DEFAULT_TIMEOUT,
            )
            entries = (data or {}).get("data") or []
            if entries:
                return entries[0].get("slug")
        except http.HTTPError:
            return None
        return None

    return _cached(cache_key, _fetch)


def _timeseries(slug: str, metric: str, granularity: str, *, api_key: str) -> dict[str, Any]:
    cache_key = f"ts:{slug}:{metric}:{granularity}"

    def _fetch() -> dict[str, Any]:
        return http.get(
            f"{BASE_URL}/metrics/v2/assets/{slug}/metrics/{metric}/time-series/{granularity}",
            headers=_headers(api_key),
            timeout=DEFAULT_TIMEOUT,
        )

    return _cached(cache_key, _fetch)


def futures_volume(slug: str, *, granularity: str = "1d", api_key: str) -> dict[str, Any]:
    return _timeseries(slug, "futures-volume", granularity, api_key=api_key)


def futures_open_interest(slug: str, *, granularity: str = "1d", api_key: str) -> dict[str, Any]:
    return _timeseries(slug, "futures-open-interest", granularity, api_key=api_key)


def futures_funding_rate(slug: str, *, granularity: str = "1d", api_key: str) -> dict[str, Any]:
    return _timeseries(slug, "futures-funding-rate", granularity, api_key=api_key)


def volatility(slug: str, *, granularity: str = "1d", api_key: str) -> dict[str, Any]:
    return _timeseries(slug, "volatility", granularity, api_key=api_key)


def roi(slug: str, *, api_key: str) -> dict[str, Any]:
    cache_key = f"roi:{slug}"

    def _fetch() -> dict[str, Any]:
        return http.get_with_params(
            f"{BASE_URL}/metrics/v2/assets/roi",
            params={"slugs": slug},
            headers=_headers(api_key),
            timeout=DEFAULT_TIMEOUT,
        )

    return _cached(cache_key, _fetch)


def ath(slug: str, *, api_key: str) -> dict[str, Any]:
    cache_key = f"ath:{slug}"

    def _fetch() -> dict[str, Any]:
        return http.get_with_params(
            f"{BASE_URL}/metrics/v2/assets/ath",
            params={"slugs": slug},
            headers=_headers(api_key),
            timeout=DEFAULT_TIMEOUT,
        )

    return _cached(cache_key, _fetch)


# ---------------------------------------------------------------------------
# Bundle builder
# ---------------------------------------------------------------------------

def enrich(slug: str, *, api_key: str, depth: str = "default") -> dict[str, Any]:
    """Fetch the full Messari bundle for one asset slug."""
    if not slug or not api_key:
        return {"error": "messari: missing slug or api_key"}

    bundle: dict[str, Any] = {"slug": slug}

    # Profile
    try:
        details = asset_details([slug], api_key=api_key)
        entry = ((details or {}).get("data") or [{}])[0] or {}
        bundle["name"] = entry.get("name")
        bundle["symbol"] = (entry.get("symbol") or "").upper() or None
        bundle["description"] = entry.get("description") or entry.get("descriptionShort")
        bundle["sector"] = entry.get("sectorV2") or entry.get("sector")
        bundle["sub_sector"] = entry.get("subSectorV2")
        bundle["tags"] = entry.get("tags") or []
        bundle["network_slugs"] = entry.get("networkSlugs") or []
        # Twitter handle from links[]
        links = entry.get("links") or []
        for link in links:
            if isinstance(link, dict) and (link.get("type") or "").lower() == "twitter":
                bundle["twitter_url"] = link.get("url")
                break
    except http.HTTPError as exc:
        bundle["details_error"] = str(exc)

    # Derivatives — only at default/deep depth.
    if depth != "quick":
        bundle.update(_derivatives_summary(slug, api_key=api_key))
        bundle.update(_volatility_summary(slug, api_key=api_key))

    return bundle


def _derivatives_summary(slug: str, *, api_key: str) -> dict[str, Any]:
    """Compress timeseries into a few human-readable summary fields."""
    out: dict[str, Any] = {}
    try:
        oi_data = futures_open_interest(slug, api_key=api_key)
        points = _series_points(oi_data)
        if points:
            out["oi_latest_usd"] = _latest_value(points, "open-interest")
            out["oi_pct_change_7d"] = _pct_change(points, "open-interest", lookback=7)
    except http.HTTPError as exc:
        out["oi_error"] = str(exc)

    try:
        fr_data = futures_funding_rate(slug, api_key=api_key)
        points = _series_points(fr_data)
        if points:
            out["funding_rate_latest"] = _latest_value(points, "funding-rate-open-interest")
            out["funding_rate_avg_7d"] = _avg_value(points, "funding-rate-open-interest", lookback=7)
    except http.HTTPError as exc:
        out["funding_error"] = str(exc)

    try:
        vol_data = futures_volume(slug, api_key=api_key)
        points = _series_points(vol_data)
        if points:
            out["futures_volume_latest_usd"] = _latest_value(points, "volume-usd")
            out["futures_volume_buy_pct_7d"] = _buy_share_7d(points)
    except http.HTTPError as exc:
        out["futures_volume_error"] = str(exc)

    return out


def _volatility_summary(slug: str, *, api_key: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        data = volatility(slug, api_key=api_key)
        points = _series_points(data)
        if points:
            latest = points[-1] if isinstance(points[-1], dict) else {}
            out["volatility_30d"] = latest.get("volatility-30d") or latest.get("volatility_30d")
            out["volatility_90d"] = latest.get("volatility-90d") or latest.get("volatility_90d")
            out["volatility_1y"] = latest.get("volatility-1y") or latest.get("volatility_1y")
    except http.HTTPError as exc:
        out["volatility_error"] = str(exc)
    return out


def _series_points(payload: Any) -> list[dict[str, Any]]:
    """Messari returns timeseries as either a flat list or wrapped in
    {data: {points: [...]}} / {data: [...]} depending on endpoint version."""
    if not payload:
        return []
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    if isinstance(data, dict):
        for key in ("points", "values", "series"):
            inner = data.get(key)
            if isinstance(inner, list):
                return [p for p in inner if isinstance(p, dict)]
    return []


def _latest_value(points: list[dict[str, Any]], field: str) -> float | None:
    for p in reversed(points):
        v = p.get(field)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _avg_value(points: list[dict[str, Any]], field: str, lookback: int) -> float | None:
    tail = points[-lookback:] if lookback > 0 else points
    values = []
    for p in tail:
        v = p.get(field)
        if v is None:
            continue
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    return sum(values) / len(values)


def _pct_change(points: list[dict[str, Any]], field: str, lookback: int) -> float | None:
    if len(points) < 2:
        return None
    latest = _latest_value(points, field)
    if latest is None:
        return None
    earlier_window = points[-(lookback + 1):-lookback] or points[:1]
    earlier = _latest_value(earlier_window, field)
    if not earlier:
        return None
    try:
        return ((latest - earlier) / earlier) * 100.0
    except ZeroDivisionError:
        return None


def _buy_share_7d(points: list[dict[str, Any]]) -> float | None:
    tail = points[-7:]
    buy_total = 0.0
    sell_total = 0.0
    for p in tail:
        try:
            buy_total += float(p.get("volume-buy-usd") or 0)
            sell_total += float(p.get("volume-sell-usd") or 0)
        except (TypeError, ValueError):
            continue
    if buy_total + sell_total <= 0:
        return None
    return (buy_total / (buy_total + sell_total)) * 100.0
