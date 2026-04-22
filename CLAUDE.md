# last30days-crypto Skill

Claude Code skill (slash command `/last30days-crypto`) for crypto research. X is the dominant qualitative source (~75% of weight); CoinGecko, Messari, and LunarCrush provide market, on-chain, and social-quant data; web grounding + GitHub fill in. Reddit, Hacker News, and Perplexity were removed to keep the source set tight and X-focused. Repo: <https://github.com/Must-be-Ash/last30days-crypto>. **Fully separated from the vanilla `/last30days` skill (mvanhorn/last30days-skill)**: this skill reads from `~/.config/last30days-crypto/.env` and writes outputs to `~/Documents/Last30Days-Crypto/` so both can coexist with zero shared state.

## Structure
- `scripts/last30days.py` — main research engine
- `scripts/lib/` — search, enrichment, rendering modules
  - `coingecko.py`, `messari.py`, `lunarcrush.py` — crypto enrichment APIs
  - `firecrawl.py` — planner-driven URL scraper (tool, not a source)
  - `token_extract.py` — extracts `$TICKER` / CamelCase token refs from a topic, verifies via CoinGecko
- `scripts/lib/vendor/bird-search/` — vendored X search client
- `SKILL.md` — skill definition (deployed to ~/.claude/skills/last30days/)
- `CRYPTO_SPEC.md` — implementation plan & change log for the crypto rewrite

## Commands
```bash
python3 scripts/last30days.py "$HYPE momentum" --emit=compact     # Run research
python3 scripts/last30days.py "ETH narrative" --token ETH         # Force enrichment for a token
python3 scripts/last30days.py "AI agents" --no-crypto              # Skip crypto enrichment
bash scripts/sync.sh                                                # Deploy to ~/.claude/.../last30days-crypto, ~/.agents/skills/last30days-crypto, ~/.codex/skills/last30days-crypto
```

## Env vars
Loaded from `~/.config/last30days-crypto/.env`. Required: `AUTH_TOKEN` + `CT0` (X cookies). Recommended: `XAI_API_KEY`, `COINGECKO_API_KEY`, `MESSARI_API_KEY` (legacy `MESSARI_SDK_API_KEY` also accepted), `LUNARCRUSH_API_KEY`, `FIRECRAWL_API_KEY`. Optional: `SERPER_API_KEY`/`EXA_API_KEY` (web), `GITHUB_TOKEN`.

## Rules
- `lib/__init__.py` must be bare package marker (comment only, NO eager imports)
- After edits: run `bash scripts/sync.sh` to deploy
- Crypto APIs (`coingecko`/`messari`/`lunarcrush`) are **enrichment-only** — never returned by `_retrieve_stream`; gated by `CRYPTO_ENRICHMENT_SOURCES` in `pipeline.py`. Firecrawl is a tool, not a source.
- LunarCrush Discover tier caps at 10 req/min; default `LAST30DAYS_CRYPTO_MAX_TOKENS=2` keeps each run safely under that ceiling.
- Git remotes: `origin` only (`Must-be-Ash/last30days-crypto`). No upstream — this is a separate skill, not a fork tracking `mvanhorn/last30days-skill`.
