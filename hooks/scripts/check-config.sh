#!/bin/bash
set -euo pipefail

# Check last30days-crypto configuration status and show appropriate welcome message.
# Priority: .claude/last30days-crypto.env > ~/.config/last30days-crypto/.env > env vars

PROJECT_ENV=".claude/last30days-crypto.env"
GLOBAL_ENV="$HOME/.config/last30days-crypto/.env"

# Helper: warn if file permissions are too open
check_perms() {
  local file="$1"
  if [[ ! -f "$file" ]]; then return; fi
  local perms
  perms=$(stat -f '%Lp' "$file" 2>/dev/null || stat -c '%a' "$file" 2>/dev/null || echo "")
  if [[ -n "$perms" && "$perms" != "600" && "$perms" != "400" ]]; then
    echo "/last30days-crypto: WARNING — $file has permissions $perms (should be 600)."
    echo "  Fix: chmod 600 $file"
  fi
}

# Load env file into variables for inspection (without exporting)
load_env_vars() {
  local file="$1"
  if [[ -f "$file" ]]; then
    while IFS='=' read -r key value; do
      # Skip comments, empty lines
      [[ "$key" =~ ^[[:space:]]*# ]] && continue
      [[ -z "$key" ]] && continue
      key=$(echo "$key" | xargs)
      value=$(echo "$value" | xargs | sed 's/^["'\''"]//;s/["'\''"]$//')
      if [[ -n "$key" && -n "$value" ]]; then
        eval "ENV_${key}=\"${value}\""
      fi
    done < "$file"
  fi
}

# Determine which config file is active
CONFIG_FILE=""
if [[ -f "$PROJECT_ENV" ]]; then
  CONFIG_FILE="$PROJECT_ENV"
  check_perms "$PROJECT_ENV"
elif [[ -f "$GLOBAL_ENV" ]]; then
  CONFIG_FILE="$GLOBAL_ENV"
  check_perms "$GLOBAL_ENV"
fi

# Load config if found
if [[ -n "$CONFIG_FILE" ]]; then
  load_env_vars "$CONFIG_FILE"
fi

# Check SETUP_COMPLETE (from file or env)
SETUP_COMPLETE="${ENV_SETUP_COMPLETE:-${SETUP_COMPLETE:-}}"

# If setup has never been run, show welcome message for new users
if [[ -z "$SETUP_COMPLETE" && -z "$CONFIG_FILE" && -z "${AUTH_TOKEN:-}" && -z "${XAI_API_KEY:-}" ]]; then
  cat <<'EOF'
/last30days-crypto: Ready to use. Run /last30days-crypto to get started — add AUTH_TOKEN/CT0 (X cookies) and crypto API keys to ~/.config/last30days-crypto/.env when you're ready.

Reddit and Hacker News work out of the box. X (AUTH_TOKEN/CT0) is the primary
qualitative source; CoinGecko, Messari, and LunarCrush keys unlock crypto enrichment.
EOF
  exit 0
fi

HAS_X="${ENV_AUTH_TOKEN:-${AUTH_TOKEN:-}}"
HAS_XAI="${ENV_XAI_API_KEY:-${XAI_API_KEY:-}}"
HAS_EXA="${ENV_EXA_API_KEY:-${EXA_API_KEY:-}}"
HAS_SERPER="${ENV_SERPER_API_KEY:-${SERPER_API_KEY:-}}"
HAS_CG="${ENV_COINGECKO_API_KEY:-${COINGECKO_API_KEY:-}}"
HAS_MSR="${ENV_MESSARI_API_KEY:-${MESSARI_API_KEY:-${ENV_MESSARI_SDK_API_KEY:-${MESSARI_SDK_API_KEY:-}}}}"
HAS_LC="${ENV_LUNARCRUSH_API_KEY:-${LUNARCRUSH_API_KEY:-}}"

SOURCE_COUNT=2  # HN + Reddit always free
[[ -n "$HAS_X" || -n "$HAS_XAI" ]] && SOURCE_COUNT=$((SOURCE_COUNT + 1))
[[ -n "$HAS_EXA" || -n "$HAS_SERPER" ]] && SOURCE_COUNT=$((SOURCE_COUNT + 1))
[[ -n "$HAS_CG" ]] && SOURCE_COUNT=$((SOURCE_COUNT + 1))
[[ -n "$HAS_MSR" ]] && SOURCE_COUNT=$((SOURCE_COUNT + 1))
[[ -n "$HAS_LC" ]] && SOURCE_COUNT=$((SOURCE_COUNT + 1))

echo "/last30days-crypto: Ready — ${SOURCE_COUNT} sources active."
if [[ -z "$HAS_X" && -z "$HAS_XAI" ]]; then
  echo "  Tip: add AUTH_TOKEN + CT0 (X cookies) for primary qualitative coverage."
fi
if [[ -z "$HAS_CG" || -z "$HAS_MSR" || -z "$HAS_LC" ]]; then
  echo "  Tip: add COINGECKO_API_KEY, MESSARI_API_KEY, LUNARCRUSH_API_KEY for crypto enrichment."
fi
