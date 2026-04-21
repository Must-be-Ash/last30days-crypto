"""LLM-first query planning with deterministic guards for risky queries."""

from __future__ import annotations

import json
import re

from . import http, providers, query, schema

ALLOWED_INTENTS = {
    "factual",
    "product",
    "concept",
    "opinion",
    "how_to",
    "comparison",
    "breaking_news",
    "prediction",
    # Crypto-tailored intents — added Phase 4.3.
    # `crypto_data` = quantitative questions (price, OI, funding, holders,
    # volume, Galaxy Score). Routes heavily to coingecko/messari/lunarcrush.
    # `crypto_qual` = narrative/sentiment/launch questions. X-first with
    # LunarCrush as a heavy supporting source.
    "crypto_data",
    "crypto_qual",
}
ALLOWED_CLUSTER_MODES = {"none", "story", "workflow", "market", "debate"}
# Crypto-tailored: X is the spine; web/perplexity is the secondary qualitative
# layer; HN/GitHub/Reddit are tertiary. coingecko/messari/lunarcrush carry
# market & social-quant data and are appended only when the planner detects
# a token mention (Phase 4.3).
_CRYPTO_DATA_SOURCES = ["coingecko", "messari", "lunarcrush"]
_BASE_PRIORITY = ["x", "grounding", "perplexity", "hackernews", "reddit", "github"]
_PREDICTION_PRIORITY = ["x", "grounding"] + _CRYPTO_DATA_SOURCES + ["perplexity", "reddit", "hackernews"]
# Crypto_data: market/onchain/social-quant questions. Crypto APIs first,
# then X for chatter context, then web for news/docs.
_CRYPTO_DATA_PRIORITY = _CRYPTO_DATA_SOURCES + ["x", "grounding", "perplexity", "reddit"]
# Crypto_qual: narrative/sentiment/launch questions. X-first, LunarCrush
# heavy for sentiment, then web/perplexity for grounded news, then Messari
# for project profile, then Reddit.
_CRYPTO_QUAL_PRIORITY = ["x", "lunarcrush", "grounding", "perplexity", "messari", "reddit"]

QUICK_SOURCE_PRIORITY = {
    "factual": _BASE_PRIORITY,
    "product": _BASE_PRIORITY,
    "concept": _BASE_PRIORITY,
    "opinion": _BASE_PRIORITY,
    "how_to": _BASE_PRIORITY,
    "comparison": _BASE_PRIORITY,
    "breaking_news": _BASE_PRIORITY,
    "prediction": _PREDICTION_PRIORITY,
    "crypto_data": _CRYPTO_DATA_PRIORITY,
    "crypto_qual": _CRYPTO_QUAL_PRIORITY,
}
SOURCE_PRIORITY = {
    "factual": _BASE_PRIORITY,
    "product": _BASE_PRIORITY,
    "concept": _BASE_PRIORITY,
    "opinion": _BASE_PRIORITY,
    "how_to": _BASE_PRIORITY,
    "comparison": _BASE_PRIORITY,
    "breaking_news": _BASE_PRIORITY,
    "prediction": _PREDICTION_PRIORITY,
    "crypto_data": _CRYPTO_DATA_PRIORITY,
    "crypto_qual": _CRYPTO_QUAL_PRIORITY,
}
SOURCE_LIMITS = {
    "quick": {
        "factual": 2,
        "product": 2,
        "concept": 2,
        "opinion": 2,
        "how_to": 2,
        "comparison": 2,
        "breaking_news": 2,
        "prediction": 2,
        "crypto_data": 3,  # crypto-data quick still hits all three crypto APIs
        "crypto_qual": 3,  # X + LunarCrush + grounding minimum
    },
    # "default" intentionally absent: all available sources are searched
    # at default depth. Fusion and reranking handle quality. quick mode
    # uses tight budgets above for latency.
}
INTENT_SOURCE_EXCLUSIONS: dict[str, set[str]] = {}
SOURCE_CAPABILITIES = {
    "reddit": {"discussion", "social"},
    "x": {"discussion", "social"},
    "hackernews": {"discussion", "link"},
    "github": {"discussion", "link"},
    "grounding": {"web", "reference", "link"},
    "perplexity": {"web", "reference", "analysis"},
    "coingecko": {"crypto_data", "market"},
    "messari": {"crypto_data", "market", "onchain"},
    "lunarcrush": {"crypto_data", "social"},
}
DEFAULT_INTENT_CAPABILITIES = {
    "comparison": {"discussion", "web", "reference", "social", "link"},
    "how_to": {"discussion", "web", "reference", "link"},
}

