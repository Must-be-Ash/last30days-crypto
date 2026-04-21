# /last30days-crypto

**Crypto research from the last 30 days, scored by what crypto Twitter actually engages with — backed by market, on-chain, and social-quant data.**

A hard fork of [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) rewired for crypto. Twitter/X is the primary qualitative source, web search is secondary, and three crypto data APIs (CoinGecko, Messari, LunarCrush) attach token-level price/derivatives/sentiment data automatically when the planner detects a `$TICKER` or named project. Firecrawl scrapes whitepapers and governance posts on demand. YouTube, TikTok, Instagram, Polymarket, Bluesky, etc. are removed.

The original `/last30days` skill is unaffected — install both side-by-side from their respective repos. They have **fully separate config and output paths**: this skill uses `~/.config/last30days-crypto/.env` and writes to `~/Documents/Last30Days-Crypto/`; the vanilla skill keeps using `~/.config/last30days/.env` and `~/Documents/Last30Days/`.

## Install

### Claude Code
```
/plugin marketplace add Must-be-Ash/last30days-crypto
```

### Manual
```bash
git clone https://github.com/Must-be-Ash/last30days-crypto.git ~/.claude/skills/last30days-crypto
```

## Usage

```
/last30days-crypto $HYPE momentum on X
/last30days-crypto Hyperliquid revenue and funding rates
/last30days-crypto $BTC vs $ETH 30d --deep
/last30days-crypto AI agent token landscape --token VIRTUAL
/last30days-crypto Solana memecoin launches --no-crypto      # skip enrichment
```

CLI flags:
- `--token SYMBOL` (repeatable) — force enrichment for tokens the planner didn't detect.
- `--no-crypto` — skip the Market & On-chain section even when tokens are extracted.
- `--scrape URL` (repeatable) — Firecrawl a URL into the report's artifacts.

## Sources

| Tier | Sources |
|------|---------|
| Primary qualitative | **X / Twitter** (cookies → XAI fallback) |
| Secondary qualitative | Web (Brave / Exa / Serper / Parallel), Perplexity Sonar |
| Tertiary qualitative | Hacker News, Reddit, GitHub |
| Crypto data (enrichment) | **CoinGecko** (price, MC, FDV, exchanges), **Messari** (futures OI / funding / volume / volatility / sector), **LunarCrush** (Galaxy Score, AltRank, sentiment, top influencers, AI bull/bear themes) |
| Tools | **Firecrawl** (URL scrape) |

## Env vars

Loaded from `~/.config/last30days-crypto/.env` (separate from the vanilla `/last30days` skill, which uses `~/.config/last30days/.env`):

- **Required for X**: `AUTH_TOKEN` + `CT0` (browser cookies) or `XAI_API_KEY`.
- **Highly recommended (free tier)**: `COINGECKO_API_KEY`, `MESSARI_API_KEY` (legacy `MESSARI_SDK_API_KEY` also accepted), `LUNARCRUSH_API_KEY`, `FIRECRAWL_API_KEY`.
- **Web search (recommended)**: `BRAVE_API_KEY` / `EXA_API_KEY` / `SERPER_API_KEY` / `PARALLEL_API_KEY`.
- **Optional**: `OPENROUTER_API_KEY` (Perplexity Sonar), `GITHUB_TOKEN`.

## How it works

1. **Token extraction** (`scripts/lib/token_extract.py`) parses the topic for `$TICKER` and CamelCase project names, then verifies each candidate against CoinGecko's `/search` endpoint. Only verified tokens enter enrichment.
2. **Planner** (`scripts/lib/planner.py`) routes the topic to one of two crypto-aware intents (`crypto_data`, `crypto_qual`) plus the existing intents (breaking_news, prediction, factual, comparison, etc.). X gets the highest weight by default.
3. **Pipeline** (`scripts/lib/pipeline.py`) fans out qualitative streams in parallel, then runs `_run_crypto_enrichment` out-of-band: each detected token gets up to 3 parallel API calls (CoinGecko + Messari + LunarCrush). Capped at `LAST30DAYS_CRYPTO_MAX_TOKENS=2` per run by default to stay under LunarCrush's 10-req/min Discover ceiling.
4. **Renderer** (`scripts/lib/render.py`) emits a `## Market & On-chain` section grouped by token with seven sub-blocks: price snapshot, social signal, AI bull/bear themes, top influencers, derivatives, volatility, and where it trades.

See [CRYPTO_SPEC.md](CRYPTO_SPEC.md) for the full implementation plan and [CLAUDE.md](CLAUDE.md) for the dev cheatsheet.

## Credits

This skill is a **hard fork of [`mvanhorn/last30days-skill`](https://github.com/mvanhorn/last30days-skill) by Matt Van Horn**, rewired and re-scoped for crypto research. The original skill — multi-source research across Reddit, X, YouTube, TikTok, Instagram, Hacker News, Polymarket, GitHub, and more — is the foundation this work is built on.

The crypto fork keeps the original's pipeline architecture, planner-driven query expansion, ranking/clustering, and rendering core. It strips the non-crypto-relevant sources, swaps in three crypto data APIs (CoinGecko, Messari, LunarCrush) plus Firecrawl, makes Twitter/X the primary qualitative source, and adds a token-extraction pass that triggers automatic per-token enrichment.

Huge thanks to Matt for the original work and for making it open source. If you want general-purpose research across many platforms, install [his skill](https://github.com/mvanhorn/last30days-skill) too — they're designed to coexist.

Also built on:
- The vendored [Bird](https://github.com/steipete/bird) X-search client by Peter Steinberger (MIT, Node.js).
- CoinGecko, Messari, LunarCrush, and Firecrawl APIs.
- Python 3.12+, stdlib-first.

## License

MIT, same as upstream.
