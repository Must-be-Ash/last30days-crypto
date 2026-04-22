import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import planner


class PlannerV3Tests(unittest.TestCase):
    def test_default_how_to_expands_past_llm_narrow_source_weights(self):
        raw = {
            "intent": "how_to",
            "freshness_mode": "balanced_recent",
            "cluster_mode": "workflow",
            "source_weights": {"github": 0.7},
            "subqueries": [
                {
                    "label": "primary",
                    "search_query": "deploy app to Fly.io guide",
                    "ranking_query": "How do I deploy an app to Fly.io?",
                    "sources": ["github"],
                    "weight": 1.0,
                }
            ],
        }
        plan = planner._sanitize_plan(
            raw,
            "how to deploy on Fly.io",
            ["x", "github", "grounding"],
            None,
            "default",
        )
        sources = plan.subqueries[0].sources
        # how_to capability routing prefers GitHub for technical workflow topics
        self.assertIn("github", sources)
        self.assertIn("github", plan.source_weights)
        self.assertEqual("evergreen_ok", plan.freshness_mode)

    def test_comparison_uses_deterministic_plan_and_preserves_entities(self):
        plan = planner.plan_query(
            topic="openclaw vs nanoclaw vs ironclaw",
            available_sources=["x", "grounding", "github"],
            requested_sources=None,
            depth="default",
            provider=object(),
            model="ignored",
        )
        self.assertEqual("comparison", plan.intent)
        self.assertEqual(["deterministic-comparison-plan"], plan.notes)
        self.assertEqual(4, len(plan.subqueries))
        joined_queries = "\n".join(subquery.search_query for subquery in plan.subqueries).lower()
        self.assertIn("openclaw", joined_queries)
        self.assertIn("nanoclaw", joined_queries)
        self.assertIn("ironclaw", joined_queries)

    def test_fallback_plan_emits_dual_query_fields(self):
        plan = planner.plan_query(
            topic="codex vs claude code",
            available_sources=["x", "grounding"],
            requested_sources=None,
            depth="default",
            provider=None,
            model=None,
        )
        self.assertEqual("comparison", plan.intent)
        self.assertGreaterEqual(len(plan.subqueries), 2)
        for subquery in plan.subqueries:
            self.assertTrue(subquery.search_query)
            self.assertTrue(subquery.ranking_query)

    def test_factual_topic_uses_no_cluster_mode(self):
        plan = planner.plan_query(
            topic="what is the parameter count of claude code",
            available_sources=["x", "grounding"],
            requested_sources=None,
            depth="default",
            provider=None,
            model=None,
        )
        self.assertEqual("factual", plan.intent)
        self.assertEqual("none", plan.cluster_mode)

    def test_quick_mode_collapses_fallback_to_single_subquery(self):
        plan = planner.plan_query(
            topic="codex vs claude code",
            available_sources=["x", "grounding"],
            requested_sources=None,
            depth="quick",
            provider=None,
            model=None,
        )
        self.assertEqual("comparison", plan.intent)
        self.assertEqual(1, len(plan.subqueries))
        # X is the primary qualitative source so it leads.
        self.assertEqual("x", plan.subqueries[0].sources[0])

    def test_default_comparison_uses_all_capable_sources(self):
        plan = planner.plan_query(
            topic="codex vs claude code",
            available_sources=["x", "grounding", "github", "coingecko", "messari", "lunarcrush"],
            requested_sources=None,
            depth="default",
            provider=None,
            model=None,
        )
        self.assertEqual("comparison", plan.intent)
        for subquery in plan.subqueries:
            # Default depth should not artificially cap sources
            self.assertGreaterEqual(len(subquery.sources), 3)

    def test_ncaa_tournament_is_breaking_news(self):
        intent = planner._infer_intent("NCAA tournament brackets")
        self.assertEqual("breaking_news", intent)

    def test_march_madness_is_breaking_news(self):
        intent = planner._infer_intent("2026 March Madness")
        self.assertEqual("breaking_news", intent)

    def test_factual_plan_has_at_most_2_subqueries(self):
        plan = planner.plan_query(
            topic="who acquired Wiz",
            available_sources=["x", "grounding"],
            requested_sources=None,
            depth="default",
            provider=None,
            model=None,
        )
        self.assertEqual("factual", plan.intent)
        self.assertLessEqual(len(plan.subqueries), 2)

    def test_x_dominates_qualitative_weight(self):
        """X should get 70-80% of qualitative weight in default settings."""
        plan = planner.plan_query(
            topic="general crypto research",
            available_sources=["x", "grounding", "github"],
            requested_sources=None,
            depth="default",
            provider=None,
            model=None,
        )
        weights = plan.source_weights
        qual_total = weights.get("x", 0) + weights.get("grounding", 0) + weights.get("github", 0)
        x_share = weights.get("x", 0) / qual_total if qual_total else 0
        self.assertGreaterEqual(x_share, 0.65, f"X should be at least 65% of qualitative weight, got {x_share:.2%}")
        self.assertLessEqual(x_share, 0.85, f"X should be at most 85% of qualitative weight, got {x_share:.2%}")


if __name__ == "__main__":
    unittest.main()