def plan_query(
    *,
    topic: str,
    available_sources: list[str],
    requested_sources: list[str] | None,
    depth: str,
    provider: providers.ReasoningClient | None,
    model: str | None,
    context: str = "",
    tokens: list[schema.TokenRef] | None = None,
) -> schema.QueryPlan:
    """Create a query plan. Comparison queries with extractable entities use a
    deterministic plan; other intents prefer the configured reasoning provider.

    If ``tokens`` is non-empty, the crypto-data sources (``coingecko``,
    ``messari``, ``lunarcrush``) are appended to ``available_sources`` so the
    planner can route them into subqueries. The tokens themselves are
    attached to the returned ``QueryPlan`` for downstream enrichment.
    """
    available_sources = _expand_for_crypto_tokens(available_sources, tokens)
    if _should_force_deterministic_plan(topic):
        plan = _fallback_plan(
            topic,
            available_sources,
            requested_sources,
            depth,
            note="deterministic-comparison-plan",
        )
        plan.tokens = list(tokens or [])
        return plan
    prompt = _build_prompt(topic, available_sources, requested_sources, depth)
    if context:
        prompt += f"\n\nCurrent context (from web search): {context}"
    if provider and model:
        try:
            raw = provider.generate_json(model, prompt)
            plan = _sanitize_plan(raw, topic, available_sources, requested_sources, depth)
            if plan.subqueries:
                plan.tokens = list(tokens or [])
                return plan
        except (ValueError, KeyError, json.JSONDecodeError, OSError, http.HTTPError) as exc:
            import sys
            print(f"[Planner] LLM planning failed, using deterministic fallback: {type(exc).__name__}: {exc}", file=sys.stderr)
            plan = _fallback_plan(
                topic, available_sources, requested_sources, depth,
                note=f"fallback-plan (LLM error: {type(exc).__name__})",
            )
            plan.tokens = list(tokens or [])
            return plan
    plan = _fallback_plan(topic, available_sources, requested_sources, depth)
    plan.tokens = list(tokens or [])
    return plan


def _expand_for_crypto_tokens(
    available_sources: list[str],
    tokens: list[schema.TokenRef] | None,
) -> list[str]:
    """When tokens are present, surface the crypto-data sources so the
    planner picks them. We only append sources that the caller listed as
    available — pipeline.available_sources(config) gates on the actual key
    presence."""
    if not tokens:
        return available_sources
    return list(available_sources)  # Already includes crypto sources iff keys
                                     # were configured (gated upstream).


def _build_prompt(
    topic: str,
    available_sources: list[str],
    requested_sources: list[str] | None,
    depth: str,
) -> str:
    requested = ", ".join(requested_sources or ["auto"])
    available = ", ".join(available_sources)
    return f"""
You are the query planner for a live last-30-days CRYPTO research pipeline.

Topic: {topic}
Depth: {depth}
Available sources: {available}
Requested sources: {requested}

Return JSON only with this shape:
{{
  "intent": "factual|product|concept|opinion|how_to|comparison|breaking_news|prediction|crypto_data|crypto_qual",
  "freshness_mode": "strict_recent|balanced_recent|evergreen_ok",
  "cluster_mode": "none|story|workflow|market|debate",
  "source_weights": {{"source_name": 0.0}},
  "subqueries": [
    {{
      "label": "short label",
      "search_query": "keyword style query for search APIs",
      "ranking_query": "natural language rewrite for reranking",
      "sources": ["x", "grounding", "lunarcrush"],
      "weight": 1.0
    }}
  ],
  "notes": ["optional short notes"]
}}

Crypto-specific source vocabulary:
- ``coingecko``: market data — price, market cap, volume, ATH, exchange listings, community size.
- ``messari``: on-chain & derivatives — open interest, funding rate, futures volume, volatility, project profile.
- ``lunarcrush``: social-quant — Galaxy Score, AltRank, sentiment %, top influencers, AI bull/bear themes.
- ``x``: primary qualitative source — what crypto Twitter is actually saying right now.
- ``grounding`` / ``perplexity``: web search for news, blog posts, governance docs, whitepapers.
- ``reddit``, ``hackernews``, ``github``: tertiary qualitative + dev-activity context.

Intent rules:
- ``crypto_data`` for quantitative questions (price, holders, OI, funding, TVL, volume, on-chain metrics, Galaxy Score). Route heavily to coingecko/messari/lunarcrush.
- ``crypto_qual`` for narrative/sentiment/launch/influencer questions (memecoin narratives, sentiment shifts, top accounts, airdrop hype, ecosystem launches). X-first, LunarCrush heavy.
- Other intents (factual/comparison/breaking_news/etc.) when the topic is generic crypto research without a clear quant or narrative focus.

General rules:
- emit 1 to 4 subqueries
- every subquery must include both search_query and ranking_query
- sources must be drawn from Available sources only
- use cluster_mode=market for crypto_data and prediction; story for crypto_qual and breaking_news; debate for comparison/opinion; workflow for how_to
- use strict_recent for breaking news, predictions, and BOTH crypto intents
- search_query should be concise and keyword-heavy
- ranking_query should read like a natural-language question
- preserve exact proper nouns, ticker symbols, and entity strings from the topic
- NEVER include temporal phrases in search_query: no 'last 30 days', 'recent', month names, year numbers
- NEVER include meta-research phrases: no 'news', 'updates', 'public appearances', 'latest developments'
- search_query should match how content is TITLED on platforms
""".strip()


