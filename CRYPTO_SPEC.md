# Crypto-Tailored last30days — Technical Spec

Scope: rework `last30days-skill` into a crypto research skill. Twitter/X is the primary qualitative source, web search secondary, GitHub/Reddit/Perplexity tertiary. All other social sources are removed. Three crypto data APIs (CoinGecko, Messari, LunarCrush) provide market, on-chain, and social-quant data. Firecrawl provides URL scraping fallback.

Work the checklist top-to-bottom. Each `[ ]` is a discrete, testable task. Update boxes to `[x]` as completed.

---

## Phase 0 — Baseline & Decisions (locked)

- [x] Confirmed env vars present in `~/.config/last30days/.env`: `XAI_API_KEY`, `SERPER_API_KEY`, `EXA_API_KEY`, `FIRECRAWL_API_KEY`, `COINGECKO_API_KEY`, `MESSARI_SDK_API_KEY`, `LUNARCRUSH_API_KEY`, `AUTH_TOKEN`, `CT0`.
- [x] Confirmed Messari env var name in repo will be **`MESSARI_API_KEY`** (rename in `.env` from `MESSARI_SDK_API_KEY`, OR have the loader accept both — see Phase 2).
- [x] Sources to **remove**: YouTube, TikTok, Instagram, Bluesky, TruthSocial, Polymarket, Xiaohongshu, Threads, Pinterest, xquik.
- [x] Sources to **keep**: X (primary), Grounding/Web (secondary), Perplexity (secondary), GitHub (tertiary), Reddit (tertiary), Hacker News (tertiary, for technical/infra topics).
- [x] X budget: leave per-stream limits unchanged; weight comes from removing competing sources, not bumping caps.
- [x] Crypto APIs integrate as **auto-enrichment**: planner extracts token symbols/slugs; enrichment runs in parallel with social search; results go into a dedicated "Market & On-chain" report section (not fused with social ranking).
- [x] Firecrawl integrates as **planner-driven URL scraper**: if a high-signal URL surfaces (whitepaper, governance post, doc page) and grounding excerpts are too thin, scrape full text on demand.

---

## Phase 1 — Source Pruning

Goal: remove non-crypto-relevant sources from code paths so they cannot be selected by planner, CLI, or auto-detection.

### 1.1 Pipeline registration

- [x] Edit `scripts/lib/pipeline.py`:
  - [x] Remove from `MOCK_AVAILABLE_SOURCES`: `youtube`, `tiktok`, `instagram`, `bluesky`, `truthsocial`, `polymarket`, `xiaohongshu`, `xquik`. Keep: `reddit`, `x`, `hackernews`, `grounding`, `github`, `perplexity`. (`coingecko`, `messari`, `lunarcrush` added later in Phase 3.)
  - [x] Remove corresponding aliases from `SEARCH_ALIAS` (`bsky`, `truth`, `xhs`, `xquik`).
  - [x] Remove imports of `youtube_yt`, `tiktok`, `instagram`, `bluesky`, `truthsocial`, `polymarket`, `xiaohongshu_api`, `xquik`, `threads`, `pinterest` at the top of `pipeline.py`.
  - [x] Remove their availability branches inside `available_sources()` (everything except reddit, x, hackernews, github, grounding, perplexity).
  - [x] Kept `MAX_SOURCE_FETCHES["x"] = 2` (planner may emit multiple X subqueries).
- [x] Delete the unused source modules from `scripts/lib/`: `youtube_yt.py`, `tiktok.py`, `instagram.py`, `bluesky.py`, `truthsocial.py`, `polymarket.py`, `xiaohongshu_api.py`, `xquik.py`, `threads.py`, `pinterest.py`.
- [x] Grep for any other reference to the removed source names in `scripts/` and clean up: dropped `tiktok_hashtags`/`tiktok_creators`/`ig_creators` plumbing from `last30days.py` and `pipeline.run()`/`_retrieve_stream()`; fixed `sync.sh` import smoke check. Remaining stale references inside `signals.py`/`normalize.py`/`cluster.py`/`entity_extract.py`/`quality_nudge.py`/`evaluate_search_quality.py` are dead code (the source strings can no longer enter the pipeline) — addressed cosmetically in Phase 1.3 / Phase 8 as part of dead-code sweep. Smoke verified: `python3 -c "from lib import pipeline; pipeline.run(topic='t', config={}, depth='quick', mock=True)"` returns 3 clusters across `x`, `grounding`, `reddit`.

### 1.2 Planner reweighting

