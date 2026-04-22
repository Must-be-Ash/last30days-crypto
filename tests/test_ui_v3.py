# ruff: noqa: E402
import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import ui


class UiV3Tests(unittest.TestCase):
    def test_show_diagnostic_banner_uses_v3_source_model(self):
        diag = {
            "available_sources": ["grounding"],
            "providers": {"google": True, "openai": False, "xai": False},
            "x_backend": None,
            "bird_installed": True,
            "bird_authenticated": False,
            "bird_username": None,
            "native_web_backend": "brave",
        }
        with mock.patch.object(ui, "IS_TTY", False):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                ui.show_diagnostic_banner(diag)
        output = stderr.getvalue()
        self.assertIn("/last30days-crypto", output)
        self.assertIn("X/Twitter", output)
        self.assertIn("AUTH_TOKEN", output)
        self.assertIn("XAI_API_KEY", output)
        self.assertIn("brave API", output)
        self.assertIn("CoinGecko", output)
        self.assertIn("Messari", output)
        self.assertIn("LunarCrush", output)
        self.assertIn("~/.config/last30days-crypto/.env", output)

    def test_build_nux_message_mentions_kept_source_status(self):
        text = ui._build_nux_message(
            {"available_sources": ["x", "grounding"]}
        )
        self.assertIn("X ✓", text)
        self.assertIn("Web ✓", text)
        self.assertIn("CoinGecko ✗", text)

    def test_show_complete_uses_actual_sources_for_source_restricted_runs(self):
        with mock.patch.object(ui, "IS_TTY", False):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                progress = ui.ProgressDisplay("test topic", show_banner=False)
                progress.show_complete(
                    source_counts={"grounding": 2},
                    display_sources=["grounding"],
                )
        output = stderr.getvalue()
        self.assertIn("Web: 2 results", output)
        self.assertNotIn("X:", output)

    def test_show_complete_supports_crypto_sources(self):
        with mock.patch.object(ui, "IS_TTY", False):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                progress = ui.ProgressDisplay("test topic", show_banner=False)
                progress.show_complete(
                    source_counts={
                        "x": 3,
                        "coingecko": 1,
                        "lunarcrush": 2,
                    },
                    display_sources=["x", "coingecko", "lunarcrush"],
                )
        output = stderr.getvalue()
        self.assertIn("X: 3 posts", output)
        self.assertIn("CoinGecko: 1 bundle", output)
        self.assertIn("LunarCrush: 2 bundles", output)


if __name__ == "__main__":
    unittest.main()
