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

- [ ] Edit `scripts/lib/pipeline.py`:
  - [ ] Remove from `MOCK_AVAILABLE_SOURCES`: `youtube`, `tiktok`, `instagram`, `bluesky`, `truthsocial`, `polymarket`, `xiaohongshu`, `xquik`. Keep: `reddit`, `x`, `hackernews`, `grounding`, `github`, `perplexity`. Add new: `coingecko`, `messari`, `lunarcrush` (see Phase 3).
  - [ ] Remove corresponding aliases from `SEARCH_ALIAS` (`bsky`, `truth`, `xhs`, `xquik`).
  - [ ] Remove imports of `youtube_yt`, `tiktok`, `instagram`, `bluesky`, `truthsocial`, `polymarket`, `xiaohongshu_api`, `xquik`, `threads`, `pinterest` at the top of `pipeline.py`.
  - [ ] Remove their availability branches inside `available_sources()` (everything except reddit, x, hackernews, github, grounding, perplexity).
  - [ ] Remove `MAX_SOURCE_FETCHES["x"] = 2` only if planner sends single X query; otherwise keep.
- [ ] Delete the unused source modules from `scripts/lib/` to keep the tree clean: `youtube_yt.py`, `tiktok.py`, `instagram.py`, `bluesky.py`, `truthsocial.py`, `polymarket.py`, `xiaohongshu_api.py`, `xquik.py`, `threads.py`, `pinterest.py`. (Keep them only if tests still import them — grep first.)
- [ ] Grep for any other reference to the removed source names in `scripts/` and clean up: `Grep -r "polymarket\|bluesky\|truthsocial\|tiktok\|instagram\|xiaohongshu\|xquik\|youtube_yt\|threads\|pinterest" scripts/`.

### 1.2 Planner reweighting

- [ ] Edit `scripts/lib/planner.py`:
  - [ ] Replace every list inside `QUICK_SOURCE_PRIORITY` and `SOURCE_PRIORITY` so order is always `["x", "grounding", "perplexity", "hackernews", "reddit", "github"]` for every intent (with `coingecko`/`messari`/`lunarcrush` appended only when intent is crypto-data — see Phase 4.3).
  - [ ] Remove `polymarket` from `prediction` intent — replace with `["x", "grounding", "messari", "lunarcrush", "coingecko"]`.
  - [ ] Drop `INTENT_SOURCE_EXCLUSIONS` entries that reference deleted sources.
  - [ ] Update `SOURCE_CAPABILITIES` to remove deleted sources and add `coingecko`/`messari`/`lunarcrush` with capability set `{"crypto_data"}`.
  - [ ] Update `DEFAULT_INTENT_CAPABILITIES` so `comparison` and `how_to` no longer require `video`/`market`.

### 1.3 Render & UI cleanup

- [ ] Edit `scripts/lib/render.py`:
  - [ ] Remove deleted source labels from `SOURCE_LABELS` (truthsocial, xiaohongshu).
  - [ ] Verify `_FUN_LEVELS` and freshness logic don't reference deleted sources.
- [ ] Edit `scripts/lib/env.py`: remove `is_bluesky_available`, `is_truthsocial_available`, `is_threads_available`, `is_xquik_available`, `is_pinterest_available`, `is_xiaohongshu_available`, `is_youtube_sc_available` (and any callers).

### 1.4 SKILL.md rewrite (user-facing docs)

- [ ] Rewrite `SKILL.md` description and tags. New description (target ~25 words): *"Crypto-focused multi-source research. Twitter/X-first social search, web grounding, plus CoinGecko, Messari, and LunarCrush for market, on-chain, and social-quant data."*
- [ ] Replace tag list with: `crypto`, `defi`, `tokens`, `research`, `twitter`, `x`, `coingecko`, `messari`, `lunarcrush`, `firecrawl`, `web-search`, `multi-source`, `news`, `citations`.
- [ ] Update `metadata.openclaw.requires.optionalEnv` to add `COINGECKO_API_KEY`, `MESSARI_API_KEY`, `LUNARCRUSH_API_KEY`, `FIRECRAWL_API_KEY`. Remove `BSKY_HANDLE`, `BSKY_APP_PASSWORD`, `TRUTHSOCIAL_TOKEN`, `APIFY_API_TOKEN`.
- [ ] Strip the entire "TikTok / Instagram / Bluesky / TruthSocial" sections from the wizard prose. Replace with a "Crypto Data Setup" section that prompts for the three new keys.
- [ ] Update example `argument-hint` to crypto examples: `'last30days $HYPE Hyperliquid Q1, last30days new memecoin launches on Solana'`.

