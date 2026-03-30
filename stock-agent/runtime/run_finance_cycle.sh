#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-巡检}"
SCRIPT="/home/kent/.openclaw/workspace/stock-agent/runtime/finance_monitor.py"
OPENCLAW_BIN="openclaw"
TARGET="user:ou_382230f22d96a35fbad447656bfc6b9c"

MSG=$(python3 "$SCRIPT" "$MODE")

$OPENCLAW_BIN message send --channel feishu --account finance --target "$TARGET" --message "$MSG"

echo "$MSG"
