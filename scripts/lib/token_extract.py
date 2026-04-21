"""Extract token references from a research topic.

Returns ``TokenRef`` objects holding cross-API slugs (CoinGecko id, Messari
slug, LunarCrush topic). Slugs are populated lazily — only the CoinGecko
resolver is invoked at extraction time to confirm a candidate is a real
coin. Messari and LunarCrush slugs default to the symbol/name and are
finalized inside their respective ``enrich`` calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import coingecko, env

# $TICKER pattern: 2-10 uppercase letters/digits prefixed by $.
_TICKER_RE = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,9})\b")

# Capitalized multi-word project names (e.g. "Hyperliquid", "Pendle Finance").
_NAME_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+){0,2})\b")

# Stoplist of common English words and crypto generics that look like proper
# nouns but aren't tokens. Filters reduce CoinGecko API noise.
_NAME_STOPLIST = {
    "Solana", "Ethereum", "Bitcoin", "Polygon", "Arbitrum", "Optimism", "Base",
    "Hyperliquid", "Pendle", "Aave",  # Keep these — they ARE tokens; allow through
}
_NAME_STOPLIST_BLACKLIST = {
    "AI", "Q1", "Q2", "Q3", "Q4", "DeFi", "NFT", "DEX", "CEX", "MEV", "L1", "L2",
    "TVL", "FUD", "FOMO", "Nano", "Banana", "Pro", "Crypto", "Twitter", "X",
    "Reddit", "GitHub", "Substack", "Medium", "Discord", "Telegram",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "Spring", "Summer", "Autumn", "Winter", "Fall",
    "Tweet", "Tweets", "Post", "Posts", "News", "Update", "Updates",
    "United", "States", "America",
}

# Hard cap per topic — keeps API costs and report size sane.
MAX_TOKENS = 5


@dataclass
class TokenRef:
    """A cross-API reference to a single crypto asset."""

    symbol: str
    name: str
    coingecko_id: str | None = None
    messari_slug: str | None = None
    lunarcrush_topic: str | None = None
    market_cap_rank: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "coingecko_id": self.coingecko_id,
            "messari_slug": self.messari_slug,
            "lunarcrush_topic": self.lunarcrush_topic,
            "market_cap_rank": self.market_cap_rank,
        }


def extract_tokens(topic: str, config: dict[str, Any]) -> list[TokenRef]:
    """Extract up to ``MAX_TOKENS`` token refs from the research topic.

    A candidate is kept only if CoinGecko's ``/search`` resolves it to a
    real coin (so ad-hoc capitalized words don't trigger spurious
    enrichment). When no CoinGecko key is configured, falls back to
    returning ticker matches as raw refs (no resolution, no rank).
    """
    if not topic:
        return []

    candidates = _candidate_strings(topic)
    if not candidates:
        return []

    cg_key = env.get_coingecko_key(config)

    refs: list[TokenRef] = []
    seen_ids: set[str] = set()
    seen_symbols: set[str] = set()

    for candidate in candidates:
        if len(refs) >= MAX_TOKENS:
            break

        if cg_key:
            resolved = coingecko.resolve_token(candidate, api_key=cg_key)
            if not resolved or not resolved.get("id"):
                continue
            coin_id = resolved["id"]
            symbol = (resolved.get("symbol") or candidate).lower()
            name = resolved.get("name") or candidate
            if coin_id in seen_ids or symbol in seen_symbols:
                continue
            seen_ids.add(coin_id)
            seen_symbols.add(symbol)
            refs.append(
                TokenRef(
                    symbol=symbol.upper(),
                    name=name,
                    coingecko_id=coin_id,
                    # Messari + LunarCrush slugs default to the canonical name
                    # (lowercased, hyphenated). Their respective ``enrich``
                    # calls will resolve to canonical slugs internally.
                    messari_slug=name.lower().replace(" ", "-"),
                    lunarcrush_topic=name.lower(),
                    market_cap_rank=resolved.get("market_cap_rank"),
                )
            )
        else:
            symbol = candidate.lower()
            if symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            refs.append(TokenRef(symbol=symbol.upper(), name=candidate))

    return refs


def _candidate_strings(topic: str) -> list[str]:
    """Build the ordered candidate list from a topic. Tickers come first
    (highest signal), then capitalized name fragments."""
    seen: set[str] = set()
    out: list[str] = []

    for match in _TICKER_RE.finditer(topic):
        token = match.group(1)
        norm = token.upper()
        if norm not in _NAME_STOPLIST_BLACKLIST and norm not in seen:
            seen.add(norm)
            out.append(token)

    for match in _NAME_RE.finditer(topic):
        phrase = match.group(1).strip()
        # Reject all-uppercase short tokens (probably an acronym already).
        if phrase.upper() == phrase and len(phrase) <= 3:
            continue
        words = phrase.split()
        head = words[0]
        # Multi-word phrases: only yield the full phrase when the head is
        # not a generic verb like "Comparing"/"Reviewing"/etc. We also
        # always yield each constituent word so e.g. "Comparing Pendle"
        # still surfaces "Pendle" as a candidate even when the full phrase
        # fails to resolve.
        if head not in _NAME_STOPLIST_BLACKLIST:
            norm = phrase.lower()
            if norm not in seen:
                seen.add(norm)
                out.append(phrase)
        # Always also enqueue each word individually so partial matches
        # behind generic prefixes still get a CoinGecko lookup.
        for word in words:
            if len(word) < 3 or word in _NAME_STOPLIST_BLACKLIST:
                continue
            wnorm = word.lower()
            if wnorm in seen:
                continue
            seen.add(wnorm)
            out.append(word)

    return out