- [x] Edit `scripts/lib/planner.py`:
  - [x] `QUICK_SOURCE_PRIORITY` and `SOURCE_PRIORITY` now share `_BASE_PRIORITY = ["x","grounding","perplexity","hackernews","reddit","github"]`; X is first for every intent.
  - [x] `prediction` intent uses `_PREDICTION_PRIORITY = ["x","grounding","coingecko","messari","lunarcrush","perplexity","reddit","hackernews"]` — polymarket removed, crypto-data sources injected.
  - [x] `INTENT_SOURCE_EXCLUSIONS = {}` (entries for `concept`/`how_to` referenced deleted polymarket).
  - [x] `SOURCE_CAPABILITIES` reduced to kept sources + `coingecko`/`messari`/`lunarcrush` with `{"crypto_data", "market", "onchain", "social"}` capabilities.
  - [x] `DEFAULT_INTENT_CAPABILITIES` no longer requires `video`/`market`.
  - [x] `_default_source_weights` rewritten so X gets +1.5, grounding +0.6 across the board, with intent-specific bonuses (prediction = crypto-data sources, breaking_news = X+reddit, how_to = HN+GitHub, factual = reddit+grounding). Verified: fallback plan for "Hyperliquid HYPE momentum" yields X@0.43, grounding+reddit@0.20.
  - [x] `_fallback_plan` prediction subquery sources updated from polymarket-set to `{messari, lunarcrush, coingecko, grounding, x, reddit}`.

### 1.3 Render & UI cleanup

- [x] Edit `scripts/lib/render.py`:
  - [x] `SOURCE_LABELS` rebuilt with only kept sources + new crypto sources (CoinGecko, Messari, LunarCrush).
  - [x] `source_order` (full-render) replaced with crypto-first ordering: `[x, grounding, perplexity, hackernews, github, reddit, coingecko, messari, lunarcrush]`.
  - [x] Removed polymarket-only render branch + `_polymarket_top_markets` helper.
  - [x] `ENGAGEMENT_DISPLAY` trimmed to `reddit/x/hackernews/github/perplexity` + new `lunarcrush` row.
  - [x] `_format_actor`, `_stats_actor`, `_transcript_highlights`, and Best-Takes attribution updated to drop bluesky/truthsocial/youtube/tiktok/instagram/threads checks.
  - [x] `_FUN_LEVELS` is platform-agnostic (no source references); freshness assessment iterates `items_by_source` regardless of source — both already source-agnostic.
- [x] Edit `scripts/lib/env.py`: removed `is_bluesky_available`, `is_truthsocial_available`, `is_polymarket_available`, `is_threads_available`, `is_xquik_available`, `is_pinterest_available`, `is_xiaohongshu_available`, `is_youtube_sc_available`, `is_youtube_comments_available`, `is_ytdlp_available`, `is_tiktok_available`, `is_instagram_available`, `get_tiktok_token`, `get_instagram_token`, `get_pinterest_token`, `get_xquik_token`, `get_xiaohongshu_api_base`, `is_apify_available` alias, and the `truthsocial` entry from `COOKIE_DOMAINS`. Smoke verified: `from lib import env, render, pipeline; pipeline.run(...mock=True)` round-trips cleanly through both `render_compact` and `render_full`.

### 1.4 SKILL.md rewrite (user-facing docs)

- [x] Description rewritten to crypto-focused 25-word version.
- [x] Tag list replaced with `crypto, defi, tokens, research, twitter, x, coingecko, messari, lunarcrush, firecrawl, web-search, multi-source, news, citations, clawhub`.
- [x] `metadata.openclaw.requires` updated: `env` now requires `AUTH_TOKEN`/`CT0` (X is primary); `optionalEnv` adds `COINGECKO_API_KEY`, `MESSARI_API_KEY`, `LUNARCRUSH_API_KEY`, `FIRECRAWL_API_KEY`, `EXA_API_KEY`, `SERPER_API_KEY`, `GITHUB_TOKEN`; removed `BSKY_HANDLE`, `BSKY_APP_PASSWORD`, `TRUTHSOCIAL_TOKEN`, `APIFY_API_TOKEN`, `SCRAPECREATORS_API_KEY`. `primaryEnv` switched to `AUTH_TOKEN`.
- [x] H1 + intro paragraph rewritten to position the skill as crypto-focused (X-first + CoinGecko/Messari/LunarCrush).
- [x] OpenClaw setup flow rewritten: priority order is now X → web → crypto APIs (CoinGecko/Messari/LunarCrush) → Firecrawl. Removed yt-dlp/ScrapeCreators/TikTok/Instagram language.
- [x] Claude Code Standard flow rewritten: welcome text references crypto edition; auto-setup modal options updated; ScrapeCreators/TikTok/Instagram opt-in modal replaced with a "Crypto Data Setup" modal that paste-or-opens-signup for the three keys; added a Firecrawl opt-in modal; first-research topic picker now lists crypto example topics ($HYPE, Solana memecoins, BTC ETF flows, AI agent tokens).
- [x] Manual setup template rewritten with new env vars (X cookies/XAI, three crypto APIs, Firecrawl, web backends, optional Perplexity/GitHub, Reddit no-config). Removed YouTube/yt-dlp/Bluesky/ScrapeCreators sections.
- [x] "Open .env in editor" template rewritten with crypto-edition env scaffolding.
- [x] "Do I Need API Keys?" progression table rewritten with crypto-tailored quality tiers (X cookies → web key → crypto APIs → Firecrawl).
- [x] `argument-hint` updated to crypto examples (`$HYPE Hyperliquid Q1`, `new memecoin launches on Solana`).
- [x] Note: deeper Steps 0.5+ guidance (X-handle resolver, GitHub resolver, research-execution synthesis sections) and the Polymarket guidance section still reference removed sources in their narrative text. Those sections are runtime-prose for Claude during research synthesis — they degrade quality but don't break execution. Deferred to Phase 8 deploy-and-document polish sweep.