def _sanitize_plan(
    raw: dict,
    topic: str,
    available_sources: list[str],
    requested_sources: list[str] | None,
    depth: str,
) -> schema.QueryPlan:
    intent_hint = str(raw.get("intent") or _infer_intent(topic)).strip()
    if intent_hint not in ALLOWED_INTENTS:
        intent_hint = _infer_intent(topic)
    requested = set(requested_sources or [])
    available = set(available_sources)
    eligible_sources = [
        source for source in available_sources
        if (not requested or source in requested)
    ]
    source_weights = {
        source: float(weight)
        for source, weight in (raw.get("source_weights") or {}).items()
        if source in available
    }
    if requested:
        source_weights = {source: weight for source, weight in source_weights.items() if source in requested}
    if not source_weights:
        source_weights = _default_source_weights(_infer_intent(topic), eligible_sources)
    # Ensure all eligible sources are available for subqueries. The LLM may
    # assign high weights to its preferred sources, but omitted sources still
    # participate with base weight so retrieval can overfetch and let fusion
    # decide quality.
    for source in eligible_sources:
        source_weights.setdefault(source, 1.0)
    if intent_hint in DEFAULT_INTENT_CAPABILITIES and depth != "quick":
        for source in _default_sources_for_intent(intent_hint, eligible_sources):
            source_weights.setdefault(source, 1.0)
    source_weights = _normalize_weights(source_weights)

    subqueries: list[schema.SubQuery] = []
    for index, subquery in enumerate((raw.get("subqueries") or [])[:_max_subqueries(intent_hint)], start=1):
        if not isinstance(subquery, dict):
            continue
        sources = [source for source in subquery.get("sources") or [] if source in source_weights]
        if requested:
            sources = [source for source in sources if source in requested]
        if not sources:
            sources = list(source_weights)
        search_query = str(subquery.get("search_query") or "").strip()
        ranking_query = str(subquery.get("ranking_query") or "").strip()
        if not search_query or not ranking_query:
            continue
        subqueries.append(
            schema.SubQuery(
                label=str(subquery.get("label") or f"q{index}").strip() or f"q{index}",
                search_query=search_query,
                ranking_query=ranking_query,
                sources=sources,
                weight=max(0.05, float(subquery.get("weight") or 1.0)),
            )
        )
    if depth == "quick" and subqueries:
        subqueries = subqueries[:1]
    if not subqueries:
        return _fallback_plan(topic, available_sources, requested_sources, depth)

    intent = intent_hint
    freshness_mode = str(raw.get("freshness_mode") or _default_freshness(intent)).strip()
    if intent == "how_to":
        freshness_mode = "evergreen_ok"
    cluster_mode = str(raw.get("cluster_mode") or _default_cluster_mode(intent)).strip()
    if cluster_mode not in ALLOWED_CLUSTER_MODES:
        cluster_mode = _default_cluster_mode(intent)

    return schema.QueryPlan(
        intent=intent,
        freshness_mode=freshness_mode,
        cluster_mode=cluster_mode,
        raw_topic=topic,
        subqueries=_normalize_subquery_weights(_trim_subqueries_for_depth(subqueries, intent, depth, eligible_sources)),
        source_weights=source_weights,
        notes=[str(note).strip() for note in raw.get("notes") or [] if str(note).strip()],
    )


