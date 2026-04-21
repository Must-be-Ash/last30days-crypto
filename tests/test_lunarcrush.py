"""Unit tests for lib.lunarcrush."""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import lunarcrush


class LunarCrushEndpointTests(unittest.TestCase):
    def setUp(self):
        lunarcrush._cache.clear()
        lunarcrush._minute_window.clear()
        lunarcrush._day_window.clear()

    def test_resolve_topic_via_coins_list_symbol_match(self):
        coins_payload = {"data": [
            {"symbol": "btc", "name": "Bitcoin", "topic": "bitcoin"},
            {"symbol": "hype", "name": "Hyperliquid", "topic": "hype hyperliquid"},
        ]}
        with patch("lib.lunarcrush.http.request", return_value=coins_payload):
            self.assertEqual("hype hyperliquid", lunarcrush.resolve_topic("hype", api_key="k"))
            self.assertEqual("bitcoin", lunarcrush.resolve_topic("Bitcoin", api_key="k"))

    def test_topic_summary_url_encodes_topic_with_spaces(self):
        captured = {}
        def fake_request(method, url, *args, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers")
            return {"data": {"trend": "up"}}
        with patch("lib.lunarcrush.http.request", side_effect=fake_request):
            lunarcrush.topic_summary("hype hyperliquid", api_key="k")
        self.assertIn("hype%20hyperliquid", captured["url"])
        self.assertEqual("Bearer k", captured["headers"]["Authorization"])

    def test_enrich_quick_calls_summary_and_whatsup_only(self):
        call_log = []
        def fake_request(method, url, *args, **kwargs):
            call_log.append(url)
            if "/whatsup/" in url:
                return {"data": {"summary": "AI summary", "supportive": [], "critical": []}}
            return {"data": {"trend": "up", "interactions_24h": 100}}
        with patch("lib.lunarcrush.http.request", side_effect=fake_request):
            bundle = lunarcrush.enrich("hyperliquid", api_key="k", depth="quick")
        # Exactly 2 endpoint URLs (summary + whatsup) — no creators/posts/time-series.
        self.assertEqual(2, len(call_log))
        self.assertEqual("up", bundle["trend"])
        self.assertEqual("AI summary", bundle["ai_summary"])
        self.assertNotIn("top_creators", bundle)

    def test_enrich_default_adds_creators(self):
        creators_payload = {"data": [{
            "creator_name": "elonmusk", "creator_display_name": "Elon Musk",
            "creator_followers": 200_000_000, "creator_rank": 1,
            "interactions_24h": 5_000_000,
        }]}
        def fake_request(method, url, *args, **kwargs):
            if "/whatsup/" in url:
                return {"data": {"summary": "ok"}}
            if "/creators/" in url:
                return creators_payload
            return {"data": {"trend": "up"}}
        with patch("lib.lunarcrush.http.request", side_effect=fake_request):
            bundle = lunarcrush.enrich("hyperliquid", api_key="k", depth="default")
        self.assertEqual(1, len(bundle["top_creators"]))
        self.assertEqual("elonmusk", bundle["top_creators"][0]["handle"])

    def test_creators_to_items_yields_x_links(self):
        bundle = {"top_creators": [
            {"handle": "elonmusk", "display_name": "Elon", "followers": 1000, "interactions_24h": 50},
        ]}
        items = lunarcrush.creators_to_items(bundle, "hype hyperliquid")
        self.assertEqual(1, len(items))
        self.assertEqual("https://x.com/elonmusk", items[0]["url"])
        self.assertEqual("elonmusk", items[0]["author_handle"])

    def test_rate_limiter_blocks_at_minute_ceiling(self):
        # Pre-fill the minute window to the ceiling.
        now = time.time()
        for _ in range(lunarcrush.RATE_LIMIT_PER_MINUTE):
            lunarcrush._minute_window.append(now)

        slept_for = []
        original_sleep = time.sleep
        def fake_sleep(s):
            slept_for.append(s)
            # Simulate time passing so the window ages out and the loop can exit.
            for _ in range(lunarcrush.RATE_LIMIT_PER_MINUTE):
                if lunarcrush._minute_window:
                    lunarcrush._minute_window.popleft()

        with patch("lib.lunarcrush.time.sleep", side_effect=fake_sleep):
            lunarcrush._wait_for_slot()

        self.assertGreater(len(slept_for), 0)


if __name__ == "__main__":
    unittest.main()