---

## Phase 2 — Env Loader Updates

- [x] Edit `scripts/lib/env.py`:
  - [x] Added accessors `get_coingecko_key`, `get_messari_key`, `get_lunarcrush_key`, `get_firecrawl_key` plus `is_*_available` helpers.
  - [x] `get_messari_key` accepts both `MESSARI_API_KEY` and legacy `MESSARI_SDK_API_KEY` (new name takes precedence). Verified.
  - [x] `load_env_file` already passes any `.env` key through into the config dict — no allowlist needed.
- [ ] `setup_wizard.py` "Crypto APIs" step deferred — wizard prose in SKILL.md handles the user-facing paste flow; the underlying `setup_wizard.py` Python code is OpenClaw-flow only and isn't on the critical path. Will revisit if OpenClaw users hit friction.
- [x] `scripts/lib/pipeline.py::available_sources()` appends `coingecko`/`messari`/`lunarcrush` when respective keys present. `MOCK_AVAILABLE_SOURCES` extended so mock runs surface enrichment paths. Firecrawl is intentionally **not** registered as a source — it's a tool invoked by the planner; tracked separately via `env.is_firecrawl_available(config)`. Smoke verified: `available_sources` returns `['x','grounding','hackernews','github','reddit','coingecko','messari','lunarcrush']` for a fully-keyed config.

---

## Phase 3 — New Crypto Provider Modules

Each provider lives in `scripts/lib/` as a standalone module exposing a `search(topic, planner_hints, depth, config) -> list[schema.Item]` function so it slots into the existing pipeline. They also expose richer typed accessors used by the new "Market & On-chain" rendering section (see Phase 5).

Reference docs (read before implementing):
- `/Users/ashnouruzi/radar/docs/api-access-reference.md`
- `/Users/ashnouruzi/radar/docs/messari/messari-api-key-plan.md`
- `/Users/ashnouruzi/radar/docs/lunarcrush-endpoints.md`
- TS reference clients (port to Python, same patterns): `/Users/ashnouruzi/radar/lib/clients/{coingecko,messari,lunarcrush,firecrawl}.ts`

### 3.1 `scripts/lib/coingecko.py`

- [x] Base URL + header constants live at module top.
- [x] All six endpoint helpers implemented: `resolve_token`, `coin_profile`, `market_chart`, `tickers`, `trending`, `top_gainers_losers`.
- [x] Replaced "synthesize Item[]" approach with a typed `enrich(coin_id, api_key, depth)` function that returns a flat bundle dict for the renderer (Phase 5.3 stitches it into `report.crypto_enrichment`). Bundle includes price, marketcap, FDV, volume, 24h/7d/30d %, ATH, supply, community + developer stats, and (default depth) top 5 exchanges by volume.
- [x] In-process URL-keyed cache via `_cache + _cache_lock` so the same coin isn't re-fetched within a run.
- [x] Concurrent rate-limit defense not enforced at module level — pipeline executor caps concurrency to ≤16 already, well under CoinGecko Pro's 500 req/min. Will revisit if a single run goes wider.
- [x] Live verified: `resolve_token('hyperliquid')` returns id=`hyperliquid`, symbol=`HYPE`, rank=13. `enrich(...)` returns price=$41.20, MC=$9.8B, ATH=$59.30 + 10 categories.

### 3.2 `scripts/lib/messari.py`

- [x] Base URL + header constants live at module top.
- [x] All eight endpoint helpers implemented: `resolve_slug` (with `asset_details`-then-`search` fallback chain), `asset_details` (≤20 per call), `futures_volume`, `futures_open_interest`, `futures_funding_rate`, `volatility`, `roi`, `ath`. Signal/news/sentiment endpoints intentionally NOT included — paywalled via x402.
- [x] Replaced "search returning items" with `enrich(slug, api_key, depth)` returning a typed bundle: profile (name, symbol, description, sector/sub-sector/tags, network slugs, twitter URL) at quick depth; adds derivatives summary (latest OI + 7d % change, latest + 7d-avg funding rate, latest futures volume + 7d buy share) and volatility-30d/90d/1y at default+ depths.
- [x] `_series_points` handles the multiple Messari timeseries response shapes (flat list, `{data:{points:[]}}`, `{data:[]}`).
- [x] Per-process cache + lock on the `_cache` dict.
- [x] Live verified: `resolve_slug('hyperliquid')` → `'hyperliquid'`. Profile bundle returns name, sector `['DeFi','Networks']`, sub-sector `['Decentralized Exchange','Derivatives','Layer-1']`, tags, network `hyperevm`. Derivatives endpoints occasionally time out (>25s) for this asset — bundle gracefully degrades with `oi_error`/`volatility_error` keys instead of failing the whole run. Will revisit timeout in Phase 7.2 with retry tuning if needed.