def _normalize_subquery_weights(subqueries: list[schema.SubQuery]) -> list[schema.SubQuery]:
    total = sum(subquery.weight for subquery in subqueries) or 1.0
    return [
        schema.SubQuery(
            label=subquery.label,
            search_query=subquery.search_query,
            ranking_query=subquery.ranking_query,
            sources=subquery.sources,
            weight=subquery.weight / total,
        )
        for subquery in subqueries
    ]


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(weight, 0.0) for weight in weights.values()) or 1.0
    return {
        source: max(weight, 0.0) / total
        for source, weight in weights.items()
    }


def _trim_subqueries_for_depth(
    subqueries: list[schema.SubQuery],
    intent: str,
    depth: str,
    available_sources: list[str],
) -> list[schema.SubQuery]:
    # At non-quick depth, expand sources: use capability routing for intents
    # that define it, or all available sources otherwise. The LLM planner may
    # assign narrow source lists; we override to let fusion decide quality.
    if depth != "quick":
        expanded_sources = _default_sources_for_intent(intent, available_sources)
        return [
            schema.SubQuery(
                label=subquery.label,
                search_query=subquery.search_query,
                ranking_query=subquery.ranking_query,
                sources=expanded_sources,
                weight=subquery.weight,
            )
            for subquery in subqueries
        ]
    limits = SOURCE_LIMITS.get(depth)
    if not limits:
        return subqueries
    priority_table = QUICK_SOURCE_PRIORITY if depth == "quick" else SOURCE_PRIORITY
    priority = priority_table.get(intent, priority_table["breaking_news"])
    limit = limits.get(intent, 3)
    ranked_sources = [source for source in priority if source in available_sources]
    if not ranked_sources:
        ranked_sources = list(available_sources)
    trimmed = []
    for subquery in subqueries:
        if depth in {"quick", "default"}:
            preferred_sources = ranked_sources[:limit]
        else:
            preferred_sources = [source for source in ranked_sources if source in subquery.sources][:limit]
            if len(preferred_sources) < limit:
                for source in ranked_sources:
                    if source in preferred_sources:
                        continue
                    preferred_sources.append(source)
                    if len(preferred_sources) >= limit:
                        break
        trimmed.append(
            schema.SubQuery(
                label=subquery.label,
                search_query=subquery.search_query,
                ranking_query=subquery.ranking_query,
                sources=preferred_sources,
                weight=subquery.weight,
            )
        )
    return trimmed


def _fallback_plan(
    topic: str,
    available_sources: list[str],
    requested_sources: list[str] | None,
    depth: str,
    note: str = "fallback-plan",
) -> schema.QueryPlan:
    intent = _infer_intent(topic)
    allowed_sources = requested_sources or available_sources
    source_weights = _default_source_weights(intent, allowed_sources)
    core = query.extract_core_subject(topic, max_words=6, strip_suffixes=True)
    base_search = _keyword_query(topic, core)
    base_ranking = _ranking_query(topic, core)

    subqueries = [schema.SubQuery(
        label="primary",
        search_query=base_search,
        ranking_query=base_ranking,
        sources=list(source_weights),
        weight=1.0,
    )]

    if depth != "quick" and intent == "comparison":
        entities = _comparison_entities(topic)
        if entities:
            for index, entity in enumerate(entities, start=1):
                subqueries.append(
                    schema.SubQuery(
                        label=f"entity-{index}",
                        search_query=entity,
                        ranking_query=f"What recent evidence from the last 30 days is most relevant to {entity} in the comparison '{topic}'?",
                        sources=list(source_weights),
                        weight=0.65,
                    )
                )
    elif depth != "quick" and intent == "prediction":
        subqueries.append(
            schema.SubQuery(
                label="odds",
                search_query=f"{base_search} odds forecast",
                ranking_query=f"What are the current odds, forecasts, or market signals about {topic}?",
                sources=[source for source in source_weights if source in {"messari", "lunarcrush", "coingecko", "grounding", "x", "reddit"}] or list(source_weights),
                weight=0.7,
            )
        )
    elif depth != "quick" and intent == "breaking_news":
        subqueries.append(
            schema.SubQuery(
                label="reaction",
                search_query=f"{base_search} reaction update",
                ranking_query=f"What new reactions or follow-up reporting from the last 30 days matter for {topic}?",
                sources=[source for source in source_weights if source in {"x", "reddit", "grounding", "hackernews"}] or list(source_weights),
                weight=0.7,
            )
        )

    return schema.QueryPlan(
        intent=intent,
        freshness_mode=_default_freshness(intent),
        cluster_mode=_default_cluster_mode(intent),
        raw_topic=topic,
        subqueries=_normalize_subquery_weights(
            _trim_subqueries_for_depth(subqueries[:_max_subqueries(intent)], intent, depth, list(source_weights))
        ),
        source_weights=_normalize_weights(source_weights),
        notes=[note],
    )


