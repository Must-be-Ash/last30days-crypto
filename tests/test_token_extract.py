"""Unit tests for lib.token_extract."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import token_extract


class TickerRegexTests(unittest.TestCase):
    def test_dollar_ticker_extracted(self):
        with patch("lib.token_extract.coingecko.resolve_token") as mock_resolve:
            mock_resolve.side_effect = lambda q, api_key: {
                "id": q.lower(), "symbol": q.lower(), "name": q.title(), "market_cap_rank": 99,
            }
            refs = token_extract.extract_tokens("$HYPE momentum this week", {"COINGECKO_API_KEY": "k"})
        self.assertEqual(1, len(refs))
        self.assertEqual("HYPE", refs[0].symbol)
        self.assertEqual("hype", refs[0].coingecko_id)

    def test_capitalized_project_name_extracted(self):
        with patch("lib.token_extract.coingecko.resolve_token") as mock_resolve:
            def resolver(q, api_key):
                if q == "Hyperliquid":
                    return {"id": "hyperliquid", "symbol": "hype", "name": "Hyperliquid", "market_cap_rank": 13}
                return None
            mock_resolve.side_effect = resolver
            refs = token_extract.extract_tokens("Hyperliquid Q1 outlook", {"COINGECKO_API_KEY": "k"})
        self.assertEqual(1, len(refs))
        self.assertEqual("HYPE", refs[0].symbol)
        self.assertEqual("hyperliquid", refs[0].coingecko_id)

    def test_stoplist_filters_acronyms_and_dates(self):
        with patch("lib.token_extract.coingecko.resolve_token") as mock_resolve:
            mock_resolve.return_value = None
            refs = token_extract.extract_tokens("AI Q1 March news on DeFi NFT", {"COINGECKO_API_KEY": "k"})
        # All candidates are blacklisted — extractor should make no API calls
        # for stoplist-blocked tokens.
        self.assertEqual(0, mock_resolve.call_count)
        self.assertEqual(0, len(refs))

    def test_cap_at_max_tokens(self):
        with patch("lib.token_extract.coingecko.resolve_token") as mock_resolve:
            mock_resolve.side_effect = lambda q, api_key: {
                "id": q.lower(), "symbol": q.lower(), "name": q, "market_cap_rank": 1,
            }
            refs = token_extract.extract_tokens(
                "$AAA $BBB $CCC $DDD $EEE $FFF $GGG", {"COINGECKO_API_KEY": "k"},
            )
        self.assertEqual(token_extract.MAX_TOKENS, len(refs))

    def test_dedupes_by_symbol(self):
        with patch("lib.token_extract.coingecko.resolve_token") as mock_resolve:
            def resolver(q, api_key):
                if q.lower() == "hype" or q == "Hyperliquid":
                    return {"id": "hyperliquid", "symbol": "hype", "name": "Hyperliquid", "market_cap_rank": 13}
                return None
            mock_resolve.side_effect = resolver
            refs = token_extract.extract_tokens("$HYPE Hyperliquid is shipping", {"COINGECKO_API_KEY": "k"})
        # Both candidates resolve to coin id 'hyperliquid' — dedupe yields one ref.
        self.assertEqual(1, len(refs))

    def test_no_coingecko_key_falls_back_to_ticker_only(self):
        refs = token_extract.extract_tokens("$BTC $ETH discussion", {})
        symbols = {r.symbol for r in refs}
        self.assertIn("BTC", symbols)
        self.assertIn("ETH", symbols)
        self.assertTrue(all(r.coingecko_id is None for r in refs))

    def test_empty_topic_returns_empty(self):
        self.assertEqual([], token_extract.extract_tokens("", {}))
        self.assertEqual([], token_extract.extract_tokens("   ", {}))


if __name__ == "__main__":
    unittest.main()
