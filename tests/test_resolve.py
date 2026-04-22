import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import resolve


class TestHasBackend(unittest.TestCase):
    def test_no_keys_returns_false(self):
        self.assertFalse(resolve._has_backend({}))

    def test_brave_key_returns_true(self):
        self.assertTrue(resolve._has_backend({"BRAVE_API_KEY": "key"}))

    def test_exa_key_returns_true(self):
        self.assertTrue(resolve._has_backend({"EXA_API_KEY": "key"}))

    def test_serper_key_returns_true(self):
        self.assertTrue(resolve._has_backend({"SERPER_API_KEY": "key"}))


class TestExtractXHandle(unittest.TestCase):
    def test_extracts_from_url(self):
        items = [
            {"title": "OpenAI on X", "snippet": "Updates from @OpenAI", "url": "https://x.com/OpenAI"},
        ]
        result = resolve._extract_x_handle(items)
        self.assertEqual(result, "openai")

    def test_extracts_from_text(self):
        items = [
            {"title": "Follow @elonmusk", "snippet": "Also @elonmusk tweeted", "url": ""},
        ]
        result = resolve._extract_x_handle(items)
        self.assertEqual(result, "elonmusk")

    def test_filters_generic_handles(self):
        items = [
            {"title": "Go to @twitter", "snippet": "Visit @x", "url": ""},
        ]
        result = resolve._extract_x_handle(items)
        self.assertEqual(result, "")

    def test_empty_items_returns_empty(self):
        self.assertEqual(resolve._extract_x_handle([]), "")


class TestExtractGitHub(unittest.TestCase):
    def test_extracts_user_from_url(self):
        items = [{"title": "", "snippet": "", "url": "https://github.com/openclaw/"}]
        self.assertEqual(resolve._extract_github_user(items), "openclaw")

    def test_extracts_repos(self):
        items = [{"title": "", "snippet": "", "url": "https://github.com/foo/bar"}]
        self.assertEqual(resolve._extract_github_repos(items), ["foo/bar"])


class TestBuildContextSummary(unittest.TestCase):
    def test_builds_from_snippets(self):
        items = [
            {"snippet": "First news item about topic."},
            {"snippet": "Second news item with details."},
            {"snippet": "Third item ignored."},
        ]
        result = resolve._build_context_summary(items)
        self.assertIn("First news item", result)
        self.assertIn("Second news item", result)
        self.assertNotIn("Third item", result)

    def test_truncates_long_text(self):
        items = [{"snippet": "A" * 200}, {"snippet": "B" * 200}]
        result = resolve._build_context_summary(items)
        self.assertLessEqual(len(result), 300)
        self.assertTrue(result.endswith("..."))

    def test_empty_items_returns_empty(self):
        self.assertEqual(resolve._build_context_summary([]), "")

    def test_items_with_empty_snippets(self):
        items = [{"snippet": ""}, {"snippet": ""}]
        self.assertEqual(resolve._build_context_summary(items), "")


class TestAutoResolve(unittest.TestCase):
    def test_no_backend_returns_empty(self):
        result = resolve.auto_resolve("test topic", {})
        self.assertEqual(result["x_handle"], "")
        self.assertEqual(result["github_user"], "")
        self.assertEqual(result["context"], "")
        self.assertEqual(result["searches_run"], 0)

    @patch("lib.resolve.grounding.web_search")
    def test_full_resolve(self, mock_search):
        def side_effect(query, date_range, config):
            if "news" in query:
                return [{"snippet": "Major tech breakthrough announced this week."}], {"label": "brave"}
            if "handle" in query:
                return [
                    {"title": "TechCo on X", "snippet": "@TechCo", "url": "https://x.com/TechCo"},
                ], {"label": "brave"}
            if "github" in query:
                return [{"title": "", "snippet": "", "url": "https://github.com/techco/"}], {}
            return [], {}

        mock_search.side_effect = side_effect
        result = resolve.auto_resolve("tech", {"BRAVE_API_KEY": "fake"})

        self.assertEqual(result["x_handle"], "techco")
        self.assertIn("breakthrough", result["context"])
        self.assertEqual(result["searches_run"], 3)
        self.assertEqual(mock_search.call_count, 3)

    @patch("lib.resolve.grounding.web_search")
    def test_search_failure_graceful(self, mock_search):
        mock_search.side_effect = RuntimeError("API error")
        result = resolve.auto_resolve("test", {"BRAVE_API_KEY": "fake"})
        self.assertEqual(result["x_handle"], "")
        self.assertEqual(result["context"], "")
        self.assertEqual(result["searches_run"], 0)

    @patch("lib.resolve.grounding.web_search")
    def test_partial_failure(self, mock_search):
        def side_effect(query, date_range, config):
            if "news" in query:
                raise RuntimeError("Timeout")
            if "handle" in query:
                return [
                    {"title": "TechCo", "snippet": "", "url": "https://x.com/techco"}
                ], {}
            return [], {}

        mock_search.side_effect = side_effect
        result = resolve.auto_resolve("cooking", {"EXA_API_KEY": "fake"})
        # News search failed, so context is empty
        self.assertEqual(result["context"], "")
        # 2 of 3 succeeded (handle + github; news failed)
        self.assertEqual(result["searches_run"], 2)


if __name__ == "__main__":
    unittest.main()
