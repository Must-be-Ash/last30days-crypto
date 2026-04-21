"""Unit tests for lib.messari."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import messari


class MessariEndpointTests(unittest.TestCase):
    def setUp(self):
        messari._cache.clear()

    def test_resolve_slug_via_asset_details(self):
        details_payload = {"data": [{"slug": "hyperliquid", "name": "Hyperliquid"}]}
        captured = []
        def fake_request(method, url, *args, **kwargs):
            captured.append(url)
            return details_payload
        with patch("lib.messari.http.request", side_effect=fake_request):
            slug = messari.resolve_slug("Hyperliquid", api_key="k")
        self.assertEqual("hyperliquid", slug)
        self.assertTrue(any("/metrics/v2/assets/details" in u for u in captured))

    def test_enrich_quick_returns_profile_only(self):
        details_payload = {"data": [{
            "slug": "hyperliquid",
            "name": "Hyperliquid",
            "symbol": "HYPE",
            "description": "A perp DEX",
            "sectorV2": ["DeFi", "Networks"],
            "subSectorV2": ["DEX"],
            "tags": ["DeFi"],
            "networkSlugs": ["hyperevm"],
            "links": [{"type": "Twitter", "url": "https://twitter.com/HyperliquidX"}],
        }]}

        def fake_request(method, url, *args, **kwargs):
            self.assertNotIn("/futures-", url, "quick depth should not call futures endpoints")
            self.assertNotIn("/volatility/", url, "quick depth should not call volatility endpoint")
            return details_payload
        with patch("lib.messari.http.request", side_effect=fake_request):
            bundle = messari.enrich("hyperliquid", api_key="k", depth="quick")

        self.assertEqual("Hyperliquid", bundle["name"])
        self.assertEqual("HYPE", bundle["symbol"])
        self.assertEqual(["DeFi", "Networks"], bundle["sector"])
        self.assertEqual("https://twitter.com/HyperliquidX", bundle["twitter_url"])

    def test_enrich_default_pulls_derivatives_and_volatility(self):
        details_payload = {"data": [{"slug": "hyperliquid", "name": "Hyperliquid", "symbol": "HYPE"}]}
        oi_payload = {"data": [{"open-interest": 100.0}, {"open-interest": 105.0}, {"open-interest": 120.0}]}
        funding_payload = {"data": [{"funding-rate-open-interest": 0.0001}, {"funding-rate-open-interest": 0.0002}]}
        futures_vol_payload = {"data": [{"volume-usd": 1000, "volume-buy-usd": 600, "volume-sell-usd": 400}]}
        vol_payload = {"data": [{"volatility-30d": 0.05, "volatility-90d": 0.04, "volatility-1y": 0.06}]}

        def fake_request(method, url, *args, **kwargs):
            if "details" in url:
                return details_payload
            if "futures-open-interest" in url:
                return oi_payload
            if "futures-funding-rate" in url:
                return funding_payload
            if "futures-volume" in url:
                return futures_vol_payload
            if "/volatility/" in url:
                return vol_payload
            return {}

        with patch("lib.messari.http.request", side_effect=fake_request):
            bundle = messari.enrich("hyperliquid", api_key="k", depth="default")

        self.assertEqual(120.0, bundle["oi_latest_usd"])
        self.assertAlmostEqual(0.0002, bundle["funding_rate_latest"])
        self.assertEqual(1000.0, bundle["futures_volume_latest_usd"])
        self.assertEqual(60.0, bundle["futures_volume_buy_pct_7d"])
        self.assertEqual(0.05, bundle["volatility_30d"])
        self.assertEqual(0.04, bundle["volatility_90d"])

    def test_enrich_returns_partial_on_endpoint_error(self):
        from lib import http as http_mod
        details_payload = {"data": [{"slug": "hyperliquid", "name": "Hyperliquid"}]}

        def fake_request(method, url, *args, **kwargs):
            if "details" in url:
                return details_payload
            raise http_mod.HTTPError("504 Gateway Timeout", 504)

        with patch("lib.messari.http.request", side_effect=fake_request):
            bundle = messari.enrich("hyperliquid", api_key="k", depth="default")

        self.assertEqual("Hyperliquid", bundle["name"])
        self.assertIn("oi_error", bundle)
        self.assertIn("volatility_error", bundle)


if __name__ == "__main__":
    unittest.main()
