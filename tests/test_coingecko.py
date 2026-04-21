"""Unit tests for lib.coingecko."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import coingecko


class CoinGeckoEndpointTests(unittest.TestCase):
    def setUp(self):
        # Caches persist across calls within a process; clear between tests.
        coingecko._cache.clear()

    def _capture_url(self, payload):
        captured = {}
        def fake_request(method, url, *args, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = kwargs.get("headers")
            return payload
        return captured, fake_request

    def test_resolve_token_picks_top_search_match(self):
        payload = {
            "coins": [
                {"id": "hyperliquid", "symbol": "hype", "name": "Hyperliquid", "market_cap_rank": 13, "thumb": "x.png"},
                {"id": "hyper-other", "symbol": "hypex", "name": "HyperOther", "market_cap_rank": 999},
            ]
        }
        captured, fake = self._capture_url(payload)
        with patch("lib.coingecko.http.request", side_effect=fake):
            ref = coingecko.resolve_token("hyperliquid", api_key="cg-key")
        self.assertEqual("hyperliquid", ref["id"])
        self.assertEqual("hype", ref["symbol"])
        self.assertEqual(13, ref["market_cap_rank"])
        self.assertIn("/search?query=hyperliquid", captured["url"])
        self.assertEqual({"x-cg-pro-api-key": "cg-key", "Accept": "application/json"}, captured["headers"])

    def test_resolve_token_returns_none_on_empty(self):
        with patch("lib.coingecko.http.request", return_value={"coins": []}):
            self.assertIsNone(coingecko.resolve_token("nothing", api_key="k"))

    def test_enrich_flattens_profile_fields(self):
        profile = {
            "symbol": "hype",
            "name": "Hyperliquid",
            "market_cap_rank": 13,
            "categories": ["DeFi", "DEX"],
            "market_data": {
                "current_price": {"usd": 41.2},
                "market_cap": {"usd": 9_800_000_000},
                "fully_diluted_valuation": {"usd": 39_000_000_000},
                "total_volume": {"usd": 350_000_000},
                "price_change_percentage_24h": -0.5,
                "price_change_percentage_7d": -5.2,
                "price_change_percentage_30d": 2.4,
                "ath": {"usd": 59.3},
                "ath_change_percentage": {"usd": -30.5},
                "circulating_supply": 240_000_000,
                "total_supply": 962_000_000,
            },
            "community_data": {"twitter_followers": 100000, "reddit_subscribers": 5000, "telegram_channel_user_count": 43000},
            "developer_data": {"stars": 0, "commit_count_4_weeks": 0},
            "links": {"twitter_screen_name": "HyperliquidX", "homepage": ["https://app.hyperliquid.xyz"]},
        }
        # First call fetches profile, second fetches tickers.
        tickers_payload = {"tickers": [
            {"base": "HYPE", "target": "USDT",
             "market": {"name": "Binance"}, "converted_volume": {"usd": 100_000_000},
             "trust_score": "green", "trade_url": "https://binance.com/x"},
        ]}

        def fake_request(method, url, *args, **kwargs):
            if "/coins/hyperliquid?" in url or url.endswith("/coins/hyperliquid"):
                return profile
            if "/tickers" in url:
                return tickers_payload
            return {}
        with patch("lib.coingecko.http.request", side_effect=fake_request):
            bundle = coingecko.enrich("hyperliquid", api_key="k", depth="default")

        self.assertEqual("HYPE", bundle["symbol"])
        self.assertEqual(41.2, bundle["price_usd"])
        self.assertEqual(9_800_000_000, bundle["market_cap_usd"])
        self.assertEqual(-0.5, bundle["pct_change_24h"])
        self.assertEqual("HyperliquidX", bundle["twitter_handle"])
        self.assertEqual(1, len(bundle["top_exchanges"]))
        self.assertEqual("Binance", bundle["top_exchanges"][0]["exchange"])

    def test_enrich_quick_skips_tickers(self):
        profile = {"symbol": "hype", "name": "Hyperliquid", "market_data": {"current_price": {"usd": 41}}}
        called = []
        def fake_request(method, url, *args, **kwargs):
            called.append(url)
            if "/tickers" in url:
                self.fail("quick depth should not call tickers endpoint")
            return profile
        with patch("lib.coingecko.http.request", side_effect=fake_request):
            bundle = coingecko.enrich("hyperliquid", api_key="k", depth="quick")
        self.assertEqual(41, bundle["price_usd"])
        self.assertNotIn("top_exchanges", bundle)

    def test_enrich_returns_error_on_http_failure(self):
        from lib import http as http_mod
        with patch("lib.coingecko.http.request", side_effect=http_mod.HTTPError("502 Bad Gateway", 502)):
            bundle = coingecko.enrich("hyperliquid", api_key="k", depth="quick")
        self.assertIn("error", bundle)
        self.assertIn("502", bundle["error"])


if __name__ == "__main__":
    unittest.main()