---

## Phase 2 — Env Loader Updates

- [ ] Edit `scripts/lib/env.py`:
  - [ ] Add accessors `get_coingecko_key(config)`, `get_messari_key(config)`, `get_lunarcrush_key(config)`, `get_firecrawl_key(config)`.
  - [ ] `get_messari_key` accepts both `MESSARI_API_KEY` and legacy `MESSARI_SDK_API_KEY` (so user's existing `.env` keeps working).
  - [ ] Add to whatever ENV-keys-allowlist exists so `setup_wizard.py` reads them through.
- [ ] Edit `scripts/lib/setup_wizard.py` to add a "Crypto APIs" wizard step offering paste-in for the three keys + Firecrawl. (Optional polish — wizard is OpenClaw-only; can be deferred.)
- [ ] Update `scripts/lib/pipeline.py::available_sources()`:
  - [ ] Append `"coingecko"`, `"messari"`, `"lunarcrush"` whenever respective keys present.
  - [ ] Firecrawl is not a "source" in the listing sense; it's a tool. Track separately as `config.get("FIRECRAWL_API_KEY")`.

---

## Phase 3 — New Crypto Provider Modules

Each provider lives in `scripts/lib/` as a standalone module exposing a `search(topic, planner_hints, depth, config) -> list[schema.Item]` function so it slots into the existing pipeline. They also expose richer typed accessors used by the new "Market & On-chain" rendering section (see Phase 5).

Reference docs (read before implementing):
- `/Users/ashnouruzi/radar/docs/api-access-reference.md`
- `/Users/ashnouruzi/radar/docs/messari/messari-api-key-plan.md`
- `/Users/ashnouruzi/radar/docs/lunarcrush-endpoints.md`
- TS reference clients (port to Python, same patterns): `/Users/ashnouruzi/radar/lib/clients/{coingecko,messari,lunarcrush,firecrawl}.ts`

### 3.1 `scripts/lib/coingecko.py`

- [ ] Base URL `https://pro-api.coingecko.com/api/v3`, header `x-cg-pro-api-key: <key>`.
- [ ] Internal helpers:
  - [ ] `resolve_token(query)` → `GET /search?query=<term>` returning best-match `{id, symbol, name, market_cap_rank}`.
  - [ ] `coin_profile(coin_id)` → `GET /coins/{id}` (full profile, community_data, developer_data, links).
  - [ ] `market_chart(coin_id, days)` → `GET /coins/{id}/market_chart?vs_currency=usd&days=N`.
  - [ ] `tickers(coin_id)` → `GET /coins/{id}/tickers` (where the token trades).
  - [ ] `trending()` → `GET /search/trending`.
  - [ ] `top_gainers_losers()` → `GET /coins/top_gainers_losers?vs_currency=usd&duration=24h&top_coins=1000`.
- [ ] Public `search(...)` returns `Item[]` synthesizing 1–3 markdown-friendly summary items (price snapshot, community size, top exchanges) so it shows up in the unified report.
- [ ] Cache results within a single run (in-process dict keyed by URL) to avoid duplicate calls.
- [ ] Rate-limit defense: respect 500 req/min by capping concurrent calls at 5.

### 3.2 `scripts/lib/messari.py`

- [ ] Base URL `https://api.messari.io`, header `X-Messari-API-Key: <key>`.
- [ ] Helpers (only the working endpoints from the plan doc — do **not** call signal/news endpoints):
  - [ ] `resolve_slug(query)` → `GET /metrics/v2/assets?slugs=<slug>` to confirm; fallback to `GET /metrics/v2/assets?search=<query>` if needed.
  - [ ] `asset_details(slugs[])` → `GET /metrics/v2/assets/details?slugs=...` (≤20 per call).
  - [ ] `futures_volume(slug, granularity)` → `1h` or `1d`.
  - [ ] `futures_open_interest(slug, granularity)`.
  - [ ] `futures_funding_rate(slug, granularity)`.
  - [ ] `volatility(slug, granularity)` → 30d/90d/1y/3y daily price movement.
  - [ ] `roi(slug)` → `GET /metrics/v2/assets/roi`.
  - [ ] `ath(slug)` → `GET /metrics/v2/assets/ath`.
- [ ] Public `search(...)` returns 1–3 summary items: project profile, derivatives signal (OI + funding rate direction), volatility regime.
- [ ] Same caching + concurrency rules as CoinGecko.

### 3.3 `scripts/lib/lunarcrush.py`

- [ ] Base URL `https://lunarcrush.com/api4`, header `Authorization: Bearer <key>`.
- [ ] **Strict rate limit**: 10 req/min, 2,000/day. Add a token-bucket limiter shared across the module (use `threading.Semaphore` + sliding-window counter).
- [ ] Helpers (port from `lunarcrush.ts`):
  - [ ] `resolve_topic(query)` → use coin list `GET /public/coins/list/v2?limit=1000` cached for 1h, find by symbol/name.
  - [ ] `topic_summary(topic)` → `/public/topic/:topic/v1`.
  - [ ] `topic_whatsup(topic)` → `/public/topic/:topic/whatsup/v1` (AI bull/bear themes).
  - [ ] `topic_news(topic)` → `/public/topic/:topic/news/v1`.
  - [ ] `topic_posts(topic, start, end)` → `/public/topic/:topic/posts/v1`.
  - [ ] `topic_creators(topic)` → `/public/topic/:topic/creators/v1` (top influencers).
  - [ ] `topic_time_series(topic, bucket)` → `/public/topic/:topic/time-series/v2`.
  - [ ] `coins_list(sort, filter, limit)` → `/public/coins/list/v2`.
  - [ ] `topics_list()` → `/public/topics/list/v1`.
  - [ ] `categories_list()` → `/public/categories/list/v1`.
- [ ] Public `search(...)` calls `topic_summary`, `topic_whatsup`, and `topic_creators` by default — that's 3 requests, conservative under the 10/min budget. `--deep` adds `topic_posts` and `topic_time_series`.
- [ ] Map LunarCrush "top creators" into `Item` objects with `source="lunarcrush"` and `url=https://x.com/<handle>` so they appear in the unified ranking too.

### 3.4 `scripts/lib/firecrawl.py`

- [ ] Base URL `https://api.firecrawl.dev/v1`, header `Authorization: Bearer <key>`.
- [ ] Helpers:
  - [ ] `scrape(url, formats=["markdown"])` → `POST /scrape`.
  - [ ] `extract(urls[], schema)` → `POST /extract` (optional, for structured extraction).
- [ ] Not registered as a "source". Used by the pipeline only when:
  - [ ] A grounding result is the planner's top hit but the snippet is < N chars.
  - [ ] User passes `--scrape <url>` flag explicitly.
- [ ] Add a budget cap (max 5 scrape calls per run) and per-domain dedupe.

### 3.5 Shared HTTP utilities

- [ ] Reuse `scripts/lib/http.py`. If it doesn't expose `get_with_headers(url, headers)`, add it.
- [ ] All four new modules log via `lib.log.debug(...)` so `--debug` surfaces requests.

---

## Phase 4 — Crypto-Aware Query Planning

Goal: when the topic mentions a token, the planner extracts a canonical slug and triggers crypto enrichment. When the topic is generic ("AI agent rollups", "Solana mev landscape"), the planner skips token-specific enrichment but may still call LunarCrush trending/categories list and Messari sector metadata.

### 4.1 Token extraction

- [ ] Add `scripts/lib/token_extract.py`:
  - [ ] Function `extract_tokens(topic: str, config) -> list[TokenRef]`.
  - [ ] Heuristics first: `\$[A-Z]{2,10}` ticker regex; CamelCase project names from a small known-projects list.
  - [ ] Verify candidates via `coingecko.resolve_token(...)` — only return tokens that resolve to a real coin id.
  - [ ] Cap at 5 tokens per run.
  - [ ] Return `TokenRef(coingecko_id, messari_slug, lunarcrush_topic, symbol, name)`. Populate slugs lazily (only when enrichment is about to call them).

### 4.2 Planner integration

- [ ] In `planner.plan_query(...)`:
  - [ ] After intent classification, run `extract_tokens(topic, config)`.
  - [ ] Persist tokens on the `QueryPlan` (extend `schema.QueryPlan` with `tokens: list[TokenRef]`).
  - [ ] If tokens found AND any of `coingecko/messari/lunarcrush` are available, append them to `available_sources` and `requested_sources` for that run.
  - [ ] If no tokens found, still allow the user to opt in via `--token <symbol>` CLI flag (Phase 6).

### 4.3 New intents (optional, recommended)

- [ ] Add intent `crypto_data` (price/onchain/social-quant questions) and `crypto_qual` (narrative/launches/sentiment).
- [ ] `crypto_data` priority: `["coingecko", "messari", "lunarcrush", "x", "grounding"]`.
- [ ] `crypto_qual` priority: `["x", "lunarcrush", "grounding", "perplexity", "messari", "reddit"]`.
- [ ] Update LLM planner prompt in `_build_prompt(...)` to teach the new intents and the crypto-source vocabulary.

---

## Phase 5 — Pipeline Wiring & Rendering

### 5.1 Pipeline execution

- [ ] In `scripts/lib/pipeline.py::run(...)`:
  - [ ] Import the three new modules (`coingecko`, `messari`, `lunarcrush`).
  - [ ] Add dispatch entries so when `coingecko/messari/lunarcrush` appear in `available_sources`, their `search(...)` is invoked in parallel with the existing X/grounding/etc. searches.
  - [ ] Each enrichment call receives `planner.tokens` so it knows which slugs to query.
  - [ ] Crypto enrichment items get `source="coingecko|messari|lunarcrush"`. They should **not** be rerank-fused alongside qualitative items. Instead, pipeline stores them in a parallel field on the `Report`: `report.crypto_enrichment: dict[str, list[Item]]`.

### 5.2 Schema extension

- [ ] Edit `scripts/lib/schema.py`:
  - [ ] Add `Report.crypto_enrichment: dict[str, list[Item]] = field(default_factory=dict)`.
  - [ ] Add `Report.tokens: list[TokenRef]`.
  - [ ] Add `TokenRef` dataclass.
  - [ ] Update `to_dict()` accordingly so `--emit=json` includes the new fields.

### 5.3 Render: new "Market & On-chain" section

- [ ] Edit `scripts/lib/render.py`:
  - [ ] In `render_compact(...)`, after the existing source clusters, add a `## Market & On-chain` section if `report.crypto_enrichment` is non-empty.
  - [ ] Sub-sections per token:
    - `### {Symbol} — {Name}` heading
    - **Price snapshot** — from CoinGecko (price, mc, 24h/7d/30d %).
    - **Social signal** — from LunarCrush (Galaxy Score, AltRank, sentiment %, social dominance, trend up/down).
    - **AI bull/bear themes** — from LunarCrush `whatsup` (top 2 bullish + top 2 bearish themes with %).
    - **Top influencers** — from LunarCrush creators (top 5 with handle + 24h interactions). Link handles to `https://x.com/<handle>`.
    - **Derivatives** — from Messari (latest funding rate, OI direction over 7d).
    - **Volatility** — from Messari (30d daily vol).
    - **Where it trades** — from CoinGecko tickers (top 5 exchanges by volume).
  - [ ] In `render_full(...)`, dump every enrichment field verbatim for the on-disk debug artifact.
  - [ ] In `render_context(...)` (compact context-window mode), include only the price snapshot + bull/bear themes.

### 5.4 Source labels

- [ ] Add to `SOURCE_LABELS`: `coingecko: "CoinGecko"`, `messari: "Messari"`, `lunarcrush: "LunarCrush"`.

---

## Phase 6 — CLI Flags

- [ ] In `scripts/last30days.py::build_parser()`:
  - [ ] Add `--token SYMBOL` (repeatable) to force token enrichment even if extraction misses it.
  - [ ] Add `--no-crypto` to skip enrichment for runs where you only want pure social search.
  - [ ] Add `--scrape URL` (repeatable) to force a Firecrawl scrape on listed URLs.
  - [ ] Update `parse_search_flag(...)` so `coingecko`, `messari`, `lunarcrush` are valid `--search` values.
  - [ ] Add aliases: `cg → coingecko`, `lc → lunarcrush`, `msr → messari`.

---

## Phase 7 — Tests & Validation

### 7.1 Unit tests (add `tests/` if missing)

- [ ] `test_token_extract.py` — covers ticker regex, CoinGecko resolver, dedupe, cap-at-5.
- [ ] `test_coingecko.py` — mock HTTP, verify URL/header construction for each endpoint.
- [ ] `test_messari.py` — same pattern.
- [ ] `test_lunarcrush.py` — same pattern + verify rate limiter blocks at 10/min.
- [ ] `test_planner_crypto.py` — feed `"$HYPE narrative this week"` and assert tokens populated, intent `crypto_qual`, sources include `lunarcrush` + `x`.
- [ ] `test_render_crypto.py` — feed a synthetic Report with enrichment and assert the "Market & On-chain" section appears with all sub-sections.

### 7.2 Live smoke tests

- [ ] `python3 scripts/last30days.py "$HYPE momentum on X" --emit=compact` — expect X + LunarCrush + CoinGecko in output.
- [ ] `python3 scripts/last30days.py "Hyperliquid revenue and funding rates" --emit=compact` — expect Messari derivatives.
- [ ] `python3 scripts/last30days.py "AI agent rollup ecosystem" --emit=compact --no-crypto` — expect X + grounding only.
- [ ] `python3 scripts/last30days.py "$BTC vs $ETH 30d" --deep --emit=json | jq '.crypto_enrichment'` — verify JSON shape.

### 7.3 Regression

- [ ] Confirm `bash scripts/sync.sh` deploys cleanly to `~/.claude`, `~/.agents`, `~/.codex`.
- [ ] Confirm `verify_v3.py` passes with new sources registered.
- [ ] Run any existing tests in `scripts/test_*.py` to confirm we didn't break baseline.

---

## Phase 8 — Deploy & Document

- [ ] `bash scripts/sync.sh`.
- [ ] Update `CLAUDE.md` (project) to note the new crypto APIs and the env-key requirement.
- [ ] Update `README.md` (if present) with crypto examples.
- [ ] Commit on a feature branch (e.g. `crypto-tailored`) and push to `origin` only (private remote — `upstream` is the public fork).

---

## Open Questions / Deferred

- LunarCrush Discover tier is 10 req/min. If a single research run exceeds this (e.g. 5 tokens × 5 endpoints = 25 calls), enrichment will rate-limit. Decision needed: **(a)** cap to 2 tokens per run by default, **(b)** queue calls with backoff, **(c)** upgrade tier later. Default to (a).
- Messari's free tier blocks news/signal endpoints. We compensate with LunarCrush news + X. Revisit if we ever add x402 pay-per-call.
- Firecrawl budget: cap at 5 scrapes/run. Revisit if specific research workflows need bulk extraction.
- CoinMarketCap key is **not** in the env list. The `radar` reference docs mention it but we'll skip CMC in v1 and rely on CoinGecko trending. Add later if needed.