def _infer_intent(topic: str) -> str:
    text = topic.lower().strip()
    # Crypto-data signals — quantitative crypto questions go straight to
    # the data APIs.
    if re.search(r"\b(price|market cap|marketcap|fdv|volume|holders?|whales?|funding rate|open interest|tvl|liquidity|on[- ]?chain|galaxy score|altrank|market share|order book|spread)\b", text):
        return "crypto_data"
    # Crypto-qual signals — narrative/sentiment/launch questions.
    if re.search(r"\b(memecoin|narrative|sentiment|sentiment|airdrop|launch|listing|hype|community|influencers?|twitter sentiment|sector|thesis|alpha|narratives?)\b", text):
        return "crypto_qual"
    if re.search(r"\b(vs|versus|compare|compared to|difference between)\b", text):
        return "comparison"
    # Slash-separated proper nouns: "React/Vue/Svelte" (not URLs, not acronyms like CI/CD or I/O)
    if not re.search(r"https?://", topic) and re.search(r"\b[A-Z][a-z]{2,}(?:/[A-Z][a-z]{2,})+\b", topic):
        return "comparison"
    if re.search(r"\b(odds|predict|prediction|forecast|chance|probability|will .* win)\b", text):
        return "prediction"
    if re.search(r"\b(how to|tutorial|guide|setup|step by step|deploy|install)\b", text):
        return "how_to"
    if re.search(r"\b(what is|what are|who is|who acquired|when did|parameter count|release date)\b", text):
        return "factual"
    if re.search(r"\b(thoughts on|worth it|should i|opinion|review)\b", text):
        return "opinion"
    if re.search(r"\b(latest|news|announced|just shipped|launched|released|update)\b", text):
        return "breaking_news"
    if re.search(r"\b(pricing|feature|features|best .* for|top .* for)\b", text):
        return "product"
    if re.search(r"\b(explain|concept|protocol|architecture|what does)\b", text):
        return "concept"
    if re.search(r"\b(tournament|championship|playoffs|march madness|world cup|olympics|super bowl|final four|ceremony|awards|keynote)\b", text):
        return "breaking_news"
    return "breaking_news"


def _default_freshness(intent: str) -> str:
    if intent in {"breaking_news", "prediction", "crypto_data", "crypto_qual"}:
        return "strict_recent"
    if intent in {"concept", "how_to"}:
        return "evergreen_ok"
    return "balanced_recent"


def _default_cluster_mode(intent: str) -> str:
    return {
        "breaking_news": "story",
        "comparison": "debate",
        "opinion": "debate",
        "prediction": "market",
        "how_to": "workflow",
        "factual": "none",
        "product": "none",
        "concept": "none",
        "crypto_data": "market",
        "crypto_qual": "story",
    }.get(intent, "none")


def _default_source_weights(intent: str, sources: list[str]) -> dict[str, float]:
    # Crypto-tailored: X is the spine across most intents. Crypto-data /
    # crypto-qual intents tilt heavily toward the data APIs.
    base = {source: 1.0 for source in sources}
    for source, bonus in {"x": 1.5, "grounding": 0.6}.items():
        if source in base:
            base[source] += bonus
    if intent == "prediction":
        for source, bonus in {"x": 0.8, "messari": 1.5, "lunarcrush": 1.5, "coingecko": 1.0}.items():
            if source in base:
                base[source] += bonus
    elif intent == "breaking_news":
        for source, bonus in {"x": 1.0, "reddit": 0.6, "hackernews": 0.4}.items():
            if source in base:
                base[source] += bonus
    elif intent == "how_to":
        for source, bonus in {"hackernews": 0.8, "github": 0.5}.items():
            if source in base:
                base[source] += bonus
    elif intent == "factual":
        for source, bonus in {"reddit": 0.4, "grounding": 0.4}.items():
            if source in base:
                base[source] += bonus
    elif intent == "crypto_data":
        # Quantitative crypto: data APIs lead, X provides chatter context.
        for source, bonus in {"coingecko": 2.0, "messari": 2.0, "lunarcrush": 1.5, "grounding": 0.4}.items():
            if source in base:
                base[source] += bonus
    elif intent == "crypto_qual":
        # Narrative/sentiment: X-first, LunarCrush heavy for sentiment data,
        # web second for grounded news, Messari lightly for project profile.
        for source, bonus in {"x": 1.0, "lunarcrush": 1.8, "messari": 0.8, "grounding": 0.4}.items():
            if source in base:
                base[source] += bonus
    return base