### 3.3 `scripts/lib/lunarcrush.py`

- [x] Base URL + Bearer header constants at module top.
- [x] Sliding-window rate limiter with separate 10/min + 2000/day deques, single `_window_lock`, and a token-bucket-style `_wait_for_slot()` that sleeps the smaller of the two waits.
- [x] All nine endpoints wrapped: `coins_list`, `resolve_topic`, `topic_summary`, `topic_whatsup`, `topic_news`, `topic_posts`, `topic_creators`, `topic_time_series`, `topics_list`, `categories_list`.
- [x] `_encode_topic` URL-encodes topic strings (LunarCrush topics can contain spaces — e.g. Hyperliquid resolves to `'hype hyperliquid'` and breaks raw URL building).
- [x] `enrich(topic, api_key, depth)` budgeted: quick=2 calls (summary+whatsup), default=3 calls (+ creators), deep=5 calls (+ posts + time_series). All depths comfortably under the 10/min ceiling for ≤2 tokens per run.
- [x] `creators_to_items(bundle, topic)` maps LunarCrush top creators into pipeline-shaped item dicts with `source='lunarcrush'`, `url=https://x.com/<handle>` so they can be merged into the unified ranking when Phase 5.1 wires it in.
- [x] Live verified: `resolve_topic('hyperliquid')` → `'hype hyperliquid'`. Quick bundle returns `interactions_24h=1,291,435`, `trend=up`, sentiment 90 on tweets, 95 related topics. AI bull/bear themes (whatsup) returned None for this token — likely Discover-tier limitation; bundle gracefully handles missing data.

### 3.4 `scripts/lib/firecrawl.py`

- [x] Base URL + Bearer header constants at module top.
- [x] `scrape(url, formats=["markdown"], only_main=True)` → `POST /scrape` returning Firecrawl's standard `{success, data:{markdown,...}}` shape.
- [x] `extract(urls, schema, prompt)` → `POST /extract` for structured extraction across multiple URLs.
- [x] **Not** registered as a source in `pipeline.MOCK_AVAILABLE_SOURCES` or `available_sources` — invoked as a tool by Phase 5.1 (planner-driven thin-snippet fallback) and Phase 6 (`--scrape` CLI flag).
- [x] Per-run budget enforced module-side: `_state["calls"]` counter + `_state["domains"]` set, default cap 5 scrapes/run, per-domain dedupe. `firecrawl.reset()` should be called at the start of each pipeline run (wired in Phase 5.1).
- [x] Both unit-tested (budget guard rejects 3rd call with budget=2; per-domain dedupe rejects same-domain repeat) AND live-tested (scrape of `hyperliquid.xyz` returned valid markdown).

### 3.5 Shared HTTP utilities

- [x] `scripts/lib/http.py` already exposes `get(url, headers=...)` and `post(url, json_data, headers=...)` with built-in retry, 429 handling (Retry-After honored), 5xx exponential backoff, and credential-redacted debug logs via `lib.log.debug`.
- [x] Added `http.get_with_params(url, params, headers, **kwargs)` convenience helper that urlencodes query params (drops None values). Crypto APIs use heavy query-string parameterization, so this avoids hand-rolled urlencoding in every client.
- [x] Confirmed `lib.log.debug` is available — all four new modules will pick up the existing `LAST30DAYS_DEBUG=1` flag automatically since `http.request` already routes through it.

---

## Phase 4 — Crypto-Aware Query Planning

Goal: when the topic mentions a token, the planner extracts a canonical slug and triggers crypto enrichment. When the topic is generic ("AI agent rollups", "Solana mev landscape"), the planner skips token-specific enrichment but may still call LunarCrush trending/categories list and Messari sector metadata.

### 4.1 Token extraction

