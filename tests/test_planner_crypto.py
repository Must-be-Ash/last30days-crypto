"""Unit tests for crypto-specific planner behavior (Phase 4.3)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import planner, schema


class CryptoIntentInferenceTests(unittest.TestCase):
    def test_quant_phrasing_routes_to_crypto_data(self):
        for topic in [
            "HYPE price action",
            "Bitcoin open interest and funding rate",
            "top whales holding SOL",
            "Solana on-chain TVL",
            "Galaxy Score for Pendle",
        ]:
            self.assertEqual("crypto_data", planner._infer_intent(topic), topic)

    def test_narrative_phrasing_routes_to_crypto_qual(self):
        for topic in [
            "memecoin narrative on Solana",
            "top Twitter influencers on Pendle airdrop",
            "AI agent token sentiment shift",
            "memecoin launch on Base",
        ]:
            self.assertEqual("crypto_qual", planner._infer_intent(topic), topic)

    def test_non_crypto_topics_unchanged(self):
        self.assertEqual("comparison", planner._infer_intent("Apple vs Google"))
        self.assertEqual("how_to", planner._infer_intent("how to deploy on Fly.io"))


class CryptoSourcePriorityTests(unittest.TestCase):
    def test_crypto_data_priority_leads_with_data_apis(self):
        priority = planner.SOURCE_PRIORITY["crypto_data"]
        # First three should be the crypto-data triple.
        self.assertEqual(["coingecko", "messari", "lunarcrush"], priority[:3])

    def test_crypto_qual_priority_x_first(self):
        priority = planner.SOURCE_PRIORITY["crypto_qual"]
        self.assertEqual("x", priority[0])
        self.assertEqual("lunarcrush", priority[1])

    def test_crypto_data_default_weights_favor_data_apis(self):
        weights = planner._default_source_weights(
            "crypto_data", ["x", "grounding", "reddit", "coingecko", "messari", "lunarcrush"],
        )
        # Crypto APIs should outweigh X here.
        self.assertGreater(weights["coingecko"], weights["x"])
        self.assertGreater(weights["messari"], weights["x"])

    def test_crypto_qual_default_weights_favor_x_and_lunarcrush(self):
        weights = planner._default_source_weights(
            "crypto_qual", ["x", "grounding", "reddit", "coingecko", "messari", "lunarcrush"],
        )
        # X and LunarCrush are the two heaviest sources.
        ranked = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
        top_two = {ranked[0][0], ranked[1][0]}
        self.assertEqual({"x", "lunarcrush"}, top_two)


class PlanQueryTokenAttachmentTests(unittest.TestCase):
    def test_plan_query_attaches_tokens(self):
        tokens = [schema.TokenRef(symbol="HYPE", name="Hyperliquid", coingecko_id="hyperliquid")]
        plan = planner.plan_query(
            topic="$HYPE outlook",
            available_sources=["x", "grounding", "reddit", "coingecko", "messari", "lunarcrush"],
            requested_sources=None,
            depth="quick",
            provider=None,
            model=None,
            tokens=tokens,
        )
        self.assertEqual(1, len(plan.tokens))
        self.assertEqual("HYPE", plan.tokens[0].symbol)
        # When tokens are present and crypto sources are available, planner
        # should at least keep the crypto sources reachable in source_weights.
        self.assertIn("coingecko", plan.source_weights)
        self.assertIn("messari", plan.source_weights)
        self.assertIn("lunarcrush", plan.source_weights)


if __name__ == "__main__":
    unittest.main()