def _keyword_query(topic: str, core: str) -> str:
    compounds = query.extract_compound_terms(topic)
    quoted = " ".join(f"\"{term}\"" for term in compounds[:2])
    keywords = [quoted.strip(), core.strip() or topic.strip()]
    return " ".join(part for part in keywords if part).strip()


def _ranking_query(topic: str, core: str) -> str:
    if topic.strip().endswith("?"):
        return topic.strip()
    if core and core.lower() != topic.lower():
        return f"What recent evidence from the last 30 days is most relevant to {topic}, especially about {core}?"
    return f"What recent evidence from the last 30 days is most relevant to {topic}?"


_TRAILING_CONTEXT = re.compile(
    r"\s+\b(?:for|in|on|at|to|with|about|from|by|during|since|after|before|using|via)\b.*$",
    re.I,
)


def _comparison_entities(topic: str) -> list[str]:
    # "difference between X and Y" -> "X vs Y" (replace "and" only in this context)
    normalized = re.sub(
        r"\bdifference between\s+(.+?)\s+and\s+",
        r"\1 vs ",
        topic,
        flags=re.I,
    )
    normalized = re.sub(r"\b(compared to)\b", " vs ", normalized, flags=re.I)
    parts = [
        part.strip(" \t\r\n?.,:;!()[]{}\"'")
        for part in re.split(r"\bvs\.?\b|\bversus\b|/", normalized, flags=re.I)
        if part.strip(" \t\r\n?.,:;!()[]{}\"'")
    ]
    # Strip trailing context from parts ("Svelte for frontend in 2026" -> "Svelte")
    if len(parts) >= 2:
        parts = [_TRAILING_CONTEXT.sub("", part).strip() or part for part in parts]
        deduped = []
        for part in parts:
            if part and part not in deduped:
                deduped.append(part)
        return deduped[:_max_subqueries("comparison")]
    return []


def _should_force_deterministic_plan(topic: str) -> bool:
    return _infer_intent(topic) == "comparison" and len(_comparison_entities(topic)) >= 2


def _max_subqueries(intent: str) -> int:
    if intent == "comparison":
        return 4
    if intent in {"factual", "concept"}:
        return 2
    return 3


def _default_sources_for_intent(intent: str, available_sources: list[str]) -> list[str]:
    if intent == "how_to":
        sources = _how_to_sources(available_sources)
    else:
        target_capabilities = DEFAULT_INTENT_CAPABILITIES.get(intent)
        if not target_capabilities:
            sources = list(available_sources)
        else:
            matched = [
                source
                for source in available_sources
                if SOURCE_CAPABILITIES.get(source, set()) & target_capabilities
            ]
            sources = matched or list(available_sources)
    excluded = INTENT_SOURCE_EXCLUSIONS.get(intent, set())
    if excluded:
        filtered = [s for s in sources if s not in excluded]
        return filtered or sources
    return sources


def _how_to_sources(available_sources: list[str]) -> list[str]:
    """Pick one source per role: web/reference, video (prefer longform), discussion."""
    selected: set[str] = set()
    has_video = False
    # Order matters: web first, then longform video, generic video, discussion.
    role_capabilities = [
        {"web", "reference"},
        {"video_longform"},
        {"video"},
        {"discussion"},
    ]
    for role in role_capabilities:
        is_video_role = role & {"video", "video_longform"}
        if is_video_role and has_video:
            continue
        for source in available_sources:
            if source in selected:
                continue
            if SOURCE_CAPABILITIES.get(source, set()) & role:
                selected.add(source)
                if is_video_role:
                    has_video = True
                break
    # After core role-based selection, include remaining sources with any
    # how_to-relevant capability (video, discussion, web, reference, link).
    how_to_caps = DEFAULT_INTENT_CAPABILITIES.get("how_to", set())
    for source in available_sources:
        if source not in selected and SOURCE_CAPABILITIES.get(source, set()) & how_to_caps:
            selected.add(source)
    if not selected:
        return list(available_sources)
    return [source for source in available_sources if source in selected]