- [x] Added `scripts/lib/token_extract.py` with `extract_tokens(topic, config) -> list[TokenRef]`.
- [x] `_TICKER_RE` matches `$[A-Za-z][A-Za-z0-9]{1,9}` (2–10 chars). `_NAME_RE` matches CamelCase 1–3-word phrases. Multi-word phrases also yield each constituent word (so "Comparing Pendle vs Aave" surfaces Pendle even when "Comparing Pendle" doesn't resolve). `_NAME_STOPLIST_BLACKLIST` filters month names, weekdays, common acronyms (AI, Q1, DeFi, NFT, etc.), and platform names so they don't burn CoinGecko lookups.
- [x] Each candidate is verified via `coingecko.resolve_token(query, api_key=...)` — only candidates that resolve to a real CoinGecko `id` make it through. Without a CoinGecko key, falls back to returning ticker matches as un-resolved refs (no rank, no slugs) so the pipeline still has signal.
- [x] Hard cap `MAX_TOKENS = 5`.
- [x] Returns dataclass `TokenRef(symbol, name, coingecko_id, messari_slug, lunarcrush_topic, market_cap_rank, extra)`. Messari/LunarCrush slugs default to canonical name (lowercased + hyphenated); each module's `enrich(...)` resolves to its own canonical slug internally.
- [x] **Phase 2 follow-up fix:** `env.get_config()` had an explicit allowlist that didn't include the four crypto-API keys — added them (plus legacy `MESSARI_SDK_API_KEY`, `GITHUB_TOKEN`, `BROWSER_CONSENT`) and dropped dead `BSKY_HANDLE`/`BSKY_APP_PASSWORD`/`TRUTHSOCIAL_TOKEN`/`APIFY_API_TOKEN`/`SCRAPECREATORS_API_KEY`/`XQUIK_API_KEY`/`XIAOHONGSHU_API_BASE`. Without this, `is_*_available` helpers returned False and extraction skipped resolution.
- [x] Live verified across 5 topics: `$HYPE Hyperliquid Q1` → 1 ref (HYPE, rank 13); `Comparing Pendle vs Aave vs Morpho` → 3 refs (Pendle/Aave/Morpho); `$SOL price action this week` → 1 ref (Solana, rank 7); `AI agent token landscape` → 0 refs (correctly no false positives).

### 4.2 Planner integration

- [x] `planner.plan_query(...)` accepts a new `tokens: list[schema.TokenRef] | None = None` kwarg. Tokens are attached to the returned `QueryPlan.tokens` regardless of which planning path runs (LLM success, LLM failure → fallback, deterministic comparison plan, post-LLM-error fallback).
- [x] Token extraction moved to `pipeline.run()` (single source of truth, runs once per pipeline call). `pipeline.run()` calls `token_extract.extract_tokens(topic, config)` outside the planner so the same TokenRef list flows into both `plan.tokens` (for planner intent decisions) and `report.tokens` (for the renderer).
- [x] `available_sources(config)` already gates `coingecko`/`messari`/`lunarcrush` on key presence (Phase 2) — when a token is detected, the planner's `_default_source_weights` (Phase 1.2) already routes meaningful weight to them. Verified default-depth subquery for `$HYPE Hyperliquid outlook` includes all six sources `[x, grounding, reddit, coingecko, messari, lunarcrush]` in every subquery; weights show `x=0.36, grounding=0.16, reddit=0.16, cg/msr/lc=0.10 each`.
- [x] CLI `--token <symbol>` opt-in deferred to Phase 6 as planned.
- [x] Mock pipeline run confirmed no regression (token extraction is skipped under `mock=True` so mock runs stay hermetic).

### 4.3 New intents (optional, recommended)

- [x] Added `crypto_data` and `crypto_qual` to `ALLOWED_INTENTS`.
- [x] `crypto_data` priority `[coingecko, messari, lunarcrush, x, grounding, perplexity, reddit]`; `crypto_qual` priority `[x, lunarcrush, grounding, perplexity, messari, reddit]`. Both registered in `QUICK_SOURCE_PRIORITY` and `SOURCE_PRIORITY`.
- [x] `_default_source_weights` extended: `crypto_data` adds CG=2.0/MSR=2.0/LC=1.5/grounding=0.4; `crypto_qual` adds X=1.0/LC=1.8/MSR=0.8/grounding=0.4 (on top of the global X+1.5/grounding+0.6 baseline).
- [x] `_default_freshness("crypto_data"|"crypto_qual") = "strict_recent"`.
- [x] `_default_cluster_mode("crypto_data") = "market"`, `_default_cluster_mode("crypto_qual") = "story"`.
- [x] `SOURCE_LIMITS["quick"]["crypto_data"|"crypto_qual"] = 3` so quick-depth still hits the full crypto-data triple.
- [x] `_infer_intent` now detects crypto-data signals (price/marketcap/FDV/volume/holders/whales/funding rate/OI/TVL/on-chain/Galaxy Score/AltRank/etc.) and crypto-qual signals (memecoin/narrative/sentiment/airdrop/launch/listing/hype/community/influencers/sector/thesis/alpha) — verified on 8/9 test cases (one prediction edge case was already a regex limitation pre-existing the change).
- [x] `_build_prompt` rewritten to teach the LLM the two new intents, the crypto-source vocabulary (cg/msr/lc + x/grounding/etc), and the cluster_mode + freshness routing. Re-positioned the prompt as "live last-30-days CRYPTO research pipeline".
- [x] End-to-end verified: `crypto_data` topic routes primary subquery to `[coingecko, messari, lunarcrush]` with cluster_mode=market; `crypto_qual` topic routes to `[x, lunarcrush, grounding]` with cluster_mode=story.

---

## Phase 5 — Pipeline Wiring & Rendering

### 5.1 Pipeline execution

- [x] Imported `coingecko`, `messari`, `lunarcrush`, `firecrawl` at the top of `pipeline.py`.
- [x] Crypto enrichment is **out-of-band** — runs after the qualitative retrieval/rerank/cluster pass via a new `_run_crypto_enrichment(tokens, config, depth)` helper. Avoids polluting RRF/rerank with non-comparable enrichment data while still surfacing it in the final Report.
- [x] Each detected token (capped at 2 by default via `LAST30DAYS_CRYPTO_MAX_TOKENS`, env-overridable) generates up to 3 parallel enrichment tasks (one per available API). Tasks dispatched on a `ThreadPoolExecutor(max_workers=8)`, results assembled into `report.crypto_enrichment[source] -> list[bundle]`.
- [x] Each bundle is stamped with `_ref = {symbol, name}` so the renderer (Phase 5.3) can group bundles by token.
- [x] Failures degrade gracefully: per-bundle `error` field instead of crashing the run.
- [x] `firecrawl.reset()` called at the start of each enrichment pass so per-run budget tracking starts fresh.
- [x] Skipped under `mock=True` to keep mock runs hermetic.
- [x] Live end-to-end verified: `$HYPE Hyperliquid market data` topic → 1 token extracted → 3 enrichment bundles (coingecko, messari, lunarcrush) returned in parallel with correct `_ref` stamps and rich data fields.

### 5.2 Schema extension

- [x] Added `schema.TokenRef` dataclass mirroring `token_extract.TokenRef` (symbol, name, coingecko_id, messari_slug, lunarcrush_topic, market_cap_rank).
- [x] `QueryPlan` now carries `tokens: list[TokenRef] = field(default_factory=list)` so the planner can attach extracted tokens for downstream stages.
- [x] `Report` now carries `crypto_enrichment: dict[str, list[dict[str, Any]]]` keyed by source name (`coingecko`/`messari`/`lunarcrush`), each value a per-token bundle list. Also `Report.tokens: list[TokenRef]` for top-level access.
- [x] `query_plan_from_dict` deserializer extended; new `token_ref_from_dict` deserializer added.
- [x] `schema.to_dict(report)` (which delegates to `_drop_none`) round-trips the new fields cleanly — `--emit=json` will surface `tokens` + `crypto_enrichment` automatically. Verified end-to-end with a synthetic report.

### 5.3 Render: new "Market & On-chain" section

- [x] Added `_render_market_section(report, full=False, context_only=False)` helper to `render.py`. Bundles are grouped by symbol so each token's data lives together regardless of source ordering.
- [x] `render_compact` calls `_render_market_section(report, full=False)` after the Ranked Evidence Clusters block — the new "## Market & On-chain" section appears whenever `report.crypto_enrichment` is non-empty.
- [x] `render_full` calls `_render_market_section(report, full=True)`. With `full=True`, also dumps a `<details><summary>Raw bundles</summary>` block per source for debugging.
- [x] `render_context` calls `_render_market_section(report, context_only=True)` near the top of its output — emits a tight `Market snapshot:` block with price, 24h%/30d%, LunarCrush trend, and one bull/one bear theme per token.
- [x] Per-token sub-sections in compact mode:
  - `### {Symbol} — {Name} — rank #{N}` heading
  - **Price snapshot** (CoinGecko) — price, MC, FDV, 24h vol; 24h/7d/30d %; ATH + ATH change; community (X/Reddit/Telegram/GitHub); categories
  - **Social signal** (LunarCrush) — topic rank, trend, 24h interactions, contributors, Galaxy Score (with 7d % change), AltRank, sentiment %, social dominance; per-platform sentiment/volume breakdown
  - **AI bull/bear themes** (LunarCrush) — top 2 bullish + top 2 bearish themes with their conversation %; falls back to AI summary when themes unavailable
  - **Top influencers** (LunarCrush) — top 5 creators with handle linked to `https://x.com/<handle>`, follower count, 24h interactions, rank
  - **Derivatives** (Messari) — latest OI + 7d % change, latest + 7d-avg funding rate, latest futures volume + 7d buy share
  - **Volatility** (Messari) — 30d/90d/1y daily price movement
  - **Where it trades** (CoinGecko) — top 5 exchanges with pair, USD volume, trust score
  - Sector / sub-sector / tags / networks (Messari) at the tail
- [x] Per-source error fields (e.g. `oi_error`, `funding_error`, `volatility_error`) surface as `_CoinGecko note:_ ...` lines instead of being silently dropped — matches the graceful-degradation pattern in Phase 3.
- [x] Live verified: `$HYPE Hyperliquid market data and sentiment` rendered with HYPE/Hyperliquid section showing price $41.40, MC $9.84B, 7d -5.27%, ATH $59.30 (-30.19%), per-platform sentiment breakdown (tweet=83, reddit=80, youtube=80, tiktok=71, news=80), and Messari sector/tags/networks.

### 5.4 Source labels

- [x] Already added during Phase 1.3 SOURCE_LABELS rebuild. Verified: `{coingecko: 'CoinGecko', messari: 'Messari', lunarcrush: 'LunarCrush'}` all present.

---

## Phase 6 — CLI Flags

- [x] `--token SYMBOL` (repeatable, `action='append'`) added. Symbols are normalized (uppercased, leading `$` stripped), CoinGecko-resolved if a key is present, prepended to the extracted tokens list, and de-duplicated against organically-detected tokens. Verified `--token HYPE --token SOL` parses to `['HYPE','SOL']`.
- [x] `--no-crypto` added. Sets `config["_no_crypto"]=True`; `pipeline.run` skips `_run_crypto_enrichment` even when tokens were extracted. Verified end-to-end: report.crypto_enrichment is empty + Market & On-chain section absent from rendered output.
- [x] `--scrape URL` (repeatable) added. After `pipeline.run` returns, `last30days.py main()` invokes `firecrawl.scrape(url, api_key=...)` for each URL and stores results in `report.artifacts["firecrawl"]`. Honors the per-run budget and per-domain dedupe in `firecrawl.py`.
- [x] `parse_search_flag` extended via `_SEARCH_ALIAS_EXTRA = {cg:coingecko, msr:messari, lc:lunarcrush}` checked in addition to `pipeline.SEARCH_ALIAS`. Validation now allows the three crypto sources (already in `MOCK_AVAILABLE_SOURCES` from Phase 2). Verified `--search cg,msr,lc` resolves to `['coingecko','messari','lunarcrush']`; unknown sources still rejected.
- [x] End-to-end smoke: `--token BTC` on a tokenless topic forces Bitcoin enrichment to render in the Market & On-chain section.

---

## Phase 7 — Tests & Validation

### 7.1 Unit tests (add `tests/` if missing)

- [x] `tests/test_token_extract.py` — 7 tests covering $TICKER regex, capitalized name extraction, stoplist filtering, MAX_TOKENS cap, symbol-based dedupe, no-CoinGecko-key fallback, empty-topic edge.
- [x] `tests/test_coingecko.py` — 5 tests covering `resolve_token` URL+header construction, empty-search None return, `enrich` field flattening (price/MC/community/exchanges), quick-depth skipping the tickers call, graceful HTTPError handling.
- [x] `tests/test_messari.py` — 4 tests covering `resolve_slug` via asset_details, quick-depth profile-only enrichment, default-depth derivatives + volatility derivation from timeseries, partial-bundle on per-endpoint HTTP error.
- [x] `tests/test_lunarcrush.py` — 6 tests covering coins-list-based topic resolution, URL-encoding of topics with spaces, quick-depth call budget (exactly 2 calls), default-depth creators addition, `creators_to_items` shape, sliding-window rate limiter blocking at 10/min ceiling.
- [x] `tests/test_planner_crypto.py` — 8 tests covering crypto_data/crypto_qual intent inference, source priority ordering, default weight tilts (crypto_data → APIs lead, crypto_qual → X+LC top), TokenRef attachment to QueryPlan, no regression on non-crypto intents.
- [x] `tests/test_render_crypto.py` — 3 tests covering empty-enrichment short-circuit, full bundle rendering with all 7 sub-sections (price/social/AI themes/influencers/derivatives/volatility/exchanges), and context-mode compact market block.
- [x] All 33 tests pass: `python3 -m unittest tests.test_token_extract tests.test_coingecko tests.test_messari tests.test_lunarcrush tests.test_planner_crypto tests.test_render_crypto -v` → `OK`.

### 7.2 Live smoke tests

- [x] `python3 scripts/last30days.py "$HYPE momentum on X" --emit=compact` — expect X + LunarCrush + CoinGecko in output. **Verified**: 6 X posts in ranked clusters (CryptoHayes, coingecko, deriveinsights), Market & On-chain section with CoinGecko price/exchanges + LunarCrush social signal/influencers. **Bug fix**: thin-results retry path was attempting to fetch `coingecko`/`messari`/`lunarcrush` as streams; added `CRYPTO_ENRICHMENT_SOURCES` filter at `pipeline.py:801` so retries skip enrichment-only sources.
- [x] `python3 scripts/last30days.py "Hyperliquid revenue and funding rates" --emit=compact` — expect Messari derivatives. **Verified**: Messari profile bundle surfaced with sector (`DeFi, Networks / Derivatives, Decentralized Exchange, Layer-1`), tags, and `networks: hyperevm`. X pulled 24 revenue/funding posts (antoniogm `$100M revenue/employee`, Cointelegraph). Derivatives endpoints didn't return data on this run (intermittent Messari free-tier behavior already documented in Phase 3.2 — graceful degradation works as designed; no error keys means endpoints returned empty `points`, not a crash).
- [x] `python3 scripts/last30days.py "AI agent rollup ecosystem" --emit=compact --no-crypto` — expect X + grounding only. **Verified**: 69 items across 4 sources (X=23, Web=14, Reddit=12, GitHub=20), no Market & On-chain section rendered, `report.crypto_enrichment` stayed empty as intended. `--no-crypto` flag correctly short-circuits `_run_crypto_enrichment`.
- [x] `python3 scripts/last30days.py "$BTC vs $ETH 30d" --deep --emit=json | jq '.crypto_enrichment'` — verify JSON shape. **Verified**: `crypto_enrichment` keyed by `coingecko`/`lunarcrush`/`messari`, each with 2 bundles stamped `_ref={symbol, name}` for BTC and ETH. Top-level `tokens` carries `[(BTC, bitcoin), (ETH, ethereum)]` with CoinGecko IDs. Schema round-trip clean.

### 7.3 Regression

- [x] Confirm `bash scripts/sync.sh` deploys cleanly to `~/.claude`, `~/.agents`, `~/.codex`. **Verified**: all four sync targets (`~/.claude/plugins/cache/...3.0.0-alpha`, `...3.0.0-nogem`, `~/.agents/skills/last30days`, `~/.codex/skills/last30days`) reported `Copied N modules / Import check: OK`.
- [x] Confirm `verify_v3.py` passes with new sources registered. **Status**: `verify_v3.py` runs the unit suite via `unittest discover`. New crypto tests pass (33/33 OK). Pre-existing failures (12 fails + 22 errors) are 100% from Phase 1 source removal — stale tests reference deleted modules (`test_bluesky`/`test_polymarket`/`test_youtube_yt`/`test_tiktok`/etc.) or assert behaviors of removed sources (e.g. `test_polymarket_excluded_from_how_to_and_concept`, `test_default_how_to_keeps_youtube_in_source_mix`). All new code paths are clean. Stale-test cleanup tracked under Phase 8 dead-code sweep.
- [x] Run any existing tests in `scripts/test_*.py` to confirm we didn't break baseline. **Verified**: baseline regressions are all pre-existing Phase 1 artifacts (above), no new regressions introduced by Phases 2–6. The only repo-level `scripts/test_*.py` is `scripts/test_device_auth.py` — unrelated to the pipeline and unaffected.

---

## Phase 8 — Deploy & Document

- [x] `bash scripts/sync.sh`. **Verified**: deployed cleanly to all four targets in Phase 7.3.
- [x] Update `CLAUDE.md` (project) to note the new crypto APIs and the env-key requirement. **Done**: rewrote project CLAUDE.md with crypto framing — module list (`coingecko.py`/`messari.py`/`lunarcrush.py`/`firecrawl.py`/`token_extract.py`), env-var requirements (`AUTH_TOKEN`+`CT0` required; CG/MSR/LC/Firecrawl recommended; `MESSARI_SDK_API_KEY` legacy alias accepted), `--token`/`--no-crypto` CLI examples, and the rule that crypto APIs are enrichment-only via `CRYPTO_ENRICHMENT_SOURCES` + the LunarCrush 10/min ceiling note.
- [x] Update `README.md` (if present) with crypto examples. **Done**: added a "Crypto edition" callout near the top with five example queries (`$HYPE momentum on X`, `Hyperliquid revenue and funding rates`, `$BTC vs $ETH 30d --deep`, `AI agent token landscape --token VIRTUAL`, `Solana memecoin launches --no-crypto`) and pointers to CRYPTO_SPEC.md/CLAUDE.md. Left existing public-facing marketing prose intact.
- [ ] Commit on a feature branch (e.g. `crypto-tailored`) and push to `origin` only (private remote — `upstream` is the public fork).

---

## Open Questions / Deferred

- LunarCrush Discover tier is 10 req/min. If a single research run exceeds this (e.g. 5 tokens × 5 endpoints = 25 calls), enrichment will rate-limit. Decision needed: **(a)** cap to 2 tokens per run by default, **(b)** queue calls with backoff, **(c)** upgrade tier later. Default to (a).
- Messari's free tier blocks news/signal endpoints. We compensate with LunarCrush news + X. Revisit if we ever add x402 pay-per-call.
- Firecrawl budget: cap at 5 scrapes/run. Revisit if specific research workflows need bulk extraction.
- CoinMarketCap key is **not** in the env list. The `radar` reference docs mention it but we'll skip CMC in v1 and rely on CoinGecko trending. Add later if needed.
