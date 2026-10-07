#!/bin/sh
# install.sh - Install OmniRoute plugins to a Hermes Agent profile.

set -e

DEFAULT_ENABLE_MODEL=1
DEFAULT_ENABLE_IMAGE=1
DEFAULT_ENABLE_WEB_SEARCH=1

ENABLE_MODEL=$DEFAULT_ENABLE_MODEL
ENABLE_IMAGE=$DEFAULT_ENABLE_IMAGE
ENABLE_WEB_SEARCH=$DEFAULT_ENABLE_WEB_SEARCH
SET_DEFAULT_WEB_SEARCH=1
NO_CONFIG=0
DRY_RUN=0
PROFILE=""
BASE_URL=""

usage() {
  cat <<'EOF'
Usage: bash install.sh [options]

Install OmniRoute provider plugins into a Hermes Agent profile.

Options:
  --profile PATH              Target Hermes profile directory. If omitted, scan and prompt.
  --base-url URL              Set OMNIROUTE_BASE_URL in the profile .env.

  --enable-model              Install/enable model provider plugin. Default: enabled.
  --enable-image              Install/enable image generation plugin. Default: enabled.
  --enable-web-search         Install/enable web search plugin. Default: enabled.

  --no-model                  Do not install/enable model provider plugin.
  --no-image                  Do not install/enable image generation plugin.
  --no-web-search             Do not install/enable web search plugin.

  --set-default-web-search    Set web.search_backend=omniroute. Default: enabled.
  --no-default-web-search     Do not change web.search_backend.

  --no-config                 Copy plugins only; do not edit config.yaml or .env.
  --dry-run                   Print actions without changing files.
  -h, --help                  Show this help.

OmniRoute 是 keyless 网关（任意 Bearer 放行），无需真实 API key。
如需自定义端点，在 profile .env 中设置：
  OMNIROUTE_BASE_URL=http://localhost:20128/v1
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --profile)
      PROFILE=${2:-}
      shift 2
      ;;
    --base-url)
      BASE_URL=${2:-}
      shift 2
      ;;
    --enable-model) ENABLE_MODEL=1; shift ;;
    --enable-image) ENABLE_IMAGE=1; shift ;;
    --enable-web-search) ENABLE_WEB_SEARCH=1; shift ;;
    --no-model) ENABLE_MODEL=0; shift ;;
    --no-image) ENABLE_IMAGE=0; shift ;;
    --no-web-search) ENABLE_WEB_SEARCH=0; shift ;;
    --set-default-web-search) SET_DEFAULT_WEB_SEARCH=1; shift ;;
    --no-default-web-search) SET_DEFAULT_WEB_SEARCH=0; shift ;;
    --no-config) NO_CONFIG=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -z "$PROFILE" ]; then
  echo "Scanning for Hermes profiles..." >&2
  for dir in "$HOME/.hermes" "$HOME/.config/hermes" "/opt/data/profiles" "$LOCALAPPDATA/hermes"; do
    if [ -d "$dir" ]; then
      echo "Found candidate profile dir: $dir" >&2
      PROFILE=$dir
      break
    fi
  done
  if [ -z "$PROFILE" ]; then
    echo "No profile found. Pass --profile PATH explicitly." >&2
    exit 1
  fi
fi

PLUGIN_DIR="$PROFILE/plugins"
CONFIG_FILE="$PROFILE/config.yaml"
ENV_FILE="$PROFILE/.env"

say() { [ "$DRY_RUN" = 1 ] && echo "[dry-run] $*" || echo "$*"; }
do_copy() {
  [ "$DRY_RUN" = 1 ] && return 0
  mkdir -p "$PLUGIN_DIR"
  cp -r "$SCRIPT_DIR/plugins/." "$PLUGIN_DIR/"
}

if [ "$ENABLE_MODEL" = 1 ] || [ "$ENABLE_IMAGE" = 1 ] || [ "$ENABLE_WEB_SEARCH" = 1 ]; then
  say "Copying plugins to $PLUGIN_DIR"
  do_copy
fi

if [ "$ENABLE_MODEL" = 1 ]; then
  say "Enable model-provider omniroute"
  [ "$DRY_RUN" = 1 ] || true
fi
if [ "$ENABLE_IMAGE" = 1 ]; then
  say "Enable image-gen omniroute (default model doubao-seedream-5.0-pro)"
  [ "$DRY_RUN" = 1 ] || true
fi
if [ "$ENABLE_WEB_SEARCH" = 1 ]; then
  say "Enable web-search omniroute"
  [ "$DRY_RUN" = 1 ] || true
fi

if [ "$NO_CONFIG" = 1 ]; then
  echo "Done (--no-config: plugins copied, config untouched)." >&2
  exit 0
fi

if [ "$ENABLE_MODEL" = 1 ]; then
  say "Write OMNIROUTE_BASE_URL to $ENV_FILE"
  if [ "$DRY_RUN" = 0 ]; then
    touch "$ENV_FILE"
    if [ -n "$BASE_URL" ] && ! grep -q "^OMNIROUTE_BASE_URL=" "$ENV_FILE" 2>/dev/null; then
      echo "OMNIROUTE_BASE_URL=$BASE_URL" >> "$ENV_FILE"
    elif [ -z "$BASE_URL" ] && ! grep -q "^OMNIROUTE_BASE_URL=" "$ENV_FILE" 2>/dev/null; then
      echo "OMNIROUTE_BASE_URL=http://localhost:20128/v1" >> "$ENV_FILE"
    fi
  fi
fi

if [ "$SET_DEFAULT_WEB_SEARCH" = 1 ] && [ "$ENABLE_WEB_SEARCH" = 1 ]; then
  say "Set web.search_backend=omniroute in $CONFIG_FILE"
  if [ "$DRY_RUN" = 0 ] && [ -f "$CONFIG_FILE" ]; then
    grep -q "^web:" "$CONFIG_FILE" || echo "web:" >> "$CONFIG_FILE"
    grep -q "search_backend:" "$CONFIG_FILE" || sed -i.bak '/^web:/a\  search_backend: omniroute' "$CONFIG_FILE"
    echo "Remember to set custom model via 'hermes model set omniroute/volcengine-agent/glm-5.3-flash' if needed." >&2
  fi
fi

echo "Done." >&2
