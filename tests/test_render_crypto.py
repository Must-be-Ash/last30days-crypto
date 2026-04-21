"""Unit tests for the Market & On-chain rendering section (Phase 5.3)."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import render, schema


def _make_report(crypto_enrichment, tokens=None) -> schema.Report:
    plan = schema.QueryPlan(
        intent="crypto_qual",
        freshness_mode="strict_recent",
        cluster_mode="story",
        raw_topic="HYPE crypto research",
        subqueries=[schema.SubQuery(label="primary", search_query="hype", ranking_query="What about HYPE?", sources=["x"])],
        source_weights={"x": 1.0},
        tokens=tokens or [],
    )
    return schema.Report(
        topic="HYPE crypto research",
        range_from="2026-03-21",
        range_to="2026-04-20",
        generated_at=datetime.now(timezone.utc).isoformat(),
        provider_runtime=schema.ProviderRuntime(
            reasoning_provider="local", planner_model="mock", rerank_model="mock", x_search_backend=None,
        ),
        query_plan=plan,
        clusters=[],
        ranked_candidates=[],
        items_by_source={},
        errors_by_source={},
        crypto_enrichment=crypto_enrichment,
        tokens=tokens or [],
    )


class MarketSectionRenderTests(unittest.TestCase):
    def test_empty_enrichment_omits_section(self):
        report = _make_report({})
        out = render.render_compact(report)
        self.assertNotIn("Market & On-chain", out)

    def test_full_bundle_renders_all_sub_sections(self):
        enrichment = {
            "coingecko": [{
                "_ref": {"symbol": "HYPE", "name": "Hyperliquid"},
                "coin_id": "hyperliquid",
                "symbol": "HYPE",
                "name": "Hyperliquid",
                "market_cap_rank": 13,
                "categories": ["DeFi", "DEX"],
                "price_usd": 41.2,
                "market_cap_usd": 9_800_000_000,
                "fully_diluted_valuation_usd": 39_000_000_000,
                "total_volume_usd": 350_000_000,
                "pct_change_24h": -0.5,
                "pct_change_7d": -5.2,
                "pct_change_30d": 2.4,
                "ath_usd": 59.3,
                "ath_change_pct": -30.5,
                "twitter_followers": 100000,
                "twitter_handle": "HyperliquidX",
                "top_exchanges": [
                    {"exchange": "Binance", "pair": "HYPE/USDT", "volume_usd": 100_000_000, "trust_score": "green", "url": "https://binance.com"},
                ],
            }],
            "messari": [{
                "_ref": {"symbol": "HYPE", "name": "Hyperliquid"},
                "slug": "hyperliquid",
                "name": "Hyperliquid",
                "symbol": "HYPE",
                "sector": ["DeFi"],
                "sub_sector": ["DEX"],
                "tags": ["DeFi", "Perpetuals"],
                "network_slugs": ["hyperevm"],
                "oi_latest_usd": 1_000_000_000,
                "oi_pct_change_7d": 5.0,
                "funding_rate_latest": 0.0001,
                "funding_rate_avg_7d": 0.0002,
                "futures_volume_latest_usd": 500_000_000,
                "futures_volume_buy_pct_7d": 55.5,
                "volatility_30d": 0.05,
                "volatility_90d": 0.04,
                "volatility_1y": 0.06,
            }],
            "lunarcrush": [{
                "_ref": {"symbol": "HYPE", "name": "Hyperliquid"},
                "topic": "hype hyperliquid",
                "topic_rank": 50,
                "trend": "up",
                "interactions_24h": 1_000_000,
                "num_contributors": 5000,
                "types_count": {"tweet": 2000, "reddit-post": 50},
                "types_sentiment": {"tweet": 90, "reddit-post": 80},
                "bullish_themes": [
                    {"title": "Bull theme A", "description": "Strong rev growth", "percent": 60},
                ],
                "bearish_themes": [
                    {"title": "Bear theme B", "description": "Token unlock concerns", "percent": 25},
                ],
                "top_creators": [
                    {"handle": "elonmusk", "display_name": "Elon Musk", "followers": 200_000_000, "interactions_24h": 5_000_000, "rank": 1},
                ],
            }],
        }
        report = _make_report(enrichment, tokens=[
            schema.TokenRef(symbol="HYPE", name="Hyperliquid", coingecko_id="hyperliquid"),
        ])
        out = render.render_compact(report)

        self.assertIn("## Market & On-chain", out)
        self.assertIn("### HYPE — Hyperliquid — rank #13", out)
        self.assertIn("Price snapshot", out)
        self.assertIn("$41.20", out)
        self.assertIn("$9.80B", out)
        self.assertIn("Social signal", out)
        self.assertIn("trend up", out)
        self.assertIn("AI bull/bear themes", out)
        self.assertIn("Bull theme A", out)
        self.assertIn("Bear theme B", out)
        self.assertIn("Top influencers", out)
        self.assertIn("https://x.com/elonmusk", out)
        self.assertIn("Derivatives", out)
        self.assertIn("OI $1.00B", out)
        self.assertIn("Volatility", out)
        self.assertIn("Where it trades", out)
        self.assertIn("Binance", out)

    def test_context_render_includes_compact_market_block(self):
        enrichment = {
            "coingecko": [{
                "_ref": {"symbol": "HYPE", "name": "Hyperliquid"},
                "name": "Hyperliquid",
                "price_usd": 41.2,
                "pct_change_24h": -0.5,
                "pct_change_30d": 2.4,
            }],
            "lunarcrush": [{
                "_ref": {"symbol": "HYPE", "name": "Hyperliquid"},
                "trend": "up",
                "bullish_themes": [{"title": "Bull A", "description": "x", "percent": 50}],
                "bearish_themes": [],
            }],
        }
        report = _make_report(enrichment)
        out = render.render_context(report)
        self.assertIn("Market snapshot", out)
        self.assertIn("HYPE", out)
        self.assertIn("Bull A", out)


if __name__ == "__main__":
    unittest.main()
